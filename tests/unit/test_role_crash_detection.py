"""Tests for ephemeral role PID tracking, crash detection, in-flight guard.

Covers the P0 bugfix: role.py was not persisting the subprocess PID into
StateStore, so `gru/loop.py` always skipped the liveness check and the
3-strike dismissal path was unreachable. Also covers the in-flight guard
for concurrent invocations and proper log-fp lifecycle on reap.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from minions.gru.loop import GruLoop
from minions.lifecycle import role as role_mod
from minions.state.store import ProjectEntry, RoleEntry


class FakeStore:
    def __init__(self, roles: list[RoleEntry] | None = None) -> None:
        self.project = ProjectEntry(
            port=37596,
            real_name="T",
            status="active",
            created="2026-01-01T00:00:00Z",
            current_branch="minionsos/project-37596",
            active_roles=roles
            or [
                RoleEntry(name="noter", state="active", pid=None, spawned_at="x"),
            ],
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

    def list_projects(self, filter: str = "active") -> list[ProjectEntry]:
        return [self.project]


@pytest.fixture(autouse=True)
def _clear_inflight() -> None:
    with role_mod._INFLIGHT_LOCK:
        role_mod._INFLIGHT.clear()
        role_mod._STARTING.clear()
    yield
    with role_mod._INFLIGHT_LOCK:
        role_mod._INFLIGHT.clear()
        role_mod._STARTING.clear()


def _make_proc(pid: int, rc: int | None = None) -> MagicMock:
    proc = MagicMock()
    proc.pid = pid
    proc.poll.return_value = rc
    return proc


def test_invoke_persists_pid_and_spawned_at(tmp_path: Path) -> None:
    store = FakeStore()
    proc = _make_proc(pid=9999, rc=None)  # still running
    with (
        patch("minions.lifecycle.role.subprocess.Popen", return_value=proc),
        patch("minions.lifecycle.role.project_workspace", return_value=tmp_path),
        patch("minions.lifecycle.role.project_role_log", return_value=tmp_path / "role-noter.log"),
    ):
        out = role_mod.invoke_role_ephemeral("noter", 37596, [{"id": "e1"}], store=store)
    assert out["pid"] == 9999
    assert out["deferred"] is False
    persisted = [u for u in store.upserts if u.name == "noter"][-1]
    assert persisted.state == "active"
    assert persisted.pid == 9999
    assert persisted.spawned_at is not None


def test_reaper_does_not_clear_newer_persisted_pid() -> None:
    store = FakeStore()
    store.upsert_role(
        37596,
        RoleEntry(name="noter", state="active", pid=2222, spawned_at="new"),
    )
    old_proc = _make_proc(pid=1111, rc=0)
    log_fp = MagicMock()

    with role_mod._INFLIGHT_LOCK:
        role_mod._INFLIGHT[(37596, "noter")] = (old_proc, log_fp)

    reaped = role_mod.reap_finished(store=store)

    assert reaped == [(37596, "noter", 0)]
    log_fp.close.assert_called_once()
    role = store.get_project(37596).active_roles[0]  # type: ignore[union-attr]
    assert role.state == "active"
    assert role.pid == 2222


def test_reaper_clears_each_reaped_role_with_its_own_pid() -> None:
    store = FakeStore(
        roles=[
            RoleEntry(name="noter", state="active", pid=1111, spawned_at="x"),
            RoleEntry(name="coder", state="active", pid=2222, spawned_at="x"),
        ]
    )
    noter_proc = _make_proc(pid=1111, rc=0)
    coder_proc = _make_proc(pid=2222, rc=0)
    noter_log = MagicMock()
    coder_log = MagicMock()

    with role_mod._INFLIGHT_LOCK:
        role_mod._INFLIGHT[(37596, "noter")] = (noter_proc, noter_log)
        role_mod._INFLIGHT[(37596, "coder")] = (coder_proc, coder_log)

    reaped = role_mod.reap_finished(store=store)

    assert sorted(reaped) == [(37596, "coder", 0), (37596, "noter", 0)]
    roles = {role.name: role for role in store.get_project(37596).active_roles}  # type: ignore[union-attr]
    assert roles["noter"].state == "sleeping"
    assert roles["noter"].pid is None
    assert roles["coder"].state == "sleeping"
    assert roles["coder"].pid is None


def test_concurrent_invoke_for_same_role_defers_second_launch(tmp_path: Path) -> None:
    import threading

    store = FakeStore()
    proc = _make_proc(pid=9998, rc=None)
    entered = threading.Event()
    release = threading.Event()

    def fake_popen(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return proc

    first_result: dict[str, object] = {}

    def first_call() -> None:
        first_result.update(
            role_mod.invoke_role_ephemeral("noter", 37596, [{"id": "e1"}], store=store)
        )

    with (
        patch("minions.lifecycle.role.subprocess.Popen", side_effect=fake_popen) as popen,
        patch("minions.lifecycle.role.project_workspace", return_value=tmp_path),
        patch("minions.lifecycle.role.project_role_log", return_value=tmp_path / "role-noter.log"),
    ):
        thread = threading.Thread(target=first_call)
        thread.start()
        assert entered.wait(timeout=5)
        second = role_mod.invoke_role_ephemeral("noter", 37596, [{"id": "e2"}], store=store)
        release.set()
        thread.join(timeout=5)

    assert first_result["deferred"] is False
    assert second["deferred"] is True
    assert popen.call_count == 1


def test_crash_three_times_triggers_dismissal(tmp_path: Path, monkeypatch) -> None:
    """Simulate 3 role crashes within the rolling window → role dismissed."""
    store = FakeStore()
    store.upsert_role(
        37596,
        RoleEntry(name="noter", state="active", pid=424242, spawned_at="x"),
    )
    store.upserts.clear()

    monkeypatch.setattr("minions.gru.loop._pid_alive", lambda pid: False)
    monkeypatch.setattr("minions.gru.loop.backend_health", lambda port, timeout=3.0: True)
    monkeypatch.setattr(
        "minions.lifecycle.project.project_repair_eacn_agents",
        lambda port, store=None: None,
    )
    monkeypatch.setattr(
        "minions.lifecycle.health.project_logs_dir",
        lambda port: tmp_path / f"project_{port}" / "logs",
    )

    loop = GruLoop(heartbeat_interval=1)
    loop._store = store  # inject

    for _ in range(3):
        loop._tick()

    dismissed = [u for u in store.upserts if u.state == "dismissed"]
    assert dismissed, f"expected dismissal, got upserts={store.upserts}"
    events_path = tmp_path / "project_37596" / "logs" / "health_events.jsonl"
    assert "role_crash" in events_path.read_text(encoding="utf-8")


def test_reap_closes_log_fp_no_resource_warning(tmp_path: Path) -> None:
    """Verify real file handle is closed on reap — no ResourceWarning."""
    store = FakeStore()
    store.upsert_role(
        37596,
        RoleEntry(name="noter", state="active", pid=7777, spawned_at="x"),
    )
    log_path = tmp_path / "role-noter.log"
    real_fp = log_path.open("a", encoding="utf-8")

    proc = _make_proc(pid=7777, rc=0)  # exited
    with role_mod._INFLIGHT_LOCK:
        role_mod._INFLIGHT[(37596, "noter")] = (proc, real_fp)

    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        reaped = role_mod.reap_finished(store=store)

    assert reaped == [(37596, "noter", 0)]
    assert real_fp.closed
    persisted = store.project.active_roles[0]
    assert persisted.state == "sleeping"
    assert persisted.pid is None
