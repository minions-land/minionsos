"""Unit tests for the Python-level WakeupScheduler."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from minions.lifecycle import role_inbox
from minions.lifecycle.wakeup import WakeupScheduler, _EventDedup


@dataclass
class FakeRole:
    name: str
    state: str = "active"
    poll_interval: str = "1m"


@dataclass
class FakeProject:
    port: int
    active_roles: list[FakeRole] = field(default_factory=list)


class FakeStore:
    def __init__(self, projects: list[FakeProject]) -> None:
        self._projects = projects

    def list_projects(self, filter: str = "active") -> list[FakeProject]:
        return [p for p in self._projects if True]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


@pytest.fixture(autouse=True)
def _isolate_runtime_paths(tmp_path: Path):
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


# ─────────────────────────────────────────────────────────────────────────────


class TestDedup:
    def test_new_events_are_new(self) -> None:
        d = _EventDedup()
        assert d.is_new(1, "noter", "e1") is True
        assert d.is_new(1, "noter", "e1") is False
        assert d.is_new(1, "noter", "e2") is True


class TestWakeup:
    def test_empty_poll_does_not_spawn(self) -> None:
        project = FakeProject(port=37596, active_roles=[FakeRole("noter")])
        store = FakeStore([project])

        calls: list[Any] = []

        def invoke(role: str, port: int, events: list[dict]) -> None:
            calls.append((role, port, events))

        sched = WakeupScheduler(store=store, invoke_fn=invoke)
        with patch("minions.lifecycle.wakeup.poll_events", return_value={"events": []}):
            count = _run(sched.tick_once())
        assert count == 0
        assert calls == []

    def test_events_spawn_once(self) -> None:
        project = FakeProject(port=37596, active_roles=[FakeRole("noter")])
        store = FakeStore([project])
        calls: list[Any] = []

        def invoke(role: str, port: int, events: list[dict]) -> None:
            calls.append((role, port, [e["id"] for e in events]))

        sched = WakeupScheduler(store=store, invoke_fn=invoke)
        payload = {"events": [{"id": "e1", "x": 1}, {"id": "e2", "x": 2}]}
        with patch("minions.lifecycle.wakeup.poll_events", return_value=payload):
            count = _run(sched.tick_once())
        assert count == 1
        assert calls == [("noter", 37596, ["e1", "e2"])]

    def test_duplicate_events_deduped(self) -> None:
        project = FakeProject(port=37596, active_roles=[FakeRole("noter")])
        store = FakeStore([project])
        calls: list[Any] = []

        def invoke(role: str, port: int, events: list[dict]) -> None:
            calls.append([e["id"] for e in events])

        sched = WakeupScheduler(store=store, invoke_fn=invoke)
        payload = {"events": [{"id": "e1", "x": 1}]}

        # First tick triggers, second tick (same event) does not.
        with patch("minions.lifecycle.wakeup.poll_events", return_value=payload):
            c1 = _run(sched.tick_once())
            # Force cadence bypass: reset last-poll ts.
            sched._last_poll_ts.clear()
            c2 = _run(sched.tick_once())
        assert c1 == 1
        assert c2 == 0
        assert calls == [["e1"]]

    def test_schedulable_roles_polled(self) -> None:
        project = FakeProject(
            port=37596,
            active_roles=[
                FakeRole("noter"),
                FakeRole("writer", state="sleeping"),
                FakeRole("coder", state="dismissed"),
            ],
        )
        store = FakeStore([project])
        polled: list[str] = []

        def fake_poll(port: int, agent_id: str, **_: Any) -> dict:
            polled.append(agent_id)
            return {"events": []}

        sched = WakeupScheduler(store=store, invoke_fn=lambda *a: None)
        with patch("minions.lifecycle.wakeup.poll_events", side_effect=fake_poll):
            _run(sched.tick_once())
        # "gru" is polled once per project for the passive-mailbox inbox;
        # active/sleeping roles are polled, dismissed roles are skipped.
        assert "noter" in polled
        assert "writer" in polled
        assert "coder" not in polled

    def test_public_open_task_scan_wakes_all_roles_without_agent_event(self) -> None:
        project = FakeProject(
            port=37596,
            active_roles=[FakeRole("noter"), FakeRole("coder")],
        )
        store = FakeStore([project])
        calls: list[tuple[str, list[dict[str, Any]]]] = []

        def invoke(role: str, port: int, events: list[dict]) -> None:
            calls.append((role, events))

        task = {
            "id": "t-coding",
            "domains": ["coding"],
            "content": {"description": "fix implementation"},
            "invited_agent_ids": [],
        }
        sched = WakeupScheduler(store=store, invoke_fn=invoke, cooldown_seconds=0)
        with (
            patch("minions.lifecycle.wakeup.poll_events", return_value={"events": []}),
            patch("minions.lifecycle.wakeup.list_open_tasks", return_value=[task]),
        ):
            count = _run(sched.tick_once())

        assert count == 2
        assert [call[0] for call in calls] == ["noter", "coder"]
        by_role = {role: events[0] for role, events in calls}
        assert by_role["coder"]["id"] == "open-task:t-coding:coder"
        assert by_role["coder"]["task_id"] == "t-coding"
        assert by_role["coder"]["payload"]["matched_by"] == "domain"
        assert by_role["noter"]["payload"]["matched_by"] == "public_open_task"
        assert by_role["coder"]["payload"]["source"] == "tasks_open_scan"

    def test_public_open_task_wakes_all_roles_even_when_noter_present(self) -> None:
        project = FakeProject(
            port=37596,
            active_roles=[FakeRole("noter"), FakeRole("coder")],
        )
        store = FakeStore([project])
        calls: list[str] = []

        def invoke(role: str, port: int, events: list[dict]) -> None:
            calls.append(role)

        task = {
            "id": "t-generic",
            "domains": ["unknown-domain"],
            "content": {"description": "triage this"},
        }
        sched = WakeupScheduler(store=store, invoke_fn=invoke, cooldown_seconds=0)
        with (
            patch("minions.lifecycle.wakeup.poll_events", return_value={"events": []}),
            patch("minions.lifecycle.wakeup.list_open_tasks", return_value=[task]),
        ):
            count = _run(sched.tick_once())

        assert count == 2
        assert calls == ["noter", "coder"]

    def test_invited_open_task_wakes_only_invited_role(self) -> None:
        project = FakeProject(
            port=37596,
            active_roles=[FakeRole("noter"), FakeRole("coder"), FakeRole("writer")],
        )
        store = FakeStore([project])
        calls: list[str] = []

        def invoke(role: str, port: int, events: list[dict]) -> None:
            calls.append(role)

        task = {
            "id": "t-invited",
            "domains": ["writing"],
            "content": {"description": "specific request"},
            "invited_agent_ids": ["coder"],
        }
        sched = WakeupScheduler(store=store, invoke_fn=invoke, cooldown_seconds=0)
        with (
            patch("minions.lifecycle.wakeup.poll_events", return_value={"events": []}),
            patch("minions.lifecycle.wakeup.list_open_tasks", return_value=[task]),
        ):
            count = _run(sched.tick_once())

        assert count == 1
        assert calls == ["coder"]

    def test_inflight_deferral_survives_scheduler_restart(self) -> None:
        project = FakeProject(port=37596, active_roles=[FakeRole("noter")])
        store = FakeStore([project])
        calls: list[list[str]] = []

        def invoke(role: str, port: int, events: list[dict]) -> None:
            calls.append([e["id"] for e in events])

        first = WakeupScheduler(store=store, invoke_fn=invoke, cooldown_seconds=0)
        with (
            patch("minions.lifecycle.wakeup.poll_events", return_value={"events": [{"id": "e1"}]}),
            patch("minions.lifecycle.role.is_inflight", return_value=True),
        ):
            count = _run(first.tick_once())

        assert count == 0
        assert calls == []
        assert role_inbox.read_events(37596, "noter") == [{"id": "e1"}]

        second = WakeupScheduler(store=store, invoke_fn=invoke, cooldown_seconds=0)
        with (
            patch("minions.lifecycle.wakeup.poll_events", return_value={"events": []}),
            patch("minions.lifecycle.role.is_inflight", return_value=False),
        ):
            count = _run(second.tick_once())

        assert count == 1
        assert calls == [["e1"]]
        assert role_inbox.read_events(37596, "noter") == []

    def test_dispatch_failure_leaves_events_buffered(self) -> None:
        project = FakeProject(port=37596, active_roles=[FakeRole("noter")])
        store = FakeStore([project])

        def invoke(role: str, port: int, events: list[dict]) -> None:
            raise RuntimeError("spawn failed")

        sched = WakeupScheduler(store=store, invoke_fn=invoke, cooldown_seconds=0)
        with patch(
            "minions.lifecycle.wakeup.poll_events",
            return_value={"events": [{"id": "boom"}]},
        ):
            count = _run(sched.tick_once())

        assert count == 0
        assert role_inbox.read_events(37596, "noter") == [{"id": "boom"}]
