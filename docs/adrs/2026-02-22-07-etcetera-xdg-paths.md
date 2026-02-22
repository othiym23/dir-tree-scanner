# Use etcetera for XDG and native path resolution

Date: 2026-02-22

## Status

Accepted

## Context

The project runs on both macOS (development) and Linux (NAS deployment). It
needs standard locations for its config file, database, and CAS blob store.
macOS has `~/Library/Application Support/`, Linux uses XDG base directories. The
current approach of writing state files into the scanned directory doesn't scale
to a shared database.

## Decision

Use the `etcetera` crate for path resolution. On macOS, use native paths
(`~/Library/Application Support/net.aoaioxxysz.etp/`). On Linux, use strict XDG
(`$XDG_DATA_HOME/euterpe-tools/`, `$XDG_CONFIG_HOME/euterpe-tools/`).

Paths:

- Config: `config.kdl` in the config directory
- Database: `metadata.sqlite` in the data directory
- CAS: `assets/{ab}/{hash}` in the data directory

## Consequences

- Files land where each platform's users expect them.
- `etcetera` is a small, well-maintained crate with no transitive dependencies.
- The reverse-domain bundle ID (`net.aoaioxxysz.etp`) is only used on macOS —
  Linux uses the plain app name.
- All paths are overridable via CLI flags (`--db`, `--config`) for testing and
  non-standard deployments.
