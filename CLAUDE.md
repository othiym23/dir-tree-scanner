# caching-scanners

Incremental CLI filesystem scanner that produces CSV metadata indexes and text
representations of filesystem trees. Designed for NAS use (spinning disks, RAID
6 with two parity disks) at 200K-500K file scale. For performance, intended to
be run on a Synology DiskStation running DSM 7.3.

Cargo package name is `caching-scanners` (library crate: `caching_scanners`).

## Build & run

```bash
just build            # native (aarch64-apple-darwin)
just build-nas        # NAS (static binary)
just build-nas-cross  # alternative via cross tool
just deploy           # check + test + build + mount NAS + copy everything

# Usage
dir-tree-scanner csv <directory> [--output <file.csv>] [--state <file.state>] [--exclude <name>...] [-v]
dir-tree-scanner tree <directory> [--state <file.state>] [--exclude <name>...] [-N] [-I <pattern>...] [-a] [-v]
dir-tree-scanner --version
```

Defaults: output is `<dir>/index.csv`, state is `<dir>/.fsscan.state`, exclude
is `@eaDir` (Synology metadata directories). The `tree` subcommand hides
dotfiles by default (`-a` to show). State file and CSV output are written into
the scanned directory by default (they become part of the scan).

## Architecture

Library crate (`src/lib.rs`) re-exports shared modules:

- `ops.rs` — shared operations: `validate_directory`, `resolve_state_path`,
  `load_state`, `run_scan`, `save_state`, `write_csv`, `render_tree`,
  `parse_ignore_patterns`
- `bin/dir_tree_scanner.rs` — CLI with `csv` and `tree` subcommands
- `state.rs` — `ScanState`: `HashMap<String, DirEntry>`, rkyv serialized with
  `FSSN` magic + version header. `LoadOutcome` enum for validation
- `scanner.rs` — walkdir-based scanning; skips unchanged directories by mtime
- `csv_writer.rs` — sorted CSV (`path,size,ctime,mtime`)
- `tree.rs` — tree rendering with ICU4X collation for Unicode-aware sorting
- `build.rs` — embeds short git hash in `--version` output

### Key design decisions

- **Incremental scanning**: directory mtime is the cache key. Unchanged
  directories cost one stat call instead of N.
- **Unix-only**: uses `std::os::unix::fs::MetadataExt` for ctime/mtime.
- **rkyv 0.8** for state serialization. State files have a 5-byte header: 4-byte
  magic `FSSN` + 1-byte version. Version 2 (current) adds brotli compression.
  The load path handles both v1 (raw rkyv) and v2 (brotli-compressed).
  `ScanState.dirs` uses `String` keys (not `PathBuf`) for rkyv compatibility.
  `save()` writes to `.tmp` then renames for atomicity. Changing `FileEntry` or
  `DirEntry` structs invalidates state files; bump `VERSION` if the format
  changes.
- **ICU4X collation** for tree sort order (musl's `strcoll` is just `strcmp`).
  Root locale, `Strength::Quaternary`, `AlternateHandling::Shifted`. The `csv`
  subcommand uses byte-order sorting for determinism.

## Testing

Unit tests in each module. CLI snapshot tests use **trycmd 0.15** in
`tests/cmd/`.

### trycmd tests

Each `tests/cmd/<name>.toml` defines one CLI invocation. Optional `<name>.in/`
directory provides fixture files when `fs.sandbox = true`. Use
`fs.sandbox = true` and pass `.` as the directory for deterministic output
paths.

```toml
bin.name = "dir-tree-scanner"
args = ["csv", ".", "--some-flag"]
status = "success"
stdout = ""
fs.sandbox = true
```

## Scripts

`scripts/` contains a Python orchestrator (`catalog-nas.py`) that drives
dir-tree-scanner across multiple directory trees, configured via `catalog.toml`.
Tests in `test_catalog.py`.

```bash
cd scripts && uv sync     # creates .venv with ruff, pyright, pytest
just check                 # clippy + ruff + pyright
just test                  # cargo test + pytest
```

## Formatting

Always run `cargo fmt` before finishing work on Rust files.

## Git workflow

Branch protection is enabled on `main`. All changes must go through a feature
branch and pull request — never commit directly to `main`.

## Plans

Implementation plans are saved in `docs/plans/` using the naming convention
`YYYY-MM-DD-plan-name.md`.

## Cross-compilation

`.cargo/config.toml` sets the linker for `x86_64-unknown-linux-musl` to
`x86_64-linux-musl-gcc`. Two options:

1. **musl toolchain**: `brew install filosottile/musl-cross/musl-cross`, then
   `rustup target add x86_64-unknown-linux-musl`
2. **cross (Docker-based)**: Must use the git version
   (`cargo install cross --git https://github.com/cross-rs/cross`) — the
   crates.io release (0.2.5) lacks ARM64 Docker image support and fails on Apple
   Silicon.
