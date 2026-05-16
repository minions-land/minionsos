"""Unit tests for register_role / register_expert."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from minions.lifecycle import role as role_mod
from minions.state.store import ProjectEntry, RoleEntry


class FakeStore:
    def __init__(self) -> None:
        self.project = ProjectEntry(
            port=37596,
            real_name="Test",
            status="active",
            created="2026-01-01T00:00:00Z",
            current_branch="minionsos/project-37596",
            active_roles=[],
        )
        self.upserts: list[RoleEntry] = []

    def get_project(self, port: int) -> ProjectEntry | None:
        return self.project if port == self.project.port else None

    def upsert_role(self, port: int, role: RoleEntry) -> None:
        self.upserts.append(role)
        self.project = self.project.model_copy(
            update={
                "active_roles": [
                    *(r for r in self.project.active_roles if r.name != role.name),
                    role,
                ]
            }
        )


@pytest.fixture(autouse=True)
def _fake_role_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    def _workspace(port: int, role_name: str, base_branch: str | None = None):
        branch = f"minionsos/project-{port}-{role_name}"
        return branch, Path(f"/tmp/minionsos-test-workspaces/{port}/{role_name}")

    monkeypatch.setattr(role_mod, "ensure_role_workspace", _workspace)


class TestRegister:
    def test_register_role_records_entry(self) -> None:
        store = FakeStore()
        with patch.object(
            role_mod, "register_project_role_agent", return_value=("tok", [])
        ) as reg:
            out = role_mod.register_role(37596, "noter", init_brief=None, store=store)
        reg.assert_called_once_with(37596, "noter")
        assert out["name"] == "noter"
        assert out["session_name"] == "p37596/noter"
        assert str(out["workspace_path"]).endswith("/37596/noter")
        assert out["ephemeral"] is True
        assert out["eacn_agent_id"] == "noter"
        assert store.upserts[0].state == "active"
        assert store.upserts[0].pid is None
        assert store.upserts[0].session_name == "p37596/noter"
        assert store.upserts[0].workspace_branch == "minionsos/project-37596-noter"
        assert store.upserts[0].eacn_agent_id == "noter"
        assert store.upserts[0].eacn_agent_token == "tok"

    def test_register_work_role_with_init_brief_creates_zero_budget_task(self) -> None:
        store = FakeStore()
        with (
            patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])),
            patch("minions.lifecycle.eacn_client.create_task", return_value={}) as create_task,
        ):
            role_mod.register_role(37596, "coder", init_brief="hello world", store=store)
        assert create_task.call_count == 1
        kwargs = create_task.call_args.kwargs
        assert kwargs["port"] == 37596
        assert kwargs["initiator_id"] == "gru"
        assert kwargs["invited_agent_ids"] == ["coder"]
        assert kwargs["budget"] == 0.0
        assert kwargs["description"] == "hello world"

    def test_register_noter_with_init_brief_sends_direct_message_not_task(self) -> None:
        store = FakeStore()
        with (
            patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])),
            patch("minions.lifecycle.eacn_client.create_task", return_value={}) as create_task,
            patch("minions.lifecycle.eacn_client.send_message", return_value={}) as send_message,
        ):
            role_mod.register_role(37596, "noter", init_brief="observe quietly", store=store)
        assert create_task.call_count == 0
        send_message.assert_called_once()
        kwargs = send_message.call_args.kwargs
        assert kwargs["port"] == 37596
        assert kwargs["from_agent_id"] == "gru"
        assert kwargs["to_agent_id"] == "noter"
        assert kwargs["content"]["type"] == "init_brief"
        assert kwargs["content"]["description"] == "observe quietly"

    def test_register_rejects_duplicate_active(self) -> None:
        store = FakeStore()
        with patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])):
            role_mod.register_role(37596, "noter", store=store)
        with pytest.raises(Exception):
            role_mod.register_role(37596, "noter", store=store)

    def test_register_expert_slugifies(self) -> None:
        store = FakeStore()
        with (
            patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])),
            patch("minions.lifecycle.eacn_client.create_task", return_value={}),
        ):
            out = role_mod.register_expert(
                37596,
                "Deep Learning Architecture",
                init_brief=None,
                store=store,
            )
        assert out["name"].startswith("expert-")

    def test_register_fails_if_role_cannot_join_eacn(self) -> None:
        store = FakeStore()
        with (
            patch.object(
                role_mod,
                "register_project_role_agent",
                side_effect=role_mod.BackendError("backend down"),
            ),
            pytest.raises(role_mod.RoleError),
        ):
            role_mod.register_role(37596, "noter", store=store)
        assert store.upserts == []

    def test_spawn_role_alias(self) -> None:
        assert role_mod.spawn_role is role_mod.register_role
        assert role_mod.spawn_expert is role_mod.register_expert

