# Use sqlx with SQLite for the metadata database

Date: 2026-02-22

## Status

Accepted. Supersedes
[2026-02-15-01 rkyv state serialization](2026-02-15-01-rkyv-state-serialization.md)
and
[2026-02-15-03 brotli state compression](2026-02-15-03-brotli-state-compression.md).

## Context

The project is evolving from a filesystem scanner into a metadata management
toolkit. The rkyv state file stores only directory mtimes and file lists — it
can't represent audio metadata, embedded images, or cue sheets, and it isn't
queryable. The metadata database needs to support ad-hoc queries (find files by
tag, compute aggregate sizes, detect duplicates) and eventually migrate to
PostgreSQL.

## Decision

Use sqlx with SQLite as the primary database. Use sqlx's built-in migration
system. Schema uses only types that map directly to PostgreSQL (TEXT, INTEGER) —
no SQLite-specific syntax. Timestamps are ISO 8601 text for human-facing values,
Unix epoch integers for filesystem-derived values.

Directory paths are stored relative to the scan root, with the root path stored
once in the `scans` table. Surrogate keys throughout for join performance.

## Consequences

- The scan state, audio metadata, embedded images, and cue sheets all live in
  one queryable store.
- `ad-hoc` queries become trivial — `etp query` can pass sanitized WHERE clauses
  directly to SQLite.
- sqlx's compile-time query checking (optional) catches SQL errors early.
- Adds tokio as a runtime dependency (sqlx requires async). See
  [2026-02-22-02](2026-02-22-02-single-threaded-tokio.md).
- Relative paths make libraries relocatable — moving a collection requires
  updating one row in `scans`.
- Migration from rkyv state files requires a one-time import tool.
- rkyv and brotli dependencies can be removed after migration is complete.
