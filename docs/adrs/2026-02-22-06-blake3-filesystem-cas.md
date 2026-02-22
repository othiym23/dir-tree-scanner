# Use BLAKE3 filesystem CAS for embedded images

Date: 2026-02-22

## Status

Accepted

## Context

Music files frequently contain embedded cover art, often duplicated across every
track in an album. Storing these images in the database would bloat it
significantly. The images need to be deduplicated, inspectable, and garbage
collected when no longer referenced. The NAS filesystem is Btrfs.

## Decision

Use content-addressed storage on the filesystem with BLAKE3 hashing. Blobs are
stored at `$XDG_DATA_HOME/euterpe-tools/assets/{ab}/{abcdef...}` (first two hex
characters as a directory prefix). The database stores only the hash and a
reference count.

Write invariant: always write the blob to disk BEFORE inserting the database
reference. This means orphaned blobs (blob on disk, no DB reference) are
possible but harmless — cleaned up by `etp cas gc`. The reverse (DB reference to
missing blob) cannot happen.

## Consequences

- Album cover art shared across 12–20 tracks is stored once on disk.
- No database bloat — SQLite stays small and fast to query.
- BLAKE3 is fast enough to hash large images without becoming a bottleneck, even
  on the NAS CPU.
- The write-blob-before-reference invariant is safe on Btrfs (which has metadata
  journaling) — a crash between blob write and DB insert leaves only an orphan.
- Garbage collection (`etp cas gc`) is a separate, explicit operation — no
  background processes on the NAS.
