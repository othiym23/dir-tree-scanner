# Target Python 3.8 with vendored tomli

Date: 2026-02-14

## Status

Superseded by [2026-02-15-04 Python 3.14](2026-02-15-04-python-314.md)

## Context

The catalog orchestrator script needs to run on the Synology NAS, which ships
Python 3.8 via DSM's package manager. The script needs to parse TOML
configuration, but `tomllib` was not added to the standard library until Python
3.11.

## Decision

Target Python 3.8. Vendor `tomli` 2.4.0 (the backport of `tomllib`) into
`scripts/_vendor/tomli/` to avoid requiring `pip install` on the NAS. Use
`from __future__ import annotations` for newer typing syntax.

## Consequences

- The script runs on the NAS without installing any packages beyond what DSM
  provides.
- Vendoring avoids a runtime dependency but means manually updating if tomli has
  security fixes.
- Python 3.8 typing limitations require `from __future__ import annotations` and
  `typing.Dict`/`typing.List` instead of builtins.
- Cannot use newer Python features: walrus operator patterns, `match`
  statements, union type syntax (`X | Y`), etc.
