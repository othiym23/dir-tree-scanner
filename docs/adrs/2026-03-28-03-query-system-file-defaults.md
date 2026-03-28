# ADR: etp-query System File Filtering Defaults

## Status

Accepted (2026-03-28)

## Context

`etp-query` is a low-level plumbing command for searching the indexed database.
Unlike the porcelain commands (`etp-tree`, `etp-csv`, `etp-find`) which default
to hiding system files, etp-query needs different defaults because it serves
different use cases.

The question: should etp-query hide system files by default like the other
commands, or show everything?

## Decision

etp-query **includes** system files by default (opposite of tree/csv/find), with
per-subcommand overrides:

| Subcommand | Default          | Rationale                                              |
| ---------- | ---------------- | ------------------------------------------------------ |
| `files`    | include          | Low-level listing should show everything               |
| `tags`     | n/a              | Operates on a single file by path, no filtering needed |
| `find`     | include          | Metadata search should find all matching files         |
| `stats`    | **exclude**      | System file counts/sizes badly skew statistics         |
| `size`     | include (always) | System files are real disk usage, always counted       |
| `sql`      | n/a (no filter)  | Raw SQL passthrough, no display-time filtering         |

The `--[no-]include-system-files` flag overrides the default for any subcommand.

### stats exception

The `stats` subcommand shows file counts, total size, and extension breakdown.
Including system files would:

- Inflate the file count with NAS thumbnails and metadata files
- Include `@eaDir` storage in the total size (misleading for "how much music do
  I have?")
- Add system-only extensions to the breakdown

Since `stats` is the summary people look at to understand their collection,
defaulting to `--no-include-system-files` gives the useful answer. Users can
pass `--include-system-files` to see the raw totals.

### size exception

The `size` subcommand always includes system files regardless of the flag. This
matches the `--du` behavior on etp-tree: disk usage should reflect actual disk
usage, including system overhead.

### Dotfile handling

etp-query does **not** apply dotfile hiding. It always shows dotfiles regardless
of whether `-A`/`--all` is passed (it doesn't accept that flag). This is
consistent with its role as plumbing.

## Consequences

- etp-query is the only command that defaults to `--include-system-files`. This
  is documented in `resolve_system_files()` and in DESIGN_NOTES.md.
- The per-subcommand default inversion is encoded in a single function, making
  it easy to audit and modify.
- `sql` deliberately bypasses all display-time filtering — it's the escape hatch
  for queries that need to see the raw database.
