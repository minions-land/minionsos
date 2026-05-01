"""Unit tests for hook-driven wake signal helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.lifecycle import role_inbox
from minions.lifecycle.wake_signals import (
    direct_message_signal,
    phase_change_signal,
    summarize_signal,
    task_signal,
)
from minions.state.store import ProjectEntry, RoleEntry, StateStore


@pytest.fixture(autouse=True)
def _isolate_runtime_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "minions.lifecycle.role_inbox.project_logs_dir",
        lambda port: tmp_path / f"project_{port}" / "logs",
    )


def _make_store(tmp_path: Path) -> StateStore:
    store = StateStore(root=tmp_path / "state")
    store.add_project(
        ProjectEntry(
            port=37596,
            real_name="test-project",
            status="active",
            created="2026-05-01T00:00:00Z",
            current_branch="minionsos/project-37596",
            current_phase="analysis",
            phase_version=1,
            phase_allowed_roles=["coder"],
            active_roles=[
                RoleEntry(
                    name="coder",
                    state="active",
                    eacn_agent_id="coder-agent",
                ),
                RoleEntry(
                    name="noter",
                    state="active",
                    eacn_agent_id="noter-agent",
                ),
            ],
        )
    )
    return store


def test_direct_message_signal_targets_local_role(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    matched = direct_message_signal(
        port=37596,
        to_agent_id="coder-agent",
        from_agent_id="gru-agent",
        content={"type": "text", "body": "ping"},
        source="test",
        store=store,
    )

    assert matched == ["coder"]
    events = role_inbox.read_events(37596, "coder")
    assert len(events) == 1
    assert events[0]["kind"] == "direct_message"
    assert events[0]["to_agent_id"] == "coder-agent"
    assert role_inbox.read_events(37596, "noter") == []


def test_task_signal_matches_router_candidate(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    matched = task_signal(
        port=37596,
        task={
            "id": "t-1",
            "domains": ["coding"],
            "initiator_id": "gru-agent",
            "content": {"description": "fix a bug"},
        },
        source="test",
        store=store,
    )

    assert matched == ["coder"]
    events = role_inbox.read_events(37596, "coder")
    assert len(events) == 1
    assert events[0]["kind"] == "task_router"
    assert events[0]["matched_by"] == "domain"
    assert events[0]["task_id"] == "t-1"


def test_phase_change_signal_summarizes_phase(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    targets = phase_change_signal(
        port=37596,
        phase="execution",
        reason="phase transition",
        store=store,
    )

    assert sorted(targets) == ["coder", "noter"]
    coder_events = role_inbox.read_events(37596, "coder")
    noter_events = role_inbox.read_events(37596, "noter")
    assert coder_events[0]["kind"] == "phase_change"
    assert coder_events[0]["phase_allowed"] is True
    assert noter_events[0]["kind"] == "phase_change"
    assert noter_events[0]["phase_allowed"] is False
    assert "phase change" in summarize_signal(coder_events[0])
