"""Phase 2 tests: wakeup classes, cooldown, time/human triggers, context control."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from minions.lifecycle.wakeup import WakeupClass, WakeupScheduler

# ── Fakes ────────────────────────────────────────────────────────────────────


@dataclass
class FakeRole:
    name: str
    state: str = "active"
    poll_interval: str = "1m"
    time_trigger_interval: str | None = None


@dataclass
class FakeProject:
    port: int
    active_roles: list[FakeRole] = field(default_factory=list)


class FakeStore:
    def __init__(self, projects: list[FakeProject]) -> None:
        self._projects = projects

    def list_projects(self, filter: str = "active") -> list[FakeProject]:
        return list(self._projects)

    def get_project(self, port: int) -> FakeProject | None:
        return next((p for p in self._projects if p.port == port), None)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


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


# ── WakeupClass enum ────────────────────────────────────────────────────────


class TestWakeupClass:
    def test_enum_values(self) -> None:
        assert WakeupClass.event.value == "event"
        assert WakeupClass.time.value == "time"
        assert WakeupClass.human.value == "human"


# ── Cooldown ─────────────────────────────────────────────────────────────────


class TestCooldown:
    def test_cooldown_prevents_rapid_dispatch(self) -> None:
        project = FakeProject(port=37596, active_roles=[FakeRole("noter")])
        store = FakeStore([project])
        calls: list[tuple[str, int]] = []

        def invoke(role: str, port: int, events: list[dict]) -> None:
            calls.append((role, port))

        sched = WakeupScheduler(
            store=store,
            invoke_fn=invoke,
            cooldown_seconds=60,
        )
        payload = {"events": [{"id": "e1"}]}
        with patch("minions.lifecycle.wakeup.poll_events", return_value=payload):
            _run(sched.tick_once())
            assert len(calls) == 1

            # Reset poll ts so cadence check passes, but cooldown should block.
            sched._last_poll_ts.clear()
            payload2 = {"events": [{"id": "e2"}]}
            with patch(
                "minions.lifecycle.wakeup.poll_events",
                return_value=payload2,
            ):
                _run(sched.tick_once())
            # Second dispatch blocked by cooldown.
            assert len(calls) == 1

    def test_cooldown_allows_after_expiry(self) -> None:
        project = FakeProject(port=37596, active_roles=[FakeRole("noter")])
        store = FakeStore([project])
        calls: list[tuple[str, int]] = []

        def invoke(role: str, port: int, events: list[dict]) -> None:
            calls.append((role, port))

        sched = WakeupScheduler(
            store=store,
            invoke_fn=invoke,
            cooldown_seconds=0,
        )
        payload1 = {"events": [{"id": "e1"}]}
        payload2 = {"events": [{"id": "e2"}]}
        with patch("minions.lifecycle.wakeup.poll_events", return_value=payload1):
            _run(sched.tick_once())
        sched._last_poll_ts.clear()
        with patch("minions.lifecycle.wakeup.poll_events", return_value=payload2):
            _run(sched.tick_once())
        assert len(calls) == 2


# ── Human-triggered wakeup ───────────────────────────────────────────────────


class TestHumanTrigger:
    def test_trigger_role_dispatches(self) -> None:
        project = FakeProject(port=37596, active_roles=[FakeRole("noter")])
        store = FakeStore([project])
        calls: list[tuple[str, int, list[dict]]] = []

        def invoke(role: str, port: int, events: list[dict], **kw: Any) -> None:
            calls.append((role, port, events))

        sched = WakeupScheduler(
            store=store,
            invoke_fn=invoke,
            cooldown_seconds=0,
        )
        sched.trigger_role(37596, "noter", reason="user requested review")
        assert len(calls) == 1
        assert calls[0][0] == "noter"
        assert calls[0][1] == 37596
        evt = calls[0][2][0]
        assert evt["type"] == "human_trigger"
        assert "user requested review" in evt["reason"]

    def test_trigger_role_respects_cooldown(self) -> None:
        project = FakeProject(port=37596, active_roles=[FakeRole("noter")])
        store = FakeStore([project])
        calls: list[Any] = []

        def invoke(role: str, port: int, events: list[dict], **kw: Any) -> None:
            calls.append(1)

        sched = WakeupScheduler(
            store=store,
            invoke_fn=invoke,
            cooldown_seconds=9999,
        )
        sched.trigger_role(37596, "noter", reason="first")
        sched.trigger_role(37596, "noter", reason="second")
        assert len(calls) == 1

    def test_trigger_role_unknown_role_raises(self) -> None:
        store = FakeStore([FakeProject(port=37596, active_roles=[])])
        sched = WakeupScheduler(store=store, cooldown_seconds=0)
        with pytest.raises(ValueError, match="not found"):
            sched.trigger_role(37596, "ghost", reason="test")


# ── Time-triggered wakeup ────────────────────────────────────────────────────


class TestTimeTrigger:
    def test_time_trigger_fires_without_events(self) -> None:
        project = FakeProject(
            port=37596,
            active_roles=[FakeRole("noter", time_trigger_interval="1m")],
        )
        store = FakeStore([project])
        calls: list[tuple[str, int, list[dict]]] = []

        def invoke(role: str, port: int, events: list[dict], **kw: Any) -> None:
            calls.append((role, port, events))

        sched = WakeupScheduler(
            store=store,
            invoke_fn=invoke,
            cooldown_seconds=0,
        )
        # Simulate that the time trigger interval has elapsed by backdating.
        sched._last_time_trigger_ts[(37596, "noter")] = time.monotonic() - 120
        empty = {"events": []}
        with patch("minions.lifecycle.wakeup.poll_events", return_value=empty):
            count = _run(sched.tick_once())
        assert count == 1
        assert calls[0][2][0]["type"] == "time_trigger"

    def test_time_trigger_skipped_before_interval(self) -> None:
        project = FakeProject(
            port=37596,
            active_roles=[FakeRole("noter", time_trigger_interval="5m")],
        )
        store = FakeStore([project])
        calls: list[Any] = []

        def invoke(role: str, port: int, events: list[dict], **kw: Any) -> None:
            calls.append(1)

        sched = WakeupScheduler(
            store=store,
            invoke_fn=invoke,
            cooldown_seconds=0,
        )
        # Last time trigger was just now — should not fire again.
        sched._last_time_trigger_ts[(37596, "noter")] = time.monotonic()
        empty = {"events": []}
        with patch("minions.lifecycle.wakeup.poll_events", return_value=empty):
            count = _run(sched.tick_once())
        assert count == 0
        assert calls == []


# ── Dispatch logging includes wakeup class ───────────────────────────────────


class TestDispatchLogging:
    def test_dispatch_logs_wakeup_class(self) -> None:
        project = FakeProject(port=37596, active_roles=[FakeRole("noter")])
        store = FakeStore([project])

        def invoke(role: str, port: int, events: list[dict], **kw: Any) -> None:
            pass

        sched = WakeupScheduler(
            store=store,
            invoke_fn=invoke,
            cooldown_seconds=0,
        )
        payload = {"events": [{"id": "e1"}]}
        with (
            patch(
                "minions.lifecycle.wakeup.poll_events",
                return_value=payload,
            ),
            patch("minions.lifecycle.wakeup.logger") as mock_log,
        ):
            _run(sched.tick_once())
        info_calls = [c for c in mock_log.info.call_args_list if "wakeup_class=" in str(c)]
        assert len(info_calls) >= 1


# ── Context entry control ────────────────────────────────────────────────────


class TestContextEntryControl:
    def test_dispatch_passes_wakeup_class_env(self) -> None:
        project = FakeProject(port=37596, active_roles=[FakeRole("noter")])
        store = FakeStore([project])
        captured_env: dict[str, str] = {}

        def invoke(
            role: str,
            port: int,
            events: list[dict],
            extra_env: dict[str, str] | None = None,
            **kw: Any,
        ) -> None:
            if extra_env:
                captured_env.update(extra_env)

        sched = WakeupScheduler(
            store=store,
            invoke_fn=invoke,
            cooldown_seconds=0,
        )
        payload = {"events": [{"id": "e1"}]}
        with patch("minions.lifecycle.wakeup.poll_events", return_value=payload):
            _run(sched.tick_once())
        assert captured_env.get("MINIONS_WAKEUP_CLASS") == "event"
