"""Fuzz tests for the parsy-based parser using Hypothesis.

Reuses the filename strategies from test_media_parser_fuzz and runs them
against parse_component_parsy. Also does parity comparison against the
existing parser on structured filenames.
"""

from __future__ import annotations

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from etp_lib import media_parser as mp
from etp_lib import media_parser_parsy as pp
from etp_lib.media_parser import ParsedMedia

import importlib
import sys
from pathlib import Path

# Import strategies from sibling test module
_test_dir = str(Path(__file__).parent)
if _test_dir not in sys.path:
    sys.path.insert(0, _test_dir)
fuzz_mod = importlib.import_module("test_media_parser_fuzz")

_any_filename = fuzz_mod._any_filename
_bare_episode_filename = fuzz_mod._bare_episode_filename
_fansub_filename = fuzz_mod._fansub_filename
_scene_filename = fuzz_mod._scene_filename
_sonarr_filename = fuzz_mod._sonarr_filename


# ===================================================================
# Never-crash invariants
# ===================================================================


class TestParsyNeverCrash:
    """parse_component_parsy should never raise on any input."""

    @given(text=st.text(min_size=0, max_size=500))
    @settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
    def test_arbitrary_text(self, text):
        result = pp.parse_component_parsy(text)
        assert isinstance(result, ParsedMedia)

    @given(
        text=st.binary(min_size=0, max_size=200).map(
            lambda b: b.decode("utf-8", errors="replace")
        )
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_decoded_bytes(self, text):
        result = pp.parse_component_parsy(text)
        assert isinstance(result, ParsedMedia)

    @given(filename=_any_filename)
    @settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
    def test_structured_filenames(self, filename):
        result = pp.parse_component_parsy(filename)
        assert isinstance(result, ParsedMedia)


# ===================================================================
# Idempotency
# ===================================================================


class TestParsyIdempotency:
    """Parsing the same input twice should produce identical results."""

    @given(filename=_any_filename)
    @settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
    def test_idempotent(self, filename):
        a = pp.parse_component_parsy(filename)
        b = pp.parse_component_parsy(filename)
        assert a.series_name == b.series_name
        assert a.episode == b.episode
        assert a.season == b.season
        assert a.source_type == b.source_type
        assert a.resolution == b.resolution
        assert a.release_group == b.release_group


# ===================================================================
# Parity comparison: old parser vs new parser on structured filenames
# ===================================================================

# Fields where the new parser is expected to match the old parser.
# We compare only fields where the old parser produces a non-empty value.
_PARITY_FIELDS = [
    "episode",
    "season",
    "series_name",
    "source_type",
    "is_remux",
    "resolution",
    "video_codec",
    "hash_code",
    "year",
]


def _has_significant_value(val: object) -> bool:
    return val not in ("", None, False, 0, [])


class TestParsyParityFuzz:
    """Compare old and new parser on generated filenames."""

    @given(filename=_fansub_filename())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_fansub_episode_parity(self, filename):
        old = mp.parse_component(filename)
        new = pp.parse_component_parsy(filename)
        if old.episode is not None:
            assert new.episode == old.episode, (
                f"episode: old={old.episode}, new={new.episode} for {filename!r}"
            )

    @given(filename=_fansub_filename())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_fansub_series_parity(self, filename):
        old = mp.parse_component(filename)
        new = pp.parse_component_parsy(filename)
        if old.series_name:
            # Skip cases where old parser fails to extract episode and
            # includes it in series name (e.g. "Title - 00" → old treats
            # 00 as part of title, new correctly extracts as episode 0)
            if new.episode is not None and old.episode is None:
                return
            assert new.series_name == old.series_name, (
                f"series: old={old.series_name!r}, new={new.series_name!r} "
                f"for {filename!r}"
            )

    @given(filename=_scene_filename())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_scene_episode_parity(self, filename):
        old = mp.parse_component(filename)
        new = pp.parse_component_parsy(filename)
        if old.episode is not None:
            assert new.episode == old.episode, (
                f"episode: old={old.episode}, new={new.episode} for {filename!r}"
            )

    @given(filename=_scene_filename())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_scene_season_parity(self, filename):
        old = mp.parse_component(filename)
        new = pp.parse_component_parsy(filename)
        if old.season is not None:
            assert new.season == old.season, (
                f"season: old={old.season}, new={new.season} for {filename!r}"
            )

    @given(filename=_scene_filename())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_scene_group_parity(self, filename):
        old = mp.parse_component(filename)
        new = pp.parse_component_parsy(filename)
        if old.release_group:
            assert new.release_group == old.release_group, (
                f"group: old={old.release_group!r}, new={new.release_group!r} "
                f"for {filename!r}"
            )

    @given(filename=_sonarr_filename())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_sonarr_episode_parity(self, filename):
        old = mp.parse_component(filename)
        new = pp.parse_component_parsy(filename)
        if old.episode is not None:
            assert new.episode == old.episode, (
                f"episode: old={old.episode}, new={new.episode} for {filename!r}"
            )

    @given(filename=_sonarr_filename())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_sonarr_season_parity(self, filename):
        old = mp.parse_component(filename)
        new = pp.parse_component_parsy(filename)
        if old.season is not None:
            assert new.season == old.season, (
                f"season: old={old.season}, new={new.season} for {filename!r}"
            )

    @given(filename=_bare_episode_filename())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_bare_episode_parity(self, filename):
        old = mp.parse_component(filename)
        new = pp.parse_component_parsy(filename)
        if old.episode is not None:
            assert new.episode == old.episode, (
                f"episode: old={old.episode}, new={new.episode} for {filename!r}"
            )
