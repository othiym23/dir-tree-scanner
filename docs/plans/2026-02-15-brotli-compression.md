# Plan: Add brotli compression to state files

## Context

State files use rkyv serialization with a `FSSN` magic + version header and
atomic write-via-rename. The data is highly compressible — filesystem paths
share long prefixes and filenames follow patterns. At target scale (100K–1M
files), uncompressed state files could reach 50–100 MB. On the NAS (spinning
disks, Btrfs/SHR-2), reducing I/O size with fast compression should be roughly
I/O-neutral or faster, since the write penalty on spinning RAID outweighs the
CPU cost of compression at low quality settings.

## Approach

Add brotli compression between rkyv serialization and the file write. Bump the
version byte from 1 → 2 so old binaries reject compressed files cleanly
("unsupported version 2") rather than seeing corrupt data. Use brotli quality 1
for fast compression with good ratios on this data profile.

### File format (version 2)

```
[magic: 4 bytes "FSSN"] [version: u8 = 2] [brotli-compressed rkyv data...]
```

### Save path

```
ScanState → rkyv::to_bytes → brotli::compress → prepend header → write tmp → rename
```

### Load path

```
read file → validate header → if version 2: brotli::decompress → AlignedVec → rkyv::from_bytes
```

Version 1 files (uncompressed rkyv) should still load successfully for backwards
compatibility during the transition. The load function checks the version byte
and skips decompression for version 1.

## Files to modify

### `Cargo.toml`

Add `brotli = "7"` to dependencies. The `brotli` crate is pure Rust (no C deps),
safe for musl cross-compilation.

### `src/state.rs`

1. Change `VERSION` from `1` to `2`
2. In `save()`: brotli-compress the rkyv bytes before prepending the header. Use
   `brotli::CompressorWriter` wrapping a `Vec<u8>`, quality 1, lgwin 22 (default
   window, 4 MB)
3. In `load()`: after header validation, branch on version:
   - Version 1: existing path (copy to AlignedVec, rkyv deserialize)
   - Version 2: brotli decompress into AlignedVec, then rkyv deserialize
   - Consolidate the shared rkyv deserialization into a helper or inline after
     the branch

### `CLAUDE.md`

Update the rkyv design decision bullet to mention brotli compression at quality
1, version 2 format, and backwards-compatible loading of version 1 files.

## Tests

### Existing tests

All existing round-trip tests (`round_trip_populated_state`,
`round_trip_empty_state`, `save_overwrites_corrupt_file`,
`round_trip_large_state`) exercise save→load and will automatically validate the
new compressed format since save now writes version 2.

### New tests

1. **`load_version_1_uncompressed`** — manually construct a version-1 file
   (header + raw rkyv bytes, no compression) and verify it loads successfully.
   This confirms backwards compatibility.
2. **`compressed_smaller_than_uncompressed`** — save a large state, compare file
   size against raw rkyv bytes to verify compression is actually working.

### trycmd snapshot tests

No changes needed — the CLI tests don't inspect the state file contents, only
the stdout/stderr output.

## Verification

1. `cargo clippy -- -D warnings`
2. `cargo test` — all unit + trycmd tests pass
3. `cargo fmt --check`
4. Manually: run `fsscan` or `cached-tree` on a directory, inspect state file is
   smaller than before, re-run to confirm cache hits still work
