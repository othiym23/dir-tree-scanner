# Use bincode for scan state serialization

Date: 2026-02-11

## Status

Superseded by
[2026-02-15-01 rkyv state serialization](2026-02-15-01-rkyv-state-serialization.md)

## Context

The incremental scanner needs to persist directory metadata between runs so
unchanged directories can be skipped. The initial implementation needs a simple,
fast binary format for serializing a `HashMap<String, DirEntry>` of file
metadata. Development speed matters — this is the first working version.

## Decision

Use bincode (via serde) for state serialization. State is written as raw bincode
with no header or version information.

## Consequences

- Simple to implement — just `#[derive(Serialize, Deserialize)]` on the state
  structs and call `bincode::serialize`/`deserialize`.
- Fast enough for the initial file counts.
- No magic bytes or versioning means any structural change to the state structs
  silently produces corrupt data on load. There is no way to distinguish a
  bincode state file from arbitrary garbage.
- No compression — state files grow linearly with collection size.
