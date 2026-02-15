"""Tests for catalog-nas.py config loading and resolution."""

from __future__ import annotations

import importlib
import textwrap

# Import the script as a module
catalog = importlib.import_module("catalog-nas")


class TestResolveGlobal:
    def test_plain_values_pass_through(self):
        result = catalog.resolve_global({"a": "hello", "b": "world"})
        assert result == {"a": "hello", "b": "world"}

    def test_env_var_expansion(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "/some/path")
        result = catalog.resolve_global({"dir": "$TEST_VAR/sub"})
        assert result == {"dir": "/some/path/sub"}

    def test_key_interpolation(self):
        result = catalog.resolve_global(
            {
                "base": "/root",
                "sub": "{base}/child",
            }
        )
        assert result == {"base": "/root", "sub": "/root/child"}

    def test_chained_interpolation(self):
        result = catalog.resolve_global(
            {
                "a": "/root",
                "b": "{a}/mid",
                "c": "{b}/leaf",
            }
        )
        assert result == {
            "a": "/root",
            "b": "/root/mid",
            "c": "/root/mid/leaf",
        }

    def test_unresolvable_key_left_as_is(self):
        result = catalog.resolve_global({"x": "{unknown}/path"})
        assert result == {"x": "{unknown}/path"}

    def test_env_var_and_interpolation_combined(self, monkeypatch):
        monkeypatch.setenv("HOME", "/home/user")
        result = catalog.resolve_global(
            {
                "base": "$HOME/data",
                "sub": "{base}/trees",
            }
        )
        assert result == {
            "base": "/home/user/data",
            "sub": "/home/user/data/trees",
        }


class TestLoadConfig:
    def test_loads_toml_with_scans(self, tmp_path):
        config = tmp_path / "test.toml"
        config.write_text(
            textwrap.dedent("""\
            [global]
            scanner = "/usr/bin/fsscan"
            base = "/data"

            [scan.mydir]
            enabled = true
            mode = "used"
            disk = "/tmp/test"
            desc = "test directory"
            header = "test header"
        """)
        )

        cfg = catalog.load_config(config)
        assert cfg["global"]["scanner"] == "/usr/bin/fsscan"
        assert cfg["global"]["base"] == "/data"
        assert "mydir" in cfg["scans"]
        assert cfg["scans"]["mydir"]["mode"] == "used"
        assert cfg["scans"]["mydir"]["enabled"] is True

    def test_empty_config(self, tmp_path):
        config = tmp_path / "empty.toml"
        config.write_text("")

        cfg = catalog.load_config(config)
        assert cfg["global"] == {}
        assert cfg["scans"] == {}

    def test_global_interpolation_applied(self, tmp_path):
        config = tmp_path / "interp.toml"
        config.write_text(
            textwrap.dedent("""\
            [global]
            base = "/vol"
            trees = "{base}/trees"
        """)
        )

        cfg = catalog.load_config(config)
        assert cfg["global"]["trees"] == "/vol/trees"


class TestTimer:
    def test_str_format(self):
        with catalog.Timer() as t:
            pass
        s = str(t)
        assert s.startswith("real ")
        assert "user " in s
        assert "sys " in s

    def test_elapsed_is_positive(self):
        import time

        with catalog.Timer() as t:
            time.sleep(0.01)
        assert t.elapsed >= 0.01


class TestCLIDryRun:
    def test_dry_run_prints_plan(self, tmp_path, capsys):
        config = tmp_path / "test.toml"
        config.write_text(
            textwrap.dedent("""\
            [global]
            scanner = "/usr/bin/fsscan"
            trees_path = "/tmp/trees"
            csvs_path = "/tmp/csv"
            state_path = "/tmp/state"

            [scan.mytest]
            enabled = true
            mode = "df"
            disk = "/tmp/testdisk"
            desc = "test scan"
            header = "test header"
        """)
        )

        rc = catalog.main(["--dry-run", str(config)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Dry run" in out
        assert "[mytest]" in out
        assert "mode=df" in out

    def test_unknown_scan_name_errors(self, tmp_path, capsys):
        config = tmp_path / "test.toml"
        config.write_text(
            textwrap.dedent("""\
            [global]
            scanner = "/usr/bin/fsscan"

            [scan.real]
            mode = "used"
            disk = "/tmp"
            desc = "test"
            header = "test"
        """)
        )

        rc = catalog.main(["--scan", "bogus", str(config)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "bogus" in err

    def test_no_enabled_scans(self, tmp_path, capsys):
        config = tmp_path / "test.toml"
        config.write_text(
            textwrap.dedent("""\
            [global]
            scanner = "/usr/bin/fsscan"

            [scan.disabled]
            enabled = false
            mode = "used"
            disk = "/tmp"
            desc = "test"
            header = "test"
        """)
        )

        rc = catalog.main([str(config)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "No scans to run" in out

    def test_missing_config_errors(self, capsys):
        rc = catalog.main(["/nonexistent/config.toml"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "not found" in err
