# Use mlua with LuaJIT for embedded scripting

Date: 2026-02-22

## Status

Accepted

## Context

Large-scale metadata management requires user-defined transforms — normalizing
genres, fixing artist names, applying bulk tag changes. These transforms need to
be expressible without recompiling the Rust binary, iterable quickly, and safe
(a bad script shouldn't corrupt files).

## Decision

Embed LuaJIT via `mlua` with the `vendored` feature. Scripts receive file
metadata and return tag changes. A batch runner collects all changes per file
across all scripts and coalesces them into a single write operation.

The Lua API exposes: `file:tag(name)`, `file:set_tag(name, value)`, `file.path`,
`file.format`, and `etp.run(cmd, args)` for calling external binaries.

## Consequences

- LuaJIT is fast enough for iterating over 220K+ files without becoming the
  bottleneck.
- The `vendored` feature statically links LuaJIT — works on musl without system
  dependencies.
- Coalesced writes mean each file is touched at most once regardless of how many
  scripts run, reducing disk I/O and corruption risk.
- Script errors abort processing for that file but don't stop the batch —
  partial failures are reported, never silently applied.
- Lua is a less common choice than Python for scripting, but embedding Python
  (via PyO3) would be far heavier and harder to statically link.
