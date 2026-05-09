"""Unit tests for minions.lifecycle.session_archive."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from minions.lifecycle import session_archive as sa


def _fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def test_claude_project_dir_encodes_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_home(tmp_path, monkeypatch)
    ws = tmp_path / "workspace" / "MinionsOS_V5"
    ws.mkdir(parents=True)
    mangled = sa.claude_project_dir(ws)
    assert mangled.name.endswith("-workspace-MinionsOS-V5")
    assert mangled.parent.name == "projects"
    assert mangled.parent.parent.name == ".claude"


def test_find_claude_session_file_picks_latest_after_started_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_home(tmp_path, monkeypatch)
    ws = tmp_path / "proj" / "branches" / "coder"
    ws.mkdir(parents=True)
    proj_dir = sa.claude_project_dir(ws)
    proj_dir.mkdir(parents=True)

    old = proj_dir / "aaaaaaaa-0000-0000-0000-000000000000.jsonl"
    mid = proj_dir / "bbbbbbbb-0000-0000-0000-000000000000.jsonl"
    new = proj_dir / "cccccccc-0000-0000-0000-000000000000.jsonl"
    for p in (old, mid, new):
        p.write_text("{}\n", encoding="utf-8")

    base = time.time()
    os.utime(old, (base - 100, base - 100))
    os.utime(mid, (base + 10, base + 10))
    os.utime(new, (base + 20, base + 20))

    found = sa.find_claude_session_file(ws, started_after=base)
    assert found == new

    # Nothing qualifies if started_after is in the far future.
    assert sa.find_claude_session_file(ws, started_after=base + 1000) is None


def test_find_codex_session_file_matches_cwd_and_mtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _fake_home(tmp_path, monkeypatch)
    ws = tmp_path / "proj37596" / "branches" / "coder"
    ws.mkdir(parents=True)
    other_ws = tmp_path / "proj37596" / "branches" / "writer"
    other_ws.mkdir(parents=True)

    today = time.localtime()
    day_dir = (
        home
        / ".codex"
        / "sessions"
        / f"{today.tm_year:04d}"
        / f"{today.tm_mon:02d}"
        / f"{today.tm_mday:02d}"
    )
    day_dir.mkdir(parents=True)
    base = time.time()

    # Not our cwd - ignore.
    wrong_cwd = day_dir / "rollout-x1.jsonl"
    _write_jsonl(
        wrong_cwd,
        [{"type": "session_meta", "payload": {"cwd": str(other_ws.resolve())}}],
    )
    os.utime(wrong_cwd, (base + 5, base + 5))

    # Right cwd but too old - ignore.
    too_old = day_dir / "rollout-x2.jsonl"
    _write_jsonl(
        too_old,
        [{"type": "session_meta", "payload": {"cwd": str(ws.resolve())}}],
    )
    os.utime(too_old, (base - 500, base - 500))

    # Right cwd and fresh - match.
    good = day_dir / "rollout-x3.jsonl"
    _write_jsonl(
        good,
        [{"type": "session_meta", "payload": {"cwd": str(ws.resolve())}}],
    )
    os.utime(good, (base + 3, base + 3))

    found = sa.find_codex_session_file(ws, started_after=base)
    assert found == good


def test_archive_session_copies_claude_and_assigns_wake_numbers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_home(tmp_path, monkeypatch)
    ws = tmp_path / "proj" / "branches" / "coder"
    ws.mkdir(parents=True)
    proj_dir = sa.claude_project_dir(ws)
    proj_dir.mkdir(parents=True)

    src = proj_dir / "deadbeef-1111-2222-3333-444455556666.jsonl"
    src.write_text('{"role":"user","text":"hi"}\n', encoding="utf-8")
    base = time.time()
    os.utime(src, (base + 1, base + 1))

    dest = sa.archive_session(host="claude", workspace=ws, started_at=base)
    assert dest is not None
    assert dest.parent == ws / ".minionsos" / "sessions"
    assert dest.name.endswith("-wake001.jsonl")
    assert dest.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")

    # Second wake: mtime bumped a second later, counter increments.
    os.utime(src, (base + 2, base + 2))
    dest2 = sa.archive_session(host="claude", workspace=ws, started_at=base + 1.5)
    assert dest2 is not None
    assert dest2.name.endswith("-wake002.jsonl")


def test_archive_session_no_source_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_home(tmp_path, monkeypatch)
    ws = tmp_path / "proj" / "branches" / "coder"
    ws.mkdir(parents=True)

    result = sa.archive_session(host="claude", workspace=ws, started_at=time.time())
    assert result is None
    assert not (ws / ".minionsos" / "sessions").exists()


def test_archive_session_unknown_host_is_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_home(tmp_path, monkeypatch)
    ws = tmp_path / "proj" / "branches" / "coder"
    ws.mkdir(parents=True)
    assert sa.archive_session(host="nope", workspace=ws, started_at=time.time()) is None
