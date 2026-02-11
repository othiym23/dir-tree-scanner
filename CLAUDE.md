# fsscan

Incremental filesystem scanner CLI that produces CSV metadata indexes. Designed for NAS use (spinning disks, RAID 5) at 100K-1M file scale.

## Build & run

```bash
cargo build --release                                    # native (aarch64-apple-darwin)
cargo build --release --target x86_64-unknown-linux-musl # NAS (static binary)
just build-nas-cross                                     # alternative via cross tool

# Usage
fsscan <directory> [--output <file.csv>] [--state <file.state>] [--verbose]
```

Defaults: output is `<dir>/index.csv`, state is `<dir>/.fsscan.state`.

## Architecture

Four modules, no tests yet:

- `main.rs` — CLI (clap derive), wires modules together
- `state.rs` — `ScanState` type: `HashMap<PathBuf, DirEntry>`, bincode serialized to disk
- `scanner.rs` — Walks directory tree with walkdir; compares directory mtime against cached state to skip unchanged directories entirely (no per-file stat calls)
- `csv_writer.rs` — Writes sorted CSV (`path,size,ctime,mtime`), directories sorted for stable diffs

### Key design decisions

- **Incremental scanning**: directory mtime is the cache key. If a directory's mtime hasn't changed, all file entries within it are reused from the state file. This means unchanged directories cost one stat call instead of N.
- **Unix-only**: uses `std::os::unix::fs::MetadataExt` for ctime/mtime as raw `i64` values from the inode.
- **bincode v1** for state serialization (not v2). Changing the `FileEntry` or `DirEntry` structs will invalidate existing state files.
- **CSV stability**: directories are sorted lexicographically in output; files within a directory appear in readdir order.
- State file and CSV output are written into the scanned directory by default — keep this in mind when scanning (they become part of the scan).

## Dependencies

clap 4 (derive), serde 1, bincode 1, csv 1, walkdir 2. Rust edition 2021.

## Cross-compilation

`.cargo/config.toml` sets the linker for `x86_64-unknown-linux-musl` to `x86_64-linux-musl-gcc`. Two options:

1. **musl toolchain**: `brew install filosottile/musl-cross/musl-cross`, then `rustup target add x86_64-unknown-linux-musl`
2. **cross (Docker-based)**: Must use the git version (`cargo install cross --git https://github.com/cross-rs/cross`) — the crates.io release (0.2.5) lacks ARM64 Docker image support and fails on Apple Silicon.
