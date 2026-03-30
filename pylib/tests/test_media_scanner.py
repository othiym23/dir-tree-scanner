"""Tests for the position-based token scanner.

Validates that scan_words and scan_dot_segments produce correct typed
tokens from the parsy primitives, handling compound tokens and dash
compounds that the regex-based approach struggles with.
"""

from __future__ import annotations

import pytest

from etp_lib.media_scanner import scan_words, scan_dot_segments, _try_recognize
from etp_lib.media_parser import TokenKind


# ===================================================================
# scan_words: space/comma-separated content
# ===================================================================


class TestScanWords:
    """Test word-level scanning with parsy recognizers."""

    def test_resolution(self):
        tokens = scan_words("1080p")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.RESOLUTION
        assert tokens[0].text == "1080p"

    def test_video_codec(self):
        tokens = scan_words("HEVC")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.VIDEO_CODEC

    def test_audio_codec_simple(self):
        tokens = scan_words("FLAC")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.AUDIO_CODEC

    def test_audio_codec_compound(self):
        tokens = scan_words("AAC2.0")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.AUDIO_CODEC
        assert tokens[0].text == "AAC2.0"

    def test_dts_hdma(self):
        tokens = scan_words("DTS-HDMA")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.AUDIO_CODEC
        assert tokens[0].text == "DTS-HDMA"

    def test_source(self):
        tokens = scan_words("BluRay")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.SOURCE

    def test_remux(self):
        tokens = scan_words("REMUX")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.REMUX

    def test_episode_se(self):
        tokens = scan_words("S01E05")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.EPISODE
        assert tokens[0].season == 1
        assert tokens[0].episode == 5

    def test_episode_se_version(self):
        tokens = scan_words("S01E01v2")
        assert len(tokens) == 1
        assert tokens[0].version == 2

    def test_episode_bare(self):
        tokens = scan_words("08")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.EPISODE
        assert tokens[0].episode == 8

    def test_year_not_episode(self):
        tokens = scan_words("2019")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.YEAR
        assert tokens[0].year == 2019

    def test_crc32(self):
        tokens = scan_words("D98B31F3")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.CRC32

    def test_unrecognized_text(self):
        tokens = scan_words("Champignon")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.TEXT
        assert tokens[0].text == "Champignon"

    def test_mixed_content(self):
        """Bracket content like 'WEB 1080p x265' should produce typed tokens."""
        tokens = scan_words("WEB 1080p x265")
        kinds = [t.kind for t in tokens]
        assert TokenKind.SOURCE in kinds
        assert TokenKind.RESOLUTION in kinds
        assert TokenKind.VIDEO_CODEC in kinds

    def test_bracket_audio_metadata(self):
        """[LPCM 2.0 + DTS-HDMA 2.1] content should recognize audio codecs."""
        tokens = scan_words("LPCM 2.0 + DTS-HDMA 2.1")
        audio = [t for t in tokens if t.kind == TokenKind.AUDIO_CODEC]
        assert len(audio) >= 1
        # Multi-word scanner may match "LPCM 2.0" as a compound audio codec
        texts = [t.text for t in audio]
        assert any("LPCM" in t for t in texts)

    def test_dash_compound_remux_group(self):
        """REMUX-FraMeSToR should split into REMUX + unknown FraMeSToR."""
        tokens = scan_words("REMUX-FraMeSToR")
        kinds = [t.kind for t in tokens]
        assert TokenKind.REMUX in kinds
        texts = [t.text for t in tokens]
        assert "FraMeSToR" in texts

    def test_sonarr_bracket_content(self):
        """Sonarr-style [Group source,res,...] bracket content."""
        tokens = scan_words("Hinna Bluray-1080p Remux,8bit,AVC,FLAC")
        # Hinna = text (release group), rest = metadata
        assert tokens[0].kind == TokenKind.TEXT
        assert tokens[0].text == "Hinna"

    def test_bonus_ncop(self):
        tokens = scan_words("NCOP")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.BONUS

    def test_bonus_nc_ed1(self):
        tokens = scan_words("NC ED1")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.BONUS

    def test_japanese_episode(self):
        tokens = scan_words("第01話")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.EPISODE
        assert tokens[0].episode == 1

    def test_special_ova(self):
        tokens = scan_words("OVA2")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.EPISODE

    def test_language(self):
        tokens = scan_words("jpn")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.LANGUAGE


# ===================================================================
# scan_dot_segments: scene-style dot-separated content
# ===================================================================


class TestScanDotSegments:
    """Test dot-separated scene scanning with compound token handling."""

    def test_simple_scene(self):
        tokens = scan_dot_segments("Show.S01E05.1080p.BluRay.x265-GROUP")
        texts = [t.text for t in tokens]
        kinds = [t.kind for t in tokens]
        assert "Show" in texts
        assert TokenKind.EPISODE in kinds
        assert TokenKind.RESOLUTION in kinds
        assert TokenKind.SOURCE in kinds

    def test_compound_h264(self):
        """H.264 should be recognized as a single video codec token."""
        tokens = scan_dot_segments("Show.S01E05.1080p.H.264-VARYG")
        video = [t for t in tokens if t.kind == TokenKind.VIDEO_CODEC]
        assert len(video) == 1
        assert video[0].text == "H.264"

    def test_compound_h264_with_trailing_group(self):
        """H.264-VARYG should produce H.264 (codec) + VARYG (group)."""
        tokens = scan_dot_segments("Show.S01E05.H.264-VARYG")
        groups = [t for t in tokens if t.kind == TokenKind.RELEASE_GROUP]
        assert len(groups) == 1
        assert groups[0].text == "VARYG"

    def test_compound_aac20(self):
        """AAC2.0 should be recognized as a single audio codec token."""
        tokens = scan_dot_segments("Show.S01E05.AAC2.0.x265")
        audio = [t for t in tokens if t.kind == TokenKind.AUDIO_CODEC]
        assert len(audio) == 1
        assert audio[0].text == "AAC2.0"

    def test_scene_trailing_group(self):
        """x265-GROUP should split into codec + release group."""
        tokens = scan_dot_segments("Show.S01E05.1080p.x265-GROUP")
        groups = [t for t in tokens if t.kind == TokenKind.RELEASE_GROUP]
        assert len(groups) == 1
        assert groups[0].text == "GROUP"

    def test_full_scene_filename(self):
        """Full scene filename with all metadata types."""
        tokens = scan_dot_segments(
            "You.and.I.Are.Polar.Opposites.S01E01.You.My.Polar.Opposite"
            ".1080p.CR.WEB-DL.DUAL.AAC2.0.H.264-VARYG"
        )
        kinds = {t.kind for t in tokens}
        assert TokenKind.EPISODE in kinds
        assert TokenKind.RESOLUTION in kinds
        assert TokenKind.AUDIO_CODEC in kinds
        assert TokenKind.VIDEO_CODEC in kinds
        assert TokenKind.RELEASE_GROUP in kinds

        # Verify compound tokens were recognized
        video = [t for t in tokens if t.kind == TokenKind.VIDEO_CODEC]
        assert video[0].text == "H.264"
        audio = [t for t in tokens if t.kind == TokenKind.AUDIO_CODEC]
        assert audio[0].text == "AAC2.0"

    def test_season_only(self):
        """S01 without E should be recognized as season."""
        tokens = scan_dot_segments("Golden.Kamuy.S01.1080p.BluRay")
        seasons = [t for t in tokens if t.kind == TokenKind.SEASON]
        assert len(seasons) == 1
        assert seasons[0].season == 1

    def test_unrecognized_words_are_dot_text(self):
        """Words that don't match any recognizer stay as DOT_TEXT."""
        tokens = scan_dot_segments("You.and.I.Are.Polar.Opposites")
        assert all(t.kind == TokenKind.DOT_TEXT for t in tokens)
        assert [t.text for t in tokens] == [
            "You",
            "and",
            "I",
            "Are",
            "Polar",
            "Opposites",
        ]


# ===================================================================
# _try_recognize: individual word recognition
# ===================================================================


class TestTryRecognize:
    """Test individual word recognition."""

    @pytest.mark.parametrize(
        "word,expected_kind",
        [
            ("1080p", TokenKind.RESOLUTION),
            ("HEVC", TokenKind.VIDEO_CODEC),
            ("x265", TokenKind.VIDEO_CODEC),
            ("FLAC", TokenKind.AUDIO_CODEC),
            ("AAC2.0", TokenKind.AUDIO_CODEC),
            ("DTS-HDMA", TokenKind.AUDIO_CODEC),
            ("BD", TokenKind.SOURCE),
            ("BluRay", TokenKind.SOURCE),
            ("WEB-DL", TokenKind.SOURCE),
            ("REMUX", TokenKind.REMUX),
            ("S01E05", TokenKind.EPISODE),
            ("OVA", TokenKind.EPISODE),
            ("v2", TokenKind.VERSION),
            ("2019", TokenKind.YEAR),
            ("D98B31F3", TokenKind.CRC32),
            ("jpn", TokenKind.LANGUAGE),
            ("NCOP", TokenKind.BONUS),
        ],
    )
    def test_recognized(self, word, expected_kind):
        token = _try_recognize(word)
        assert token is not None, f"{word!r} was not recognized"
        assert token.kind == expected_kind, (
            f"{word!r}: expected {expected_kind.name}, got {token.kind.name}"
        )

    @pytest.mark.parametrize(
        "word",
        ["Champignon", "the", "of", "Hello", "FraMeSToR", "VARYG"],
    )
    def test_not_recognized(self, word):
        assert _try_recognize(word) is None
