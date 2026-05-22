"""Tests for Reel (L0) — raw session-level execution traces."""

from __future__ import annotations

import json

import pytest

from minions.tools.reel import (
    append_reel_index,
    archive_transcript,
    mos_reel_get,
    mos_reel_window,
)


@pytest.fixture
def mock_project_port(monkeypatch, tmp_path):
    """Set up a mock project environment."""
    port = 12345
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))

    # Create project structure
    project_dir = tmp_path / f"project_{port}"
    project_dir.mkdir()

    # Create role workspaces
    branches_dir = project_dir / "branches"
    for role in ["coder", "writer", "gru"]:
        role_dir = branches_dir / role
        role_dir.mkdir(parents=True)

    # Mock project_role_workspace to return our tmp paths
    def mock_workspace(port_arg, role):
        return branches_dir / role

    import minions.tools.reel

    original_workspace = minions.tools.reel.project_role_workspace
    minions.tools.reel.project_role_workspace = mock_workspace

    yield port, tmp_path

    # Restore
    minions.tools.reel.project_role_workspace = original_workspace


def test_append_reel_index(mock_project_port, monkeypatch):
    """Test appending entries to reel index."""
    port, tmp_path = mock_project_port
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")

    session_id = "sess-20260522-123456"

    # Append first entry
    append_reel_index(
        port=port,
        role="coder",
        session_id=session_id,
        kind="subagent",
        task_id="task-001",
        draft_refs=["H-001"],
    )

    # Append second entry
    append_reel_index(
        port=port,
        role="coder",
        session_id=session_id,
        kind="codex",
        task_id="task-002",
        draft_refs=["H-002", "Q-003"],
    )

    # Read index
    index_path = (
        tmp_path / f"project_{port}" / "branches" / "coder" / "reel" / session_id / "index.jsonl"
    )
    assert index_path.exists()

    entries = []
    with index_path.open("r") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    assert len(entries) == 2
    assert entries[0]["seq"] == 0
    assert entries[0]["kind"] == "subagent"
    assert entries[0]["task_id"] == "task-001"
    assert entries[0]["draft_refs"] == ["H-001"]

    assert entries[1]["seq"] == 1
    assert entries[1]["kind"] == "codex"
    assert entries[1]["task_id"] == "task-002"
    assert entries[1]["draft_refs"] == ["H-002", "Q-003"]


def test_archive_transcript(mock_project_port, monkeypatch):
    """Test archiving a transcript file."""
    port, tmp_path = mock_project_port
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")

    session_id = "sess-20260522-123456"
    task_id = "task-abc123"

    # Create a mock transcript
    source_file = tmp_path / "source_transcript.jsonl"
    with source_file.open("w") as f:
        f.write('{"turn": 1, "content": "test"}\n')
        f.write('{"turn": 2, "content": "more test"}\n')

    # Archive it
    archive_transcript(
        port=port,
        role="coder",
        session_id=session_id,
        task_id=task_id,
        source_path=source_file,
        kind="subagent",
    )

    # Verify transcript was copied
    dest_path = (
        tmp_path
        / f"project_{port}"
        / "branches"
        / "coder"
        / "reel"
        / session_id
        / "transcripts"
        / f"{task_id}.jsonl"
    )
    assert dest_path.exists()
    assert dest_path.read_text() == source_file.read_text()

    # Verify index entry was created
    index_path = (
        tmp_path / f"project_{port}" / "branches" / "coder" / "reel" / session_id / "index.jsonl"
    )
    assert index_path.exists()

    with index_path.open("r") as f:
        entry = json.loads(f.readline())

    assert entry["kind"] == "subagent"
    assert entry["task_id"] == task_id


def test_mos_reel_get_success(mock_project_port, monkeypatch):
    """Test reading a transcript via mos_reel_get."""
    port, tmp_path = mock_project_port
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")

    session_id = "sess-20260522-123456"
    task_id = "task-xyz"

    # Set up transcript
    source_file = tmp_path / "source.jsonl"
    with source_file.open("w") as f:
        f.write('{"line": 1, "data": "first"}\n')
        f.write('{"line": 2, "data": "second"}\n')

    archive_transcript(
        port=port,
        role="coder",
        session_id=session_id,
        task_id=task_id,
        source_path=source_file,
        kind="codex",
    )

    # Read via MCP tool
    ref = f"coder/{session_id}/{task_id}"
    result = mos_reel_get(ref)

    assert result["ref"] == ref
    assert result["role"] == "coder"
    assert result["session_id"] == session_id
    assert result["task_id"] == task_id
    assert result["kind"] == "codex"
    assert len(result["lines"]) == 2
    assert result["lines"][0] == {"line": 1, "data": "first"}
    assert result["lines"][1] == {"line": 2, "data": "second"}


def test_mos_reel_get_permission_denied(mock_project_port, monkeypatch):
    """Test that non-Gru roles cannot read other roles' reels."""
    port, tmp_path = mock_project_port

    # Coder tries to read Writer's reel
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")

    session_id = "sess-20260522-123456"
    task_id = "task-xyz"

    # Set up Writer's transcript
    source_file = tmp_path / "source.jsonl"
    source_file.write_text('{"data": "test"}\n')

    archive_transcript(
        port=port,
        role="writer",
        session_id=session_id,
        task_id=task_id,
        source_path=source_file,
        kind="subagent",
    )

    # Coder tries to read it
    ref = f"writer/{session_id}/{task_id}"

    with pytest.raises(PermissionError, match="cannot read reel for role 'writer'"):
        mos_reel_get(ref)


def test_mos_reel_get_gru_can_read_any_role(mock_project_port, monkeypatch):
    """Test that Gru can read any role's reel."""
    port, tmp_path = mock_project_port

    # Set up Coder's transcript
    session_id = "sess-20260522-123456"
    task_id = "task-xyz"

    source_file = tmp_path / "source.jsonl"
    source_file.write_text('{"data": "test"}\n')

    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
    archive_transcript(
        port=port,
        role="coder",
        session_id=session_id,
        task_id=task_id,
        source_path=source_file,
        kind="subagent",
    )

    # Gru reads it
    monkeypatch.setenv("MINIONS_ROLE_NAME", "gru")
    ref = f"coder/{session_id}/{task_id}"
    result = mos_reel_get(ref)

    assert result["role"] == "coder"
    assert len(result["lines"]) == 1


def test_mos_reel_window(mock_project_port, monkeypatch):
    """Test reading a window of index entries."""
    port, _tmp_path = mock_project_port
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")

    session_id = "sess-20260522-123456"

    # Create multiple entries
    for i in range(10):
        append_reel_index(
            port=port,
            role="coder",
            session_id=session_id,
            kind="subagent",
            task_id=f"task-{i:03d}",
            draft_refs=[],
        )

    # Read window around task-005 (seq=5)
    ref = f"coder/{session_id}/task-005"
    window = mos_reel_window(ref, span=2)

    # Should get seq 3, 4, 5, 6, 7 (5 entries total)
    assert len(window) == 5
    assert window[0]["seq"] == 3
    assert window[2]["seq"] == 5
    assert window[2]["task_id"] == "task-005"
    assert window[4]["seq"] == 7


def test_mos_reel_get_malformed_ref(mock_project_port, monkeypatch):
    """Test that malformed refs are rejected."""
    _port, _tmp_path = mock_project_port
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")

    with pytest.raises(ValueError, match="Invalid reel ref format"):
        mos_reel_get("invalid-ref")

    with pytest.raises(ValueError, match="Invalid reel ref format"):
        mos_reel_get("coder/session")  # Missing task_id


def test_archive_transcript_missing_source(mock_project_port, monkeypatch, caplog):
    """Test that missing source files are handled gracefully."""
    port, tmp_path = mock_project_port
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")

    session_id = "sess-20260522-123456"
    task_id = "task-missing"

    # Try to archive a non-existent file
    source_file = tmp_path / "does_not_exist.jsonl"

    archive_transcript(
        port=port,
        role="coder",
        session_id=session_id,
        task_id=task_id,
        source_path=source_file,
        kind="subagent",
    )

    # Should log warning but not crash
    assert "source does not exist" in caplog.text

    # Index should not be created
    index_path = (
        tmp_path / f"project_{port}" / "branches" / "coder" / "reel" / session_id / "index.jsonl"
    )
    assert not index_path.exists()


def test_validate_ref_component_accepts_normal_values():
    """Sanity check: normal component values pass validation."""
    from minions.tools.reel import _validate_ref_component

    assert _validate_ref_component("coder", "role") == "coder"
    assert _validate_ref_component("sess-20260522-123456", "session_id") == "sess-20260522-123456"
    assert _validate_ref_component("a1b2c3d4e5f6", "task_id") == "a1b2c3d4e5f6"
    # Whitespace is stripped.
    assert _validate_ref_component("  coder  ", "role") == "coder"


@pytest.mark.parametrize(
    "value",
    [
        "",
        " ",
        ".",
        "..",
        "../etc",
        "..\\etc",
        "foo/bar",
        "foo\\bar",
        ".hidden",
        ".env",
    ],
)
def test_validate_ref_component_rejects_traversal_patterns(value):
    """Path-traversal guard: reject any component that could escape the reel root.

    Added in v13.5 after pass-2 audit identified that mos_reel_get(ref) accepted
    refs from model output with only a count check; a malicious ref like
    'coder/../foo/bar' would resolve outside the project's reel directory.
    """
    from minions.tools.reel import _validate_ref_component

    with pytest.raises(ValueError, match="Invalid reel ref"):
        _validate_ref_component(value, "test_label")


def test_mos_reel_get_rejects_traversal_ref(mock_project_port, monkeypatch):
    """End-to-end: mos_reel_get(ref) rejects path-traversal in any component."""
    monkeypatch.setenv("MINIONS_ROLE_NAME", "gru")  # Gru can read any role's reel

    with pytest.raises(ValueError, match="Invalid reel ref"):
        mos_reel_get("coder/../foo/bar")

    with pytest.raises(ValueError, match="Invalid reel ref"):
        mos_reel_get("coder/sess-1/..")

    with pytest.raises(ValueError, match="Invalid reel ref"):
        mos_reel_get("../etc/sess-1/task-1")


def test_mos_reel_window_rejects_traversal_ref(mock_project_port, monkeypatch):
    """End-to-end: mos_reel_window(ref) rejects path-traversal in any component."""
    monkeypatch.setenv("MINIONS_ROLE_NAME", "gru")

    with pytest.raises(ValueError, match="Invalid reel ref"):
        mos_reel_window("coder/../foo/bar")
