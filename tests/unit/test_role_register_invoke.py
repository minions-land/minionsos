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


@pytest.fixture(autouse=True)
def _stub_role_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    """Don't actually spawn tmux during unit tests."""
    from minions.lifecycle import role_launcher as launcher_mod

    def fake_launch(role_entry, project_port, *, cfg=None):
        return {
            "session_name": f"mos-{project_port}-{role_entry.name}",
            "started": True,
            "attach_cmd": ["tmux", "attach", "-t", f"mos-{project_port}-{role_entry.name}"],
        }

    monkeypatch.setattr(launcher_mod, "launch_role_process", fake_launch)
    monkeypatch.setattr(launcher_mod, "session_alive", lambda *a, **k: False)
    monkeypatch.setattr(launcher_mod, "kill_session", lambda *a, **k: False)


class TestRegister:
    def test_register_role_records_entry(self) -> None:
        store = FakeStore()
        with patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])) as reg:
            out = role_mod.register_role(37596, "coder", init_brief=None, store=store)
        reg.assert_called_once_with(37596, "coder")
        assert out["name"] == "coder"
        assert out["session_name"] == "p37596/coder"
        assert str(out["workspace_path"]).endswith("/37596/coder")
        assert out["eacn_agent_id"] == "coder"
        assert out["tmux_session"] == "mos-37596-coder"
        assert out["launch_started"] is True
        assert store.upserts[0].state == "active"
        assert store.upserts[0].pid is None
        assert store.upserts[0].session_name == "p37596/coder"
        assert store.upserts[0].workspace_branch == "minionsos/project-37596-coder"
        assert store.upserts[0].eacn_agent_id == "coder"
        assert store.upserts[0].eacn_agent_token == "tok"

    def test_register_noter_skips_eacn(self) -> None:
        """Noter is not registered on EACN3 — no AgentCard, no init_brief delivery."""
        store = FakeStore()
        with patch.object(role_mod, "register_project_role_agent") as reg:
            out = role_mod.register_role(37596, "noter", init_brief="observe", store=store)
        reg.assert_not_called()
        assert out["name"] == "noter"
        assert out["launch_started"] is True
        assert store.upserts[0].eacn_agent_token == ""

    def test_register_work_role_with_init_brief_sends_message(self) -> None:
        """v15.6+: cold-start init_brief is delivered as an addressable EACN
        message (advisory), not a Task with a bid/claim contract. The message
        carries kind=role_init_brief so the recipient can route it without
        treating it as work-to-bid-on."""
        store = FakeStore()
        with (
            patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])),
            patch("minions.lifecycle.eacn_client.send_message", return_value={}) as send_message,
            patch("minions.lifecycle.eacn_client.create_task", return_value={}) as create_task,
        ):
            role_mod.register_role(37596, "coder", init_brief="hello world", store=store)
        # No Task created — that's the regression we're locking.
        assert create_task.call_count == 0
        # Exactly one advisory message sent to the role.
        assert send_message.call_count == 1
        kwargs = send_message.call_args.kwargs
        assert kwargs["port"] == 37596
        assert kwargs["from_agent_id"] == "gru"
        assert kwargs["to_agent_id"] == "coder"
        content = kwargs["content"]
        assert content["kind"] == "role_init_brief"
        assert content["role"] == "coder"
        assert content["brief"] == "hello world"
        assert (
            "advisory" in content["guidance"].lower() or "not a task" in content["guidance"].lower()
        )

    def test_register_noter_with_init_brief_skips_eacn_delivery(self) -> None:
        """Noter is not on EACN — init_brief is silently skipped."""
        store = FakeStore()
        with (
            patch("minions.lifecycle.eacn_client.create_task", return_value={}) as create_task,
            patch("minions.lifecycle.eacn_client.send_message", return_value={}) as send_message,
        ):
            role_mod.register_role(37596, "noter", init_brief="observe quietly", store=store)
        assert create_task.call_count == 0
        assert send_message.call_count == 0

    def test_register_duplicate_active_smart_respawns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Second register_role on a same-name active role triggers smart respawn,
        not an error: if the tmux session is alive nothing happens; if it died
        the launcher relaunches it. The registry-side EACN re-registration is
        skipped."""
        store = FakeStore()
        with patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])) as reg:
            first = role_mod.register_role(37596, "coder", store=store)
        assert first["launch_started"] is True

        # Now pretend the session is alive — second register_role should no-op.
        from minions.lifecycle import role_launcher as launcher_mod

        monkeypatch.setattr(launcher_mod, "session_alive", lambda *a, **k: True)
        with patch.object(
            role_mod, "register_project_role_agent", return_value=("tok", [])
        ) as reg2:
            second = role_mod.register_role(37596, "coder", store=store)
        assert reg2.call_count == 0  # EACN re-registration is skipped
        assert second["respawn"] is False
        assert second["launch_started"] is False
        # And reg was only called once across both attempts.
        assert reg.call_count == 1

    def test_register_expert_slugifies(self) -> None:
        store = FakeStore()
        with (
            patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])),
            patch("minions.lifecycle.eacn_client.send_message", return_value={}),
        ):
            out = role_mod.register_expert(
                37596,
                "Deep Learning Architecture",
                init_brief=None,
                store=store,
            )
        assert out["name"].startswith("expert-")

    def test_register_expert_coerces_bare_slug_name(self) -> None:
        """Caller name without expert prefix/suffix must be coerced.

        Reproduces the coda-epilogue/p37596 incident: Gru called
        mos_spawn_expert(name="coda-epilogue"); the bare slug bypassed
        is_expert_role() so server authz fell through to the empty
        list and every MCP tool the spawned Role called was denied.
        """
        store = FakeStore()
        with (
            patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])),
            patch("minions.lifecycle.eacn_client.send_message", return_value={}),
        ):
            out = role_mod.register_expert(
                37596,
                domain="CODA epilogue rewrites",
                name="coda-epilogue",
                init_brief=None,
                store=store,
            )
        assert out["name"] == "expert-coda-epilogue"
        from minions.config import is_expert_role, resolve_server_authz

        assert is_expert_role(out["name"])
        assert resolve_server_authz(out["name"], "main"), (
            "coerced expert name must resolve to a non-empty server authz row"
        )

    def test_register_expert_accepts_prefix_form_verbatim(self) -> None:
        store = FakeStore()
        with (
            patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])),
            patch("minions.lifecycle.eacn_client.send_message", return_value={}),
        ):
            out = role_mod.register_expert(
                37596,
                domain="theory normalization",
                name="theory-normalization-expert",
                init_brief=None,
                store=store,
            )
        assert out["name"] == "theory-normalization-expert"

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
            role_mod.register_role(37596, "coder", store=store)
        assert store.upserts == []
