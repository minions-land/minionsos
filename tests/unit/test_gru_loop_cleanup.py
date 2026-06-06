"""Unit tests for Gru loop process cleanup (orphan reaper + auto-exit)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from minions.gru.loop import GruLoop
from minions.state.store import ProjectEntry, StateStore


@pytest.fixture
def mock_store(tmp_path: Path, monkeypatch):
    """Mock StateStore with controllable project list."""
    store = StateStore()
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    return store


def test_gru_loop_auto_exit_when_no_active_projects(mock_store: StateStore):
    """Gru loop should set _stopped=True when no active projects remain."""
    loop = GruLoop(heartbeat_interval=1)
    loop._store = mock_store

    # Simulate empty active projects
    with patch.object(mock_store, "list_projects", return_value=[]):
        loop._tick()

    assert loop._stopped is True


def test_gru_loop_continues_when_active_projects_exist(mock_store: StateStore):
    """Gru loop should NOT exit when active projects exist."""
    loop = GruLoop(heartbeat_interval=1)
    loop._store = mock_store

    fake_project = ProjectEntry(
        port=9999,
        real_name="test-project",
        status="active",
        created="2026-05-24T00:00:00+00:00",
        upstream_branch="HEAD",
        current_branch="minionsos/project-9999",
        workspace_root="/tmp/project_9999/branches",
        workspace_main="/tmp/project_9999/branches/main",
        workspace_roles_root="/tmp/project_9999/branches",
        workspace_shared="/tmp/project_9999/branches/main",
        active_roles=[],
    )

    with (
        patch.object(mock_store, "list_projects", return_value=[fake_project]),
        patch("minions.gru.loop.backend_health", return_value=True),
    ):
        loop._tick()

    assert loop._stopped is False


def test_reap_orphan_sessions_kills_non_active_ports(mock_store: StateStore):
    """_reap_orphan_sessions should kill tmux sessions for non-active ports."""
    loop = GruLoop(heartbeat_interval=1)
    loop._store = mock_store

    # Mock tmux ls output with one orphan session
    fake_tmux_output = "mos-12345-expert: 1 windows (created Sat May 24 00:00:00 2026)\n"

    # Mock active projects (port 12345 is NOT active)
    fake_project = ProjectEntry(
        port=9999,
        real_name="active-project",
        status="active",
        created="2026-05-24T00:00:00+00:00",
        upstream_branch="HEAD",
        current_branch="minionsos/project-9999",
        workspace_root="/tmp/project_9999/branches",
        workspace_main="/tmp/project_9999/branches/main",
        workspace_roles_root="/tmp/project_9999/branches",
        workspace_shared="/tmp/project_9999/branches/main",
        active_roles=[],
    )

    with (
        patch.object(mock_store, "list_projects", return_value=[fake_project]),
        patch("subprocess.run") as mock_run,
    ):
        # First call: tmux ls
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_tmux_output, stderr="")

        loop._reap_orphan_sessions()

        # Should have called tmux ls, then tmux kill-session
        assert mock_run.call_count == 2
        kill_call = mock_run.call_args_list[1]
        assert kill_call[0][0] == ["tmux", "kill-session", "-t", "mos-12345-expert"]


def test_reap_orphan_sessions_preserves_active_ports(mock_store: StateStore):
    """_reap_orphan_sessions should NOT kill sessions for active ports."""
    loop = GruLoop(heartbeat_interval=1)
    loop._store = mock_store

    # Mock tmux ls output with active session
    fake_tmux_output = "mos-9999-expert: 1 windows (created Sat May 24 00:00:00 2026)\n"

    # Mock active projects (port 9999 IS active)
    fake_project = ProjectEntry(
        port=9999,
        real_name="active-project",
        status="active",
        created="2026-05-24T00:00:00+00:00",
        upstream_branch="HEAD",
        current_branch="minionsos/project-9999",
        workspace_root="/tmp/project_9999/branches",
        workspace_main="/tmp/project_9999/branches/main",
        workspace_roles_root="/tmp/project_9999/branches",
        workspace_shared="/tmp/project_9999/branches/main",
        active_roles=[],
    )

    with (
        patch.object(mock_store, "list_projects", return_value=[fake_project]),
        patch("subprocess.run") as mock_run,
    ):
        # First call: tmux ls
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_tmux_output, stderr="")

        loop._reap_orphan_sessions()

        # Should only call tmux ls, NOT kill-session
        assert mock_run.call_count == 1
        assert mock_run.call_args[0][0] == ["tmux", "ls"]


def test_reap_orphan_sessions_handles_no_tmux():
    """_reap_orphan_sessions should gracefully handle missing tmux."""
    loop = GruLoop(heartbeat_interval=1)

    with patch("subprocess.run", side_effect=FileNotFoundError):
        loop._reap_orphan_sessions()  # Should not raise


def test_reap_orphan_sessions_handles_no_sessions():
    """_reap_orphan_sessions should gracefully handle no tmux sessions."""
    loop = GruLoop(heartbeat_interval=1)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        loop._reap_orphan_sessions()  # Should not raise
