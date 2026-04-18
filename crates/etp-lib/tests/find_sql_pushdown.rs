//! Behavior tests for `-i` → REGEXP UDF, literal → LIKE, and regex → REGEXP
//! in `collect_find_matches` / `stream_find_matches`. Exercises the real
//! sqlx-sqlite REGEXP UDF registered by `with_regexp()`.

use etp_lib::db;
use etp_lib::ops;
use etp_lib::scanner;
use std::fs;

fn make_fixture(dir: &std::path::Path) {
    // Mix of filenames exercising case, Unicode, and special chars.
    fs::write(dir.join("Swans - The Seer.flac"), b"x").unwrap();
    fs::write(dir.join("swans-demo.mp3"), b"x").unwrap();
    fs::write(dir.join("SWANS_live.mp3"), b"x").unwrap();
    fs::write(dir.join("Björk.flac"), b"x").unwrap();
    fs::write(dir.join("bjork.flac"), b"x").unwrap();
    fs::write(dir.join("50% off.txt"), b"x").unwrap();
    fs::write(dir.join("notes_2026.md"), b"x").unwrap();
    fs::create_dir_all(dir.join("sub")).unwrap();
    fs::write(dir.join("sub/track01-swans.flac"), b"x").unwrap();
}

async fn scanned_pool() -> (sqlx::SqlitePool, i64, tempfile::TempDir) {
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path().join("fixture");
    fs::create_dir(&root).unwrap();
    make_fixture(&root);

    let pool = db::open_memory().await.unwrap();
    let run_type = root.to_string_lossy();
    let (scan_id, _stats) = scanner::scan_to_db(&root, &pool, &run_type, &[], false, None)
        .await
        .unwrap();
    (pool, scan_id, tmp)
}

#[tokio::test]
async fn literal_without_i_is_case_sensitive() {
    // Path: LIKE narrows (ASCII ci); Rust re-verifies case-sensitive.
    // Only "swans-demo.mp3" and "track01-swans.flac" match "swans".
    let (pool, scan_id, _tmp) = scanned_pool().await;
    let filter = ops::FilterConfig::new(true);

    let matches = ops::collect_find_matches(&pool, Some(scan_id), "swans", false, &[], &filter)
        .await
        .unwrap();
    let names: Vec<&str> = matches
        .iter()
        .map(|m| m.full_path.rsplit('/').next().unwrap())
        .collect();
    assert!(names.iter().any(|n| *n == "swans-demo.mp3"), "{names:?}");
    assert!(
        names.iter().any(|n| *n == "track01-swans.flac"),
        "{names:?}"
    );
    assert!(
        !names.iter().any(|n| *n == "Swans - The Seer.flac"),
        "uppercase should not match without -i: {names:?}"
    );
    assert!(
        !names.iter().any(|n| *n == "SWANS_live.mp3"),
        "allcaps should not match without -i: {names:?}"
    );
}

#[tokio::test]
async fn literal_with_i_matches_unicode_case_fold() {
    // `-i` takes the REGEXP path with `(?i)` prefix so the Rust regex engine
    // applies full Unicode case folding (covers björk/Björk).
    let (pool, scan_id, _tmp) = scanned_pool().await;
    let filter = ops::FilterConfig::new(true);

    let matches = ops::collect_find_matches(&pool, Some(scan_id), "björk", true, &[], &filter)
        .await
        .unwrap();
    let names: Vec<String> = matches
        .iter()
        .map(|m| m.full_path.rsplit('/').next().unwrap().to_string())
        .collect();
    assert!(names.iter().any(|n| n == "Björk.flac"), "{names:?}");
    // Note: "bjork" (no diacritic) is not a case fold of "björk" so the
    // diacritic-stripped filename does not match this pattern. Fold-to-NFD
    // ASCII folding would be needed for that, which Rust's regex doesn't do.
}

#[tokio::test]
async fn literal_with_i_matches_all_case_variants() {
    let (pool, scan_id, _tmp) = scanned_pool().await;
    let filter = ops::FilterConfig::new(true);

    let matches = ops::collect_find_matches(&pool, Some(scan_id), "swans", true, &[], &filter)
        .await
        .unwrap();
    let names: Vec<String> = matches
        .iter()
        .map(|m| m.full_path.rsplit('/').next().unwrap().to_string())
        .collect();
    // With -i: lowercase, mixed, and uppercase all match.
    assert!(names.iter().any(|n| n == "swans-demo.mp3"));
    assert!(names.iter().any(|n| n == "Swans - The Seer.flac"));
    assert!(names.iter().any(|n| n == "SWANS_live.mp3"));
    assert!(names.iter().any(|n| n == "track01-swans.flac"));
}

#[tokio::test]
async fn regex_pattern_uses_regexp_udf() {
    // A real regex (with metachars) must go through the REGEXP UDF. The UDF
    // is case-sensitive without -i, case-insensitive with -i.
    let (pool, scan_id, _tmp) = scanned_pool().await;
    let filter = ops::FilterConfig::new(true);

    // "sw.*s" matches "swans" in lowercase filenames only (no -i).
    let matches = ops::collect_find_matches(&pool, Some(scan_id), "sw.*s", false, &[], &filter)
        .await
        .unwrap();
    let names: Vec<String> = matches
        .iter()
        .map(|m| m.full_path.rsplit('/').next().unwrap().to_string())
        .collect();
    assert!(names.iter().any(|n| n == "swans-demo.mp3"));
    assert!(names.iter().any(|n| n == "track01-swans.flac"));
    assert!(
        !names.iter().any(|n| n == "Swans - The Seer.flac"),
        "Upper-S should not match regex sw.*s without -i: {names:?}"
    );
}

#[tokio::test]
async fn like_pattern_escapes_wildcards() {
    // "50%" is a literal (no regex metachars); LIKE path must escape the %.
    let (pool, scan_id, _tmp) = scanned_pool().await;
    let filter = ops::FilterConfig::new(true);

    let matches = ops::collect_find_matches(&pool, Some(scan_id), "50%", false, &[], &filter)
        .await
        .unwrap();
    let names: Vec<String> = matches
        .iter()
        .map(|m| m.full_path.rsplit('/').next().unwrap().to_string())
        .collect();
    assert_eq!(names, vec!["50% off.txt".to_string()], "{names:?}");
}

#[tokio::test]
async fn underscore_in_literal_is_escaped() {
    // "_2026" is literal. LIKE path must escape the _ so it doesn't match
    // any single char (which would match "SWANS_live.mp3" via " live" etc.).
    let (pool, scan_id, _tmp) = scanned_pool().await;
    let filter = ops::FilterConfig::new(true);

    let matches = ops::collect_find_matches(&pool, Some(scan_id), "_2026", false, &[], &filter)
        .await
        .unwrap();
    let names: Vec<String> = matches
        .iter()
        .map(|m| m.full_path.rsplit('/').next().unwrap().to_string())
        .collect();
    assert_eq!(names, vec!["notes_2026.md".to_string()], "{names:?}");
}
