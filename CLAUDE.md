# fsscan

Incremental filesystem scanner CLI that produces CSV metadata indexes. Designed
for NAS use (spinning disks, RAID 5) at 100K-1M file scale.

## Build & run

```bash
cargo build --release                                    # native (aarch64-apple-darwin)
cargo build --release --target x86_64-unknown-linux-musl # NAS (static binary)
just build-nas-cross                                     # alternative via cross tool
just deploy                                              # build + mount NAS + copy everything

# Usage
fsscan <directory> [--output <file.csv>] [--state <file.state>] [--exclude <name>...] [--verbose]
```

Defaults: output is `<dir>/index.csv`, state is `<dir>/.fsscan.state`, exclude
is `@eaDir` (Synology metadata directories).

## Architecture

Four modules:

- `main.rs` — CLI (clap derive), wires modules together
- `state.rs` — `ScanState` type: `HashMap<PathBuf, DirEntry>`, bincode
  serialized to disk
- `scanner.rs` — Walks directory tree with walkdir; compares directory mtime
  against cached state to skip unchanged directories entirely (no per-file stat
  calls)
- `csv_writer.rs` — Writes sorted CSV (`path,size,ctime,mtime`), directories
  sorted for stable diffs

### Key design decisions

- **Incremental scanning**: directory mtime is the cache key. If a directory's
  mtime hasn't changed, all file entries within it are reused from the state
  file. This means unchanged directories cost one stat call instead of N.
- **Unix-only**: uses `std::os::unix::fs::MetadataExt` for ctime/mtime as raw
  `i64` values from the inode.
- **bincode v1** for state serialization (not v2). Changing the `FileEntry` or
  `DirEntry` structs will invalidate existing state files.
- **CSV stability**: directory traversal uses `sort_by_file_name()` for
  deterministic order, and files within each directory are sorted by filename
  after scanning. This ensures identical CSV output across runs when the
  filesystem is unchanged.
- State file and CSV output are written into the scanned directory by default —
  keep this in mind when scanning (they become part of the scan).

## Scripts

`scripts/` contains a Python orchestrator that drives fsscan across multiple
directory trees, configured via TOML.

### Files

- `catalog-nas.py` — main script, runs on Python 3.8+ (NAS target: 3.8.15)
- `catalog.toml` — TOML config with global paths and 7 scan entries
- `_vendor/tomli/` — vendored TOML parser for NAS (no pip install needed)
- `test_catalog.py` — pytest tests for config loading and CLI behavior
- `catalog-nas.sh` — original bash version (kept for reference)

### Dev setup

```bash
cd scripts && uv sync             # creates .venv with ruff, pyright, pytest, tomli
just check                        # clippy + ruff + pyright
just test                         # cargo test + pytest
```

`just deploy` runs `check` and `test` before building and copying to the NAS, so
lints and tests gate deployment.

### Usage

```bash
python3 catalog-nas.py                          # run all scans from catalog.toml
python3 catalog-nas.py --dry-run                # print plan without executing
python3 catalog-nas.py --scan laptop-music      # run single scan
python3 catalog-nas.py catalog.toml --verbose   # explicit config path + verbose
```

### NAS deployment

`just deploy` automates the full workflow: builds the x86_64 binary, mounts the
NAS home directory (`/Volumes/home` via SMB from `euterpe.local`), and copies
everything into place. The deploy layout on the NAS:

```
/Volumes/home/
├── bin/fsscan                      # x86_64 static binary
├── scripts/
│   ├── catalog-nas.py              # orchestrator script (chmod +x)
│   ├── catalog.toml                # scan configuration
│   └── _vendor/                    # vendored tomli (rsync --delete)
└── catalog-nas → scripts/catalog-nas.py  # convenience symlink
```

The `mount-home` recipe is idempotent — it checks if `/Volumes/home` is already
mounted before attempting `mount_smbfs`. The vendor directory uses
`rsync --delete` to stay in sync (plain `cp -R` nests on repeated runs).

Manual deployment: copy `catalog-nas.py`, `catalog.toml`, `_vendor/`. The script
uses `tomllib` (3.11+) when available, falls back to vendored `tomli` for 3.8.

### Config format

`catalog.toml` has two sections:

- `[global]` — paths with `$ENV_VAR` expansion and `{key}` interpolation
  (resolved in definition order, so later keys can reference earlier ones)
- `[scan.<name>]` — per-directory entries with `mode` (`used`/`df`/`subs`),
  `disk`, `desc`, `header`, and optional `enabled` (default true)

## Dependencies

clap 4 (derive), serde 1, bincode 1, csv 1, walkdir 2. Rust edition 2021.

## Cross-compilation

`.cargo/config.toml` sets the linker for `x86_64-unknown-linux-musl` to
`x86_64-linux-musl-gcc`. Two options:

1. **musl toolchain**: `brew install filosottile/musl-cross/musl-cross`, then
   `rustup target add x86_64-unknown-linux-musl`
2. **cross (Docker-based)**: Must use the git version
   (`cargo install cross --git https://github.com/cross-rs/cross`) — the
   crates.io release (0.2.5) lacks ARM64 Docker image support and fails on Apple
   Silicon.
