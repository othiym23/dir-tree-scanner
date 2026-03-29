use etp_lib::csv_writer;
use etp_lib::db;
use etp_lib::db::dao::{self, FileInput};
use etp_lib::ops::FilterConfig;

/// Helper: create a scan with system and normal files in the DB.
/// Layout:
///   root/song.mp3 (normal file)
///   root/.hidden (dotfile)
///   root/@eaDir/thumb.jpg (system directory + file)
///   root/.etp.db (system file, starts with .)
async fn setup_scan_with_system_files(pool: &sqlx::SqlitePool) -> i64 {
    let scan_id = dao::upsert_scan(pool, "test", "/data").await.unwrap();

    // Normal file at root
    let root_dir = dao::upsert_directory(pool, scan_id, "", 100, 4096)
        .await
        .unwrap();
    dao::replace_files(
        pool,
        root_dir,
        &[
            FileInput {
                filename: "song.mp3".into(),
                size: 1000,
                ctime: 100,
                mtime: 200,
            },
            FileInput {
                filename: ".hidden".into(),
                size: 50,
                ctime: 100,
                mtime: 200,
            },
            FileInput {
                filename: ".etp.db".into(),
                size: 8192,
                ctime: 100,
                mtime: 200,
            },
        ],
    )
    .await
    .unwrap();

    // System directory @eaDir with a thumbnail
    let ea_dir = dao::upsert_directory(pool, scan_id, "@eaDir", 100, 4096)
        .await
        .unwrap();
    dao::replace_files(
        pool,
        ea_dir,
        &[FileInput {
            filename: "thumb.jpg".into(),
            size: 500,
            ctime: 100,
            mtime: 200,
        }],
    )
    .await
    .unwrap();

    scan_id
}

/// Default filter: system files hidden, dotfiles hidden.
#[tokio::test]
async fn default_filter_hides_system_files_and_dotfiles() {
    let pool = db::open_memory().await.unwrap();
    let scan_id = setup_scan_with_system_files(&pool).await;
    let filter = FilterConfig::new(false);

    let files = dao::list_files(&pool, scan_id).await.unwrap();
    let visible: Vec<_> = files
        .iter()
        .filter(|f| filter.should_show(&f.dir_path, &f.filename))
        .collect();

    assert_eq!(visible.len(), 1, "only song.mp3 should be visible");
    assert_eq!(visible[0].filename, "song.mp3");
}

/// --include-system-files: system files shown, dotfiles still hidden.
#[tokio::test]
async fn include_system_files_shows_system_but_not_dotfiles() {
    let pool = db::open_memory().await.unwrap();
    let scan_id = setup_scan_with_system_files(&pool).await;
    let filter = FilterConfig::new(true);

    let files = dao::list_files(&pool, scan_id).await.unwrap();
    let visible: Vec<_> = files
        .iter()
        .filter(|f| filter.should_show(&f.dir_path, &f.filename))
        .collect();

    let names: Vec<&str> = visible.iter().map(|f| f.filename.as_str()).collect();
    assert!(names.contains(&"song.mp3"), "normal file shown");
    assert!(
        names.contains(&"thumb.jpg"),
        "@eaDir file shown with --include-system-files"
    );
    assert!(
        names.contains(&".etp.db"),
        ".etp.db shown with --include-system-files"
    );
    assert!(!names.contains(&".hidden"), "dotfiles still hidden");
}

/// --all: dotfiles shown, system files still hidden.
#[tokio::test]
async fn show_hidden_reveals_dotfiles_but_not_system() {
    let pool = db::open_memory().await.unwrap();
    let scan_id = setup_scan_with_system_files(&pool).await;
    let mut filter = FilterConfig::new(false);
    filter.show_hidden = true;

    let files = dao::list_files(&pool, scan_id).await.unwrap();
    let visible: Vec<_> = files
        .iter()
        .filter(|f| filter.should_show(&f.dir_path, &f.filename))
        .collect();

    let names: Vec<&str> = visible.iter().map(|f| f.filename.as_str()).collect();
    assert!(names.contains(&"song.mp3"), "normal file shown");
    assert!(names.contains(&".hidden"), "dotfile shown with --all");
    assert!(!names.contains(&"thumb.jpg"), "@eaDir still hidden");
    assert!(
        !names.contains(&".etp.db"),
        ".etp.db still hidden (system file)"
    );
}

/// --all --include-system-files: everything shown.
#[tokio::test]
async fn show_all_and_include_system_shows_everything() {
    let pool = db::open_memory().await.unwrap();
    let scan_id = setup_scan_with_system_files(&pool).await;
    let mut filter = FilterConfig::new(true);
    filter.show_hidden = true;

    let files = dao::list_files(&pool, scan_id).await.unwrap();
    let visible: Vec<_> = files
        .iter()
        .filter(|f| filter.should_show(&f.dir_path, &f.filename))
        .collect();

    assert_eq!(visible.len(), 4, "all 4 files should be visible");
}

/// System files contribute to size even when hidden.
#[tokio::test]
async fn system_files_included_in_size_calculation() {
    let pool = db::open_memory().await.unwrap();
    let scan_id = setup_scan_with_system_files(&pool).await;

    let total = dao::subtree_size(&pool, scan_id, "").await.unwrap();
    // song.mp3 (1000) + .hidden (50) + .etp.db (8192) + thumb.jpg (500) = 9742
    assert_eq!(total, 9742, "size should include all files");
}

/// CSV output respects system file filtering.
#[tokio::test]
async fn csv_filters_system_files() {
    let pool = db::open_memory().await.unwrap();
    let scan_id = setup_scan_with_system_files(&pool).await;
    let filter = FilterConfig::new(false);

    let tmp = tempfile::tempdir().unwrap();
    let csv_path = tmp.path().join("out.csv");
    csv_writer::write_csv_from_db(&pool, scan_id, &csv_path, &[], &filter)
        .await
        .unwrap();

    let content = std::fs::read_to_string(&csv_path).unwrap();
    assert!(content.contains("song.mp3"), "normal file in CSV");
    assert!(!content.contains("@eaDir"), "system dir not in CSV");
    assert!(!content.contains(".etp.db"), "system file not in CSV");
    assert!(!content.contains(".hidden"), "dotfile not in CSV");
}

/// CSV with --include-system-files shows system files.
#[tokio::test]
async fn csv_with_include_system_shows_system_files() {
    let pool = db::open_memory().await.unwrap();
    let scan_id = setup_scan_with_system_files(&pool).await;
    let filter = FilterConfig::new(true);

    let tmp = tempfile::tempdir().unwrap();
    let csv_path = tmp.path().join("out.csv");
    csv_writer::write_csv_from_db(&pool, scan_id, &csv_path, &[], &filter)
        .await
        .unwrap();

    let content = std::fs::read_to_string(&csv_path).unwrap();
    assert!(content.contains("song.mp3"), "normal file in CSV");
    assert!(content.contains("thumb.jpg"), "@eaDir file in CSV");
    assert!(content.contains(".etp.db"), ".etp.db in CSV");
    assert!(!content.contains(".hidden"), "dotfile still hidden in CSV");
}

/// etp-query stats behavior: default excludes system files.
#[tokio::test]
async fn query_stats_excludes_system_files_by_default() {
    let pool = db::open_memory().await.unwrap();
    let scan_id = setup_scan_with_system_files(&pool).await;

    // Stats filter: system files excluded (default for stats), dotfiles shown (query is low-level)
    let mut filter = FilterConfig::new(false);
    filter.show_hidden = true;

    let files = dao::list_files(&pool, scan_id).await.unwrap();
    let filtered: Vec<_> = files
        .iter()
        .filter(|f| filter.should_show(&f.dir_path, &f.filename))
        .collect();

    let total: u64 = filtered.iter().map(|f| f.size).sum();
    // song.mp3 (1000) + .hidden (50) = 1050 (system files excluded)
    assert_eq!(filtered.len(), 2, "stats should show song.mp3 + .hidden");
    assert_eq!(total, 1050, "stats total excludes system files");
}

/// etp-query files behavior: default includes system files.
#[tokio::test]
async fn query_files_includes_system_files_by_default() {
    let pool = db::open_memory().await.unwrap();
    let scan_id = setup_scan_with_system_files(&pool).await;

    // Files filter: system files included (default for files), dotfiles shown (query is low-level)
    let mut filter = FilterConfig::new(true);
    filter.show_hidden = true;

    let files = dao::list_files(&pool, scan_id).await.unwrap();
    let filtered: Vec<_> = files
        .iter()
        .filter(|f| filter.should_show(&f.dir_path, &f.filename))
        .collect();

    assert_eq!(filtered.len(), 4, "query files should show everything");
}

/// etp-query files with --no-include-system-files hides system files.
#[tokio::test]
async fn query_files_no_include_hides_system() {
    let pool = db::open_memory().await.unwrap();
    let scan_id = setup_scan_with_system_files(&pool).await;

    let mut filter = FilterConfig::new(false);
    filter.show_hidden = true;

    let files = dao::list_files(&pool, scan_id).await.unwrap();
    let filtered: Vec<_> = files
        .iter()
        .filter(|f| filter.should_show(&f.dir_path, &f.filename))
        .collect();

    let names: Vec<&str> = filtered.iter().map(|f| f.filename.as_str()).collect();
    assert!(names.contains(&"song.mp3"));
    assert!(names.contains(&".hidden"));
    assert!(!names.contains(&"thumb.jpg"));
    assert!(!names.contains(&".etp.db"));
}
