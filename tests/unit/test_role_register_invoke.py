"""Unit tests for register_role / invoke_role_ephemeral."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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


class TestRegister:
    def test_register_role_no_subprocess(self) -> None:
        store = FakeStore()
        with (
            patch.object(role_mod, "invoke_role_ephemeral") as inv,
            patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])) as reg,
        ):
            out = role_mod.register_role(
                37596, "noter", init_brief=None, store=store, poll_interval="1m"
            )
        assert inv.call_count == 0
        reg.assert_called_once_with(37596, "noter")
        assert out["name"] == "noter"
        assert out["poll_interval"] == "1m"
        assert out["ephemeral"] is True
        assert out["eacn_agent_id"] == "noter"
        assert store.upserts[0].state == "active"
        assert store.upserts[0].pid is None
        assert store.upserts[0].eacn_agent_id == "noter"
        assert store.upserts[0].eacn_agent_token == "tok"

    def test_register_with_init_brief_invokes_once(self) -> None:
        store = FakeStore()
        with (
            patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])),
            patch("minions.lifecycle.eacn_client.create_task", return_value={}) as create_task,
        ):
            role_mod.register_role(
                37596, "noter", init_brief="hello world", store=store, poll_interval="1m"
            )
        assert create_task.call_count == 1
        kwargs = create_task.call_args.kwargs
        assert kwargs["port"] == 37596
        assert kwargs["initiator_id"] == "gru"
        assert kwargs["invited_agent_ids"] == ["noter"]
        assert kwargs["budget"] == 0.0
        assert kwargs["description"] == "hello world"

    def test_register_rejects_duplicate_active(self) -> None:
        store = FakeStore()
        with patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])):
            role_mod.register_role(37596, "noter", store=store, poll_interval="1m")
        with pytest.raises(Exception):
            role_mod.register_role(37596, "noter", store=store, poll_interval="1m")

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
                poll_interval="1m",
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
            role_mod.register_role(37596, "noter", store=store, poll_interval="1m")
        assert store.upserts == []

    def test_spawn_role_alias(self) -> None:
        assert role_mod.spawn_role is role_mod.register_role
        assert role_mod.spawn_expert is role_mod.register_expert


class TestInvokeEphemeral:
    def test_invoke_launches_subprocess(self, tmp_path: Path) -> None:
        fake_proc = MagicMock()
        fake_proc.pid = 4321
        with (
            patch("minions.lifecycle.role.subprocess.Popen", return_value=fake_proc) as popen,
            patch("minions.lifecycle.role.project_workspace", return_value=tmp_path),
            patch(
                "minions.lifecycle.role.project_role_log", return_value=tmp_path / "role-noter.log"
            ),
        ):
            out = role_mod.invoke_role_ephemeral("noter", 37596, [{"id": "e1", "content": "hi"}])
        assert out["name"] == "noter"
        assert out["pid"] == 4321
        assert out["events"] == 1
        assert out["deferred"] is False
        assert popen.call_count == 1
        cmd = popen.call_args[0][0]
        # Prompt is now piped via stdin in -p/--print mode (was --message flag).
        assert "-p" in cmd or "--print" in cmd
        assert "--message" not in cmd
        assert "--permission-mode" in cmd
        assert "bypassPermissions" in cmd
        assert "--allowed-tools" in cmd
        # stdin must be a pipe so the prompt can be written.
        assert popen.call_args.kwargs.get("stdin") is not None
        # And the message was actually written to the subprocess stdin.
        fake_proc.stdin.write.assert_called()
        fake_proc.stdin.close.assert_called()
