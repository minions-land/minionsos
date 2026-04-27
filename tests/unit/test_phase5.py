"""Phase 5 tests: MCP failure handling, viz data, lifecycle hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import patch

import pytest

from minions.lifecycle.failure import (
    FailureLog,
    ToolFailureKind,
    classify_failure,
    with_retry,
)
from minions.lifecycle.hooks import HookRegistry, LifecycleEvent
from minions.lifecycle.viz_data import viz_all_projects, viz_project_snapshot

# ── Fakes for viz tests ──────────────────────────────────────────────────────


@dataclass
class FakeRole:
    name: str
    state: str = "active"
    last_seen: str | None = None
    current_task: str | None = None


@dataclass
class FakeProject:
    port: int
    real_name: str = "test-project"
    status: str = "active"
    active_roles: list[FakeRole] = field(default_factory=list)


class FakeStore:
    def __init__(self, projects: list[FakeProject]) -> None:
        self._projects = projects

    def list_projects(self, filter: str = "all") -> list[FakeProject]:
        if filter == "all":
            return list(self._projects)
        return [p for p in self._projects if p.status == filter]

    def get_project(self, port: int) -> FakeProject | None:
        return next((p for p in self._projects if p.port == port), None)


# ── ToolFailureKind ──────────────────────────────────────────────────────────


class TestToolFailureKind:
    def test_enum_values(self) -> None:
        assert ToolFailureKind.transient.value == "transient"
        assert ToolFailureKind.permanent.value == "permanent"
        assert ToolFailureKind.auth.value == "auth"
        assert ToolFailureKind.timeout.value == "timeout"


# ── classify_failure ─────────────────────────────────────────────────────────


class TestClassifyFailure:
    def test_timeout_classified(self) -> None:
        exc = TimeoutError("connection timed out")
        f = classify_failure("my_tool", exc)
        assert f.kind == ToolFailureKind.timeout
        assert f.retryable is True

    def test_connection_error_is_transient(self) -> None:
        exc = ConnectionError("refused")
        f = classify_failure("my_tool", exc)
        assert f.kind == ToolFailureKind.transient
        assert f.retryable is True

    def test_permission_error_is_auth(self) -> None:
        exc = PermissionError("forbidden")
        f = classify_failure("my_tool", exc)
        assert f.kind == ToolFailureKind.auth
        assert f.retryable is False

    def test_generic_error_is_permanent(self) -> None:
        exc = ValueError("bad input")
        f = classify_failure("my_tool", exc)
        assert f.kind == ToolFailureKind.permanent
        assert f.retryable is False

    def test_failure_records_tool_name(self) -> None:
        f = classify_failure("eacn3_post", RuntimeError("boom"))
        assert f.tool_name == "eacn3_post"


# ── with_retry ───────────────────────────────────────────────────────────────


class TestWithRetry:
    def test_succeeds_on_first_try(self) -> None:
        calls = []

        def fn() -> str:
            calls.append(1)
            return "ok"

        result = with_retry(fn, max_retries=3)
        assert result == "ok"
        assert len(calls) == 1

    def test_retries_on_transient(self) -> None:
        attempts = []

        def fn() -> str:
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("transient")
            return "recovered"

        result = with_retry(fn, max_retries=3, delay=0)
        assert result == "recovered"
        assert len(attempts) == 3

    def test_gives_up_after_max_retries(self) -> None:
        def fn() -> str:
            raise ConnectionError("always fails")

        with pytest.raises(ConnectionError):
            with_retry(fn, max_retries=2, delay=0)

    def test_no_retry_on_permanent(self) -> None:
        attempts = []

        def fn() -> str:
            attempts.append(1)
            raise ValueError("permanent")

        with pytest.raises(ValueError):
            with_retry(fn, max_retries=3, delay=0)
        assert len(attempts) == 1


# ── FailureLog ───────────────────────────────────────────────────────────────


class TestFailureLog:
    def test_record_and_recent(self) -> None:
        log = FailureLog(max_entries=10)
        f = classify_failure("tool_a", ConnectionError("down"))
        log.record(f)
        assert len(log.recent()) == 1
        assert log.recent()[0].tool_name == "tool_a"

    def test_max_entries_enforced(self) -> None:
        log = FailureLog(max_entries=3)
        for i in range(5):
            log.record(classify_failure(f"tool_{i}", RuntimeError("err")))
        assert len(log.recent()) == 3

    def test_summary(self) -> None:
        log = FailureLog()
        log.record(classify_failure("a", ConnectionError("x")))
        log.record(classify_failure("b", TimeoutError("y")))
        s = log.summary()
        assert s["total"] == 2
        assert "transient" in s["by_kind"]
        assert "timeout" in s["by_kind"]


# ── LifecycleEvent + HookRegistry ────────────────────────────────────────────


class TestLifecycleEvent:
    def test_enum_values(self) -> None:
        assert LifecycleEvent.project_created.value == "project_created"
        assert LifecycleEvent.role_dispatched.value == "role_dispatched"
        assert LifecycleEvent.review_completed.value == "review_completed"


class TestHookRegistry:
    def test_register_and_fire(self) -> None:
        reg = HookRegistry()
        received: list[dict] = []
        reg.register(LifecycleEvent.project_created, lambda data: received.append(data))
        reg.fire(LifecycleEvent.project_created, {"port": 37596})
        assert len(received) == 1
        assert received[0]["port"] == 37596

    def test_multiple_hooks_same_event(self) -> None:
        reg = HookRegistry()
        a: list[str] = []
        b: list[str] = []
        reg.register(LifecycleEvent.role_dispatched, lambda d: a.append("a"))
        reg.register(LifecycleEvent.role_dispatched, lambda d: b.append("b"))
        reg.fire(LifecycleEvent.role_dispatched, {})
        assert a == ["a"]
        assert b == ["b"]

    def test_hook_error_does_not_propagate(self) -> None:
        reg = HookRegistry()
        ok: list[str] = []
        reg.register(LifecycleEvent.project_closed, lambda d: 1 / 0)
        reg.register(LifecycleEvent.project_closed, lambda d: ok.append("ok"))
        reg.fire(LifecycleEvent.project_closed, {})
        assert ok == ["ok"]

    def test_unregistered_event_is_noop(self) -> None:
        reg = HookRegistry()
        reg.fire(LifecycleEvent.review_completed, {})


# ── Viz data producers ───────────────────────────────────────────────────────


class TestVizProjectSnapshot:
    def test_snapshot_has_required_keys(self) -> None:
        project = FakeProject(
            port=37596,
            active_roles=[FakeRole("noter"), FakeRole("coder")],
        )
        store = FakeStore([project])
        with patch("minions.lifecycle.viz_data.backend_health", return_value=False):
            snap = viz_project_snapshot(37596, store)
        required = {"port", "name", "status", "backend_alive", "agents", "roles"}
        assert required <= snap.keys()

    def test_snapshot_includes_roles(self) -> None:
        project = FakeProject(
            port=37596,
            active_roles=[FakeRole("noter"), FakeRole("coder")],
        )
        store = FakeStore([project])
        with patch("minions.lifecycle.viz_data.backend_health", return_value=False):
            snap = viz_project_snapshot(37596, store)
        assert len(snap["roles"]) == 2

    def test_snapshot_unknown_port_returns_none(self) -> None:
        store = FakeStore([])
        snap = viz_project_snapshot(99999, store)
        assert snap is None


class TestVizAllProjects:
    def test_returns_list_of_snapshots(self) -> None:
        projects = [
            FakeProject(port=37596, active_roles=[FakeRole("noter")]),
            FakeProject(port=37597, active_roles=[]),
        ]
        store = FakeStore(projects)
        with patch("minions.lifecycle.viz_data.backend_health", return_value=False):
            snaps = viz_all_projects(store)
        assert len(snaps) == 2
        assert snaps[0]["port"] == 37596
