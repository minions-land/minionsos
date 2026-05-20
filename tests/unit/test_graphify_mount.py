"""Tests for the Atlas (L3 structural index) graphify mount.

Covers:
- _maybe_rebuild_atlas short-circuit when atlas is fresh.
- _maybe_rebuild_atlas trigger path with mocked subprocess success.
- subprocess failure / timeout never crashes the wake loop.
- Whitelist exposes mcp__graphify__* read tools to every main role.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from minions.tools import noter_wait


def _make_project_layout(tmp_path: Path, port: int = 12345) -> Path:
    """Create project_{port}/branches/main + shared subtree, return main worktree."""
    project = tmp_path / f"project_{port}"
    branches = project / "branches"
    main = branches / "main"
    shared = branches / "shared"
    (shared / "library" / "sources").mkdir(parents=True, exist_ok=True)
    (shared / "notes").mkdir(parents=True, exist_ok=True)
    (shared / "ethics").mkdir(parents=True, exist_ok=True)
    (shared / "exp").mkdir(parents=True, exist_ok=True)
    (shared / "atlas").mkdir(parents=True, exist_ok=True)
    main.mkdir(parents=True, exist_ok=True)
    return main


def _write_atlas(shared: Path, *, mtime: float | None = None) -> Path:
    """Write an atlas.json large enough to be considered non-stub."""
    p = shared / "atlas" / "atlas.json"
    payload = {
        "directed": True,
        "graph": {},
        "nodes": [{"id": f"n{i}"} for i in range(20)],
        "links": [],
        "communities": {},
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    if mtime is not None:
        import os as _os

        _os.utime(p, (mtime, mtime))
    return p


def _write_source(shared: Path, sub: str, name: str, *, mtime: float | None = None) -> Path:
    p = shared / sub / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# placeholder\n", encoding="utf-8")
    if mtime is not None:
        import os as _os

        _os.utime(p, (mtime, mtime))
    return p


def test_rebuild_skipped_when_atlas_is_fresh(tmp_path: Path) -> None:
    main = _make_project_layout(tmp_path)
    shared = main.parent / "shared"
    now = time.time()
    _write_source(shared, "library/sources", "noter-foo.md", mtime=now - 100)
    _write_atlas(shared, mtime=now)

    result = noter_wait._maybe_rebuild_atlas(main)
    assert result["rebuilt"] is False
    assert "fresh" in result["reason"]


def test_rebuild_skipped_when_no_sources(tmp_path: Path) -> None:
    main = _make_project_layout(tmp_path)
    result = noter_wait._maybe_rebuild_atlas(main)
    assert result["rebuilt"] is False
    assert "no source files" in result["reason"]


def test_rebuild_skipped_when_workspace_missing() -> None:
    result = noter_wait._maybe_rebuild_atlas(None)
    assert result["rebuilt"] is False
    assert "no workspace" in result["reason"]


def test_rebuild_triggers_when_source_newer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main = _make_project_layout(tmp_path)
    shared = main.parent / "shared"
    now = time.time()
    _write_atlas(shared, mtime=now - 100)
    _write_source(shared, "library/sources", "noter-foo.md", mtime=now)

    fake_extract = tmp_path / "extract.py"
    fake_extract.write_text("# stub", encoding="utf-8")
    fake_python = tmp_path / "python"
    fake_python.write_text("# stub", encoding="utf-8")

    def fake_resolve(path: Path) -> Path:
        return tmp_path

    monkeypatch.setattr(
        noter_wait,
        "_maybe_rebuild_atlas",
        noter_wait._maybe_rebuild_atlas,  # keep real fn
    )
    # Patch the path-resolution constants by patching subprocess
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        payload = {"rebuilt": True, "node_count": 7, "edge_count": 4, "file_count": 1}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")

    monkeypatch.setattr(noter_wait.subprocess, "run", fake_run)

    # Bypass the venv existence check by creating fake artifacts at the
    # expected path (mcp-servers/graphify/.venv/bin/python and extract.py)
    repo_root = Path(noter_wait.__file__).resolve().parent.parent.parent
    venv_python = repo_root / "mcp-servers" / "graphify" / ".venv" / "bin" / "python"
    extract_script = repo_root / "mcp-servers" / "graphify" / "extract.py"
    if not venv_python.exists() or not extract_script.exists():
        pytest.skip("graphify venv not installed; run setup before this test")

    result = noter_wait._maybe_rebuild_atlas(main)
    assert result["rebuilt"] is True
    assert result["node_count"] == 7
    assert "duration_s" in result
    assert captured["cmd"][1] == str(extract_script)
    assert "--port" in captured["cmd"]


def test_rebuild_handles_subprocess_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main = _make_project_layout(tmp_path)
    shared = main.parent / "shared"
    now = time.time()
    _write_source(shared, "notes", "x.md", mtime=now)

    repo_root = Path(noter_wait.__file__).resolve().parent.parent.parent
    if not (repo_root / "mcp-servers" / "graphify" / ".venv" / "bin" / "python").exists():
        pytest.skip("graphify venv not installed")

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="boom\n")

    monkeypatch.setattr(noter_wait.subprocess, "run", fake_run)
    result = noter_wait._maybe_rebuild_atlas(main)
    assert result["rebuilt"] is False
    assert "exit 2" in result["reason"]
    assert "boom" in result["stderr_tail"]


def test_rebuild_handles_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main = _make_project_layout(tmp_path)
    shared = main.parent / "shared"
    now = time.time()
    _write_source(shared, "ethics", "e.md", mtime=now)

    repo_root = Path(noter_wait.__file__).resolve().parent.parent.parent
    if not (repo_root / "mcp-servers" / "graphify" / ".venv" / "bin" / "python").exists():
        pytest.skip("graphify venv not installed")

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 300))

    monkeypatch.setattr(noter_wait.subprocess, "run", fake_run)
    result = noter_wait._maybe_rebuild_atlas(main)
    assert result["rebuilt"] is False
    assert "timeout" in result["reason"]


def test_rebuild_skipped_when_venv_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main = _make_project_layout(tmp_path)
    shared = main.parent / "shared"
    now = time.time()
    _write_source(shared, "library/sources", "x.md", mtime=now)

    # Override the project-root resolution by pointing at a tmp_path with no venv.
    fake_root = tmp_path / "fake-repo"
    (fake_root / "minions" / "tools").mkdir(parents=True, exist_ok=True)
    fake_module = fake_root / "minions" / "tools" / "noter_wait.py"
    fake_module.write_text("# stub", encoding="utf-8")
    monkeypatch.setattr(noter_wait, "__file__", str(fake_module))

    result = noter_wait._maybe_rebuild_atlas(main)
    assert result["rebuilt"] is False
    assert "graphify venv not installed" in result["reason"]


def test_graphify_tools_in_main_whitelists() -> None:
    from minions.config import resolve_whitelist

    expected = {
        "mcp__graphify__query_graph",
        "mcp__graphify__get_node",
        "mcp__graphify__get_neighbors",
        "mcp__graphify__get_community",
        "mcp__graphify__god_nodes",
        "mcp__graphify__graph_stats",
        "mcp__graphify__shortest_path",
    }
    for role in ("gru", "noter", "coder", "writer", "ethics", "expert"):
        allowed = set(resolve_whitelist(role, "main"))
        missing = expected - allowed
        assert not missing, f"{role} main is missing graphify tools: {missing}"


def test_graphify_tools_NOT_in_subagent_whitelists() -> None:
    """Atlas mount keeps graphify off subagent surface; defer to later phases."""
    from minions.config import resolve_whitelist

    for role in ("gru", "noter", "coder", "writer", "ethics", "expert"):
        try:
            allowed = set(resolve_whitelist(role, "subagent"))
        except Exception:
            continue
        for tool in (
            "mcp__graphify__query_graph",
            "mcp__graphify__god_nodes",
        ):
            assert tool not in allowed, f"{role} subagent unexpectedly has {tool}"
