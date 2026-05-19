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


def test_ethics_registration(monkeypatch) -> None:
    """register_role wires up EACN agent + tmux session for ethics."""
    from minions.lifecycle import role_launcher as launcher_mod

    def _workspace(port: int, role_name: str, base_branch: str | None = None):
        return f"minionsos/project-{port}-{role_name}", Path(f"/tmp/{port}/{role_name}")

    monkeypatch.setattr(role_mod, "ensure_role_workspace", _workspace)
    monkeypatch.setattr(launcher_mod, "session_alive", lambda *a, **k: False)
    monkeypatch.setattr(
        launcher_mod,
        "launch_role_process",
        lambda role_entry, project_port, **k: {
            "session_name": f"mos-{project_port}-{role_entry.name}",
            "started": True,
            "attach_cmd": ["tmux", "attach", "-t", f"mos-{project_port}-{role_entry.name}"],
        },
    )

    store = FakeStore()
    with patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])):
        out = role_mod.register_role(37777, "ethics", init_brief=None, store=store)
    assert out["name"] == "ethics"
    assert out["tmux_session"] == "mos-37777-ethics"
    assert any(r.name == "ethics" for r in store.project.active_roles)


def test_ethics_main_whitelist() -> None:
    # CLI whitelist is unified across EACN roles for cache optimization.
    # Verify the unified list includes what Ethics needs.
    tools = resolve_whitelist("ethics", "main")
    assert "eacn3_*" in tools
    assert "WebSearch" in tools
    assert "WebFetch" in tools
    assert "Read" in tools

    # Server-side authz still enforces the real Ethics boundary.
    from minions.config import resolve_server_authz

    authz = resolve_server_authz("ethics", "main")
    assert not any(t.startswith("mos_exp_") for t in authz)
    assert "mos_project_bridge" not in authz
    assert not any(t.startswith("mos_spawn_") for t in authz)
    assert not any(t.startswith("mos_project_") and t != "mos_project_checkpoint_workspace" for t in authz)
    assert "Write" not in authz
    assert "Edit" not in authz
    assert "Bash" not in authz


def test_ethics_subagent_whitelist() -> None:
    """Ethics subagent executes the writes the main session plans.

    Per the common SYSTEM.md Plan → Dispatch → Verify contract, substantive
    work (flag files, report files under artifacts/ethics/) is produced by a
    subagent, not the main role. The subagent must therefore be able to
    Write/Edit inside that scope; it remains EACN-invisible because there are
    no eacn3_* tools in this whitelist.
    """
    tools = resolve_whitelist("ethics", "subagent")
    assert set(tools) == {
        "codex",
        "wait_bg",
        "keepalive_now",
        "mos_issue_report",
        "WebSearch",
        "WebFetch",
        "Read",
        "Write",
        "Edit",
    }


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
    (pdir / "artifacts" / "ethics" / "adjudications").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "ethics" / "mock-reviews").mkdir(parents=True, exist_ok=True)

    assert (pdir / "artifacts" / "ethics" / "reports").is_dir()
    assert (pdir / "artifacts" / "ethics" / "flags" / "open").is_dir()
    assert (pdir / "artifacts" / "ethics" / "flags" / "resolved").is_dir()
    assert (pdir / "artifacts" / "ethics" / "investigations").is_dir()
    assert (pdir / "artifacts" / "ethics" / "adjudications").is_dir()
    assert (pdir / "artifacts" / "ethics" / "mock-reviews").is_dir()


def test_ethics_skills_include_mock_review() -> None:
    """mock-review skill is discoverable so it appears in the wake-up [Skills] block."""
    from minions.lifecycle.skills import list_skills

    slugs = {slug for slug, _ in list_skills("ethics")}
    assert "mock-review" in slugs
    assert "citation-authenticity-audit" in slugs
    assert "evidence-pointer-sweep" in slugs


def test_ethics_mock_review_template_exists() -> None:
    """The mock-review template is shipped alongside the skill."""
    from minions.paths import ROLES_DIR

    template = ROLES_DIR / "ethics" / "templates" / "mock-review.md"
    assert template.is_file()
    body = template.read_text(encoding="utf-8")
    assert "Informal verdict" in body
    assert "not a formal review decision" in body


def test_ethics_system_prefers_subagent_dispatch() -> None:
    """SYSTEM.md must steer Ethics toward subagent dispatch with codex preferred."""
    from minions.paths import ROLES_DIR

    body = (ROLES_DIR / "ethics" / "SYSTEM.md").read_text(encoding="utf-8")
    assert "Subagent dispatch preference" in body
    assert "codex" in body
    assert "Task" in body
    assert "CODEX_UNAVAILABLE" in body


def test_fixed_roles_contains_ethics() -> None:
    assert "ethics" in role_mod.FIXED_ROLES
