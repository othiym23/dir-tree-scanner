# Use brotli compression for state files

Date: 2026-02-15

## Status

Superseded by
[2026-02-22-01 sqlx with SQLite](2026-02-22-01-sqlx-sqlite-database.md)

## Context

rkyv state files for a 200K+ file collection are large (repetitive path prefixes
compress well). The state file is written once per scan and read once on the
next scan, so compression ratio matters more than decompression speed.

## Decision

State file format version 2 wraps the rkyv payload in brotli compression
(quality 5, 4 MB window). The load path handles both v1 (raw rkyv) and v2
(brotli-compressed) for backward compatibility.

## Consequences

- State files are significantly smaller than raw rkyv (repetitive paths compress
  well).
- Quality 5 is a good balance — fast enough for interactive use, much better
  ratio than zstd at equivalent speed.
- Backward compatibility with v1 files means old state files continue to work
  after the upgrade.
- Adds the `brotli` crate dependency.
