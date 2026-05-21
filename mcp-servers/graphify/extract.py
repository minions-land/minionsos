"""Build the project's atlas.json by shelling out to ``graphify extract``.

Invoked by Noter's periodic wake when shared/ artifacts have changed since
the last Atlas (L3 structural index) rebuild. See
``minions/tools/noter_wait.py`` → ``_maybe_rebuild_atlas``.

The third-party ``graphify`` CLI is unchanged — this wrapper only renames
the MinionsOS-side concept (Corpus Graph → Atlas) and re-routes output to
``branches/shared/atlas/atlas.json``.

Usage (from Noter cron, NOT directly):
    python mcp-servers/graphify/extract.py --port <port>

The script:
  1. Resolves the project workspace from the port + repo root.
  2. Walks branches/shared/{book,notes,ethics,exp} and feeds each
     existing subdir to graphify-extract via a temporary corpus root.
  3. Writes the merged graph.json atomically to
     branches/shared/atlas/atlas.json so a concurrent graphify.serve MCP
     reader gets a clean swap.

Notes:
  * Uses ``.venv/bin/graphify`` from this directory — must be installed
    via ``uv pip install -e .`` first (see README.md).
  * Backend is ``--backend claude-cli`` so extraction routes through the
    host Claude Code CLI (zero $$, requires interactive Claude Code).
  * The whole call is wrapped in subprocess.run with timeout=300; Noter
    gates this script behind its own 5-minute subprocess timeout.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_SHARED_SUBDIRS = ("book", "notes", "ethics", "exp")

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_GRAPHIFY_BIN = _HERE / ".venv" / "bin" / "graphify"


def _project_workspace(port: int) -> Path:
    """Return the project_{port}/ workspace root, raising if missing."""
    ws = _REPO_ROOT / f"project_{port}"
    if not ws.is_dir():
        raise FileNotFoundError(f"Project workspace not found: {ws}")
    return ws


def _stage_corpus(workspace: Path, dst: Path) -> int:
    """Copy each existing branches/shared/<subdir>/ into dst/<subdir>/.

    Returns the number of source files staged. graphify treats *dst* as a
    single corpus root so we can extract the whole shared/ landscape in
    one pass.
    """
    shared = workspace / "branches" / "shared"
    if not shared.is_dir():
        return 0
    total = 0
    for sub in _SHARED_SUBDIRS:
        src = shared / sub
        if not src.is_dir():
            continue
        target = dst / sub
        shutil.copytree(src, target, dirs_exist_ok=True)
        total += sum(1 for _ in target.rglob("*") if _.is_file())
    return total


def _atomic_replace(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def rebuild_atlas(port: int, *, timeout_s: int = 300) -> dict[str, object]:
    """Run graphify extract over branches/shared/ and atomically install atlas.json.

    Returns a dict suitable for embedding in Noter's periodic-wake event:
        {"rebuilt": True, "node_count": N, "edge_count": M, "duration_s": float}
    or {"rebuilt": False, "reason": "..."}.
    """
    if not _GRAPHIFY_BIN.exists():
        return {
            "rebuilt": False,
            "reason": (
                f"{_GRAPHIFY_BIN} missing. "
                "Install via: cd mcp-servers/graphify && "
                "VIRTUAL_ENV=$PWD/.venv uv pip install -e ."
            ),
        }

    workspace = _project_workspace(port)
    target = workspace / "branches" / "shared" / "atlas" / "atlas.json"

    import time

    started = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="mos-graphify-") as staging_str:
        staging = Path(staging_str)
        file_count = _stage_corpus(workspace, staging)
        if file_count == 0:
            return {"rebuilt": False, "reason": "no source files in branches/shared/"}

        cmd = [
            str(_GRAPHIFY_BIN),
            "extract",
            str(staging),
            "--backend",
            "claude-cli",
            "--no-cluster",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=str(staging),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "rebuilt": False,
                "reason": f"graphify extract timed out after {timeout_s}s",
            }
        if result.returncode != 0:
            tail = "\n".join(result.stderr.strip().splitlines()[-20:])
            return {"rebuilt": False, "reason": f"graphify extract failed: {tail}"}

        produced = staging / "graphify-out" / "graph.json"
        if not produced.exists():
            return {
                "rebuilt": False,
                "reason": f"graphify wrote no graph.json under {produced.parent}",
            }

        _atomic_replace(produced, target)

    duration = time.monotonic() - started
    try:
        graph = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"rebuilt": False, "reason": f"unreadable result: {exc}"}

    node_count = len(graph.get("nodes", []))
    edge_count = len(graph.get("links", []))
    return {
        "rebuilt": True,
        "node_count": node_count,
        "edge_count": edge_count,
        "duration_s": round(duration, 2),
        "file_count": file_count,
    }


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Rebuild a MinionsOS project's Atlas (L3).")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    result = rebuild_atlas(args.port, timeout_s=args.timeout)
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0 if result.get("rebuilt") else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
