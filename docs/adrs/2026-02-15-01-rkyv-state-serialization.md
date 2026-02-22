# Use rkyv for scan state serialization

Date: 2026-02-15

## Status

Superseded by
[2026-02-22-01 sqlx with SQLite](2026-02-22-01-sqlx-sqlite-database.md).
Supersedes
[2026-02-11-01 bincode state serialization](2026-02-11-01-bincode-state-serialization.md).

## Context

The incremental scanner needs to persist directory metadata (mtimes and file
lists) between runs so it can skip unchanged directories. The state format must
support fast serialization of a `HashMap<String, DirEntry>` containing 200K+
file entries, and tolerate version changes gracefully.

## Decision

Use rkyv 0.8 with bytecheck for zero-copy deserialization. State files have a
5-byte header (4-byte `FSSN` magic + 1-byte version). `ScanState.dirs` uses
`String` keys rather than `PathBuf` because `PathBuf` doesn't implement rkyv
traits.

## Consequences

- Fast serialization — significantly faster than serde-based formats at this
  scale.
- Zero-copy deserialization avoids allocating the full structure on read.
- Changing `FileEntry` or `DirEntry` structs invalidates all existing state
  files. Version must be bumped on any structural change.
- rkyv's derive macros add compile time. The `bytecheck` feature adds runtime
  validation overhead but prevents unsafe deserialization of corrupt data.
- State files are opaque binary — not human-inspectable or queryable.
