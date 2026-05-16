from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_agent_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests independent from the user's active Gru host."""
    monkeypatch.delenv("MINIONS_AGENT_HOST", raising=False)


@pytest.fixture(autouse=True)
def _isolate_projects_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Point ``projects_root()`` at a per-session tmp dir so tests that
    exercise registry / logs / inbox writes never leak into ``~`` (or wherever
    the real user has run MinionsOS).
    """
    root = tmp_path_factory.mktemp("projects-root")
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(root))


@pytest.fixture(autouse=True)
def _stub_ensure_role_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Default-stub filesystem-side role-workspace helpers so tests never
    touch the real parent repo or create runaway branches / directories.

    Tests that genuinely want real ``git worktree add`` behaviour can override
    the stubs inside the test body (patch takes precedence over earlier patch).
    """
    from minions import paths as paths_mod
    from minions.lifecycle import role as role_mod

    tmp_root = tmp_path_factory.mktemp("role-workspaces")

    def fake_ensure_role_workspace(
        port: int, role_name: str, base_branch: str | None = None
    ) -> tuple[str, Path]:
        branch = (
            f"minionsos/project-{port}"
            if role_name in {"gru", "main"}
            else f"minionsos/project-{port}-{role_name}"
        )
        path = tmp_root / f"p{port}" / role_name
        path.mkdir(parents=True, exist_ok=True)
        return branch, path

    def fake_project_scratchpad(port: int, role_name: str) -> Path:
        return tmp_root / f"p{port}" / role_name / ".minionsos" / "scratchpad.md"

    monkeypatch.setattr(role_mod, "ensure_role_workspace", fake_ensure_role_workspace)
    monkeypatch.setattr(paths_mod, "project_scratchpad", fake_project_scratchpad)
