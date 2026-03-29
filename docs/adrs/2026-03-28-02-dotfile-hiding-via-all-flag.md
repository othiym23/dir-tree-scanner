# ADR: Dotfile Hiding via --all Flag, Not User Excludes

## Status

Accepted (2026-03-28)

## Context

Dotfiles (names starting with `.`) need to be hidden by default in tree, CSV,
and find output, matching the behavior users expect from `ls` and `tree`.

Two approaches were considered:

1. **User exclude pattern**: Include `.*` in `DEFAULT_USER_EXCLUDES`, hiding
   dotfiles via the same glob matching used for other user-specified excludes.
2. **Dedicated `--all` flag**: Hide dotfiles via a boolean check in the display
   filter, controlled by `-A`/`--all`.

## Decision

Use the `--all` flag approach. Dotfile hiding is handled by a `show_hidden`
field in `FilterConfig`, checked in `should_show()` and `should_show_name()`.
The `-A`/`--all` flag is available on `etp-tree`, `etp-csv`, and `etp-find`.

`DEFAULT_USER_EXCLUDES` is empty. User excludes are reserved for user-specified
patterns via `--exclude` and `--ignore`.

`etp-query` does not filter dotfiles — it is a lower-level search command that
shows all indexed files. Users can pass `--exclude '.*'` to etp-query's CLI
exclude list if needed.

## Consequences

- `-A`/`--all` is the familiar mechanism from `ls` and `tree`.
- No interaction between dotfile hiding and user exclude patterns — they're
  independent concerns.
- System files that start with `.` (like `.etp.db`, `.SynologyWorkingDirectory`)
  are managed by the system file filter, not the dotfile filter. They're exempt
  from dotfile hiding to avoid double-filtering.
- `etp-query` shows everything by default, consistent with its role as plumbing.
  The `--exclude` flag on etp-query ADDS to the exclude list (it doesn't replace
  defaults, since there are no defaults to replace).
