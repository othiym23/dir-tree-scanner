"""PEG-based media filename parser using parsimonious.

Each naming convention has its own PEG grammar. Convention detection
dispatches to the appropriate grammar. A NodeVisitor walks the parse
tree and assembles a ParsedMedia directly.
"""

from __future__ import annotations

import re
from parsimonious.grammar import Grammar
from parsimonious.nodes import NodeVisitor
from parsimonious.exceptions import ParseError as ParsimoniousParseError

from etp_lib.media_parser import (
    _AUDIO_CODECS,
    _COMPOUND_TOKENS,
    _LANGUAGES,
    _SOURCE_TYPE_MAP,
    _SOURCES,
    _VIDEO_CODECS,
    ParsedMedia,
)


# ---------------------------------------------------------------------------
# Shared vocabulary patterns for PEG grammars
# ---------------------------------------------------------------------------


# Build regex alternations from vocabulary sets (longest first to avoid
# prefix matches consuming partial tokens).
def _alt_pattern(words: frozenset[str]) -> str:
    """Build a regex alternation from a word set, longest first."""
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))  # ty: ignore[invalid-argument-type]


_VIDEO_CODEC_PAT = _alt_pattern(_VIDEO_CODECS)
_AUDIO_CODEC_PAT = _alt_pattern(_AUDIO_CODECS)
_SOURCE_PAT = _alt_pattern(_SOURCES)
_LANG_PAT = _alt_pattern(_LANGUAGES)

# Compound audio codecs: AAC2.0, DDP5.1, DTS-HD MA, etc.
_AUDIO_COMPOUND_PAT = (
    r"(?:DTS-HDMA|DTS-HD\s*MA|DTS-HD|DTS|DDP|DD|EAC3|E-AC-3|AC3|AAC|FLAC|TrueHD|PCM|LPCM)"
    r"(?:[.\s]?\d\.\d)?"
)

# Resolutions
_RESOLUTION_PAT = r"(?:480|540|576|720|1080)[pi]|2160p|4[kK]|\d{3,4}x\d{3,4}"


# ---------------------------------------------------------------------------
# Grammar: Fansub  [Group] Title - Episode [metadata][hash].ext
# ---------------------------------------------------------------------------

_FANSUB_GRAMMAR = Grammar(
    r"""
    filename      = bracket ws? title_and_ep brackets? extension?
    bracket       = "[" bracket_body "]"
    bracket_body  = ~"[^\]]+"
    brackets      = (ws? bracket)+
    title_and_ep  = title separator episode_part (separator title_word+)?
                  / title
    title         = title_word (ws title_word)*
    title_word    = ~"[^\[\]\s\-][^\[\]\s]*"
    separator     = ws? "-" ws?
    episode_part  = se_episode / special_ep / bare_episode
    se_episode    = ~"[Ss]\d{1,2}[Ee]\d{1,4}(?:v\d+)?"
    special_ep    = ~"(?:SP|OVA|OAD|ONA)\d*"i
    bare_episode  = ~"\d{1,4}(?:v\d+)?(?:\s*END)?"i
    extension     = ~"\.\w{2,4}$"
    ws            = ~"\s+"
    """
)


class _FansubVisitor(NodeVisitor):
    """Walk a fansub parse tree and build ParsedMedia."""

    def _unwrap(self, val):
        """Recursively unwrap single-element lists from parsimonious."""
        while isinstance(val, list) and len(val) == 1:
            val = val[0]
        return val

    def visit_filename(self, node, visited_children):
        pm = ParsedMedia()
        group_node, _, title_ep, brackets, ext = visited_children

        # First bracket = release group (or metadata)
        group_text = str(self._unwrap(group_node))
        group_words = re.split(r"[\s,]+", group_text)
        meta_count = sum(1 for w in group_words if _is_meta_word(w))
        if meta_count > 0 and meta_count >= len(group_words) // 2:
            if not _is_meta_word(group_words[0]):
                pm.release_group = group_words[0]
                _apply_meta_words(pm, group_words[1:])
            else:
                _apply_meta_words(pm, group_words)
        else:
            pm.release_group = str(group_text)

        title_ep = self._unwrap(title_ep)

        # Title and episode
        if isinstance(title_ep, dict):
            pm.series_name = title_ep.get("title", "")
            if "season" in title_ep:
                pm.season = title_ep["season"]
            if "episode" in title_ep:
                pm.episode = title_ep["episode"]
            if "version" in title_ep:
                pm.version = title_ep["version"]
            if "is_special" in title_ep:
                pm.is_special = title_ep["is_special"]
                pm.special_tag = title_ep.get("special_tag", "")

        # Trailing brackets — flatten any nested lists
        def _flatten(obj):
            if isinstance(obj, list):
                for item in obj:
                    yield from _flatten(item)
            elif isinstance(obj, str) and obj.strip():
                yield obj

        if brackets:
            for content in _flatten(brackets):
                if re.match(r"^[0-9A-Fa-f]{8}$", content):
                    pm.hash_code = content.upper()
                else:
                    _apply_meta_words(pm, re.split(r"[\s,]+", content))

        # Extension
        ext = self._unwrap(ext)
        if isinstance(ext, str) and ext:
            pm.extension = ext.lower()

        # Year in series name
        year_m = re.search(r"\((\d{4})\)", pm.series_name)
        if year_m:
            y = int(year_m.group(1))
            if 1900 <= y <= 2099:
                pm.year = y
                pm.series_name = (
                    pm.series_name[: year_m.start()] + pm.series_name[year_m.end() :]
                ).strip()

        return pm

    def visit_bracket(self, node, visited_children):
        _, body, _ = visited_children
        return body.text if hasattr(body, "text") else str(body)

    def visit_bracket_body(self, node, visited_children):
        return node.text

    def visit_brackets(self, node, visited_children):
        results = []
        for item in visited_children:
            # Each item is [ws?, bracket] — bracket is already a string
            if isinstance(item, list):
                for sub in item:
                    if isinstance(sub, list):
                        for s in sub:
                            if isinstance(s, str) and s.strip():
                                results.append(s)
                    elif isinstance(sub, str) and sub.strip():
                        results.append(sub)
            elif isinstance(item, str) and item.strip():
                results.append(item)
        return results

    def visit_title_and_ep(self, node, visited_children):
        # This is an ordered choice — first alt or second
        result = visited_children[0]
        if isinstance(result, list) and len(result) >= 3:
            title, _, ep_part = result[0], result[1], result[2]
            info = {"title": title}
            if isinstance(ep_part, dict):
                info.update(ep_part)
            return info
        if isinstance(result, str):
            return {"title": result}
        return {"title": node.text}

    def visit_title(self, node, visited_children):
        return node.text.strip()

    def visit_title_word(self, node, visited_children):
        return node.text

    def visit_se_episode(self, node, visited_children):
        m = re.match(r"[Ss](\d+)[Ee](\d+)(?:v(\d+))?", node.text)
        if m:
            result = {"season": int(m.group(1)), "episode": int(m.group(2))}
            if m.group(3):
                result["version"] = int(m.group(3))
            return result
        return {}

    def visit_special_ep(self, node, visited_children):
        m = re.match(r"(SP|OVA|OAD|ONA)(\d*)", node.text, re.IGNORECASE)
        if m:
            result = {
                "is_special": True,
                "special_tag": node.text,
            }
            if m.group(2):
                result["episode"] = int(m.group(2))
            return result
        return {}

    def visit_bare_episode(self, node, visited_children):
        m = re.match(r"(\d+)(?:v(\d+))?", node.text)
        if m:
            num = int(m.group(1))
            if 1900 <= num <= 2099:
                return {}  # Year, not episode
            result = {"episode": num}
            if m.group(2):
                result["version"] = int(m.group(2))
            return result
        return {}

    def visit_episode_part(self, node, visited_children):
        return visited_children[0]

    def visit_extension(self, node, visited_children):
        return node.text

    def visit_separator(self, node, visited_children):
        return None

    def visit_ws(self, node, visited_children):
        return None

    def generic_visit(self, node, visited_children):
        return visited_children or node.text


# ---------------------------------------------------------------------------
# Grammar: Scene  Title.S01E05.metadata.codec-GROUP.ext
# ---------------------------------------------------------------------------

# Build compound token alternation for PEG (longest first)
_COMPOUND_SORTED = sorted(_COMPOUND_TOKENS, key=len, reverse=True)
_COMPOUND_PEG = " / ".join(f'"{t}"' for t in _COMPOUND_SORTED)

_SCENE_GRAMMAR = Grammar(
    r"""
    filename       = title_parts dot episode_marker after_ep
    title_parts    = title_seg (dot title_seg)*
    title_seg      = !episode_marker segment
    episode_marker = ~"[Ss]\d{1,2}[Ee]\d{1,4}(?:v\d+)?"
                   / ~"[Ss]\d{1,2}(?![Ee\d])"
    after_ep       = (dot segment)*
    segment        = compound_token / ~"[^.]+"
    compound_token = """
    + _COMPOUND_PEG
    + r"""
    dot            = "."
    """
)


class _SceneVisitor(NodeVisitor):
    """Walk a scene parse tree and build ParsedMedia."""

    def visit_filename(self, node, visited_children):
        pm = ParsedMedia()
        title_parts, _, ep, after_parts = visited_children

        pm.series_name = " ".join(title_parts)

        # Episode
        ep_text = ep
        m = re.match(r"[Ss](\d+)[Ee](\d+)(?:v(\d+))?", ep_text, re.IGNORECASE)
        if m:
            pm.season = int(m.group(1))
            pm.episode = int(m.group(2))
            if m.group(3):
                pm.version = int(m.group(3))
        else:
            m = re.match(r"[Ss](\d+)", ep_text, re.IGNORECASE)
            if m:
                pm.season = int(m.group(1))

        # After episode: split into ep title + metadata
        ep_title_parts = []
        meta_parts = []
        in_meta = False
        for seg in after_parts:
            if not in_meta and _is_meta_word(seg):
                in_meta = True
            if in_meta:
                meta_parts.append(seg)
            else:
                ep_title_parts.append(seg)

        pm.episode_title = " ".join(ep_title_parts)

        # Trailing group from last meta part
        if meta_parts:
            last = meta_parts[-1]
            dash_m = re.match(r"^(.*)-([A-Za-z][A-Za-z0-9]+)$", last)
            if dash_m:
                meta_parts[-1] = dash_m.group(1)
                pm.release_group = dash_m.group(2)

        _apply_meta_words(pm, meta_parts)

        return pm

    def visit_title_parts(self, node, visited_children):
        first, rest = visited_children
        parts = [first]
        if isinstance(rest, list):
            for item in rest:
                if isinstance(item, list) and len(item) >= 2:
                    parts.append(item[-1])  # [dot, title_seg]
                elif isinstance(item, str):
                    parts.append(item)
        return parts

    def visit_title_seg(self, node, visited_children):
        # !episode_marker segment — the lookahead produces empty, segment is the content
        return node.text

    def visit_episode_marker(self, node, visited_children):
        return node.text

    def visit_after_ep(self, node, visited_children):
        # visited_children = [[None, "1080p"], [None, "BluRay"], ...]
        parts = []
        for pair in visited_children:
            if isinstance(pair, list) and len(pair) >= 2:
                seg = pair[-1]
                if isinstance(seg, str) and seg:
                    parts.append(seg)
        return parts

    def visit_segment(self, node, visited_children):
        return node.text

    def visit_compound_token(self, node, visited_children):
        return node.text

    def visit_dot(self, node, visited_children):
        return None

    def generic_visit(self, node, visited_children):
        # For anonymous sequence nodes (like "(dot segment)"), return the
        # full children list so parents can destructure. Only unwrap for
        # single-child nodes.
        if len(visited_children) == 1:
            return visited_children[0]
        return visited_children or node.text


# ---------------------------------------------------------------------------
# Shared metadata helpers
# ---------------------------------------------------------------------------


def _is_meta_word(word: str) -> bool:
    """Check if a word is a known metadata keyword."""
    lower = word.lower().strip()
    if lower in _VIDEO_CODECS | _AUDIO_CODECS | _SOURCES | _LANGUAGES:
        return True
    if lower in {"480p", "540p", "576p", "720p", "1080p", "1080i", "2160p", "4k"}:
        return True
    if lower == "remux":
        return True
    if re.match(
        r"(?:DTS-HDMA|DTS-HD\s*MA|DTS-HD|DTS|DDP|DD|EAC3|E-AC-3|AC3|AAC|FLAC|TrueHD)"
        r"(?:[.\s]?\d\.\d)?$",
        word,
        re.IGNORECASE,
    ):
        return True
    if "-" in word:
        parts = word.split("-")
        return any(
            p.lower() in _AUDIO_CODECS | _VIDEO_CODECS | _SOURCES for p in parts if p
        )
    return False


def _apply_meta_words(pm: ParsedMedia, words: list[str]) -> None:
    """Classify metadata words and apply to ParsedMedia."""
    for w in words:
        lower = w.lower().strip()
        if not lower:
            continue
        # Resolution
        if lower in {"480p", "540p", "576p", "720p", "1080p", "1080i", "2160p", "4k"}:
            if not pm.resolution:
                pm.resolution = w
        elif re.match(r"^\d{3,4}x\d{3,4}$", w):
            if not pm.resolution:
                pm.resolution = w
        # Video codec
        elif lower in _VIDEO_CODECS:
            if not pm.video_codec:
                pm.video_codec = w
        # Audio codec
        elif lower in _AUDIO_CODECS or re.match(
            _AUDIO_COMPOUND_PAT + "$", w, re.IGNORECASE
        ):
            pm.audio_codecs.append(w)
        # Source
        elif lower in _SOURCES:
            mapped = _SOURCE_TYPE_MAP.get(lower, "")
            if mapped and not pm.source_type:
                pm.source_type = mapped
        # Remux
        elif lower == "remux":
            pm.is_remux = True
            if not pm.source_type:
                pm.source_type = "BD"
        # Dash compounds
        elif "-" in w and not w.startswith("-"):
            parts = w.split("-")
            has_meta = any(
                p.lower() in _AUDIO_CODECS | _VIDEO_CODECS | _SOURCES
                or p.lower() == "remux"
                for p in parts
                if p
            )
            if has_meta:
                for p in parts:
                    if p:
                        _apply_meta_words(pm, [p])
                # Last unclassified part = release group
                last = parts[-1]
                if not _is_meta_word(last) and not pm.release_group:
                    pm.release_group = last


# ---------------------------------------------------------------------------
# Convention detection and dispatch
# ---------------------------------------------------------------------------

_fansub_visitor = _FansubVisitor()
_scene_visitor = _SceneVisitor()


def _strip_ext(text: str) -> tuple[str, str]:
    """Strip file extension, returning (base, extension)."""
    m = re.search(r"\.(\w{2,4})$", text)
    if m:
        return text[: m.start()], m.group(0).lower()
    return text, ""


def detect_convention(text: str) -> str:
    """Detect filename convention. Returns 'fansub', 'scene', 'japanese', or 'bare'."""
    base = re.sub(r"\.\w{2,4}$", "", text)
    if "第" in base and "話" in base and base.startswith("["):
        return "japanese"
    if base.startswith("["):
        return "fansub"
    if "." in base and base.count(".") >= 3 and base.count(".") > base.count(" "):
        return "scene"
    if re.search(r"[Ss]\d+[Ee]\d+", base):
        return "sonarr"
    return "bare"


def parse_component_peg(text: str) -> ParsedMedia:
    """Parse a filename using PEG grammars with convention detection."""
    convention = detect_convention(text)

    if convention == "fansub":
        try:
            tree = _FANSUB_GRAMMAR.parse(text)
            return _fansub_visitor.visit(tree)
        except ParsimoniousParseError:
            pass

    if convention == "scene":
        try:
            base, ext = _strip_ext(text)
            tree = _SCENE_GRAMMAR.parse(base)
            pm = _scene_visitor.visit(tree)
            pm.extension = ext
            return pm
        except ParsimoniousParseError:
            pass

    # Fallback: try fansub then scene
    for grammar, visitor in [
        (_FANSUB_GRAMMAR, _fansub_visitor),
        (_SCENE_GRAMMAR, _scene_visitor),
    ]:
        try:
            tree = grammar.parse(text)
            return visitor.visit(tree)
        except ParsimoniousParseError:
            continue

    # Last resort: bare title
    pm = ParsedMedia()
    m = re.search(r"\.(\w{2,4})$", text)
    if m:
        pm.extension = m.group(0).lower()
        pm.series_name = text[: m.start()].strip()
    else:
        pm.series_name = text
    return pm
