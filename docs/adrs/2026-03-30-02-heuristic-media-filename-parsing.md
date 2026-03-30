# Heuristic media filename parsing

Date: 2026-03-30

## Status

Accepted

## Context

Anime and media filenames follow loosely adopted conventions that are not
intended for machine processing. They exist to communicate metadata to humans
browsing torrent indexes or Usenet crawlers. The same information can appear in
different positions, with different delimiters, in different languages, and with
varying levels of completeness.

Four major naming conventions coexist:

1. **Fansub**: `[Group] Title - 01 [metadata] [hash].ext`
2. **Scene**: `Title.S01E05.metadata.codec-GROUP.ext`
3. **Sonarr/PVR**: `Title - s1e01 - Episode Name [Group meta,...].ext`
4. **Japanese BD**: `[Group] Title 第01話「EpTitle」(metadata).ext`

An evaluation of formal parsing approaches (parser combinators with parsy, PEG
grammars with parsimonious) showed that these conventions resist grammar-based
parsing because:

- The same delimiter (dot, dash, bracket) means different things in different
  positions.
- Vocabulary is open-ended — any word could be a title word or a metadata
  keyword depending on context.
- Compound tokens span delimiters (H.264 spans a dot, DTS-HD MA spans a space).
- Bracket content is context-dependent (first bracket = group in fansub style,
  metadata in other styles).

## Decision

Use a three-phase heuristic pipeline:

1. **Structural tokenization**: Character-by-character scan that identifies
   delimiters (brackets, parens, lenticular quotes, dots, separators) without
   interpreting content. Scene-style dot-separated text uses a position-based
   scanner with typed recognizers for compound token handling.

2. **Semantic classification**: Walks the token list with positional state
   (`seen_episode`, `first_bracket_seen`) to reclassify structural tokens by
   content. Uses parsy-based recognizers for word-level classification.

3. **Assembly**: Extracts series name, episode title, and metadata fields from
   the classified token list using zone-based heuristics (title before episode,
   episode title after episode, metadata after first metadata token).

Accept false positives where fixing them would break the common case:

- `chi` (Chinese language code) matches the start of Japanese movie titles —
  accepted because donghua language detection is more important.
- Bracket content after credit specials (e.g., `[Artist Name]`) may be
  misidentified as a release group — mitigated by preferring directory-level
  groups when available.

Directory metadata propagation fills gaps: when a filename has no metadata
(common for minimal scene names like `S01E01-Title.mkv`), metadata is extracted
from directory names by scanning all path components with the same recognizers.

## Consequences

- The parser handles ~95% of real-world filenames correctly without manual
  intervention.
- The remaining ~5% can be corrected via the editable KDL manifest before file
  operations execute.
- New naming patterns are addressed by adding recognizers or adjusting the
  classify phase — not by rewriting the architecture.
- A QA tool (`pylib/tools/qa_parser.py`) enables systematic review of parser
  output against real filename corpora, logging problems for regression testing.
- The parser is not suitable for untrusted input — it uses `assert` in
  recognizer callbacks and does not validate string lengths.
