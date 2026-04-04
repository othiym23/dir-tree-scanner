"""ANSI 256-color helpers for media filename display.

Provides token-level colorization of media paths and formatted display of
ParsedMedia objects. Used by both the QA tool and the manifest workflow to
give a visual breakdown of parsed filename components.
"""

from __future__ import annotations

import re

from etp_lib.media_parser import (
    ParsedMedia,
    TokenKind,
    classify,
    scan_words,
    tokenize_component,
)


def _c(n: int) -> str:
    return f"\033[38;5;{n}m"


TOKEN_COLORS: dict[TokenKind, str] = {
    TokenKind.TEXT: _c(228),  # bright yellow — series name
    TokenKind.DOT_TEXT: _c(228),  # bright yellow — series name
    TokenKind.EPISODE_TITLE: _c(218),  # light pink — episode title
    TokenKind.RELEASE_GROUP: _c(214),  # orange
    TokenKind.CRC32: _c(245),  # mid gray
    TokenKind.EPISODE: _c(51),  # bright cyan — episode number
    TokenKind.SEASON: _c(39),  # deep sky blue — season number
    TokenKind.SPECIAL: _c(207),  # hot pink
    TokenKind.VERSION: _c(141),  # medium purple
    TokenKind.RESOLUTION: _c(114),  # pale green
    TokenKind.VIDEO_CODEC: _c(79),  # medium aquamarine
    TokenKind.AUDIO_CODEC: _c(180),  # tan / light salmon
    TokenKind.SOURCE: _c(176),  # pink / light magenta
    TokenKind.REMUX: _c(204),  # hot pink (distinct from source)
    TokenKind.YEAR: _c(75),  # steel blue
    TokenKind.BATCH_RANGE: _c(87),  # aquamarine
    TokenKind.SUBTITLE_INFO: _c(102),  # gray-green
    TokenKind.LANGUAGE: _c(103),  # olive gray
    TokenKind.BONUS: _c(213),  # orchid
    TokenKind.DUAL_AUDIO: _c(222),  # light gold
    TokenKind.UNCENSORED: _c(196),  # red
    TokenKind.EDITION: _c(147),  # light steel blue
    TokenKind.HDR: _c(226),  # yellow
    TokenKind.BIT_DEPTH: _c(156),  # light green
    TokenKind.SEPARATOR: _c(240),  # dark gray
    TokenKind.EXTENSION: _c(240),  # dark gray
    TokenKind.SITE_PREFIX: _c(240),  # dark gray
    TokenKind.UNKNOWN: _c(244),  # gray — unclassified metadata
}
RESET = "\033[0m"

_FIELD_TO_KIND: dict[str, TokenKind] = {
    "series": TokenKind.TEXT,
    "alt_title": TokenKind.TEXT,
    "ep_title": TokenKind.EPISODE_TITLE,
    "season": TokenKind.SEASON,
    "episode": TokenKind.EPISODE,
    "episodes": TokenKind.EPISODE,
    "version": TokenKind.VERSION,
    "special": TokenKind.SPECIAL,
    "bonus": TokenKind.BONUS,
    "batch": TokenKind.BATCH_RANGE,
    "group": TokenKind.RELEASE_GROUP,
    "source": TokenKind.SOURCE,
    "streamer": TokenKind.SOURCE,
    "remux": TokenKind.REMUX,
    "dual-audio": TokenKind.DUAL_AUDIO,
    "criterion": TokenKind.EDITION,
    "uncensored": TokenKind.UNCENSORED,
    "res": TokenKind.RESOLUTION,
    "bit_depth": TokenKind.BIT_DEPTH,
    "hdr": TokenKind.HDR,
    "video": TokenKind.VIDEO_CODEC,
    "audio": TokenKind.AUDIO_CODEC,
    "hash": TokenKind.CRC32,
    "year": TokenKind.YEAR,
    "ext": TokenKind.EXTENSION,
    "dir_series": TokenKind.TEXT,
}

_RE_SE_SPLIT = re.compile(r"([Ss]\d{1,2})([Ee]\d{1,4}(?:v\d+)?)", re.IGNORECASE)


def colorize(text: str, kind: TokenKind) -> str:
    """Wrap text in ANSI color for a token kind."""
    color = TOKEN_COLORS.get(kind, "")
    if color:
        return f"{color}{text}{RESET}"
    return text


def color_for_field(field: str) -> str:
    """Return the ANSI color code for a parsed field name."""
    kind = _FIELD_TO_KIND.get(field)
    if kind:
        return TOKEN_COLORS.get(kind, "")
    return ""


def colorize_token_text(text: str, kind: TokenKind) -> str:
    """Colorize a token's text, splitting S01E01 into season+episode colors."""
    if kind == TokenKind.EPISODE:
        m = _RE_SE_SPLIT.match(text)
        if m:
            season_part = colorize(m.group(1), TokenKind.SEASON)
            ep_part = colorize(m.group(2), TokenKind.EPISODE)
            rest = text[m.end() :]
            return season_part + ep_part + (colorize(rest, kind) if rest else "")
    return colorize(text, kind)


def colorize_path(rel_path: str) -> str:
    """Colorize a media path by overlaying token classifications.

    Splits the path into components, classifies each, and reconstructs
    the path with ANSI colors applied to each recognized span. Large
    unclassified TEXT tokens (like directory names with metadata) are
    further scanned with scan_words for finer-grained coloring.
    """
    parts = rel_path.split("/")
    colored_parts: list[str] = []

    for part in parts:
        tokens = classify(tokenize_component(part))
        # Reconstruct the part by finding each token's text in order
        result: list[str] = []
        remaining = part
        for token in tokens:
            text = token.text

            # Large TEXT/DOT_TEXT tokens may contain unclassified metadata
            # (e.g., directory names). Scan for finer-grained tokens.
            if token.kind in (TokenKind.TEXT, TokenKind.DOT_TEXT) and " " in text:
                sub_tokens = scan_words(text)
                if any(t.kind != TokenKind.UNKNOWN for t in sub_tokens):
                    # Found classifiable content — colorize each sub-token
                    idx = remaining.find(text)
                    if idx > 0:
                        result.append(remaining[:idx])
                    sub_remaining = text
                    for st in sub_tokens:
                        si = sub_remaining.find(st.text)
                        if si > 0:
                            result.append(sub_remaining[:si])
                        if si >= 0:
                            kind = (
                                st.kind if st.kind != TokenKind.UNKNOWN else token.kind
                            )
                            result.append(colorize_token_text(st.text, kind))
                            sub_remaining = sub_remaining[si + len(st.text) :]
                        else:
                            result.append(colorize_token_text(st.text, st.kind))
                    if sub_remaining:
                        result.append(sub_remaining)
                    remaining = remaining[idx + len(text) :] if idx >= 0 else remaining
                    continue

            # Find the token text in remaining string
            # For brackets/parens, search for the delimited form
            if token.kind == TokenKind.BRACKET:
                search = f"[{text}]"
            elif token.kind == TokenKind.PAREN:
                search = f"({text})"
            elif token.kind == TokenKind.LENTICULAR:
                search = f"\u300c{text}\u300d"
            else:
                search = text

            idx = remaining.find(search)
            if idx == -1:
                idx = remaining.find(text)

            if idx >= 0:
                if idx > 0:
                    result.append(remaining[:idx])
                display = search if search != text else text
                result.append(colorize_token_text(display, token.kind))
                remaining = remaining[idx + len(display) :]
            else:
                result.append(colorize_token_text(text, token.kind))

        if remaining:
            result.append(remaining)

        colored_parts.append("".join(result))

    return "/".join(colored_parts)


def format_parsed_media(pm: ParsedMedia) -> str:
    """Format ParsedMedia for display, showing only non-empty fields."""
    lines = []
    for field, value in [
        ("series", pm.series_name),
        ("alt_title", pm.series_name_alt if pm.series_name_alt else None),
        ("ep_title", pm.episode_title),
        ("season", pm.season),
        ("episode", pm.episode),
        (
            "episodes",
            ", ".join(str(e) for e in pm.episodes) if pm.episodes else None,
        ),
        ("version", pm.version),
        ("special", f"{pm.is_special} ({pm.special_tag})" if pm.is_special else None),
        ("bonus", pm.bonus_type),
        (
            "batch",
            f"{pm.batch_range[0]}~{pm.batch_range[1]}" if pm.batch_range else None,
        ),
        ("group", pm.release_group),
        ("source", pm.source_type),
        ("streamer", pm.streaming_service if pm.streaming_service else None),
        ("remux", pm.is_remux if pm.is_remux else None),
        ("dual-audio", pm.is_dual_audio if pm.is_dual_audio else None),
        ("criterion", pm.is_criterion if pm.is_criterion else None),
        ("uncensored", pm.is_uncensored if pm.is_uncensored else None),
        ("res", pm.resolution),
        ("bit_depth", f"{pm.bit_depth}bit" if pm.bit_depth else None),
        ("hdr", pm.hdr if pm.hdr else None),
        ("video", pm.video_codec),
        ("audio", ", ".join(pm.audio_codecs) if pm.audio_codecs else None),
        ("hash", pm.hash_code),
        ("year", pm.year),
        ("ext", pm.extension),
        ("dir_series", pm.path_series_name if pm.path_series_name else None),
    ]:
        if value is not None and value != "" and value is not False:
            color = color_for_field(field)
            val_str = f"{color}{value}{RESET}" if color else str(value)
            lines.append(f"  {field:12s} {val_str}")
    return "\n".join(lines)
