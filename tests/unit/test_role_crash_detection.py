"""Tests for ephemeral role PID tracking, crash detection, in-flight guard.

Covers the P0 bugfix: role.py was not persisting the subprocess PID into
StateStore, so `gru/loop.py` always skipped the liveness check and the
3-strike dismissal path was unreachable. Also covers the in-flight guard
in the wakeup scheduler and proper log-fp lifecycle on reap.
"""

from __future__ import annotations

import asyncio
import warnings
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from minions.gru.loop import GruLoop
from minions.lifecycle import role as role_mod
from minions.lifecycle.wakeup import WakeupScheduler
from minions.state.store import ProjectEntry, RoleEntry


class FakeStore:
    def __init__(self) -> None:
        self.project = ProjectEntry(
            port=37596,
            real_name="T",
            status="active",
            created="2026-01-01T00:00:00Z",
            current_branch="minionsos/project-37596",
            active_roles=[
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
    yield
    with role_mod._INFLIGHT_LOCK:
        role_mod._INFLIGHT.clear()


@pytest.fixture(autouse=True)
def _isolate_wakeup_runtime(tmp_path: Path):
    with (
        patch(
            "minions.lifecycle.role_inbox.project_logs_dir",
            lambda port: tmp_path / f"project_{port}" / "logs",
        ),
        patch(
            "minions.lifecycle.wakeup.project_memory_dir",
            lambda port: tmp_path / f"project_{port}" / "memory",
        ),
        patch(
            "minions.lifecycle.wakeup.project_scratchpad",
            lambda port, role: tmp_path / f"project_{port}" / "memory" / f"{role}.md",
        ),
        patch("minions.lifecycle.wakeup.list_open_tasks", return_value=[]),
    ):
        yield


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
    # PID persisted.
    persisted = [u for u in store.upserts if u.name == "noter"][-1]
    assert persisted.pid == 9999
    assert persisted.spawned_at is not None


def test_crash_three_times_triggers_dismissal(tmp_path: Path, monkeypatch) -> None:
    """Simulate 3 role crashes within the rolling window → role dismissed."""
    store = FakeStore()
    # Mark role as running with a pid that is "not alive".
    store.upsert_role(
        37596,
        RoleEntry(name="noter", state="active", pid=424242, spawned_at="x"),
    )
    store.upserts.clear()

    monkeypatch.setattr("minions.gru.loop._pid_alive", lambda pid: False)
    monkeypatch.setattr("minions.gru.loop.backend_health", lambda port, timeout=3.0: True)

    loop = GruLoop(heartbeat_interval=1)
    loop._store = store  # inject

    # Three ticks in quick succession.
    for _ in range(3):
        loop._tick()

    # Should have flipped state to dismissed.
    dismissed = [u for u in store.upserts if u.state == "dismissed"]
    assert dismissed, f"expected dismissal, got upserts={store.upserts}"


def test_second_wakeup_while_inflight_is_deferred_not_dropped() -> None:
    """Second tick while first invocation in-flight: events must be deferred."""
    from dataclasses import dataclass, field

    @dataclass
    class FR:
        name: str
        state: str = "active"
        poll_interval: str = "1m"

    @dataclass
    class FP:
        port: int
        active_roles: list[FR] = field(default_factory=list)

    class S:
        def __init__(self) -> None:
            self._p = [FP(port=37596, active_roles=[FR("noter")])]

        def list_projects(self, filter: str = "active") -> list[FP]:
            return self._p

    calls: list[list[str]] = []

    def invoke(role: str, port: int, events: list[dict[str, Any]]) -> None:
        calls.append([e["id"] for e in events])

    sched = WakeupScheduler(store=S(), invoke_fn=invoke, cooldown_seconds=0)

    # Simulate tick 1 events.
    payload1 = {"events": [{"id": "a"}]}
    # Simulate tick 2 events.
    payload2 = {"events": [{"id": "b"}]}

    # Before tick 2, mark (port, noter) in-flight so dispatch is deferred.
    running_proc = _make_proc(pid=1, rc=None)
    # fake log_fp
    log_fp = MagicMock()

    with patch("minions.lifecycle.wakeup.poll_events", return_value=payload1):
        asyncio.run(sched.tick_once())
    assert calls == [["a"]]

    # Force the second tick to run (bypass cadence gate).
    sched._last_poll_ts.clear()
    with role_mod._INFLIGHT_LOCK:
        role_mod._INFLIGHT[(37596, "noter")] = (running_proc, log_fp)
    with patch("minions.lifecycle.wakeup.poll_events", return_value=payload2):
        asyncio.run(sched.tick_once())
    # No second dispatch — deferred, not dropped.
    assert calls == [["a"]]
    assert sched._pending.get((37596, "noter")) == [{"id": "b"}]

    # Now in-flight process "exits"; reap should clear it and next tick flushes.
    running_proc.poll.return_value = 0
    sched._last_poll_ts.clear()
    with patch("minions.lifecycle.wakeup.poll_events", return_value={"events": []}):
        asyncio.run(sched.tick_once())
    assert calls == [["a"], ["b"]]
    # log_fp was closed on reap.
    log_fp.close.assert_called()


def test_reap_closes_log_fp_no_resource_warning(tmp_path: Path) -> None:
    """Verify real file handle is closed on reap — no ResourceWarning."""
    store = FakeStore()
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
