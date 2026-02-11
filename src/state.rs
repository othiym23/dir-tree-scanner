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
        let data =
            bincode::serialize(self).map_err(|e| io::Error::new(io::ErrorKind::Other, e))?;
        fs::write(path, data)
    }
}
