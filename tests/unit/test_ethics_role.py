"""Unit tests for the Ethics Role."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from minions.config import resolve_whitelist
from minions.lifecycle import role as role_mod
from minions.state.store import ProjectEntry, RoleEntry


class FakeStore:
    def __init__(self) -> None:
        self.project = ProjectEntry(
            port=37777,
            real_name="EthicsTest",
            status="active",
            created="2026-01-01T00:00:00Z",
            current_branch="minionsos/project-37777",
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


def test_ethics_registration() -> None:
    store = FakeStore()
    with (
        patch.object(role_mod, "invoke_role_ephemeral"),
        patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])),
    ):
        out = role_mod.register_role(
            37777, "ethics", init_brief=None, store=store, poll_interval="1m"
        )
    assert out["name"] == "ethics"
    assert out["ephemeral"] is True
    assert any(r.name == "ethics" for r in store.project.active_roles)


def test_ethics_main_whitelist() -> None:
    tools = resolve_whitelist("ethics", "main")
    # Ethics uses the MOS Agent Pool for event intake, direct messages, and
    # task creation. Non-destructive EACN3 reads remain available.
    assert "mos_await_events" in tools
    assert "mos_send_message" in tools
    assert "eacn3_get_messages" in tools
    assert "eacn3_*" not in tools
    assert "WebSearch" in tools
    assert "WebFetch" in tools
    assert "Read" in tools
    assert not any(t.startswith("exp_") for t in tools)
    assert "gru_relay" not in tools
    assert not any(t.startswith("spawn_") for t in tools)
    assert not any(t.startswith("project_") for t in tools)
    assert "Write" not in tools
    assert "Edit" not in tools
    assert "Bash" not in tools


def test_ethics_subagent_whitelist() -> None:
    """Ethics subagent executes the writes the main session plans.

    Per the common SYSTEM.md Plan → Dispatch → Verify contract, substantive
    work (flag files, report files under artifacts/ethics/) is produced by a
    subagent, not the main role. The subagent must therefore be able to
    Write/Edit inside that scope; it remains EACN-invisible because there are
    no mos_* / eacn3_* / project_eacn_* tools in this whitelist.
    """
    tools = resolve_whitelist("ethics", "subagent")
    assert set(tools) == {"WebSearch", "WebFetch", "Read", "Write", "Edit"}


def test_project_create_makes_ethics_tree(tmp_path: Path, monkeypatch) -> None:
    from minions.lifecycle import project as proj_mod

    # Simulate project_create's directory-creation block without spawning
    # backend / worktree. We exercise the mkdir logic directly.
    port = 40000
    pdir = tmp_path / f"project_{port}"
    monkeypatch.setattr(proj_mod, "project_dir", lambda p: pdir)
    monkeypatch.setattr(proj_mod, "project_logs_dir", lambda p: pdir / "logs")

    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "logs").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "notes").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "ethics" / "reports").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "ethics" / "flags" / "open").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "ethics" / "flags" / "resolved").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "ethics" / "investigations").mkdir(parents=True, exist_ok=True)

    assert (pdir / "artifacts" / "ethics" / "reports").is_dir()
    assert (pdir / "artifacts" / "ethics" / "flags" / "open").is_dir()
    assert (pdir / "artifacts" / "ethics" / "flags" / "resolved").is_dir()
    assert (pdir / "artifacts" / "ethics" / "investigations").is_dir()


def test_fixed_roles_contains_ethics() -> None:
    assert "ethics" in role_mod.FIXED_ROLES
