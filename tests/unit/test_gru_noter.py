"""Tests for Gru project-local EACN actions and the Noter terminal."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from minions.config import GruConfig
from minions.lifecycle import noter_terminal, project_eacn
from minions.lifecycle.role import register_role
from minions.state.store import ProjectEntry, RoleEntry


class FakeRoleStore:
    def __init__(self) -> None:
        self.project = ProjectEntry(
            port=37596,
            real_name="Test",
            status="active",
            created="2026-01-01T00:00:00Z",
            current_branch="minionsos/project-37596",
            active_roles=[],
        )
        self.roles: list[RoleEntry] = []

    def get_project(self, port: int) -> ProjectEntry | None:
        return self.project if port == self.project.port else None

    def upsert_role(self, port: int, role: RoleEntry) -> None:
        self.roles.append(role)
        self.project = self.project.model_copy(update={"active_roles": [role]})


def test_register_noter_defaults_to_periodic_time_trigger() -> None:
    store = FakeRoleStore()
    cfg = GruConfig(noter_report_interval="12m")
    with (
        patch("minions.lifecycle.role.load_gru_config", return_value=cfg),
        patch("minions.lifecycle.role.register_project_role_agent", return_value=("tok", [])),
    ):
        result = register_role(37596, "noter", store=store)

    role = store.roles[-1]
    assert result["time_trigger_interval"] == "12m"
    assert role.time_trigger_interval == "12m"
    assert role.wake_policy == "any"


def test_noter_default_report_interval_is_30m() -> None:
    assert GruConfig().noter_report_interval == "30m"


def test_register_coder_remains_event_driven() -> None:
    store = FakeRoleStore()
    with patch("minions.lifecycle.role.register_project_role_agent", return_value=("tok", [])):
        result = register_role(37596, "coder", store=store)

    role = store.roles[-1]
    assert result["time_trigger_interval"] is None
    assert role.time_trigger_interval is None
    assert role.wake_policy == "event"


def test_project_eacn_create_task_invites_target_role() -> None:
    created: dict[str, Any] = {}

    def fake_create_task(**kwargs: Any) -> dict[str, Any]:
        created.update(kwargs)
        return {"id": "task-1", "status": "unclaimed"}

    with (
        patch("minions.lifecycle.project_eacn.load_gru_config", return_value=GruConfig()),
        patch.object(project_eacn.eacn_client, "require_agent", return_value={"agent_id": "coder"}),
        patch.object(project_eacn.eacn_client, "create_task", side_effect=fake_create_task),
    ):
        result = project_eacn.project_eacn_create_task(
            port=37596,
            description="Implement status probe",
            domains=["coding"],
            invited_roles=["coder"],
        )

    assert result["ok"] is True
    assert created["initiator_id"] == "gru"
    assert created["invited_agent_ids"] == ["coder"]
    assert "role:coder" in created["domains"]
    assert result["invited_agent_ids"] == ["coder"]


def test_project_eacn_create_task_rejects_unknown_target_before_create() -> None:
    with (
        patch("minions.lifecycle.project_eacn.load_gru_config", return_value=GruConfig()),
        patch.object(
            project_eacn.eacn_client,
            "require_agent",
            side_effect=project_eacn.eacn_client.BackendError("unknown agent"),
        ),
        patch.object(project_eacn.eacn_client, "create_task") as create_task,
        pytest.raises(project_eacn.eacn_client.BackendError),
    ):
        project_eacn.project_eacn_create_task(
            port=37596,
            description="Implement status probe",
            domains=["coding"],
            invited_roles=["codre"],
        )

    create_task.assert_not_called()


def test_project_eacn_create_task_allows_untargeted_open_task() -> None:
    created: dict[str, Any] = {}

    def fake_create_task(**kwargs: Any) -> dict[str, Any]:
        created.update(kwargs)
        return {"id": "task-open", "status": "unclaimed"}

    with (
        patch("minions.lifecycle.project_eacn.load_gru_config", return_value=GruConfig()),
        patch.object(project_eacn.eacn_client, "create_task", side_effect=fake_create_task),
    ):
        result = project_eacn.project_eacn_create_task(
            port=37596,
            description="Anyone suitable may bid",
            domains=["coding"],
        )

    assert result["ok"] is True
    assert created["invited_agent_ids"] == []
    assert created["domains"] == ["coding"]


def test_project_eacn_create_task_allows_role_initiator_for_public_task() -> None:
    created: dict[str, Any] = {}

    def fake_create_task(**kwargs: Any) -> dict[str, Any]:
        created.update(kwargs)
        return {"id": "task-role-open", "status": "unclaimed"}

    with (
        patch.object(project_eacn, "resolve_agent_id", side_effect=lambda port, role: role),
        patch.object(project_eacn.eacn_client, "create_task", side_effect=fake_create_task),
    ):
        result = project_eacn.project_eacn_create_task(
            port=37596,
            description="Role-created public task",
            domains=["analysis"],
            initiator_role="writer",
        )

    assert result["ok"] is True
    assert result["initiator_id"] == "writer"
    assert created["initiator_id"] == "writer"
    assert created["invited_agent_ids"] == []
    assert created["domains"] == ["analysis"]


def test_project_eacn_send_message_uses_generic_eacn_send() -> None:
    sent: dict[str, Any] = {}

    def fake_send_message(**kwargs: Any) -> dict[str, Any]:
        sent.update(kwargs)
        return {"ok": True}

    with (
        patch("minions.lifecycle.project_eacn.load_gru_config", return_value=GruConfig()),
        patch.object(project_eacn.eacn_client, "send_message", side_effect=fake_send_message),
    ):
        result = project_eacn.project_eacn_send_message(
            port=37596,
            to_role="noter",
            content={"type": "status"},
        )

    assert result["ok"] is True
    assert sent["to_agent_id"] == "noter"
    assert sent["from_agent_id"] == "gru"


@dataclass
class FakeStore:
    project: ProjectEntry

    def get_project(self, port: int) -> ProjectEntry | None:
        return self.project if port == self.project.port else None


def test_noter_snapshot_is_read_only_and_reports_tasks(tmp_path: Path) -> None:
    notes_dir = tmp_path / "artifacts" / "notes"
    notes_dir.mkdir(parents=True)
    note = notes_dir / "summary.md"
    note.write_text("hello", encoding="utf-8")
    project = ProjectEntry(
        port=37596,
        real_name="Test",
        status="active",
        created="2026-01-01T00:00:00Z",
        current_branch="minionsos/project-37596",
        active_roles=[RoleEntry(name="noter", state="active")],
    )

    with (
        patch.object(
            noter_terminal,
            "project_status_snapshot",
            return_value={
                "backend_alive": True,
                "recent_failures": [],
                "agents": [],
                "queue_depth": 0,
            },
        ),
        patch.object(
            noter_terminal.eacn_client,
            "list_tasks",
            return_value=[{"id": "t1", "status": "unclaimed", "content": {}}],
        ) as list_tasks,
        patch.object(noter_terminal, "project_artifacts_dir", return_value=tmp_path / "artifacts"),
    ):
        snap = noter_terminal.collect_noter_snapshot(37596, store=FakeStore(project))

    assert snap.project.port == 37596
    assert snap.tasks[0]["id"] == "t1"
    assert snap.notes == [note]
    assert snap.role_buffers["noter"] == 0
    list_tasks.assert_called_once_with(
        37596,
        status=None,
        limit=12,
        offset=0,
        order="desc",
    )


def test_noter_snapshot_passes_task_filter_and_offset(tmp_path: Path) -> None:
    project = ProjectEntry(
        port=37596,
        real_name="Test",
        status="active",
        created="2026-01-01T00:00:00Z",
        current_branch="minionsos/project-37596",
        active_roles=[],
    )

    with (
        patch.object(
            noter_terminal,
            "project_status_snapshot",
            return_value={
                "backend_alive": True,
                "recent_failures": [],
                "agents": [],
                "queue_depth": 0,
            },
        ),
        patch.object(noter_terminal.eacn_client, "list_tasks", return_value=[]) as list_tasks,
        patch.object(noter_terminal, "project_artifacts_dir", return_value=tmp_path / "artifacts"),
    ):
        noter_terminal.collect_noter_snapshot(
            37596,
            store=FakeStore(project),
            max_tasks=5,
            task_offset=10,
            task_status="completed",
        )

    list_tasks.assert_called_once_with(
        37596,
        status="completed",
        limit=5,
        offset=10,
        order="desc",
    )
