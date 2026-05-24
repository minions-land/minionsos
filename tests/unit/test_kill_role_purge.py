"""Tests for ``mos_kill_role`` recycle vs purge semantics.

GitHub Issue #3: ``mos_kill_role`` returned ``{killed: true}`` but the
registry row stayed at ``state=active`` — leaving an undocumented
``active + pid=null + session_resumable=false`` third-state that the Gru
watchdog and observers had to special-case. v15.7 adds ``purge=True`` to
flip the row to ``state=dismissed`` so observers see an honest terminal
state.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from minions.state.store import ProjectEntry, RoleEntry
from minions.tools.mcp.runtime_tools import KillRoleArgs, mos_kill_role


@pytest.fixture(autouse=True)
def _enable_authz(monkeypatch: pytest.MonkeyPatch) -> None:
    """The MCP authz guard depends on env. We're calling tools directly
    here so we disable the guard for this test module."""
    monkeypatch.setenv("MINIONS_DISABLE_MCP_AUTHZ", "1")


class _FakeStore:
    """Just enough StateStore surface for the purge path."""

    def __init__(self, role_name: str = "theory-normalization-expert") -> None:
        self._role = RoleEntry(
            name=role_name,
            state="active",
            pid=None,
            spawned_at="2026-01-01T00:00:00Z",
            session_name=f"p37596/{role_name}",
            session_resumable=True,
            workspace_path=f"/tmp/{role_name}",
            workspace_branch=f"minionsos/project-37596-{role_name}",
        )
        self.project = ProjectEntry(
            port=37596,
            real_name="Test",
            status="active",
            created="2026-01-01T00:00:00Z",
            current_branch="minionsos/project-37596",
            active_roles=[self._role],
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


def test_kill_role_default_recycle_keeps_state_active() -> None:
    """purge=False (default): tmux is killed but state stays 'active' so
    the watchdog respawns the role. The registry must NOT be touched."""
    fake_store = _FakeStore()
    with (
        patch("minions.lifecycle.role_launcher.kill_session", return_value=True),
        patch("minions.state.store.StateStore", return_value=fake_store),
    ):
        result = mos_kill_role(
            KillRoleArgs(project_port=37596, role_name="theory-normalization-expert")
        )

    assert result["killed"] is True
    assert result["purged"] is False
    assert result["state"] is None
    assert fake_store.upserts == [], (
        "default kill must NOT touch the registry — that's the recycle semantic"
    )
    assert fake_store.project.active_roles[0].state == "active"


def test_kill_role_purge_flips_state_to_dismissed() -> None:
    """purge=True: tmux killed AND registry row flipped to dismissed.
    The watchdog respawn loop skips dismissed rows, so the role stays gone."""
    fake_store = _FakeStore()
    with (
        patch("minions.lifecycle.role_launcher.kill_session", return_value=True),
        patch("minions.state.store.StateStore", return_value=fake_store),
    ):
        result = mos_kill_role(
            KillRoleArgs(
                project_port=37596,
                role_name="theory-normalization-expert",
                purge=True,
            )
        )

    assert result["killed"] is True
    assert result["purged"] is True
    assert result["state"] == "dismissed"
    assert len(fake_store.upserts) == 1
    upserted = fake_store.upserts[0]
    assert upserted.state == "dismissed"
    assert upserted.pid is None
    assert upserted.session_resumable is False


def test_kill_role_purge_when_already_dismissed_is_idempotent() -> None:
    """If the role is already dismissed (or doesn't exist), purge=True
    should not raise and should not append a duplicate registry row."""
    fake_store = _FakeStore()
    fake_store._role = fake_store._role.model_copy(update={"state": "dismissed"})
    fake_store.project = fake_store.project.model_copy(update={"active_roles": [fake_store._role]})

    with (
        patch("minions.lifecycle.role_launcher.kill_session", return_value=False),
        patch("minions.state.store.StateStore", return_value=fake_store),
    ):
        result = mos_kill_role(
            KillRoleArgs(
                project_port=37596,
                role_name="theory-normalization-expert",
                purge=True,
            )
        )

    # tmux kill returned False because session already gone.
    assert result["killed"] is False
    # Registry already at dismissed → no upsert.
    assert result["purged"] is False
    assert result["state"] is None
    assert fake_store.upserts == []


def test_kill_role_purge_swallows_registry_errors() -> None:
    """The tmux kill is the load-bearing action; a registry-update failure
    must not unkill tmux. Verify by pointing StateStore at a broken double."""

    class _BrokenStore:
        def get_project(self, _port):
            raise RuntimeError("synthetic failure")

    with (
        patch("minions.lifecycle.role_launcher.kill_session", return_value=True),
        patch("minions.state.store.StateStore", return_value=_BrokenStore()),
    ):
        result = mos_kill_role(KillRoleArgs(project_port=37596, role_name="foo-expert", purge=True))

    assert result["killed"] is True  # tmux kill survives
    assert result["purged"] is False  # but purge couldn't be applied
    assert result["state"] is None
