# Use KDL with knuffel for configuration

Date: 2026-02-22

## Status

Accepted

## Context

The catalog orchestrator currently uses TOML (`catalog.toml`) to configure scan
targets. As the project grows to include metadata rules, scripting paths, CAS
configuration, and per-scan overrides, the configuration structure needs better
nesting support than TOML provides naturally.

## Decision

Use KDL as the configuration format, with the `knuffel` crate for
deserialization into Rust structs via `#[derive(Decode)]`. Disabled scans use
KDL's slashdash (`/-`) comment syntax instead of an `enabled` boolean field.

## Consequences

- KDL's node-based syntax handles nested configuration (scan targets, global
  settings, per-scan overrides) more naturally than TOML's table syntax.
- `knuffel` provides derive-based deserialization similar to serde, with good
  error messages for invalid config.
- Slashdash for disabling scans is more idiomatic than a boolean field — the
  entire node is commented out, making it visually obvious.
- KDL is less widely known than TOML — users need to learn the syntax. The
  format is simple enough that this is a minor concern.
- Existing `catalog.toml` must be manually converted to `catalog.kdl`.
