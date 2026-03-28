use crate::cas;
use crate::db::dao::{self, FileInput};
use sqlx::SqlitePool;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::io;
use std::os::unix::fs::MetadataExt;
use std::path::Path;
use std::time::Instant;
use walkdir::WalkDir;

use crate::db::dao::RemovedFile;

pub struct ScanStats {
    pub dirs_cached: usize,
    pub dirs_scanned: usize,
    pub dirs_removed: usize,
    pub elapsed_ms: u128,
}

#[cfg_attr(
    feature = "profiling",
    tracing::instrument(name = "scan_to_db", skip_all)
)]
pub async fn scan_to_db(
    root: &Path,
    pool: &SqlitePool,
    run_type: &str,
    exclude: &[String],
    verbose: bool,
) -> io::Result<(i64, ScanStats)> {
    let start = Instant::now();

    if verbose {
        eprintln!("starting scan: {}", root.display());
    }

    let root_str = root.to_string_lossy();
    let scan_id = dao::upsert_scan(pool, run_type, &root_str)
        .await
        .map_err(io::Error::other)?;

    let mut stats = ScanStats {
        dirs_cached: 0,
        dirs_scanned: 0,
        dirs_removed: 0,
        elapsed_ms: 0,
    };
    let mut seen_paths = HashSet::new();

    let mut all_removed: Vec<RemovedFile> = Vec::new();

    // Bulk-load all cached mtimes in one query instead of per-directory SELECTs.
    let cached_mtimes: HashMap<String, i64> = dao::all_directory_mtimes(pool, scan_id)
        .await
        .map_err(io::Error::other)?;

    // Walk without sorting — order doesn't matter for scanning (output reads
    // from DB with its own sort). Skipping sort avoids buffering + extra
    // syscalls per directory. filter_entry skips excluded directories so
    // walkdir never descends into them (e.g. Synology @eaDir).
    let exclude_set: HashSet<&str> = exclude.iter().map(|s| s.as_str()).collect();
    let walker = WalkDir::new(root).into_iter().filter_entry(|e| {
        if e.file_type().is_dir()
            && let Some(name) = e.file_name().to_str()
        {
            return !exclude_set.contains(name);
        }
        true
    });

    let mut pending: Vec<DirUpdate> = Vec::new();
    const BATCH_SIZE: usize = 256;

    for entry in walker {
        let entry = entry.map_err(io::Error::other)?;
        if !entry.file_type().is_dir() {
            continue;
        }

        let dir_path = entry.path().to_path_buf();
        let relative = dir_path
            .strip_prefix(root)
            .map_err(|e| io::Error::other(format!("path not under root: {}", e)))?
            .to_string_lossy()
            .into_owned();
        seen_paths.insert(relative.clone());

        let dir_meta = fs::metadata(&dir_path)?;
        let dir_mtime = dir_meta.mtime();
        let dir_size = dir_meta.size();

        if cached_mtimes.get(&relative) == Some(&dir_mtime) {
            stats.dirs_cached += 1;
            #[cfg(feature = "profiling")]
            if (stats.dirs_scanned + stats.dirs_cached).is_multiple_of(1000) {
                tracing::info!(
                    scanned = stats.dirs_scanned,
                    cached = stats.dirs_cached,
                    "scan_progress"
                );
                crate::profiling::sample_proc_metrics("scan_progress");
            }
            if verbose {
                eprintln!("directory unchanged, skipping: {}", dir_path.display());
            }
            continue;
        }

        stats.dirs_scanned += 1;

        #[cfg(feature = "profiling")]
        if (stats.dirs_scanned + stats.dirs_cached).is_multiple_of(1000) {
            tracing::info!(
                scanned = stats.dirs_scanned,
                cached = stats.dirs_cached,
                "scan_progress"
            );
            crate::profiling::sample_proc_metrics("scan_progress");
        }

        let files = scan_directory(&dir_path)?;
        if verbose {
            eprintln!("scanning: {} ({} files)", dir_path.display(), files.len());
        }

        pending.push(DirUpdate {
            relative,
            mtime: dir_mtime,
            size: dir_size,
            files,
        });

        if pending.len() >= BATCH_SIZE {
            let removed = flush_pending(pool, scan_id, &mut pending)
                .await
                .map_err(io::Error::other)?;
            all_removed.extend(removed);
        }
    }

    // Flush any remaining directories
    if !pending.is_empty() {
        let removed = flush_pending(pool, scan_id, &mut pending)
            .await
            .map_err(io::Error::other)?;
        all_removed.extend(removed);
    }

    // If nothing was scanned, every directory matched its cached mtime —
    // the DB is already in sync and no directories can be stale.
    let (dir_removed, stale_orphans) = if stats.dirs_scanned > 0 {
        dao::remove_stale_directories(pool, scan_id, &seen_paths)
            .await
            .map_err(io::Error::other)?
    } else {
        (0, Vec::new())
    };
    stats.dirs_removed = dir_removed;

    // Move-tracking: match removed files against newly appeared files by
    // size, then verify with BLAKE3 hash. Matched files get their dir_id
    // and filename updated; unmatched files are deleted.
    let orphan_hashes = reconcile_moves(pool, root, &mut all_removed, verbose)
        .await
        .map_err(io::Error::other)?;

    // Clean up CAS blobs orphaned by unmatched deletions + stale dirs
    for hash in orphan_hashes.iter().chain(stale_orphans.iter()) {
        let _ = cas::remove_blob(hash);
    }

    dao::finish_scan(pool, scan_id)
        .await
        .map_err(io::Error::other)?;

    stats.elapsed_ms = start.elapsed().as_millis();

    Ok((scan_id, stats))
}

/// Flush a batch of pending directory updates in a single transaction.
/// Returns removed files for move-tracking reconciliation.
#[cfg_attr(feature = "profiling", tracing::instrument(name = "flush_pending", skip_all, fields(batch_size = pending.len())))]
async fn flush_pending(
    pool: &SqlitePool,
    scan_id: i64,
    pending: &mut Vec<DirUpdate>,
) -> Result<Vec<RemovedFile>, sqlx::Error> {
    let mut tx = pool.begin().await?;
    let mut removed = Vec::new();

    for update in pending.drain(..) {
        let dir_id = {
            let result = sqlx::query(
                "INSERT INTO directories (scan_id, path, mtime, size)
                 VALUES (?, ?, ?, ?)
                 ON CONFLICT(scan_id, path) DO UPDATE SET mtime = excluded.mtime, size = excluded.size
                 RETURNING id",
            )
            .bind(scan_id)
            .bind(&update.relative)
            .bind(update.mtime)
            .bind(update.size as i64)
            .fetch_one(&mut *tx)
            .await?;
            sqlx::Row::get::<i64, _>(&result, 0)
        };

        let sync = dao::replace_files_on(&mut tx, dir_id, &update.files).await?;
        removed.extend(sync.removed_files);
    }

    tx.commit().await?;
    Ok(removed)
}

/// Match removed files against newly appeared files to detect moves/renames.
///
/// For each removed file, check if a file with the same size exists in the
/// current scan that wasn't there before (i.e., has no metadata_scanned_at and
/// was just inserted). If sizes match, verify with BLAKE3 hash. Matched files
/// get an UPDATE to their dir_id and filename; unmatched files are deleted.
async fn reconcile_moves(
    pool: &SqlitePool,
    root: &Path,
    removed: &mut [RemovedFile],
    verbose: bool,
) -> Result<Vec<String>, sqlx::Error> {
    if removed.is_empty() {
        return Ok(Vec::new());
    }

    // Build a size → removed-files index for quick lookup
    let mut by_size: HashMap<u64, Vec<usize>> = HashMap::new();
    for (i, rf) in removed.iter().enumerate() {
        by_size.entry(rf.size).or_default().push(i);
    }

    // Find newly inserted files (metadata_scanned_at IS NULL) that could be
    // move targets. We only need files whose sizes match a removed file.
    let sizes: Vec<u64> = by_size.keys().copied().collect();
    if sizes.is_empty() {
        let mut conn = pool.acquire().await?;
        return dao::delete_unmatched_files(&mut conn, removed).await;
    }

    // Query new files that match sizes of removed files
    let placeholders: String = sizes.iter().map(|_| "?").collect::<Vec<_>>().join(",");
    let query = format!(
        "SELECT f.id, d.path, f.filename, f.size, f.dir_id
         FROM files f
         JOIN directories d ON f.dir_id = d.id
         WHERE f.metadata_scanned_at IS NULL
           AND f.size IN ({placeholders})"
    );
    let mut q = sqlx::query_as::<_, (i64, String, String, i64, i64)>(&query);
    for &s in &sizes {
        q = q.bind(s as i64);
    }
    let candidates: Vec<(i64, String, String, i64, i64)> = q.fetch_all(pool).await?;

    // Try to match each candidate against removed files by size, then hash
    let mut matched_removed: HashSet<usize> = HashSet::new();
    let mut matched_new: HashSet<i64> = HashSet::new();
    let mut conn = pool.acquire().await?;

    for (new_id, dir_path, new_filename, new_size, new_dir_id) in &candidates {
        if matched_new.contains(new_id) {
            continue;
        }
        let size = *new_size as u64;
        let Some(indices) = by_size.get(&size) else {
            continue;
        };

        // Build the full path of the new file for hashing
        let new_path = if dir_path.is_empty() {
            root.join(new_filename)
        } else {
            root.join(dir_path).join(new_filename)
        };
        let new_hash = match hash_file(&new_path) {
            Some(h) => h,
            None => continue,
        };

        // Check each removed file with matching size
        for &idx in indices {
            if matched_removed.contains(&idx) {
                continue;
            }
            let rf = &removed[idx];

            // Build old path for hashing
            let old_dir_path = get_dir_path(pool, rf.dir_id).await;
            let old_path = match &old_dir_path {
                Some(dp) if dp.is_empty() => root.join(&rf.filename),
                Some(dp) => root.join(dp).join(&rf.filename),
                None => continue,
            };
            let old_hash = match hash_file(&old_path) {
                Some(h) => h,
                None => {
                    // Old file is gone (expected for a move) — accept the
                    // match based on size alone if there's exactly one candidate
                    if indices.len() == 1 {
                        if verbose {
                            eprintln!(
                                "  move detected (size match): {} -> {}",
                                rf.filename, new_filename
                            );
                        }
                        // Move the old file record to the new location
                        dao::move_file(&mut conn, rf.file_id, *new_dir_id, new_filename).await?;
                        // Delete the newly inserted duplicate
                        sqlx::query("DELETE FROM files WHERE id = ?")
                            .bind(new_id)
                            .execute(&mut *conn)
                            .await?;
                        matched_removed.insert(idx);
                        matched_new.insert(*new_id);
                        break;
                    }
                    continue;
                }
            };

            if old_hash == new_hash {
                if verbose {
                    eprintln!(
                        "  move detected (hash match): {} -> {}",
                        rf.filename, new_filename
                    );
                }
                dao::move_file(&mut conn, rf.file_id, *new_dir_id, new_filename).await?;
                sqlx::query("DELETE FROM files WHERE id = ?")
                    .bind(new_id)
                    .execute(&mut *conn)
                    .await?;
                matched_removed.insert(idx);
                matched_new.insert(*new_id);
                break;
            }
        }
    }

    // Delete unmatched removed files
    let unmatched: Vec<RemovedFile> = removed
        .iter()
        .enumerate()
        .filter(|(i, _)| !matched_removed.contains(i))
        .map(|(_, rf)| rf.clone())
        .collect();

    let orphans = dao::delete_unmatched_files(&mut conn, &unmatched).await?;
    Ok(orphans)
}

/// BLAKE3 hash of a file, or None if the file can't be read.
fn hash_file(path: &Path) -> Option<String> {
    let data = fs::read(path).ok()?;
    Some(blake3::hash(&data).to_hex().to_string())
}

/// Look up a directory's relative path by its ID.
async fn get_dir_path(pool: &SqlitePool, dir_id: i64) -> Option<String> {
    let row: Option<(String,)> = sqlx::query_as("SELECT path FROM directories WHERE id = ?")
        .bind(dir_id)
        .fetch_optional(pool)
        .await
        .ok()?;
    row.map(|(p,)| p)
}

/// Local struct for batching directory updates in scan_to_db.
struct DirUpdate {
    relative: String,
    mtime: i64,
    size: u64,
    files: Vec<dao::FileInput>,
}

fn scan_directory(dir: &Path) -> io::Result<Vec<FileInput>> {
    let mut files = Vec::new();
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let ft = entry.file_type()?;
        if !ft.is_file() {
            continue;
        }
        let meta = entry.metadata()?;
        files.push(FileInput {
            filename: entry.file_name().to_string_lossy().into_owned(),
            size: meta.size(),
            ctime: meta.ctime(),
            mtime: meta.mtime(),
        });
    }
    files.sort_by(|a, b| a.filename.cmp(&b.filename));
    Ok(files)
}
