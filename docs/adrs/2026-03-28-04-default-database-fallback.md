# ADR: Default Database Fallback Behavior

## Status

Accepted (2026-03-28)

## Context

Commands need a database to operate. Before `config.kdl`, users had to pass
`--db` explicitly or rely on `<directory>/.etp.db` existing. With database
nicknames and `default-database`, there's a new fallback chain to define.

## Decision

The `default-database` setting in `config.kdl` names a configured database
nickname that serves as the fallback when no `--db` is specified and no
`.etp.db` exists in the target directory.

### Fallback chain (etp-tree, etp-csv, etp-find)

1. Explicit `--db <path>` or `--db <nickname>` — used as-is
2. `<directory>/.etp.db` — used if the file exists
3. `default-database` from `config.kdl` — resolved via nickname
4. Exit with code 2 (EXIT_NO_SCAN) — no database found

### etp-query

Same chain, except etp-query requires `--db` (it has no directory argument). The
fallback is:

1. `--db <path>` or `--db <nickname>`
2. `default-database` from `config.kdl`
3. Exit with error

### etp-scan

etp-scan does NOT fall back to `default-database`. When no `--db` is given, it
always creates `<directory>/.etp.db`. This is deliberate: scanning creates or
updates a database, and silently writing to a pre-existing database via an
implicit fallback could cause unexpected data in the wrong database.

### Validation

`default-database` must name a database nickname that exists in `config.kdl`. If
the nickname is invalid, config loading fails with a clear error message before
any command runs.

## Consequences

- Users can run `etp tree /volume1/music` without `--db` if `default-database`
  is configured and `/volume1/music/.etp.db` doesn't exist.
- etp-scan always writes to an explicit or co-located database — no implicit
  fallback prevents accidental cross-database pollution.
- The `default-database` setting is validated at config load time, preventing
  typos from causing confusing runtime failures.
