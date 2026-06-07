"""Tests for the orphan ``mos-{port}-*`` tmux-session sweep.

These tests pin down three contracts:

1. ``role_launcher.kill_project_sessions(port)`` matches sessions by
   ``mos-{port}-*`` prefix only, and reports the names it killed.
2. ``project_kill`` invokes the sweep after the recorded-roles loop
   and the result includes ``swept_tmux_sessions``.
3. ``project_revive`` invokes the sweep BEFORE relaunching, so a stale
   session cannot be silently re-attached by the launcher's
   ``has-session`` idempotency check.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from minions.lifecycle import project as proj_mod
from minions.lifecycle import role_launcher
from minions.state.store import ProjectEntry, RoleEntry, StateStore

# ---------------------------------------------------------------------------
# role_launcher.kill_project_sessions / list_project_sessions
# ---------------------------------------------------------------------------


def test_list_project_sessions_filters_by_port_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(role_launcher, "_have_tmux", lambda: True)

    listed_stdout = "\n".join(
        [
            "mos-37596-expert",
            "mos-37596-ethics",
            "mos-37596-expert-mathematician",
            "mos-12345-expert",  # different port — must be skipped
            "unrelated-session",
        ]
    )

    def fake_run(argv, **_kwargs):
        assert argv[0:3] == ["tmux", "ls", "-F"]
        result = MagicMock()
        result.returncode = 0
        result.stdout = listed_stdout
        return result

    monkeypatch.setattr(role_launcher.subprocess, "run", fake_run)

    names = role_launcher.list_project_sessions(37596)
    assert names == [
        "mos-37596-expert",
        "mos-37596-ethics",
        "mos-37596-expert-mathematician",
    ]


def test_list_project_sessions_returns_empty_when_no_tmux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(role_launcher, "_have_tmux", lambda: False)
    assert role_launcher.list_project_sessions(37596) == []


def test_kill_project_sessions_kills_all_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(role_launcher, "_have_tmux", lambda: True)

    listed_stdout = "mos-37596-expert\nmos-37596-ethics\nmos-99999-other\n"
    killed: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        if argv[:3] == ["tmux", "ls", "-F"]:
            result = MagicMock()
            result.returncode = 0
            result.stdout = listed_stdout
            return result
        if argv[:2] == ["tmux", "kill-session"]:
            killed.append(list(argv))
            result = MagicMock()
            result.returncode = 0
            return result
        raise AssertionError(f"unexpected argv: {argv}")

    monkeypatch.setattr(role_launcher.subprocess, "run", fake_run)

    swept = role_launcher.kill_project_sessions(37596)
    assert swept == ["mos-37596-expert", "mos-37596-ethics"]
    assert killed == [
        ["tmux", "kill-session", "-t", "mos-37596-expert"],
        ["tmux", "kill-session", "-t", "mos-37596-ethics"],
    ]


def test_kill_project_sessions_no_op_when_nothing_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(role_launcher, "_have_tmux", lambda: True)

    def fake_run(argv, **_kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "mos-99999-other\n"
        return result

    monkeypatch.setattr(role_launcher.subprocess, "run", fake_run)
    assert role_launcher.kill_project_sessions(37596) == []


# ---------------------------------------------------------------------------
# project_kill: orphan tmux sweep wired in
# ---------------------------------------------------------------------------


def test_project_kill_sweeps_orphan_tmux_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dismissed role records do not block tmux session cleanup.

    All recorded roles are ``state="dismissed", pid=None`` (so the
    pid-based stop loop is a no-op), but ``mos-{port}-*`` tmux sessions
    are still alive on the host. ``project_kill`` must sweep them.
    """
    port = 40130
    pdir = tmp_path / f"project_{port}"
    pdir.mkdir(parents=True)

    store = StateStore(path=tmp_path / "projects.json")
    entry = ProjectEntry(
        port=port,
        real_name="Orphan TMux",
        status="active",
        created="2026-05-26T00:00:00+00:00",
        current_branch=f"minionsos/project-{port}",
        # Roles are all dismissed with pid=None, so the pid stop loop is empty.
        active_roles=[
            RoleEntry(name="expert", state="dismissed", pid=None),
            RoleEntry(name="ethics", state="dismissed", pid=None),
        ],
    )
    store.add_project(entry)
    (pdir / "meta.json").write_text(
        json.dumps({**entry.model_dump(), "backend_pid": 111}, indent=2),
        encoding="utf-8",
    )

    sweep_calls: list[int] = []

    def fake_kill_project_sessions(p: int) -> list[str]:
        sweep_calls.append(p)
        return [f"mos-{p}-expert", f"mos-{p}-ethics", f"mos-{p}-stale-extra"]

    monkeypatch.setattr(proj_mod, "project_meta_json", lambda p: pdir / "meta.json")
    monkeypatch.setattr(proj_mod, "_stop_backend", lambda p, pid=None: True)
    monkeypatch.setattr(proj_mod, "_stop_role_process", lambda *args, **kw: "terminated")
    monkeypatch.setattr(
        "minions.lifecycle.role_launcher.kill_project_sessions",
        fake_kill_project_sessions,
    )

    result = proj_mod.project_kill(port, store=store)

    # Sweep was invoked exactly once on the right port.
    assert sweep_calls == [port]

    # Result reports the swept session names.
    assert result["swept_tmux_sessions"] == [
        f"mos-{port}-expert",
        f"mos-{port}-ethics",
        f"mos-{port}-stale-extra",
    ]

    # Recorded-role loop produced 0 entries (all were pid=None) — but the
    # status still flips to dormant and the meta is updated.
    assert result["roles"] == []
    assert result["status"] == "dormant"


def test_project_kill_sweep_failure_does_not_abort_kill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the orphan-tmux sweep raises, project_kill still completes.

    The sweep is best-effort cleanup, not a precondition for marking
    the project dormant.
    """
    port = 40131
    pdir = tmp_path / f"project_{port}"
    pdir.mkdir(parents=True)

    store = StateStore(path=tmp_path / "projects.json")
    entry = ProjectEntry(
        port=port,
        real_name="Sweep Boom",
        status="active",
        created="2026-05-26T00:00:00+00:00",
        current_branch=f"minionsos/project-{port}",
        active_roles=[],
    )
    store.add_project(entry)
    (pdir / "meta.json").write_text(
        json.dumps({**entry.model_dump(), "backend_pid": 222}),
        encoding="utf-8",
    )

    def boom(_p: int) -> list[str]:
        raise RuntimeError("tmux unavailable")

    monkeypatch.setattr(proj_mod, "project_meta_json", lambda p: pdir / "meta.json")
    monkeypatch.setattr(proj_mod, "_stop_backend", lambda p, pid=None: True)
    monkeypatch.setattr("minions.lifecycle.role_launcher.kill_project_sessions", boom)

    result = proj_mod.project_kill(port, store=store)
    assert result["status"] == "dormant"
    assert result["swept_tmux_sessions"] == []


# ---------------------------------------------------------------------------
# project_revive: stale tmux cleanup before relaunch
# ---------------------------------------------------------------------------


def test_project_revive_sweeps_stale_tmux_before_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_git_operations,
) -> None:
    """``launch_role_process`` is idempotent on ``has-session``: a stale
    tmux session would silently swallow the relaunch. ``project_revive``
    must sweep ``mos-{port}-*`` BEFORE invoking the launcher.
    """
    port = 40132

    # Use MINIONS_PROJECTS_ROOT from conftest's _isolate_projects_root
    import os

    projects_root = Path(os.environ["MINIONS_PROJECTS_ROOT"])
    pdir = projects_root / f"project_{port}"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "branches" / "shared").mkdir(parents=True, exist_ok=True)

    # Create parent_repo.git directory structure for git operations
    parent_repo = pdir / "parent_repo.git"
    parent_repo.mkdir(parents=True, exist_ok=True)
    (parent_repo / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    (parent_repo / "objects").mkdir(parents=True, exist_ok=True)
    (parent_repo / "HEAD").write_text("ref: refs/heads/main\n")

    store = StateStore(path=tmp_path / "projects.json")
    role = RoleEntry(name="expert", state="dismissed", pid=None)
    entry = ProjectEntry(
        port=port,
        real_name="Stale Tmux",
        status="dormant",
        created="2026-05-26T00:00:00+00:00",
        dormant_at="2026-05-26T00:00:00+00:00",
        current_branch=f"minionsos/project-{port}",
        active_roles=[role],
    )
    store.add_project(entry)
    (pdir / "meta.json").write_text(
        json.dumps({**entry.model_dump(), "backend_pid": None}, indent=2),
        encoding="utf-8",
    )

    # Track ordering: stale-sweep MUST happen before any launch.
    events: list[str] = []

    def fake_sweep(p: int) -> list[str]:
        events.append(f"sweep:{p}")
        return [f"mos-{p}-expert"]

    def fake_launch(role_entry, project_port: int, **_kw):
        events.append(f"launch:{role_entry.name}")
        return {"session_name": f"mos-{project_port}-{role_entry.name}", "started": True}

    fake_proc = MagicMock()
    fake_proc.pid = 9999

    # Stub everything that hits the network / disk lifecycle.
    monkeypatch.setattr(proj_mod, "project_meta_json", lambda p: pdir / "meta.json")
    # Patch helpers used through project_metadata and project_lifecycle.
    from minions.lifecycle import project_lifecycle, project_metadata

    def fake_read_meta_raw(p: int):
        import json

        path = pdir / "meta.json"
        return json.loads(path.read_text(encoding="utf-8"))

    monkeypatch.setattr(project_metadata, "project_meta_json", lambda p: pdir / "meta.json")
    monkeypatch.setattr(project_lifecycle, "read_meta_raw", fake_read_meta_raw)

    monkeypatch.setattr(proj_mod, "_start_backend", lambda p: fake_proc)
    monkeypatch.setattr(proj_mod, "_wait_for_health", lambda p: None)
    monkeypatch.setattr(proj_mod, "_migrate_legacy_memory_dirs", lambda p: None)
    monkeypatch.setattr(
        proj_mod,
        "_register_server",
        lambda p: ("srv-test", "srv-token"),
    )
    monkeypatch.setattr(
        proj_mod,
        "_register_gru_eacn_agent",
        lambda p, sid: ("gru", "gru-token"),
    )
    monkeypatch.setattr(
        proj_mod,
        "ensure_role_workspace",
        lambda *a, **kw: (f"minionsos/project-{port}-expert", pdir / "branches" / "expert"),
    )
    monkeypatch.setattr(
        "minions.lifecycle.agent_registry.register_project_role_agent",
        lambda port, name, server_id: ("role-token", []),
    )
    monkeypatch.setattr(proj_mod, "identity_map_for_meta", lambda p: {})

    # The two functions whose ordering matters.
    monkeypatch.setattr(
        "minions.lifecycle.role_launcher.kill_project_sessions",
        fake_sweep,
    )
    monkeypatch.setattr(
        "minions.lifecycle.role_launcher.launch_role_process",
        fake_launch,
    )

    proj_mod.project_revive(port, store=store)

    # Sweep happened, and happened BEFORE any launch.
    assert events[0] == f"sweep:{port}", f"sweep must run first, got events={events}"
    assert "launch:expert" in events
    assert events.index(f"sweep:{port}") < events.index("launch:expert")
