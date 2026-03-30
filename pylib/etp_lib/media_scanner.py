"""Position-based token scanner using parsy primitives.

Replaces regex-heavy tokenization with a longest-match scanner that tries
typed recognizers at each position.  Structural delimiters (brackets, parens,
lenticular quotes) are handled first as boundaries.  Between boundaries,
content is scanned with parsy primitives for metadata tokens.  Unrecognized
text accumulates as TEXT tokens.

The output is the same Token list that the existing classify() and
_build_parsed_media() expect, so this is a drop-in replacement for
tokenize_component's internal splitting logic.
"""

from __future__ import annotations

import re

from parsy import Parser

from etp_lib.media_parser import Token, TokenKind

# Import the parsy primitives
from etp_lib.media_parser_parsy import (
    AudioCodec,
    BatchRange,
    BonusKeyword,
    CRC32,
    EpisodeBare,
    EpisodeJP,
    EpisodeSE,
    Language,
    Remux,
    Resolution,
    SeasonJP,
    SeasonOnly,
    SeasonWord,
    Source,
    Special,
    Version,
    VideoCodec,
    Year,
    audio_codec,
    batch_range,
    bonus_en,
    crc32,
    episode_bare,
    episode_jp,
    episode_se,
    language,
    remux,
    resolution,
    season_jp,
    season_only,
    season_word,
    source,
    special,
    version,
    video_codec,
    year,
)


# ---------------------------------------------------------------------------
# Result type → TokenKind mapping
# ---------------------------------------------------------------------------

_TYPE_TO_KIND: dict[type, TokenKind] = {
    Resolution: TokenKind.RESOLUTION,
    VideoCodec: TokenKind.VIDEO_CODEC,
    AudioCodec: TokenKind.AUDIO_CODEC,
    Source: TokenKind.SOURCE,
    Remux: TokenKind.REMUX,
    EpisodeSE: TokenKind.EPISODE,
    EpisodeBare: TokenKind.EPISODE,
    EpisodeJP: TokenKind.EPISODE,
    SeasonJP: TokenKind.SEASON,
    SeasonWord: TokenKind.SEASON,
    SeasonOnly: TokenKind.SEASON,
    Special: TokenKind.EPISODE,
    BatchRange: TokenKind.BATCH_RANGE,
    Version: TokenKind.VERSION,
    Year: TokenKind.YEAR,
    CRC32: TokenKind.CRC32,
    Language: TokenKind.LANGUAGE,
    BonusKeyword: TokenKind.BONUS,
}


def _result_to_token(result: object, text: str) -> Token:
    """Convert a parsy primitive result to a Token for the existing pipeline."""
    kind = _TYPE_TO_KIND.get(type(result), TokenKind.UNKNOWN)
    token = Token(kind=kind, text=text)

    # Populate numeric fields
    if isinstance(result, EpisodeSE):
        token.season = result.season
        token.episode = result.episode
        token.version = result.version
    elif isinstance(result, EpisodeBare):
        token.episode = result.episode
        token.version = result.version
    elif isinstance(result, EpisodeJP):
        token.episode = result.episode
    elif isinstance(result, SeasonJP):
        token.season = result.season
    elif isinstance(result, SeasonWord):
        token.season = result.season
    elif isinstance(result, SeasonOnly):
        token.season = result.season
    elif isinstance(result, Special):
        token.episode = result.number
        # Mark as special via text pattern — classify phase handles this
    elif isinstance(result, Year):
        token.year = result.value
    elif isinstance(result, BatchRange):
        token.batch_start = result.start
        token.batch_end = result.end

    return token


# ---------------------------------------------------------------------------
# Recognizer list — ordered by specificity (most specific first)
# ---------------------------------------------------------------------------

# Each recognizer is tried at the current position. The first (longest) match
# wins. This ordering ensures compound tokens like AAC2.0 are matched before
# AAC, and SxxExx before S-only season markers.

_RECOGNIZERS: list[Parser] = [
    # Episode markers (most distinctive)
    episode_se,  # S01E05, s1e1, S03E13v2
    episode_jp,  # 第01話
    batch_range,  # 01~26
    special,  # SP1, OVA, OAD, ONA
    season_jp,  # 第1期
    season_word,  # 4th Season
    season_only,  # S01 (after episode_se to avoid S01E05 → S01)
    episode_bare,  # 08, 12v2 (after season_only to avoid S01 → ep 1)
    # Bonus keywords
    bonus_en,  # NCOP, NC OP1, Creditless ED
    # Technical metadata (ordered: compound before simple)
    audio_codec,  # AAC2.0, DTS-HD MA, FLAC — compound first
    resolution,  # 1080p, 1920x1080
    video_codec,  # HEVC, x265, H.264
    source,  # BluRay, WEB-DL, BD
    remux,  # REMUX
    # Identifiers
    crc32,  # ABCD1234
    year,  # 2019 (after episode to avoid episode false positives)
    version,  # v2, v3
    # Context
    language,  # jpn, eng, dual
]


# ---------------------------------------------------------------------------
# Position-based scanner
# ---------------------------------------------------------------------------


def scan_words(text: str) -> list[Token]:
    """Scan a space/comma-separated text for known tokens.

    Tries each recognizer at each word boundary, longest match first.
    Unrecognized words become TEXT tokens.  This replaces regex-based
    classification for content within brackets, parens, and bare text
    segments.

    Returns tokens compatible with the existing classify/assembly pipeline.
    """
    tokens: list[Token] = []

    # First pass: try multi-word recognizers on the full text before splitting.
    # This handles patterns like "NC ED1", "Creditless OP", "4th Season",
    # "DTS-HD MA" that span whitespace.
    remaining = text
    pre_tokens: list[tuple[int, int, Token]] = []  # (start, end, token)
    for recognizer in _RECOGNIZERS:
        pos = 0
        while pos < len(remaining):
            result = recognizer(remaining, pos)
            if result.status and result.index > pos:
                # Check it's on a word boundary
                at_start = pos == 0 or remaining[pos - 1] in " ,\t-"
                at_end = (
                    result.index == len(remaining) or remaining[result.index] in " ,\t-"
                )
                if at_start and at_end:
                    pre_tokens.append(
                        (
                            pos,
                            result.index,
                            _result_to_token(
                                result.value, remaining[pos : result.index]
                            ),
                        )
                    )
                    pos = result.index
                    continue
            pos += 1

    # Sort by position, take non-overlapping matches
    pre_tokens.sort(key=lambda x: x[0])
    used: list[tuple[int, int, Token]] = []
    last_end = 0
    for start, end, token in pre_tokens:
        if start >= last_end:
            used.append((start, end, token))
            last_end = end

    # Build token list: recognized spans + unrecognized gaps as TEXT
    def _emit_gap(gap_text: str) -> None:
        gap_text = gap_text.strip(" ,-")
        if gap_text:
            for w in re.split(r"[\s,\-]+", gap_text):
                w = w.strip()
                if w:
                    tokens.append(Token(kind=TokenKind.TEXT, text=w))

    pos = 0
    for start, end, token in used:
        _emit_gap(text[pos:start])
        tokens.append(token)
        pos = end
    _emit_gap(text[pos:])

    return tokens


def scan_words_simple(text: str) -> list[Token]:
    """Simple word-by-word scanning (no multi-word support).

    For backward compatibility and bracket content where multi-word
    patterns are less common.
    """
    tokens: list[Token] = []
    words = re.split(r"([\s,]+)", text)

    for word in words:
        if not word or not word.strip():
            continue
        word = word.strip()

        # Try each recognizer
        matched = False
        for recognizer in _RECOGNIZERS:
            result = recognizer(word, 0)
            if result.status and result.index == len(word):
                # Full match — the recognizer consumed the entire word
                token = _result_to_token(result.value, word)
                tokens.append(token)
                matched = True
                break

        if not matched:
            # Try dash-split: "REMUX-FraMeSToR" → try each part
            if "-" in word and not word.startswith("-"):
                parts = word.split("-")
                sub_tokens = []
                all_recognized = False
                for part in parts:
                    if not part:
                        continue
                    part_matched = False
                    for recognizer in _RECOGNIZERS:
                        result = recognizer(part, 0)
                        if result.status and result.index == len(part):
                            sub_tokens.append(_result_to_token(result.value, part))
                            part_matched = True
                            break
                    if not part_matched:
                        sub_tokens.append(Token(kind=TokenKind.UNKNOWN, text=part))
                    else:
                        all_recognized = True

                if all_recognized:
                    tokens.extend(sub_tokens)
                    matched = True

            if not matched:
                tokens.append(Token(kind=TokenKind.TEXT, text=word))

    return tokens


def scan_dot_segments(text: str) -> list[Token]:
    """Scan dot-separated scene-style text.

    Instead of the placeholder approach for compound tokens, this scanner
    tries recognizers at each position in the dot-split stream.  When a
    recognizer matches across a dot boundary (e.g. 'H' + '264' → H.264),
    the segments are rejoined.

    Returns DOT_TEXT tokens for unrecognized segments and typed tokens for
    recognized metadata.
    """
    raw_parts = text.split(".")
    tokens: list[Token] = []
    i = 0

    while i < len(raw_parts):
        part = raw_parts[i]

        if not part:
            i += 1
            continue

        # Try multi-segment compounds first (longest match)
        # Check 3-segment: "MA.5.1", "FLAC.2.0"
        if i + 2 < len(raw_parts):
            compound3 = f"{part}.{raw_parts[i + 1]}.{raw_parts[i + 2]}"
            token = _try_recognize(compound3)
            if token is not None:
                tokens.append(token)
                i += 3
                continue

        # Check 2-segment: "H.264", "AAC2.0"
        if i + 1 < len(raw_parts):
            # Also try with trailing "-suffix" stripped for "H.264-VARYG"
            next_part = raw_parts[i + 1]
            compound2 = f"{part}.{next_part}"
            token = _try_recognize(compound2)
            if token is not None:
                tokens.append(token)
                i += 2
                continue

            # Strip trailing -suffix and try: "H" + "264-VARYG" → "H.264"
            next_base = re.sub(r"-[A-Za-z].*$", "", next_part)
            if next_base != next_part:
                compound2_stripped = f"{part}.{next_base}"
                token = _try_recognize(compound2_stripped)
                if token is not None:
                    tokens.append(token)
                    # The suffix after the dash is the release group
                    # (scene convention: codec-GROUP)
                    suffix = next_part[len(next_base) + 1 :]
                    if suffix:
                        suffix_token = _try_recognize(suffix)
                        if suffix_token is not None:
                            tokens.append(suffix_token)
                        else:
                            tokens.append(
                                Token(kind=TokenKind.RELEASE_GROUP, text=suffix)
                            )
                    i += 2
                    continue

        # Single segment
        token = _try_recognize(part)
        if token is not None:
            tokens.append(token)
        else:
            # Check if it has a trailing "-GROUP" (scene convention)
            dash_m = re.match(r"^(.+)-([A-Za-z][A-Za-z0-9]+)$", part)
            if dash_m:
                prefix = dash_m.group(1)
                suffix = dash_m.group(2)
                prefix_token = _try_recognize(prefix)
                if prefix_token is not None:
                    tokens.append(prefix_token)
                    tokens.append(Token(kind=TokenKind.RELEASE_GROUP, text=suffix))
                else:
                    tokens.append(Token(kind=TokenKind.DOT_TEXT, text=part))
            else:
                tokens.append(Token(kind=TokenKind.DOT_TEXT, text=part))

        i += 1

    return tokens


def _try_recognize(text: str) -> Token | None:
    """Try all recognizers against a complete text. Returns Token or None."""
    for recognizer in _RECOGNIZERS:
        result = recognizer(text, 0)
        if result.status and result.index == len(text):
            return _result_to_token(result.value, text)
    return None
