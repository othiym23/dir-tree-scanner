# Use lofty with TagLib FFI fallback for audio metadata

Date: 2026-02-22

## Status

Accepted

## Context

The metadata scanner needs to read (and eventually write) audio tags across the
full range of formats in a 220K+ file music collection: MP3, FLAC, OGG, Opus,
WAV, M4A/AAC, APE, DSF, WMA, and MKA. The primary deployment is a statically
linked musl binary on the NAS.

## Decision

Use `lofty` as the primary metadata library — it covers MP3, FLAC, OGG, Opus,
WAV, M4A/AAC, and APE (95%+ of the collection). For formats lofty doesn't
support (DSF, WMA, MKA), fall back to TagLib via C FFI bindings, feature-gated
behind a `taglib` cargo feature.

Tag names are normalized to `lowercase_snake_case`. Multi-value frames within
the same frame type are combined into JSON arrays with order preserved.

## Consequences

- lofty is pure Rust — statically links without issue on musl, no system
  dependencies.
- TagLib is C++ — may require dynamic linking on the NAS or a vendored build.
  The feature gate means the lofty-only path always works statically.
- Two code paths for metadata reading adds complexity to `reader.rs`, but the
  dispatch is simple: try lofty first, fall back to TagLib for unrecognized
  formats.
- The write path (SP3) uses the same dispatch — lofty for most formats, TagLib
  for gap formats.
