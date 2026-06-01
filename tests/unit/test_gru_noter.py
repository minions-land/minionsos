"""Tests for role registration defaults and the Noter terminal snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from minions.config import GruConfig
from minions.lifecycle import noter_terminal
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


def test_noter_default_periodic_interval_is_3m() -> None:
    assert GruConfig().noter_periodic_interval == "3m"


def test_noter_default_report_interval_is_30m() -> None:
    assert GruConfig().noter_report_interval == "30m"


def test_register_ethics_remains_event_driven() -> None:
    store = FakeRoleStore()
    with patch("minions.lifecycle.role.register_project_role_agent", return_value=("tok", [])):
        result = register_role(37596, "ethics", store=store)

    role = store.roles[-1]
    assert result["time_trigger_interval"] is None
    assert role.time_trigger_interval is None


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
        current_phase="execution",
        phase_allowed_roles=["noter"],
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
    assert snap.current_phase == "execution"
    assert snap.phase_allowed_roles == ["noter"]
    assert snap.phase_online_roles == ["noter"]
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
