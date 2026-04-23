"""Unit tests for the Python-level WakeupScheduler."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

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

    def test_only_active_roles_polled(self) -> None:
        project = FakeProject(
            port=37596,
            active_roles=[FakeRole("noter"), FakeRole("coder", state="dismissed")],
        )
        store = FakeStore([project])
        polled: list[str] = []

        def fake_poll(port: int, agent_id: str, **_: Any) -> dict:
            polled.append(agent_id)
            return {"events": []}

        sched = WakeupScheduler(store=store, invoke_fn=lambda *a: None)
        with patch("minions.lifecycle.wakeup.poll_events", side_effect=fake_poll):
            _run(sched.tick_once())
        assert polled == ["noter"]
