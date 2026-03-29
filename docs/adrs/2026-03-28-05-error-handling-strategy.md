# ADR: Error Handling Strategy

## Status

Accepted (2026-03-28)

## Context

The codebase has accumulated inconsistent error handling across etp-lib and its
binary crates:

- Library functions in `ops.rs` call `process::exit` directly, making them
  untestable and unusable in any context that needs error recovery.
- Binary crates use `unwrap_or_else(|e| { eprintln!; exit(1) })` repeatedly,
  creating deep nesting instead of using `?` propagation.
- Some functions return `Result`, others exit, others absorb errors silently.
- Hand-written `Display` and `Error` impls add boilerplate.

The project has a single developer and user. Scanning and metadata reading are
crash-only operations — errors are unrecoverable and should halt with maximum
context to speed up debugging. The database uses transactions extensively so
that crash recovery is always safe.

## Decision

### Library crate (etp-lib): per-module typed errors with `thiserror`

Each module defines its own error type using `thiserror::Error` derive:

- `config::ConfigError` — Io, Parse, Validation (already exists, convert to
  thiserror)
- `scanner::ScanError` — wraps io::Error, sqlx::Error
- `cas::CasError` — wraps io::Error, etcetera::HomeDirError
- `metadata::MetadataError` — already exists, convert to thiserror
- `tree.rs`, `csv_writer.rs` — return `io::Result` (unchanged)
- `db/dao.rs` — returns `sqlx::Error` (unchanged)

`ops.rs` is the orchestration layer that composes all modules. It uses
`anyhow::Result` internally since it doesn't need to match on specific error
variants — it just adds context and propagates.

Per-module types are preferred over a unified enum because:

- Each type only contains variants the module can actually produce
- Modules can evolve independently (e.g., etp-cue may be carved out)
- Avoids a centralizing registry enum that couples all modules

### Library crate rules

- No `unwrap()` or `expect()` anywhere in etp-lib
- No `process::exit` anywhere in etp-lib
- All fallible operations return `Result<T, Error>`
- Errors include context at each level of the call tree

### Binary crates: `anyhow` for ergonomic propagation

Binary crates use `anyhow::Result` in `main()` and `?` with `.context()` for
error propagation. `main()` is the only place that converts errors to exit
codes. This replaces the current pattern of `unwrap_or_else` + `eprintln!` +
`process::exit` scattered throughout each binary.

Error output uses anyhow's chain display, which prints the error and all its
context sources — giving the developer maximum information for debugging.

### Crash-only scanning

File scanning and metadata reading are crash-only operations. Errors in either
process are unrecoverable and should halt as quickly as is safe. The heavy
reliance on database transactions ensures that a crash at any point leaves the
database in a consistent state.

The `EXIT_NO_SCAN` (code 2) convention for "no scan exists" is preserved as a
special case — the porcelain dispatcher catches it for auto-scan retry. This
exit code is set in binary `main()` functions, not in the library.

## Consequences

- `thiserror` added as a dependency to etp-lib
- `anyhow` added as a dependency to all binary crates
- Every `process::exit` in etp-lib becomes a `Result` return
- Binary `main()` functions become `fn main() -> anyhow::Result<()>` or use a
  thin wrapper for custom exit codes
- Error messages include full context chains instead of bare `eprintln!`
- Library functions become testable for error paths
- Library crate is reusable in contexts beyond CLI tools (future GUI, daemon,
  etc.)
