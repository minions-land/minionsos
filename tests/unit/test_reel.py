"""Tests for Reel V2 (L0) — flat index pointing to native session files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minions.errors import ReelError
from minions.tools.reel import (
    _validate_ref_component,
    mos_reel_backfill_draft_ref,
    mos_reel_get,
    mos_reel_window,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def reel_env(monkeypatch, tmp_path):
    """Set up a mock project environment with reel-index.jsonl."""
    port = 12345
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))

    branches_dir = tmp_path / f"project_{port}" / "branches"
    for role in ["coder", "writer", "gru", "ethics", "expert-rl"]:
        (branches_dir / role).mkdir(parents=True)

    def mock_workspace(port_arg, role):
        return branches_dir / role

    import minions.tools.reel as reel_mod
    orig = reel_mod.project_role_workspace
    reel_mod.project_role_workspace = mock_workspace
    yield port, tmp_path, branches_dir
    reel_mod.project_role_workspace = orig


def _make_jsonl(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


def _write_index_entry(branches_dir: Path, role: str, entry: dict) -> None:
    index = branches_dir / role / "reel-index.jsonl"
    with index.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _make_entry(role: str, session_id: str, tool_use_id: str, *, claude_jsonl: str = "",
                kind: str = "subagent") -> dict:
    return {
        "ref": f"{role}/{session_id}/{tool_use_id}",
        "ts": "2026-05-22T12:34:56.789000+00:00",
        "kind": kind,
        "tool_name": "Agent",
        "claude_jsonl": claude_jsonl,
        "draft_node_refs": [],
    }


# ---------------------------------------------------------------------------
# Tests: _validate_ref_component
# ---------------------------------------------------------------------------


def test_validate_ref_component_accepts_normal():
    assert _validate_ref_component("coder", "role") == "coder"
    assert _validate_ref_component("  sess-1  ", "session_id") == "sess-1"


def test_validate_ref_component_rejects_traversal():
    for bad in ["", " ", ".", "..", "../etc", "foo/bar", ".hidden"]:
        with pytest.raises(ReelError, match="Invalid reel ref"):
            _validate_ref_component(bad, "label")


# ---------------------------------------------------------------------------
# Tests: mos_reel_get
# ---------------------------------------------------------------------------


def test_mos_reel_get_reads_claude_jsonl(reel_env, monkeypatch, tmp_path):
    port, _tmp, branches_dir = reel_env
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")

    jsonl_path = tmp_path / "s1.jsonl"
    _make_jsonl(jsonl_path, [{"turn": 1}, {"turn": 2}])

    entry = _make_entry("coder", "sess-1", "tid-001", claude_jsonl=str(jsonl_path))
    _write_index_entry(branches_dir, "coder", entry)

    result = mos_reel_get("coder/sess-1/tid-001")
    assert result["ref"] == "coder/sess-1/tid-001"
    assert result["role"] == "coder"
    assert result["session_id"] == "sess-1"
    assert result["tool_use_id"] == "tid-001"
    assert result["kind"] == "subagent"
    assert len(result["lines"]) == 2
    assert result["lines"][0] == {"turn": 1}


def test_mos_reel_get_no_jsonl_file(reel_env, monkeypatch):
    """Ref found in index but claude_jsonl missing → lines=[]."""
    port, _tmp, branches_dir = reel_env
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
    entry = _make_entry("coder", "sess-2", "tid-002", claude_jsonl="/nonexistent/path.jsonl")
    _write_index_entry(branches_dir, "coder", entry)
    result = mos_reel_get("coder/sess-2/tid-002")
    assert result["lines"] == []


def test_mos_reel_get_permission_denied(reel_env, monkeypatch, tmp_path):
    """Non-Gru/Ethics role cannot read another role's reel."""
    port, _tmp, branches_dir = reel_env
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
    entry = _make_entry("writer", "sess-3", "tid-003")
    _write_index_entry(branches_dir, "writer", entry)
    with pytest.raises(PermissionError, match="cannot read reel for role 'writer'"):
        mos_reel_get("writer/sess-3/tid-003")


def test_mos_reel_get_ethics_cross_read(reel_env, monkeypatch, tmp_path):
    """Ethics can read any role's reel."""
    port, _tmp, branches_dir = reel_env
    monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")
    jsonl_path = tmp_path / "coder_session.jsonl"
    _make_jsonl(jsonl_path, [{"data": "secret"}])
    entry = _make_entry("coder", "sess-4", "tid-004", claude_jsonl=str(jsonl_path))
    _write_index_entry(branches_dir, "coder", entry)
    result = mos_reel_get("coder/sess-4/tid-004")
    assert result["role"] == "coder"
    assert result["lines"][0] == {"data": "secret"}


def test_mos_reel_get_gru_cross_read(reel_env, monkeypatch, tmp_path):
    """Gru can read any role's reel."""
    port, _tmp, branches_dir = reel_env
    monkeypatch.setenv("MINIONS_ROLE_NAME", "gru")
    entry = _make_entry("coder", "sess-5", "tid-005")
    _write_index_entry(branches_dir, "coder", entry)
    result = mos_reel_get("coder/sess-5/tid-005")
    assert result["role"] == "coder"


# ---------------------------------------------------------------------------
# Tests: mos_reel_window
# ---------------------------------------------------------------------------


def test_mos_reel_window_returns_centred_slice(reel_env, monkeypatch):
    port, _tmp, branches_dir = reel_env
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")

    # Write 7 entries for same session so we can slice around the middle one
    for i in range(7):
        ts = f"2026-05-22T12:34:5{i}.000000+00:00"
        entry = {
            "ref": f"coder/sess-w/{i:03d}",
            "ts": ts,
            "kind": "subagent",
            "tool_name": "Agent",
            "claude_jsonl": "",
            "draft_node_refs": [],
        }
        _write_index_entry(branches_dir, "coder", entry)

    # Ask for window around middle entry (index 3), span=2 → entries 1..5
    result = mos_reel_window("coder/sess-w/003", span=2)
    assert len(result) == 5
    refs = [e["ref"] for e in result]
    assert "coder/sess-w/003" in refs
    assert refs[0] == "coder/sess-w/001"
    assert refs[-1] == "coder/sess-w/005"


def test_mos_reel_window_ref_not_found(reel_env, monkeypatch):
    port, _tmp, branches_dir = reel_env
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
    with pytest.raises(ReelError, match="not found in reel index"):
        mos_reel_window("coder/sess-missing/tid-xxx")


# ---------------------------------------------------------------------------
# Tests: mos_reel_backfill_draft_ref
# ---------------------------------------------------------------------------


def test_mos_reel_backfill_adds_draft_ref(reel_env, monkeypatch):
    port, _tmp, branches_dir = reel_env
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")

    entry = _make_entry("coder", "sess-b", "tid-b01")
    _write_index_entry(branches_dir, "coder", entry)

    result = mos_reel_backfill_draft_ref("coder/sess-b/tid-b01", "H-007")
    assert result["status"] == "ok"

    # Re-read the index and confirm the ref is present
    from minions.tools.reel import _read_index
    index_path = branches_dir / "coder" / "reel-index.jsonl"
    entries = _read_index(index_path)
    target = next(e for e in entries if e["ref"] == "coder/sess-b/tid-b01")
    assert "H-007" in target["draft_node_refs"]


def test_mos_reel_backfill_idempotent(reel_env, monkeypatch):
    """Adding the same draft_node_id twice should not duplicate it."""
    port, _tmp, branches_dir = reel_env
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")

    entry = _make_entry("coder", "sess-b2", "tid-b02")
    _write_index_entry(branches_dir, "coder", entry)

    mos_reel_backfill_draft_ref("coder/sess-b2/tid-b02", "Q-003")
    mos_reel_backfill_draft_ref("coder/sess-b2/tid-b02", "Q-003")

    from minions.tools.reel import _read_index
    index_path = branches_dir / "coder" / "reel-index.jsonl"
    entries = _read_index(index_path)
    target = next(e for e in entries if e["ref"] == "coder/sess-b2/tid-b02")
    assert target["draft_node_refs"].count("Q-003") == 1

