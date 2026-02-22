# Use a Cargo workspace with a shared library crate

Date: 2026-02-22

## Status

Accepted

## Context

The project is growing from one binary with two subcommands
(`dir-tree-scanner csv`, `dir-tree-scanner tree`) to multiple focused binaries
(`etp-csv`, `etp-tree`, `etp-meta`, `etp-query`, `etp-cas`). All binaries share
scanning, database, and metadata logic. The single-crate structure doesn't
support multiple independent binaries cleanly.

## Decision

Restructure as a Cargo workspace. All shared logic lives in `etp-lib` (library
crate). Each binary is a thin wrapper that parses CLI args and calls into
`etp-lib`. The workspace root contains no `[package]` — it's a virtual manifest.

Error handling convention: `anyhow` in binary crates for ergonomic error
propagation, `thiserror` in `etp-lib` for typed errors that callers can match
on.

## Consequences

- Each binary compiles independently and can be deployed individually.
- Shared logic changes are tested once in `etp-lib` and automatically apply to
  all binaries.
- Cross-compilation targets (`x86_64-unknown-linux-musl`) apply to the whole
  workspace via `.cargo/config.toml`.
- `build.rs` for git hash embedding must exist in each binary crate (not shared
  at workspace level).
- trycmd snapshot tests split across binary crates, each testing its own CLI.
