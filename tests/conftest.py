from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Import git mock fixture
from tests.git_mock import mock_git_operations  # noqa: F401


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Reap any ``mos-*`` tmux sessions left behind by tests.

    Stubbing _spawn_tmux is the norm in tests, but a few smoke / integration
    paths invoke the real launcher; if they crash mid-test the session leaks
    into the host and Gru's monitor will keep emitting book-lint warnings
    against pytest tempdirs that no longer exist. Best-effort sweep here
    closes that gap.
    """
    try:
        result = subprocess.run(["tmux", "ls"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return
    if result.returncode != 0:
        return
    for line in (result.stdout or "").splitlines():
        name = line.split(":", 1)[0]
        if name.startswith("mos-"):
            subprocess.run(
                ["tmux", "kill-session", "-t", name],
                capture_output=True,
                check=False,
            )


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

    monkeypatch.setattr(role_mod, "ensure_role_workspace", fake_ensure_role_workspace)
