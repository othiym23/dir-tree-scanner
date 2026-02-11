use crate::state::{DirEntry, FileEntry, ScanState};
use std::fs;
use std::io;
use std::os::unix::fs::MetadataExt;
use std::path::Path;
use walkdir::WalkDir;

pub struct ScanStats {
    pub dirs_cached: usize,
    pub dirs_scanned: usize,
    pub dirs_removed: usize,
}

pub fn scan(root: &Path, state: &mut ScanState, exclude: &[String], verbose: bool) -> io::Result<ScanStats> {
    let mut stats = ScanStats {
        dirs_cached: 0,
        dirs_scanned: 0,
        dirs_removed: 0,
    };

    let mut seen_dirs = std::collections::HashSet::new();

    let walker = WalkDir::new(root).into_iter().filter_entry(|e| {
        if e.file_type().is_dir() {
            if let Some(name) = e.path().file_name() {
                return !exclude.iter().any(|ex| ex == name.to_string_lossy().as_ref());
            }
        }
        true
    });

    for entry in walker {
        let entry = entry.map_err(io::Error::other)?;
        if !entry.file_type().is_dir() {
            continue;
        }

        let dir_path = entry.path().to_path_buf();
        seen_dirs.insert(dir_path.clone());

        let dir_meta = fs::metadata(&dir_path)?;
        let dir_mtime = dir_meta.mtime();

        if let Some(cached) = state.dirs.get(&dir_path) {
            if cached.dir_mtime == dir_mtime {
                stats.dirs_cached += 1;
                if verbose {
                    eprintln!("cache hit: {}", dir_path.display());
                }
                continue;
            }
        }

        stats.dirs_scanned += 1;
        if verbose {
            eprintln!("scanning: {}", dir_path.display());
        }

        let files = scan_directory(&dir_path)?;
        state.dirs.insert(
            dir_path,
            DirEntry {
                dir_mtime,
                files,
            },
        );
    }

    // Remove directories that no longer exist
    let to_remove: Vec<_> = state
        .dirs
        .keys()
        .filter(|k| !seen_dirs.contains(*k))
        .cloned()
        .collect();
    stats.dirs_removed = to_remove.len();
    for k in &to_remove {
        if verbose {
            eprintln!("removed: {}", k.display());
        }
        state.dirs.remove(k);
    }

    Ok(stats)
}

fn scan_directory(dir: &Path) -> io::Result<Vec<FileEntry>> {
    let mut files = Vec::new();
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let ft = entry.file_type()?;
        if !ft.is_file() {
            continue;
        }
        let meta = entry.metadata()?;
        files.push(FileEntry {
            filename: entry.file_name().to_string_lossy().into_owned(),
            size: meta.size(),
            ctime: meta.ctime(),
            mtime: meta.mtime(),
        });
    }
    Ok(files)
}
