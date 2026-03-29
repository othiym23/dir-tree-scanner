"""Tests for the dispatcher's argument extraction logic."""

from etp_commands.dispatcher import _extract_target


class TestExtractTarget:
    def test_positional_directory(self):
        directory, db = _extract_target(["/volume1/music"])
        assert directory == "/volume1/music"
        assert db is None

    def test_db_flag(self):
        directory, db = _extract_target(["--db", "/path/to/db"])
        assert directory is None
        assert db == "/path/to/db"

    def test_db_equals(self):
        directory, db = _extract_target(["--db=/path/to/db"])
        assert directory is None
        assert db == "/path/to/db"

    def test_directory_and_db(self):
        directory, db = _extract_target(["/volume1/music", "--db", "music.db"])
        assert directory == "/volume1/music"
        assert db == "music.db"

    def test_root_flag(self):
        directory, db = _extract_target(["-R", "/volume1/music"])
        assert directory == "/volume1/music"
        assert db is None

    def test_flags_before_directory(self):
        directory, db = _extract_target(["--scan", "-v", "/volume1/music"])
        assert directory == "/volume1/music"
        assert db is None

    def test_no_args(self):
        directory, db = _extract_target([])
        assert directory is None
        assert db is None

    def test_only_flags(self):
        directory, db = _extract_target(["--scan", "-v", "--du"])
        assert directory is None
        assert db is None

    def test_db_nickname(self):
        directory, db = _extract_target(["--db", "music"])
        assert directory is None
        assert db == "music"

    def test_exclude_with_value(self):
        directory, db = _extract_target(["-e", "@eaDir", "/volume1/music"])
        assert directory == "/volume1/music"
        assert db is None

    def test_output_flag_skipped(self):
        directory, db = _extract_target(["-o", "out.csv", "/volume1/music"])
        assert directory == "/volume1/music"
        assert db is None

    def test_find_with_root_flag(self):
        """For etp-find, -R provides the directory; the pattern is positional
        but _extract_target picks up -R as the directory for auto-scan."""
        directory, db = _extract_target(["*.mp3", "-R", "/volume1/music"])
        assert directory == "/volume1/music"
        assert db is None
