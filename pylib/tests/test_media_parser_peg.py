"""Tests for the PEG-based media filename parser."""

from __future__ import annotations

import pytest

from etp_lib import media_parser_peg as peg


class TestPEGFansub:
    """Fansub convention via PEG grammar."""

    def test_basic(self):
        pm = peg.parse_component_peg(
            "[Cyan] Champignon no Majo - 08 [WEB 1080p x265][AAC][D98B31F3].mkv"
        )
        assert pm.release_group == "Cyan"
        assert pm.series_name == "Champignon no Majo"
        assert pm.episode == 8
        assert pm.hash_code == "D98B31F3"
        assert pm.source_type == "Web"
        assert pm.resolution == "1080p"
        assert pm.video_codec == "x265"

    def test_erai_raws(self):
        pm = peg.parse_component_peg(
            "[Erai-raws] Champignon no Majo - 11 "
            "[1080p CR WEB-DL AVC AAC][MultiSub][0A021911].mkv"
        )
        assert pm.release_group == "Erai-raws"
        assert pm.series_name == "Champignon no Majo"
        assert pm.episode == 11
        assert pm.hash_code == "0A021911"


class TestPEGScene:
    """Scene convention via PEG grammar."""

    def test_basic(self):
        pm = peg.parse_component_peg("Show.S01E05.1080p.BluRay.x265-GROUP.mkv")
        assert pm.series_name == "Show"
        assert pm.season == 1
        assert pm.episode == 5
        assert pm.release_group == "GROUP"
        assert pm.source_type == "BD"
        assert pm.resolution == "1080p"
        assert pm.video_codec == "x265"

    def test_s_only(self):
        pm = peg.parse_component_peg(
            "Golden.Kamuy.S01.1080p.BluRay.Remux.AVC-Hinna.mkv"
        )
        assert pm.series_name == "Golden Kamuy"
        assert pm.season == 1
        assert pm.source_type == "BD"


class TestPEGConventionDetection:
    def test_fansub(self):
        assert peg.detect_convention("[Group] Title - 01.mkv") == "fansub"

    def test_scene(self):
        assert (
            peg.detect_convention("Title.S01E05.1080p.BluRay.x265-GROUP.mkv") == "scene"
        )

    def test_bare(self):
        assert peg.detect_convention("Movie (2005).mkv") == "bare"


class TestPEGNeverCrash:
    """PEG parser should never raise on any input."""

    @pytest.mark.parametrize(
        "input",
        [
            "",
            ".mkv",
            "[][][]",
            ".....",
            "-----",
            "just a title.mkv",
            "[Group] Title.mkv",
            "A" * 500 + ".mkv",
        ],
    )
    def test_various_inputs(self, input):
        pm = peg.parse_component_peg(input)
        assert pm is not None
