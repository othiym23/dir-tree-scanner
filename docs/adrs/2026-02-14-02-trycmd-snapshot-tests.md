# Use trycmd for CLI snapshot tests

Date: 2026-02-14

## Status

Accepted

## Context

The scanner binaries need integration tests that verify end-to-end CLI behavior:
argument parsing, output format, exit codes, and error messages. Unit tests
cover individual modules but don't catch regressions in the assembled binary.
The tests must be deterministic despite scanning real filesystems (timestamps,
paths).

## Decision

Use `trycmd` for CLI snapshot testing. Each test is a TOML file
(`tests/cmd/<name>.toml`) that specifies the binary, arguments, expected exit
code, and expected stdout/stderr. Optional `<name>.in/` fixture directories
provide input files when `fs.sandbox = true`. Use sandboxed mode with `.` as the
directory argument for deterministic output paths.

## Consequences

- Tests are declarative — adding a new CLI test is a TOML file and optionally a
  fixture directory, no Rust code needed.
- Sandbox mode copies fixtures into a temp directory, isolating tests from each
  other and the host filesystem.
- Expected output is stored in `.stdout`/`.stderr` sidecar files, making diffs
  obvious in code review.
- trycmd finds binaries by `bin.name` within the Cargo workspace — tests work
  regardless of which crate owns them.
- Snapshot tests are brittle to output format changes — any change to
  formatting, whitespace, or wording requires updating the expected output
  files.
