# Parsy primitives for token recognition

Date: 2026-03-30

## Status

Accepted

## Context

The media filename parser extracts metadata (resolution, codec, source type,
episode markers, etc.) from anime/media filenames that follow loosely adopted
naming conventions. The original implementation used a chain of regex patterns
and vocabulary set lookups (`_classify_text_content`) for word-level
recognition, and a NUL-byte placeholder mechanism for preserving compound tokens
(H.264, AAC2.0) during dot-separated scene-style splitting.

Problems with the regex approach:

- **Fragile compound token handling**: Adding a new compound token required
  updating a set, building a regex alternation, and hoping the placeholder
  mechanism didn't collide. Compounds with trailing suffixes (H.264-VARYG)
  couldn't be handled at all.
- **No refutable matching**: Once a regex consumed input, the decision was
  final. If `DD` matched before `DD+2.0` could be tried, the `.0` leaked into
  subsequent patterns.
- **Duplicated classification logic**: The same vocabulary checks appeared in
  `_classify_text_content`, `_expand_metadata_words`, `_is_metadata_word`, and
  `_count_metadata_words` with slight variations.

An exploration of parser combinator (parsy) and PEG (parsimonious) frameworks
showed that full grammar-based parsing doesn't fit — media filenames are
semi-structured text, not a formal language. But the _primitive recognizers_
from parsy proved valuable as typed, composable token classifiers.

## Decision

Use parsy `Parser` objects as typed recognizers for individual tokens (words,
compound tokens, episode markers). Each recognizer takes `(stream, index)` and
returns either a typed success result or a failure — this is refutable matching.

The recognizers are composed into an ordered `_RECOGNIZERS` list (longest/most
specific first) and used by position-based scanner functions:

- `scan_dot_segments` — replaces the placeholder mechanism for scene-style
  dot-separated filenames. Tries multi-segment compounds at each position.
- `scan_words` — replaces `_expand_metadata_words`. Handles multi-word patterns
  (NC ED1, DTS-HD MA), dash-compound splitting (REMUX-GROUP), and release group
  detection.
- `_try_recognize` — single-word classification, replaces
  `_classify_text_content`.
- `find_episode_in_text` — positional search for episode markers within text.

The structural tokenizer (bracket/paren/lenticular delimiter handling) and the
classify/assembly phases remain imperative Python. Only the "is this word a
known metadata token?" question is delegated to parsy.

## Consequences

- Compound tokens (H.264, AAC2.0, DD+2.0) are recognized by the audio/video
  codec recognizers directly — no placeholder mechanism needed.
- New token types are added by defining a result dataclass, a parsy `Parser`,
  and adding it to `_RECOGNIZERS` in the right priority position.
- The vocabulary sets (`_SOURCES`, `_VIDEO_CODECS`, etc.) are shared between
  recognizers and the existing code via `media_vocab.py`.
- `parsy` is a runtime dependency (pure Python, no C extensions).
- 21 hot-path regex patterns are pre-compiled at module level to avoid per-call
  compilation overhead in the recognizer functions.
