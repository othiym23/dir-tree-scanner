# caching-scanners

Incremental filesystem scanner CLI that produces CSV metadata indexes. Designed
for NAS use (spinning disks, RAID 5) at 100K-1M file scale. Cargo package name
is `caching-scanners` (library crate: `caching_scanners`).

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

```bash
# cached-tree: tree-compatible output using fsscan's incremental state
cached-tree <directory> [--state <file.state>] [--exclude <name>...] [-a] [-N] [-I <pattern>...] [--verbose]
```

Like `tree`, `cached-tree` hides dotfiles by default. Pass `-a` / `--all` to
show hidden files (names starting with `.`). The filtering is display-only —
dotfiles are still scanned and cached in the state file.

Both binaries share `.fsscan.state` files — `cached-tree` scans (or loads cached
state), then renders tree output instead of CSV.

## Architecture

Library crate (`src/lib.rs`) re-exports shared modules. Two binaries consume it:

- `lib.rs` — re-exports `scanner` and `state` for both binaries
- `main.rs` — `fsscan` CLI, wires scanner + csv_writer
- `bin/cached_tree.rs` — `cached-tree` CLI, renders tree output from scan state.
  Hidden-file filtering (`-a`) happens in `merge_entries` at display time, not
  during scanning. Sort order uses case-insensitive collation to match `tree`'s
  sort behavior (see below)
- `state.rs` — `ScanState` type: `HashMap<String, DirEntry>`, rkyv serialized to
  disk with `FSSN` magic + version header. `LoadOutcome` enum for validation
- `scanner.rs` — Walks directory tree with walkdir; compares directory mtime
  against cached state to skip unchanged directories entirely (no per-file stat
  calls)
- `csv_writer.rs` — Writes sorted CSV (`path,size,ctime,mtime`), private to
  fsscan binary

### Key design decisions

- **Incremental scanning**: directory mtime is the cache key. If a directory's
  mtime hasn't changed, all file entries within it are reused from the state
  file. This means unchanged directories cost one stat call instead of N.
- **Unix-only**: uses `std::os::unix::fs::MetadataExt` for ctime/mtime as raw
  `i64` values from the inode.
- **rkyv 0.8** for state serialization (with `bytecheck` feature for
  validation). Previously this package used bincode for state storage, but Rei
  switched to rkyv to respect the stygianentity's
  [decision to withdraw](https://old.reddit.com/r/rust/comments/1poe6ts/bincodes_source_code_still_matches_what_was_on/)
  the package from the Crates ecosystem. State files have a 5-byte header:
  4-byte magic `FSSN` + 1-byte version. Version 2 (current) adds brotli
  compression (quality 5, lgwin 22) between rkyv serialization and the file
  write, reducing state file size significantly for path-heavy data. The load
  path checks the version byte and handles both version 1 (raw rkyv) and version
  2 (brotli-compressed rkyv) for backwards compatibility. `ScanState::load()`
  returns a `LoadOutcome` enum (`Loaded`/`NotFound`/`Invalid`) so callers decide
  policy for corrupt or unrecognized files. On load, rkyv data is copied into an
  `AlignedVec` since the header (and compression) shift the payload off the
  allocation's alignment boundary. `ScanState.dirs` uses `String` keys (not
  `PathBuf`) for rkyv compatibility — conversion happens at insert/lookup
  boundaries. `save()` writes to a `.tmp` sibling then renames for atomicity
  (crash-safe on Btrfs/ext4). Changing `FileEntry` or `DirEntry` structs will
  invalidate existing state files; bump `VERSION` if the format changes.
- **CSV stability**: directory traversal uses `sort_by_file_name()` for
  deterministic order, and files within each directory are sorted by filename
  after scanning. This ensures identical CSV output across runs when the
  filesystem is unchanged.
- **Collation**: `tree` sorts entries using glibc `strcoll()`, which under UTF-8
  locales provides UCA-based ordering. Since `cached-tree` is musl-linked for
  the NAS target and musl's `strcoll` is just `strcmp`, we use ICU4X (`icu`
  crate) for proper Unicode collation. Configuration: root locale
  (`Default::default()`) for language-independent multilingual sorting,
  `Strength::Quaternary` to distinguish base letters, accents, case, and
  punctuation, and `AlternateHandling::Shifted` so punctuation/symbols are
  transparent at L1–L3 but distinguished at L4 (e.g. `show - s01e01` sorts near
  `show S01E01`). The `Collator` is created once in `render_tree` and stored in
  `TreeContext`; `merge_entries` collects into a `Vec` and sorts with a closure
  that captures the collator. Note: `fsscan`'s CSV output still uses byte-order
  sorting for determinism — only tree rendering uses ICU4X collation.
- **Directory count**: `tree` includes the root directory in its count (e.g. a
  directory with 2 subdirs reports "3 directories"). `cached-tree` matches this
  by starting `dir_count` at 1.
- State file and CSV output are written into the scanned directory by default —
  keep this in mind when scanning (they become part of the scan).

## Testing

Unit tests live in each module (`scanner.rs`, `state.rs`, `csv_writer.rs`). CLI
snapshot tests use **trycmd 0.15** and live in `tests/cmd/`.

### trycmd test structure

- `tests/cli_tests.rs` — harness that runs all `tests/cmd/*.toml` files
- Each `.toml` file defines one CLI invocation: binary, args, expected
  stdout/stderr, exit status
- `<test>.in/` directory — fixture files copied into a sandbox temp dir when
  `fs.sandbox = true`
- `<test>.stderr` (or `.stdout`) — expected output for multi-line assertions
  (short output can be inlined in the TOML)

### Writing a new test case

Create `tests/cmd/<name>.toml`:

```toml
bin.name = "fsscan"
args = [".", "--some-flag"]
status = "success"        # or status.code = 1 for expected failures
stdout = ""
stderr = ""               # or omit and provide <name>.stderr file
fs.sandbox = true         # copies <name>.in/ to temp dir, sets CWD there
```

If the test needs input files, create `tests/cmd/<name>.in/` with fixtures.

### Determinism

Use `fs.sandbox = true` and pass `.` as the directory argument. This ensures all
output paths are relative (`scanning: .`, `wrote ./index.csv`) rather than
containing temp dir paths. WalkDir preserves the root path format you pass in.

## Scripts

`scripts/` contains a Python orchestrator that drives fsscan across multiple
directory trees, configured via TOML.

### Files

- `catalog-nas.py` — main script, runs on Python 3.8+ (NAS target: 3.8.15)
- `catalog.toml` — TOML config with global paths and 7 scan entries
- `_vendor/tomli/` — vendored TOML parser for NAS (no pip install needed)
- `test_catalog.py` — pytest tests for config loading, CLI behavior, and
  `generate_tree` (all three modes: `used`, `df`, `subs`)
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
├── bin/cached-tree                 # x86_64 static binary
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

### Script architecture

`catalog-nas.py` has a single `generate_tree()` function that handles all three
scan modes (`used`, `df`, `subs`). It derives file paths and mode from
`scan_cfg` + `global_cfg`. Mode controls which summary commands run after the
shared `cached-tree` call:

- `used`: `du -sm` on the disk
- `df`: `df -PH` on the disk
- `subs`: `df -PH` + `du -sm` per subdirectory (excluding `@eaDir`)

`generate_tree` tests use a `_fake_run_cmd` mock that returns canned responses
in sequence and records all calls for assertion. This avoids running real
`du`/`df`/`tree` in tests.

### Config format

`catalog.toml` has two sections:

- `[global]` — paths with `$ENV_VAR` expansion and `{key}` interpolation
  (resolved in definition order, so later keys can reference earlier ones).
  Includes `scanner` (fsscan binary path) and `tree` (cached-tree binary path,
  defaults to system `tree` if unset).
- `[scan.<name>]` — per-directory entries with `mode` (`used`/`df`/`subs`),
  `disk`, `desc`, `header`, and optional `enabled` (default true)

## Formatting

Always run `cargo fmt` before finishing work on Rust files. The `just check`
recipe includes `cargo fmt --check` so unformatted code will fail CI.

## Plans

Implementation plans are saved in `docs/plans/` using the naming convention
`YYYY-MM-DD-plan-name.md` (e.g. `2026-02-15-icu4x-collation.md`).

## Dependencies

clap 4 (derive), rkyv 0.8 (bytecheck), brotli 7, csv 1, glob 0.3, walkdir 2.
Rust edition 2024.

## Cross-compilation

`.cargo/config.toml` sets the linker for `x86_64-unknown-linux-musl` to
`x86_64-linux-musl-gcc`. Two options:

1. **musl toolchain**: `brew install filosottile/musl-cross/musl-cross`, then
   `rustup target add x86_64-unknown-linux-musl`
2. **cross (Docker-based)**: Must use the git version
   (`cargo install cross --git https://github.com/cross-rs/cross`) — the
   crates.io release (0.2.5) lacks ARM64 Docker image support and fails on Apple
   Silicon.
