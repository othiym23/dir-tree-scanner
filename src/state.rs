use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileEntry {
    pub filename: String,
    pub size: u64,
    pub ctime: i64,
    pub mtime: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DirEntry {
    pub dir_mtime: i64,
    pub files: Vec<FileEntry>,
}

#[derive(Debug, Default, Serialize, Deserialize)]
pub struct ScanState {
    pub dirs: HashMap<PathBuf, DirEntry>,
}

impl ScanState {
    pub fn load(path: &Path) -> io::Result<Self> {
        let data = fs::read(path)?;
        bincode::deserialize(&data).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))
    }

    pub fn save(&self, path: &Path) -> io::Result<()> {
        let data = bincode::serialize(self).map_err(io::Error::other)?;
        fs::write(path, data)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip_populated_state() {
        let dir = tempfile::tempdir().unwrap();
        let state_path = dir.path().join("test.state");

        let mut state = ScanState::default();
        state.dirs.insert(
            PathBuf::from("/some/dir"),
            DirEntry {
                dir_mtime: 1234567890,
                files: vec![
                    FileEntry {
                        filename: "a.txt".into(),
                        size: 100,
                        ctime: 1000,
                        mtime: 2000,
                    },
                    FileEntry {
                        filename: "b.txt".into(),
                        size: 200,
                        ctime: 3000,
                        mtime: 4000,
                    },
                ],
            },
        );

        state.save(&state_path).unwrap();
        let loaded = ScanState::load(&state_path).unwrap();

        assert_eq!(loaded.dirs.len(), 1);
        let entry = &loaded.dirs[&PathBuf::from("/some/dir")];
        assert_eq!(entry.dir_mtime, 1234567890);
        assert_eq!(entry.files.len(), 2);
        assert_eq!(entry.files[0].filename, "a.txt");
        assert_eq!(entry.files[0].size, 100);
        assert_eq!(entry.files[1].filename, "b.txt");
        assert_eq!(entry.files[1].mtime, 4000);
    }

    #[test]
    fn round_trip_empty_state() {
        let dir = tempfile::tempdir().unwrap();
        let state_path = dir.path().join("empty.state");

        let state = ScanState::default();
        state.save(&state_path).unwrap();
        let loaded = ScanState::load(&state_path).unwrap();
        assert!(loaded.dirs.is_empty());
    }

    #[test]
    fn load_nonexistent_returns_err() {
        let result = ScanState::load(Path::new("/nonexistent/path/state.bin"));
        assert!(result.is_err());
    }

    #[test]
    fn load_garbage_returns_invalid_data() {
        let dir = tempfile::tempdir().unwrap();
        let state_path = dir.path().join("garbage.state");
        fs::write(&state_path, b"not valid bincode data at all!!!").unwrap();

        let result = ScanState::load(&state_path);
        assert!(result.is_err());
        assert_eq!(result.unwrap_err().kind(), io::ErrorKind::InvalidData);
    }

    #[test]
    fn save_to_valid_path_succeeds() {
        let dir = tempfile::tempdir().unwrap();
        let state_path = dir.path().join("ok.state");
        let state = ScanState::default();
        assert!(state.save(&state_path).is_ok());
        assert!(state_path.exists());
    }
}
