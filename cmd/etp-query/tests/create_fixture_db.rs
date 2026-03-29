/// Run this with `cargo test -p etp-query --test create_fixture_db` to regenerate
/// the fixture database used by trycmd stats format tests.
///
/// The DB is committed to the repo so trycmd can use it without async setup.
use etp_lib::db;
use etp_lib::db::dao::{self, FileInput};

#[tokio::test]
async fn create_stats_fixture_db() {
    let db_path =
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/cmd/stats-fixture.db");

    // Remove old DB + WAL/SHM files
    let _ = std::fs::remove_file(&db_path);
    let _ = std::fs::remove_file(db_path.with_extension("db-wal"));
    let _ = std::fs::remove_file(db_path.with_extension("db-shm"));

    let pool = db::open_db(&db_path, false).await.unwrap();

    let scan_id = dao::upsert_scan(&pool, "test", "/data/music")
        .await
        .unwrap();
    let root_dir = dao::upsert_directory(&pool, scan_id, "", 100, 4096)
        .await
        .unwrap();
    dao::replace_files(
        &pool,
        root_dir,
        &[
            FileInput {
                filename: "album.flac".into(),
                size: 30_000_000,
                ctime: 100,
                mtime: 200,
            },
            FileInput {
                filename: "track.flac".into(),
                size: 25_000_000,
                ctime: 100,
                mtime: 200,
            },
            FileInput {
                filename: "song.mp3".into(),
                size: 5_000_000,
                ctime: 100,
                mtime: 200,
            },
            FileInput {
                filename: "cover.jpg".into(),
                size: 500_000,
                ctime: 100,
                mtime: 200,
            },
            FileInput {
                filename: "notes.txt".into(),
                size: 1_000,
                ctime: 100,
                mtime: 200,
            },
        ],
    )
    .await
    .unwrap();

    let sub_dir = dao::upsert_directory(&pool, scan_id, "sub", 100, 4096)
        .await
        .unwrap();
    dao::replace_files(
        &pool,
        sub_dir,
        &[FileInput {
            filename: "bonus.mp3".into(),
            size: 4_000_000,
            ctime: 100,
            mtime: 200,
        }],
    )
    .await
    .unwrap();

    dao::finish_scan(&pool, scan_id).await.unwrap();
    db::close_db(pool).await;

    eprintln!("wrote fixture DB to {}", db_path.display());
}
