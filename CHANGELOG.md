# Changelog

## 0.0.2 (2026-02-12)

### Features

- **cli:** add `--exclude` / `-e` flag to prune directories by name during
  scanning (3d5b430)
- **cli:** default exclude list includes `@eaDir` (Synology metadata
  directories) (3d5b430)
- **scanner:** sort directory traversal with `WalkDir::sort_by_file_name()` for
  deterministic walk order (96eba66)
- **scanner:** sort files by filename within each directory after scanning
  (96eba66)

### Bug Fixes

- **csv:** output was not stable between runs due to unsorted readdir order and
  unsorted directory traversal (96eba66)

## 0.0.1 (2026-02-12)

### Features

- **scanner:** incremental scanning using directory mtime as cache key;
  unchanged directories cost one stat call instead of N (e6b8afc)
- **state:** binary state file via bincode v1 serialized
  `HashMap<PathBuf, DirEntry>` persists scan results between runs (e6b8afc)
- **csv:** output with header row (`path,size,ctime,mtime`), times as raw i64
  inode values (e6b8afc)
- **cli:** `fsscan <directory>` with `--output`, `--state`, and `--verbose`
  flags (e6b8afc)
- **build:** cross-compilation support for `x86_64-unknown-linux-musl` via
  `.cargo/config.toml` and justfile targets (e6b8afc)
