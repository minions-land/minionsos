"""Tests for project phase recording and hook fanout."""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.lifecycle import role_inbox
from minions.lifecycle.project import (
    project_phase_allows_role,
    project_phase_snapshot,
    project_set_phase,
)
from minions.state.store import ProjectEntry, RoleEntry, StateStore


@pytest.fixture(autouse=True)
def _isolate_runtime_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "minions.lifecycle.role_inbox.project_logs_dir",
        lambda port: tmp_path / f"project_{port}" / "logs",
    )
    monkeypatch.setattr(
        "minions.lifecycle.project.project_meta_json",
        lambda port: tmp_path / f"project_{port}" / "meta.json",
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
            active_roles=[
                RoleEntry(name="coder", state="active", eacn_agent_id="coder-agent"),
                RoleEntry(name="noter", state="active", eacn_agent_id="noter-agent"),
            ],
        )
    )
    return store


def test_project_set_phase_updates_registry_and_meta(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    updated = project_set_phase(
        37596,
        "execution",
        allowed_roles=["coder"],
        reason="shift to implementation",
        store=store,
    )

    assert updated.current_phase == "execution"
    assert updated.phase_version == 1
    assert updated.phase_allowed_roles == ["coder"]
    assert project_phase_allows_role(updated, "coder") is True
    assert project_phase_allows_role(updated, "noter") is False
    assert project_phase_snapshot(updated)["phase_online_roles"] == ["coder"]

    coder_events = role_inbox.read_events(37596, "coder")
    noter_events = role_inbox.read_events(37596, "noter")
    assert coder_events[0]["kind"] == "phase_change"
    assert coder_events[0]["phase_allowed"] is True
    assert noter_events == []
