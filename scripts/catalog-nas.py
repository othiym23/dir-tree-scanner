#!/usr/bin/env python3
"""Incremental filesystem catalog builder driven by TOML config.

Orchestrates fsscan across multiple directory trees, generating tree files
and CSV metadata indexes. Replaces catalog-nas.sh with a config-driven
approach.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# ---------------------------------------------------------------------------
# TOML loading — prefer stdlib tomllib (3.11+), fall back to vendored tomli
# ---------------------------------------------------------------------------

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:
    _vendor_dir = str(Path(__file__).resolve().parent / "_vendor")
    if _vendor_dir not in sys.path:
        sys.path.insert(0, _vendor_dir)
    import tomli as tomllib  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


def resolve_global(global_cfg: Dict[str, str]) -> Dict[str, str]:
    """Expand env vars and resolve {key} interpolation in global paths.

    Keys are processed in definition order so that later values can
    reference earlier ones (e.g. trees_path references home_base).
    """
    resolved: Dict[str, str] = {}
    for key, value in global_cfg.items():
        # First expand $ENV_VAR / ${ENV_VAR}
        value = os.path.expandvars(value)
        # Then resolve {other_key} references to already-resolved values
        value = re.sub(
            r"\{(\w+)\}",
            lambda m: resolved.get(m.group(1), m.group(0)),
            value,
        )
        resolved[key] = value
    return resolved


def load_config(path: Path) -> Dict[str, Any]:
    """Load and resolve a catalog TOML config file."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    cfg: Dict[str, Any] = {}
    cfg["global"] = resolve_global(raw.get("global", {}))
    cfg["scans"] = raw.get("scan", {})
    return cfg


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------


class Timer:
    """Context manager that captures wall-clock and child-process CPU time."""

    def __enter__(self) -> Timer:
        self.wall = time.monotonic()
        self.times = os.times()
        self.elapsed = 0.0
        self.user = 0.0
        self.sys = 0.0
        return self

    def __exit__(self, *_exc: Any) -> bool:
        wall_end = time.monotonic()
        times_end = os.times()
        self.elapsed = wall_end - self.wall
        self.user = times_end.children_user - self.times.children_user
        self.sys = times_end.children_system - self.times.children_system
        return False

    def __str__(self) -> str:
        return f"real {self.elapsed:.1f}s  user {self.user:.1f}s  sys {self.sys:.1f}s"


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------


def run_cmd(
    args: Sequence[str],
    *,
    capture: bool = False,
    env_extra: Optional[Dict[str, str]] = None,
    verbose: bool = False,
) -> Optional[str]:
    """Run a command with QUOTING_STYLE=c in the environment.

    Returns captured stdout when capture=True, otherwise None.
    """
    env = os.environ.copy()
    env["QUOTING_STYLE"] = "c"
    if env_extra:
        env.update(env_extra)

    if verbose:
        print(f"  $ {' '.join(args)}", flush=True)

    result = subprocess.run(
        args,
        check=True,
        capture_output=capture,
        text=capture,
        env=env,
    )
    if capture:
        return result.stdout
    return None


# ---------------------------------------------------------------------------
# Tree generators
# ---------------------------------------------------------------------------


VALID_MODES = {"used", "df", "subs"}


def generate_tree(
    name: str,
    scan_cfg: Dict[str, Any],
    global_cfg: Dict[str, str],
    *,
    verbose: bool = False,
) -> None:
    """Generate a tree file for a scan entry.

    Derives mode, tree/state file paths, header, and disk from scan_cfg
    and global_cfg. Mode controls the summary commands appended after
    the tree output:
      - 'used': du -sm on disk
      - 'df':   df -PH on disk
      - 'subs': df -PH on disk + du -sm per subdirectory
    """
    disk = scan_cfg["disk"]
    header = scan_cfg["header"]
    mode = scan_cfg["mode"]
    desc = scan_cfg["desc"]

    tree_bin = global_cfg.get("tree", "tree")
    tree_file = Path(global_cfg["trees_path"]) / f"{desc}.tree"
    state_file = Path(global_cfg["state_path"]) / f"{desc}.state"

    # Shared: run cached-tree
    cmd = [tree_bin, "-s", str(state_file), "-I", "@eaDir", "-N", disk]
    if verbose:
        cmd.append("-v")

    tree_out = run_cmd(cmd, capture=True, verbose=verbose)

    suffix_parts: List[str] = []
    if mode == "used":
        suffix_parts.append(
            run_cmd(["du", "-sm", disk], capture=True, verbose=verbose) or ""
        )
    elif mode == "df" or mode == "subs":
        suffix_parts.append(
            run_cmd(["df", "-PH", disk], capture=True, verbose=verbose) or ""
        )
        if mode == "subs":
            # Enumerate subdirectories explicitly instead of shell glob
            disk_path = Path(disk)
            subdirs = sorted(
                str(p) for p in disk_path.iterdir() if p.is_dir() and p.name != "@eaDir"
            )
            if subdirs:
                suffix_parts.append(
                    run_cmd(["du", "-sm"] + subdirs, capture=True, verbose=verbose)
                    or ""
                )
    else:
        print(f"error: unknown mode '{mode}' for scan '{name}'", file=sys.stderr)
        raise TypeError()

    with open(tree_file, "w", encoding="utf-8") as f:
        f.write(header + "\n\n")
        f.write(tree_out or "")
        for part in suffix_parts:
            f.write("\n")
            f.write(part)


# ---------------------------------------------------------------------------
# Scan runner
# ---------------------------------------------------------------------------


def run_scan(
    name: str,
    scan_cfg: Dict[str, Any],
    global_cfg: Dict[str, str],
    *,
    verbose: bool = False,
) -> bool:
    disk = scan_cfg["disk"]
    desc = scan_cfg["desc"]
    mode = scan_cfg["mode"]

    if not Path(disk).exists():
        print(f"warning: {disk} does not exist, skipping", file=sys.stderr)
        return False

    if mode not in VALID_MODES:
        print(f"error: unknown mode '{mode}' for scan '{name}'", file=sys.stderr)
        return False

    csv_file = Path(global_cfg["csvs_path"]) / f"{desc}.csv"
    state_file = Path(global_cfg["state_path"]) / f"{desc}.state"

    print(f"\n# cataloging {name}: {disk}")

    ok = True
    with Timer() as total:
        with Timer() as tree_t:
            try:
                generate_tree(name, scan_cfg, global_cfg, verbose=verbose)
            except subprocess.CalledProcessError as exc:
                print(
                    f"warning: {exc.cmd} failed (code {exc.returncode}): {exc.stderr or ''}",
                    file=sys.stderr,
                )
                return False
        print(f"# tree: {tree_t}")

        cmd = [global_cfg["scanner"], disk, "-s", str(state_file), "-o", str(csv_file)]
        if verbose:
            cmd.append("-v")

        with Timer() as scan_t:
            try:
                run_cmd(cmd, verbose=verbose)
            except subprocess.CalledProcessError as exc:
                print(
                    f"warning: fsscan failed (code {exc.returncode})",
                    file=sys.stderr,
                )
                ok = False
        print(f"# scan: {scan_t}")

    print(f"# {name} TOTAL: {total}")
    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Catalog filesystem trees using fsscan and tree/du/df.",
    )
    parser.add_argument(
        "config",
        nargs="?",
        default=None,
        help="Path to catalog TOML config (default: catalog.toml next to script)",
    )
    parser.add_argument(
        "--scan",
        action="append",
        dest="scans",
        metavar="NAME",
        help="Run only named scan(s); repeatable",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan without executing",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output; passes -v to fsscan",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve config path
    if args.config is not None:
        config_path = Path(args.config)
    else:
        config_path = Path(__file__).resolve().parent / "catalog.toml"

    if not config_path.exists():
        print(f"error: config file not found: {config_path}", file=sys.stderr)
        return 1

    cfg = load_config(config_path)
    global_cfg = cfg["global"]
    scans = cfg["scans"]

    # Filter to requested scans
    if args.scans:
        unknown = set(args.scans) - set(scans.keys())
        if unknown:
            print(
                f"error: unknown scan(s): {', '.join(sorted(unknown))}",
                file=sys.stderr,
            )
            return 1
        scans = {k: v for k, v in scans.items() if k in args.scans}

    # Filter to enabled scans
    scans = {k: v for k, v in scans.items() if v.get("enabled", True)}

    if not scans:
        print("No scans to run.")
        return 0

    if args.dry_run:
        print("Dry run — would execute the following scans:\n")
        print(f"  scanner:    {global_cfg.get('scanner', '(not set)')}")
        print(f"  tree:       {global_cfg.get('tree', '(not set)')}")
        print(f"  trees_path: {global_cfg.get('trees_path', '(not set)')}")
        print(f"  csvs_path:  {global_cfg.get('csvs_path', '(not set)')}")
        print(f"  state_path: {global_cfg.get('state_path', '(not set)')}")
        print()
        for name, scan_cfg in scans.items():
            mode = scan_cfg.get("mode", "used")
            disk = scan_cfg.get("disk", "(not set)")
            desc = scan_cfg.get("desc", name)
            print(f"  [{name}] mode={mode} disk={disk}")
            print(f"    desc: {desc}")
        return 0

    # ensure necessary directories exist
    Path(global_cfg["trees_path"]).mkdir(parents=True, exist_ok=True)
    Path(global_cfg["csvs_path"]).mkdir(parents=True, exist_ok=True)
    Path(global_cfg["state_path"]).mkdir(parents=True, exist_ok=True)

    # Run scans
    failed: List[str] = []
    for name, scan_cfg in scans.items():
        try:
            ok = run_scan(name, scan_cfg, global_cfg, verbose=args.verbose)
            if not ok:
                failed.append(name)
        except subprocess.CalledProcessError as exc:
            print(f"\nerror: scan '{name}' failed: {exc}", file=sys.stderr)
            failed.append(name)
        except Exception as exc:
            print(f"\nerror: scan '{name}': {exc}", file=sys.stderr)
            failed.append(name)

    if failed:
        print(f"\n{len(failed)} scan(s) failed: {', '.join(failed)}")
        return 1

    print("\nAll scans completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
