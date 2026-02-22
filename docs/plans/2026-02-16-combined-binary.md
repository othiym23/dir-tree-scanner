# Plan: Combined Executable (`dir-tree-scanner`)

## Context

The `fsscan` and `cached-tree` binaries share ~65 lines of identical code (state
loading, scanning, state saving) and diverge only in their output format.
Combining them into a single binary with subcommands eliminates this duplication
and simplifies deployment (one binary instead of two).

## Architecture

### New binary: `src/bin/dir_tree_scanner.rs`

Single binary with clap subcommands:

```
dir-tree-scanner csv <directory> [--output ...] [--state ...] [--exclude ...] [-v]
dir-tree-scanner tree <directory> [--state ...] [--exclude ...] [-N] [-I ...] [-a] [-v]
dir-tree-scanner --version  →  "0.0.3 (deadbeef)"
```

### Shared logic extracted to library

Common operations moved into `src/cli.rs` (re-exported from lib):

1. **`load_state(path, verbose) -> ScanState`** — the 18-line match block
   duplicated in both binaries
2. **`run_scan(root, state, exclude, verbose)`** — scan + error handling + stats
   logging (14 lines duplicated)
3. **`save_state(state, path, verbose)`** — save + error handling (5 lines
   duplicated)
4. **`parse_ignore_patterns(patterns) -> Vec<Pattern>`** — glob pattern parsing
   for tree's `-I` flag

### Modules moved into library

- **`csv_writer.rs`** — was a private module in `src/main.rs`. Moved to
  `src/csv_writer.rs` and added `pub mod csv_writer` to `src/lib.rs`. Import
  paths changed from `caching_scanners::state` to `crate::state`.
- **`tree.rs`** — tree rendering was inline in `src/bin/cached_tree.rs`. Moved
  to `src/tree.rs` with `render_tree()` as the public API. Helpers
  (`TreeContext`, `Entry`, `merge_entries`, `render_dir`, `maybe_escape`) kept
  module-private.

### Build-time version string

`build.rs` runs `git rev-parse HEAD`, takes 8 chars, sets `GIT_HASH` env var via
`cargo:rustc-env`. Binary uses:

```rust
#[command(version = concat!(env!("CARGO_PKG_VERSION"), " (", env!("GIT_HASH"), ")"))]
```

Rerun triggers: `.git/HEAD` and `.git/refs`.

## File changes

### Created

- **`src/cli.rs`** — shared `load_state`, `run_scan`, `save_state`,
  `parse_ignore_patterns`
- **`src/tree.rs`** — tree rendering moved from `bin/cached_tree.rs`
- **`src/bin/dir_tree_scanner.rs`** — combined CLI with `Csv` and `Tree`
  subcommands
- **`build.rs`** — git hash at build time

### Modified

- **`src/lib.rs`** — added `pub mod cli`, `pub mod csv_writer`, `pub mod tree`
- **`src/csv_writer.rs`** — changed `caching_scanners::state` imports to
  `crate::state` (now a library module, not binary-local)
- **`src/main.rs`** — refactored to use `cli::load_state`/`run_scan`/
  `save_state` from library
- **`src/bin/cached_tree.rs`** — refactored to use shared `cli` and `tree`
  modules
- **`Cargo.toml`** — added `[[bin]]` entry for `dir-tree-scanner`, bumped
  version to `0.0.3`
- **`justfile`** — deploy recipe copies `dir-tree-scanner` binary
- **`CLAUDE.md`** — updated architecture docs for new modules and binary

### Kept (backwards compatibility)

- **`src/main.rs`** — `fsscan` binary still exists, refactored to thin wrapper
- **`src/bin/cached_tree.rs`** — `cached-tree` binary still exists, refactored
  to thin wrapper

### Tests added

- `tests/cmd/dts-csv-quiet.toml` — basic csv subcommand (mirrors `quiet.toml`)
- `tests/cmd/dts-csv-verbose.toml` — verbose csv output (mirrors `verbose.toml`)
- `tests/cmd/dts-tree-basic.toml` — tree subcommand (mirrors
  `cached-tree-basic.toml`)
- `tests/cmd/dts-version.toml` — `--version` output format with `[..]` wildcard
  for git hash
- `tests/cmd/dts-not-a-dir.toml` — error handling for missing directory

## Key decisions

- **`&Path` not `&PathBuf`**: clippy enforces using `&Path` in function
  signatures — `&PathBuf` auto-derefs but creates an unnecessary layer.
- **`crate::` vs `caching_scanners::`**: when csv_writer moved into the library
  crate, imports changed from the external crate name to `crate::` (the keyword
  for the current crate root).
- **Non-breaking space in tree output**: tree connectors use `│\u{a0}\u{a0} `
  (non-breaking spaces) to match `tree`'s output — test `.stdout` files must
  contain these exact bytes, not regular spaces.
- **trycmd `[..]` wildcard**: used in the version test to match the git hash
  portion which changes on every commit.

## Verification

1. `cargo fmt --check` — no formatting issues
2. `cargo clippy -- -D warnings` — no warnings
3. `cargo test` — 27 unit tests + 11 CLI snapshot tests pass
4. `dir-tree-scanner --version` — prints `0.0.3 (abcd1234)`
5. `dir-tree-scanner csv .` — produces same CSV as `fsscan .`
6. `dir-tree-scanner tree .` — produces same tree as `cached-tree .`
