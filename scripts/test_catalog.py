"""Tests for catalog-nas.py config loading and resolution."""

from __future__ import annotations

import importlib
import textwrap
from unittest.mock import patch

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


def _make_scan_cfg(mode, disk="/vol/data"):
    return {
        "mode": mode,
        "disk": disk,
        "desc": "test-scan",
        "header": "Test Header",
    }


def _make_global_cfg(tmp_path):
    trees = tmp_path / "trees"
    state = tmp_path / "state"
    trees.mkdir()
    state.mkdir()
    return {
        "trees_path": str(trees),
        "state_path": str(state),
        "tree": "/usr/bin/cached-tree",
    }


def _fake_run_cmd(responses):
    """Return a mock for run_cmd that returns responses in order."""
    calls = []
    it = iter(responses)

    def mock(args, *, capture=False, verbose=False, env_extra=None):
        calls.append(list(args))
        return next(it) if capture else None

    return mock, calls


class TestGenerateTree:
    def test_mode_used(self, tmp_path):
        global_cfg = _make_global_cfg(tmp_path)
        scan_cfg = _make_scan_cfg("used")
        mock, calls = _fake_run_cmd(["tree output\n", "42\t/vol/data\n"])

        with patch.object(catalog, "run_cmd", mock):
            catalog.generate_tree("mytest", scan_cfg, global_cfg)

        tree_file = tmp_path / "trees" / "test-scan.tree"
        content = tree_file.read_text()
        assert content.startswith("Test Header\n\n")
        assert "tree output" in content
        assert "42\t/vol/data" in content

        # tree command + du -sm
        assert len(calls) == 2
        assert calls[0][0] == "/usr/bin/cached-tree"
        assert calls[1] == ["du", "-sm", "/vol/data"]

    def test_mode_df(self, tmp_path):
        global_cfg = _make_global_cfg(tmp_path)
        scan_cfg = _make_scan_cfg("df")
        mock, calls = _fake_run_cmd(["tree output\n", "Filesystem Size Used\n"])

        with patch.object(catalog, "run_cmd", mock):
            catalog.generate_tree("mytest", scan_cfg, global_cfg)

        tree_file = tmp_path / "trees" / "test-scan.tree"
        content = tree_file.read_text()
        assert "tree output" in content
        assert "Filesystem Size Used" in content

        assert len(calls) == 2
        assert calls[1] == ["df", "-PH", "/vol/data"]

    def test_mode_subs(self, tmp_path):
        global_cfg = _make_global_cfg(tmp_path)
        disk = tmp_path / "disk"
        disk.mkdir()
        (disk / "alpha").mkdir()
        (disk / "beta").mkdir()
        (disk / "@eaDir").mkdir()  # should be excluded from du
        scan_cfg = _make_scan_cfg("subs", disk=str(disk))

        mock, calls = _fake_run_cmd(
            [
                "tree output\n",
                "Filesystem Size Used\n",
                "10\talpha\n20\tbeta\n",
            ]
        )

        with patch.object(catalog, "run_cmd", mock):
            catalog.generate_tree("mytest", scan_cfg, global_cfg)

        tree_file = tmp_path / "trees" / "test-scan.tree"
        content = tree_file.read_text()
        assert "tree output" in content
        assert "Filesystem Size Used" in content
        assert "10\talpha" in content

        # tree + df + du
        assert len(calls) == 3
        assert calls[1] == ["df", "-PH", str(disk)]
        # du should include alpha and beta but not @eaDir
        du_args = calls[2]
        assert du_args[0:2] == ["du", "-sm"]
        du_dirs = du_args[2:]
        assert any("alpha" in d for d in du_dirs)
        assert any("beta" in d for d in du_dirs)
        assert not any("@eaDir" in d for d in du_dirs)

    def test_mode_subs_no_subdirs(self, tmp_path):
        global_cfg = _make_global_cfg(tmp_path)
        disk = tmp_path / "empty-disk"
        disk.mkdir()
        scan_cfg = _make_scan_cfg("subs", disk=str(disk))

        mock, calls = _fake_run_cmd(["tree output\n", "Filesystem Size Used\n"])

        with patch.object(catalog, "run_cmd", mock):
            catalog.generate_tree("mytest", scan_cfg, global_cfg)

        # Only tree + df, no du call when no subdirs
        assert len(calls) == 2

    def test_unknown_mode_raises(self, tmp_path):
        import pytest

        global_cfg = _make_global_cfg(tmp_path)
        scan_cfg = _make_scan_cfg("bogus")
        mock, _ = _fake_run_cmd(["tree output\n"])

        with patch.object(catalog, "run_cmd", mock):
            with pytest.raises(TypeError):
                catalog.generate_tree("mytest", scan_cfg, global_cfg)
