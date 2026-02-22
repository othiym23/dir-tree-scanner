# Changelog

## 0.0.4 (2026-02-21)

### BREAKING CHANGES

- **cli:** remove `fsscan` and `cached-tree` binaries; all functionality is now
  in the `dir-tree-scanner` binary via `csv` and `tree` subcommands (70599bb)

### Features

- **cli:** combined `dir-tree-scanner` binary with `csv` and `tree` subcommands,
  build-time git hash in `--version` output (70599bb)
- **cli:** shared operations module (`ops.rs`) eliminates duplicated
  state-load/scan/save boilerplate across binaries (70599bb)
- **scripts:** `catalog-nas.py` updated to drive `dir-tree-scanner` subcommands
  instead of separate binaries (70599bb)

## 0.0.3 (2026-02-16)

### BREAKING CHANGES

- **csv:** output now collates directories and files together in sorted order,
  rather than listing directories first (cff9d73)

### Features

- **cli:** add `cached-tree` binary for tree-compatible output using incremental
  scan state (eb78ed0)
- **cli:** hidden file filtering (`-a`/`--all`) and directory count in
  `cached-tree` (39e0b50)
- **cli:** ICU4X collation for Unicode-aware tree sort order matching glibc
  `strcoll` behavior (39e0b50)
- **cli:** silent output by default, verbose with `-v` (8c98fa4)
- **state:** migrate from bincode to rkyv 0.8 with brotli compression, backwards
  compatible with v1 state files (9a417b1)
- **scripts:** add Python `catalog-nas.py` orchestrator with TOML config
  (ba63b63, 61f64f2)
- **build:** add CI via GitHub Actions (8418b02)
- **build:** add deploy, mount-home, check, test, and format recipes to justfile
  (7e7234d, 8ca8eea, 18b5aa0)

### Bug Fixes

- **scripts:** flush progress output for non-TTY contexts (77275d6)

### Tests

- unit tests for state, scanner, and csv_writer modules (e4f77d4)
- trycmd CLI snapshot tests (8c98fa4)
- pytest tests for catalog-nas.py config loading and generate_tree modes
  (61f64f2)

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
