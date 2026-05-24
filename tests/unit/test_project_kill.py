"""Tests for hard-stopping project runtime without wiping EACN state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minions.lifecycle import project as proj_mod
from minions.state.store import ProjectEntry, RoleEntry, StateStore


def test_project_kill_stops_runtime_and_preserves_eacn_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = 40121
    pdir = tmp_path / f"project_{port}"
    eacn_db = pdir / "eacn3_data" / "eacn3.db"
    eacn_db.parent.mkdir(parents=True)
    eacn_db.write_text("keep", encoding="utf-8")

    store = StateStore(path=tmp_path / "projects.json")
    entry = ProjectEntry(
        port=port,
        real_name="Kill Runtime",
        status="active",
        created="2026-04-28T00:00:00+00:00",
        current_branch=f"minionsos/project-{port}",
        active_roles=[
            RoleEntry(name="coder", state="active", pid=222, spawned_at="x"),
            RoleEntry(name="writer", state="sleeping", pid=None),
        ],
    )
    store.add_project(entry)

    meta = pdir / "meta.json"
    meta.write_text(
        json.dumps(
            {
                **entry.model_dump(),
                "backend_pid": 111,
                "eacn3_server_id": "srv-abc",
                "eacn3_server_token": "srv-token",
                "gru_agent_id": "gru",
                "gru_agent_token": "gru-token",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    stopped_backends: list[tuple[int, int | None]] = []
    stopped_roles: list[tuple[int, str, int | None]] = []
    monkeypatch.setattr(proj_mod, "project_meta_json", lambda p: pdir / "meta.json")
    monkeypatch.setattr(
        proj_mod,
        "_stop_backend",
        lambda p, pid=None: stopped_backends.append((p, pid)),
    )
    monkeypatch.setattr(
        proj_mod,
        "_stop_role_process",
        lambda p, role, pid=None: stopped_roles.append((p, role, pid)) or "terminated",
    )

    result = proj_mod.project_kill(port, store=store)

    assert result["status"] == "dormant"
    assert stopped_backends == [(port, 111)]
    assert stopped_roles == [(port, "coder", 222)]
    assert eacn_db.read_text(encoding="utf-8") == "keep"
    assert not store.is_port_retired(port)

    updated = store.get_project(port)
    assert updated is not None
    assert updated.status == "dormant"
    assert [role.state for role in updated.active_roles] == ["dismissed", "dismissed"]
    assert [role.pid for role in updated.active_roles] == [None, None]

    updated_meta = json.loads(meta.read_text(encoding="utf-8"))
    assert updated_meta["status"] == "dormant"
    assert updated_meta["backend_pid"] is None
    assert updated_meta["eacn3_server_id"] == "srv-abc"
    assert updated_meta["gru_agent_token"] == "gru-token"


def test_project_kill_rejects_closed_project(tmp_path: Path) -> None:
    port = 40122
    store = StateStore(path=tmp_path / "projects.json")
    store.add_project(
        ProjectEntry(
            port=port,
            real_name="Closed",
            status="closed",
            created="2026-04-28T00:00:00+00:00",
            current_branch=f"minionsos/project-{port}",
        )
    )

    with pytest.raises(proj_mod.ProjectError, match="already closed"):
        proj_mod.project_kill(port, store=store)


def test_project_kill_keeps_project_active_when_backend_cannot_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = 40123
    pdir = tmp_path / f"project_{port}"
    pdir.mkdir(parents=True)
    store = StateStore(path=tmp_path / "projects.json")
    entry = ProjectEntry(
        port=port,
        real_name="Kill Fails",
        status="active",
        created="2026-04-28T00:00:00+00:00",
        current_branch=f"minionsos/project-{port}",
        active_roles=[RoleEntry(name="noter", state="sleeping")],
    )
    store.add_project(entry)
    (pdir / "meta.json").write_text(
        json.dumps({**entry.model_dump(), "backend_pid": None}),
        encoding="utf-8",
    )
    monkeypatch.setattr(proj_mod, "project_meta_json", lambda p: pdir / "meta.json")
    monkeypatch.setattr(proj_mod, "_stop_backend", lambda port, pid=None: False)

    with pytest.raises(proj_mod.ProjectError, match="Could not stop backend"):
        proj_mod.project_kill(port, store=store)

    assert store.get_project(port).status == "active"  # type: ignore[union-attr]


def test_stop_backend_falls_back_to_verified_port_listener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = 40124
    calls: list[int] = []

    # Port is not free until the listener PID 222 is terminated. Use a
    # state-driven check so the GitHub Issue #23 retry loop (up to 1 s of
    # 100 ms polls before falling back to listener discovery) reads
    # naturally rather than depending on a fixed-length iterator.
    def fake_port_is_free(_p: int) -> bool:
        return 222 in calls

    monkeypatch.setattr(proj_mod, "_port_is_free", fake_port_is_free)
    monkeypatch.setattr(proj_mod, "_backend_listener_pids", lambda p: [222])
    monkeypatch.setattr(proj_mod, "_is_minions_backend_pid", lambda pid, p: True)
    monkeypatch.setattr(proj_mod, "_terminate_backend_pid", lambda p, pid: calls.append(pid))
    # Skip real sleeps inside the retry loop so the test stays fast.
    monkeypatch.setattr(proj_mod.time, "sleep", lambda _s: None)

    assert proj_mod._stop_backend(port, None) is True
    assert calls == [222]


def test_stop_backend_retries_port_check_after_stale_pid_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub Issue #23: when the recorded PID is stale (process already gone)
    and the kernel briefly holds the socket in TIME_WAIT, the first
    _port_is_free check can return False even though the next call
    (within 100 ms) returns True. _stop_backend must retry the port-free
    probe inside the recorded-PID branch so a stale-PID stop is idempotent
    on the first call and does not fall through to listener discovery.
    """
    port = 40125
    free_checks: list[bool] = []
    listener_calls: list[int] = []

    def fake_port_is_free(_p: int) -> bool:
        # First two checks: still in TIME_WAIT. Third onwards: free.
        free_checks.append(True)
        return len(free_checks) > 2

    monkeypatch.setattr(proj_mod, "_port_is_free", fake_port_is_free)
    # Fallback listener discovery should NOT be invoked: the retry loop
    # inside the recorded-PID branch must succeed first.
    monkeypatch.setattr(
        proj_mod, "_backend_listener_pids", lambda p: listener_calls.append(p) or []
    )
    monkeypatch.setattr(proj_mod, "_terminate_backend_pid", lambda p, pid: None)
    monkeypatch.setattr(proj_mod.time, "sleep", lambda _s: None)

    assert proj_mod._stop_backend(port, 96003) is True
    # Retry loop polled at least 3 times to clear the TIME_WAIT.
    assert len(free_checks) >= 3
    # We did not enter the listener-discovery fallback.
    assert listener_calls == []
