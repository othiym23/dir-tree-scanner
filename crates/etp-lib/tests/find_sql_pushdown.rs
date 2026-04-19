//! Behavior tests for `etp-find`'s SQL-pushdown pattern matching.
//!
//! # Dispatch matrix
//!
//! Three strategies are dispatched by [`ops::collect_find_matches`] /
//! [`ops::stream_find_matches`] based on `(pattern shape, -i)`:
//!
//! | pattern shape          | `-i`     | SQL op           | post-filter |
//! | ---------------------- | -------- | ---------------- | ----------- |
//! | literal (no metachars) | off      | `LIKE … ESCAPE`  | `contains`  |
//! | literal (no metachars) | **on**   | `REGEXP (?i)pat` | none        |
//! | regex-metachar pattern | off      | `REGEXP pat`     | none        |
//! | regex-metachar pattern | **on**   | `REGEXP (?i)pat` | none        |
//!
//! # Case-sensitivity matrix
//!
//! SQLite's built-in `LIKE` is ASCII case-insensitive (`A-Z` ↔ `a-z` only).
//! Without `-i` the Rust `str::contains` post-filter re-narrows to an exact
//! byte match, so user-facing behavior is strictly case-sensitive. With `-i`
//! we hand the pattern to the Rust `regex` crate via REGEXP, prefixed with
//! `(?i)`, which applies Unicode *simple* case folding (1:1 mappings only,
//! e.g. `Å`↔`å`, `Σ`↔`σ`). The `ß`↔`SS` 1:2 mapping is *full* case folding,
//! which Rust's regex does not implement.
//!
//! |                     | ASCII case | non-ASCII 1:1 | `ß`↔`SS` (1:2) |
//! | ------------------- | ---------- | ------------- | --------------- |
//! | LIKE + verify       | strict     | strict        | no              |
//! | REGEXP, no `-i`     | strict     | strict        | no              |
//! | REGEXP with `(?i)`  | folded     | folded        | **no**          |
//!
//! Each row below has at least one test that pins its cell.
//!
//! Notes:
//! - "Folded" here is Unicode simple case folding. NFKC folding (stripping
//!   diacritics) is not applied — so `björk` and `bjork` are distinct under
//!   `-i`. The sharp-S `ß` is not folded to `SS` either — that's a full-fold
//!   mapping that the `regex` crate does not implement. `ẞ`↔`ß` is 1:1 and
//!   *is* folded.

use etp_lib::db;
use etp_lib::ops;
use etp_lib::scanner;
use std::fs;

fn make_fixture(dir: &std::path::Path) {
    // ASCII case variants
    fs::write(dir.join("Swans - The Seer.flac"), b"x").unwrap();
    fs::write(dir.join("swans-demo.mp3"), b"x").unwrap();
    fs::write(dir.join("SWANS_live.mp3"), b"x").unwrap();
    // Non-ASCII letter (diacritic) — case fold only, no diacritic strip
    fs::write(dir.join("Björk.flac"), b"x").unwrap();
    fs::write(dir.join("bjork.flac"), b"x").unwrap();
    // German sharp-S fold: ß ↔ SS
    fs::write(dir.join("Weiße Nächte.flac"), b"x").unwrap();
    fs::write(dir.join("WEISSE NACHTE.flac"), b"x").unwrap();
    // LIKE wildcard escaping
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

async fn find(pool: &sqlx::SqlitePool, scan_id: i64, pat: &str, i: bool) -> Vec<String> {
    let filter = ops::FilterConfig::new(true);
    ops::collect_find_matches(pool, Some(scan_id), pat, i, &[], &filter)
        .await
        .unwrap()
        .into_iter()
        .map(|m| m.full_path.rsplit('/').next().unwrap().to_string())
        .collect()
}

// Dispatch tests (which SQL op each (pattern, -i) combination takes) live in
// `ops::tests::build_find_op_*` as unit tests since they need access to the
// private `build_find_op` helper. This file focuses on end-to-end behavior.

// ─── LIKE + verify path: strict ASCII and Unicode case sensitivity ─────────

#[tokio::test]
async fn like_ascii_case_strict() {
    let (pool, scan_id, _tmp) = scanned_pool().await;
    let names = find(&pool, scan_id, "swans", false).await;
    // Exact-case matches only — lowercase filenames + lowercase in path.
    assert!(names.iter().any(|n| n == "swans-demo.mp3"), "{names:?}");
    assert!(names.iter().any(|n| n == "track01-swans.flac"), "{names:?}");
    assert!(
        !names.iter().any(|n| n == "Swans - The Seer.flac"),
        "mixed-case must NOT match: {names:?}"
    );
    assert!(
        !names.iter().any(|n| n == "SWANS_live.mp3"),
        "uppercase must NOT match: {names:?}"
    );
}

#[tokio::test]
async fn like_non_ascii_case_strict() {
    let (pool, scan_id, _tmp) = scanned_pool().await;
    // "björk" (lowercase, with umlaut) only matches exact casing.
    let names = find(&pool, scan_id, "björk", false).await;
    assert!(
        !names.iter().any(|n| n == "Björk.flac"),
        "non-ASCII uppercase must NOT match without -i: {names:?}"
    );
    assert!(
        !names.iter().any(|n| n == "bjork.flac"),
        "diacritic-stripped variant must NOT match: {names:?}"
    );
    // No files in the fixture have exact lowercase-with-umlaut "björk".
    assert!(names.is_empty(), "no exact-case match expected: {names:?}");
}

#[tokio::test]
async fn like_sharp_s_not_folded() {
    let (pool, scan_id, _tmp) = scanned_pool().await;
    // "weiße" should NOT match "WEISSE" without -i.
    let names = find(&pool, scan_id, "weiße", false).await;
    assert!(
        !names.iter().any(|n| n == "WEISSE NACHTE.flac"),
        "ß must not fold to SS without -i: {names:?}"
    );
    assert!(names.is_empty(), "{names:?}");
}

// ─── REGEXP no -i: strict ASCII and Unicode case sensitivity ────────────────

#[tokio::test]
async fn regexp_no_i_ascii_case_strict() {
    let (pool, scan_id, _tmp) = scanned_pool().await;
    // `sw.*s` only hits lowercase s...s runs.
    let names = find(&pool, scan_id, "sw.*s", false).await;
    assert!(names.iter().any(|n| n == "swans-demo.mp3"));
    assert!(names.iter().any(|n| n == "track01-swans.flac"));
    assert!(
        !names.iter().any(|n| n == "Swans - The Seer.flac"),
        "Upper-S must not match regex without -i: {names:?}"
    );
    assert!(
        !names.iter().any(|n| n == "SWANS_live.mp3"),
        "all-caps must not match: {names:?}"
    );
}

#[tokio::test]
async fn regexp_no_i_non_ascii_case_strict() {
    let (pool, scan_id, _tmp) = scanned_pool().await;
    // `bj.rk` only matches exact case — "Björk" starts with "B".
    let names = find(&pool, scan_id, "bj.rk", false).await;
    assert!(names.iter().any(|n| n == "bjork.flac"), "{names:?}");
    assert!(
        !names.iter().any(|n| n == "Björk.flac"),
        "Upper-B must not match regex without -i: {names:?}"
    );
}

// ─── REGEXP with -i: Unicode case-folded matching ───────────────────────────

#[tokio::test]
async fn regexp_with_i_ascii_case_folded() {
    let (pool, scan_id, _tmp) = scanned_pool().await;
    let names = find(&pool, scan_id, "swans", true).await;
    // Every casing variant matches under -i.
    assert!(names.iter().any(|n| n == "swans-demo.mp3"));
    assert!(names.iter().any(|n| n == "Swans - The Seer.flac"));
    assert!(names.iter().any(|n| n == "SWANS_live.mp3"));
    assert!(names.iter().any(|n| n == "track01-swans.flac"));
}

#[tokio::test]
async fn regexp_with_i_non_ascii_case_folded() {
    let (pool, scan_id, _tmp) = scanned_pool().await;
    // "björk" folds to match "Björk" (same letters, just case).
    let names = find(&pool, scan_id, "björk", true).await;
    assert!(names.iter().any(|n| n == "Björk.flac"), "{names:?}");
    // But "bjork" (no diacritic) is a distinct grapheme and must NOT match.
    assert!(
        !names.iter().any(|n| n == "bjork.flac"),
        "Unicode case fold does not strip diacritics: {names:?}"
    );
}

#[tokio::test]
async fn regexp_with_i_sharp_s_is_not_ss_folded() {
    let (pool, scan_id, _tmp) = scanned_pool().await;
    // Pattern "weisse" with -i matches the ASCII "WEISSE" variant (s ↔ S is
    // 1:1). It does NOT match "Weiße" because `ß` ↔ `SS` is a 1:2 full-fold
    // mapping that Rust's regex crate does not implement.
    let names = find(&pool, scan_id, "weisse", true).await;
    assert!(
        names.iter().any(|n| n == "WEISSE NACHTE.flac"),
        "ASCII case fold must apply: {names:?}"
    );
    assert!(
        !names.iter().any(|n| n == "Weiße Nächte.flac"),
        "ß ↔ SS is a 1:2 full-fold mapping that is NOT applied: {names:?}"
    );
}

#[tokio::test]
async fn regexp_with_i_sharp_s_pattern_matches_exact() {
    let (pool, scan_id, _tmp) = scanned_pool().await;
    // Pattern containing `ß` matches the filename that contains `ß` (same
    // letters, different case on the surrounding ASCII).
    let names = find(&pool, scan_id, "weiße", true).await;
    assert!(
        names.iter().any(|n| n == "Weiße Nächte.flac"),
        "exact ß match with ASCII case fold: {names:?}"
    );
    assert!(
        !names.iter().any(|n| n == "WEISSE NACHTE.flac"),
        "ß in pattern should not fold to match SS in filename: {names:?}"
    );
}

// ─── LIKE wildcard escaping ────────────────────────────────────────────────

#[tokio::test]
async fn like_escapes_percent_wildcard() {
    let (pool, scan_id, _tmp) = scanned_pool().await;
    // Literal `%` must be escaped so LIKE treats it as a literal char.
    let names = find(&pool, scan_id, "50%", false).await;
    assert_eq!(names, vec!["50% off.txt".to_string()], "{names:?}");
}

#[tokio::test]
async fn like_escapes_underscore_wildcard() {
    let (pool, scan_id, _tmp) = scanned_pool().await;
    // `_` is a LIKE single-char wildcard; must be escaped to match literally.
    let names = find(&pool, scan_id, "_2026", false).await;
    assert_eq!(names, vec!["notes_2026.md".to_string()], "{names:?}");
}
