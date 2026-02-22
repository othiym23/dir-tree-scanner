# Use Rust plumbing with Python porcelain

Date: 2026-02-22

## Status

Accepted

## Context

The toolkit needs two layers: fast, reliable core operations (scanning, database
writes, metadata reads) and flexible orchestration (running scans across
multiple directories, composing workflows, interactive use). The existing Python
orchestrator (`catalog-nas.py`) already demonstrates the pattern — it calls the
Rust binary for heavy lifting and handles workflow logic in Python.

## Decision

Follow the Git model: Rust binaries are "plumbing" commands (`etp-csv`,
`etp-tree`, `etp-meta`, `etp-query`, `etp-cas`) that do one thing each. A Python
"porcelain" layer provides user-facing commands (`etp`, `etp-catalog`) that
compose plumbing commands and handle workflow orchestration.

The `etp` entry point uses Git-style subcommand dispatch — `etp csv ...` finds
and runs `etp-csv ...` from `$PATH`.

## Consequences

- Rust handles all performance-critical and correctness-critical work (disk I/O,
  database operations, metadata parsing).
- Python handles orchestration, where startup time and runtime speed don't
  matter but flexibility and iteration speed do.
- New porcelain commands can be added without recompiling Rust.
- Users can call plumbing commands directly for scripting and automation.
- The `etp` dispatcher is simple — just `execvp("etp-" + subcommand, args)`.
- Python porcelain must be deployed alongside the Rust binaries. On the NAS,
  this means Python 3 must be available (it is, via DSM's package manager).
