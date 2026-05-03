"""Unit tests for the Gru EACN pending journal and MCP polling adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from unittest.mock import patch

import pytest

from minions.gru.loop import GruLoop
from minions.lifecycle import gru_inbox
from minions.lifecycle.wakeup import WakeupScheduler
from minions.tools.mcp_server import GruInboxPollArgs, gru_inbox_poll


@dataclass
class FakeRole:
    name: str
    state: str = "active"
    poll_interval: str = "1m"


@dataclass
class FakeProject:
    port: int
    real_name: str = "Test"
    active_roles: list[FakeRole] = field(default_factory=list)


class FakeStore:
    def __init__(self, projects: list[FakeProject]) -> None:
        self._projects = projects

    def list_projects(self, filter: str = "active") -> list[FakeProject]:
        return list(self._projects)


# ─── gru_inbox module tests ──────────────────────────────────────────────────


class TestGruInbox:
    def test_append_and_read(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )
        port = 37596
        n = gru_inbox.append_events(
            port,
            [{"id": "e1", "content": "hi"}, {"id": "e2", "content": "ho"}],
        )
        assert n == 2
        unread = gru_inbox.read_unread(port)
        assert len(unread) == 2
        assert unread[0]["seq"] == 1
        assert unread[1]["seq"] == 2
        assert unread[0]["event"]["id"] == "e1"
        assert gru_inbox.unread_count(port) == 2

    def test_cursor_advances(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )
        port = 37596
        gru_inbox.append_events(port, [{"id": "a"}, {"id": "b"}, {"id": "c"}])
        unread = gru_inbox.read_unread(port)
        assert len(unread) == 3
        gru_inbox.mark_read(port, up_to_seq=2)
        assert gru_inbox.unread_count(port) == 1
        remaining = gru_inbox.read_unread(port)
        assert len(remaining) == 1
        assert remaining[0]["event"]["id"] == "c"

    def test_append_increments_seq_across_calls(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )
        port = 37596
        gru_inbox.append_events(port, [{"id": "a"}])
        gru_inbox.append_events(port, [{"id": "b"}])
        unread = gru_inbox.read_unread(port)
        assert [e["seq"] for e in unread] == [1, 2]

    def test_empty_noops(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )
        assert gru_inbox.append_events(37596, []) == 0
        assert gru_inbox.read_unread(37596) == []
        assert gru_inbox.unread_count(37596) == 0


# ─── Gru MCP adapter / scheduler boundary ───────────────────────────────────


class TestGruInboxPollAdapter:
    def test_poll_appends_to_pending_journal(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )

        def fake_poll(port, agent_id, timeout_secs=0, http_timeout=5.0):
            assert port == 37596
            assert agent_id == "gru"
            return {"events": [{"id": "m1", "text": "ping"}, {"id": "m2", "text": "pong"}]}

        with patch("minions.lifecycle.eacn_client.poll_events", side_effect=fake_poll):
            result = gru_inbox_poll(GruInboxPollArgs(port=37596))

        assert result["total"] == 2
        assert result["polled"] == 2
        unread = result["per_port"]["37596"]
        assert [e["event"]["id"] for e in unread] == ["m1", "m2"]

    def test_mark_read_advances_cursor_without_polling_eacn(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )
        gru_inbox.append_events(37596, [{"id": "m1"}, {"id": "m2"}])

        def fake_poll(port, agent_id, timeout_secs=0, http_timeout=5.0):
            raise AssertionError("mark_read=true must not drain EACN")

        with patch("minions.lifecycle.eacn_client.poll_events", side_effect=fake_poll):
            result = gru_inbox_poll(GruInboxPollArgs(port=37596, mark_read=True))

        assert result["marked_read"] is True
        assert result["total"] == 2
        assert gru_inbox.unread_count(37596) == 0

    def test_wakeup_scheduler_does_not_poll_gru_queue(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )
        project = FakeProject(port=37596, active_roles=[FakeRole("coder")])
        store = FakeStore([project])
        polled: list[str] = []

        def fake_poll(port, agent_id, timeout_secs=0, http_timeout=5.0):
            polled.append(agent_id)
            return {"events": []}

        sched = WakeupScheduler(store=store, invoke_fn=lambda *a, **kw: None)
        with patch("minions.lifecycle.wakeup.poll_events", side_effect=fake_poll):
            asyncio.run(sched.tick_once())

        assert "coder" in polled
        assert "gru" not in polled
        assert gru_inbox.read_unread(37596) == []


class TestGruLoopInboxWakeup:
    def test_monitor_uses_eacn3_pending_count_and_wakes_gru_without_draining(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )
        project = FakeProject(port=37596, active_roles=[])
        loop = GruLoop(heartbeat_interval=1)
        loop._store = FakeStore([project])
        loop._gru_hard_cooldown_seconds = 0
        loop._gru_drive_interval_seconds = 999
        loop._gru_monitor_started_ts = 0
        invocations: list[tuple[str, int, list[dict]]] = []

        def fake_invoke(role: str, port: int, events: list[dict], **kwargs):
            invocations.append((role, port, events))
            return {"deferred": False}

        with (
            patch("minions.gru.loop.backend_health", return_value=True),
            patch("minions.lifecycle.project.project_repair_eacn_agents", return_value={}),
            patch("minions.lifecycle.eacn_client.pending_event_counts", return_value={"gru": 1}),
            patch(
                "minions.lifecycle.eacn_client.poll_events",
                side_effect=AssertionError("monitor must not drain Gru EACN queue"),
            ),
            patch("minions.lifecycle.role.is_inflight", return_value=False),
            patch("minions.lifecycle.role.invoke_role_ephemeral", side_effect=fake_invoke),
        ):
            loop._tick()

        assert gru_inbox.unread_count(37596) == 0
        assert len(invocations) == 1
        role, port, events = invocations[0]
        assert role == "gru"
        assert port == 37596
        assert events[0]["type"] == "wake_signal"
        assert events[0]["kind"] == "gru_eacn_activity"
        assert events[0]["payload"]["unread_count"] == 1

    def test_monitor_does_not_mark_gru_entries_read(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )
        gru_inbox.append_events(37596, [{"id": "pending"}])
        project = FakeProject(port=37596, active_roles=[])
        loop = GruLoop(heartbeat_interval=1)
        loop._store = FakeStore([project])
        loop._gru_hard_cooldown_seconds = 0
        loop._gru_drive_interval_seconds = 999
        loop._gru_monitor_started_ts = 0

        with (
            patch("minions.gru.loop.backend_health", return_value=True),
            patch("minions.lifecycle.project.project_repair_eacn_agents", return_value={}),
            patch("minions.lifecycle.eacn_client.pending_event_counts", return_value={}),
            patch("minions.lifecycle.role.is_inflight", return_value=False),
            patch(
                "minions.lifecycle.role.invoke_role_ephemeral",
                return_value={"deferred": False},
            ),
        ):
            loop._tick()

        assert gru_inbox.unread_count(37596) == 1

    def test_monitor_does_not_wake_gru_when_no_unread(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )
        project = FakeProject(port=37596, active_roles=[])
        loop = GruLoop(heartbeat_interval=1)
        loop._store = FakeStore([project])

        with (
            patch("minions.gru.loop.backend_health", return_value=True),
            patch("minions.lifecycle.project.project_repair_eacn_agents", return_value={}),
            patch("minions.lifecycle.eacn_client.pending_event_counts", return_value={}),
            patch("minions.lifecycle.role.invoke_role_ephemeral") as invoke,
        ):
            loop._tick()

        invoke.assert_not_called()

    def test_monitor_autonomous_drive_after_drive_interval(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )
        project = FakeProject(port=37596, active_roles=[])
        loop = GruLoop(heartbeat_interval=1)
        loop._store = FakeStore([project])
        loop._gru_hard_cooldown_seconds = 0
        loop._gru_drive_interval_seconds = 0
        loop._gru_monitor_started_ts = 0
        invocations: list[list[dict]] = []

        def fake_invoke(role: str, port: int, events: list[dict], **kwargs):
            invocations.append(events)
            return {"deferred": False}

        with (
            patch("minions.gru.loop.backend_health", return_value=True),
            patch("minions.lifecycle.project.project_repair_eacn_agents", return_value={}),
            patch("minions.lifecycle.eacn_client.pending_event_counts", return_value={}),
            patch("minions.lifecycle.role.is_inflight", return_value=False),
            patch("minions.lifecycle.role.invoke_role_ephemeral", side_effect=fake_invoke),
        ):
            loop._tick()

        assert invocations
        assert invocations[0][0]["kind"] == "gru_autonomous_drive"


# ─── register_agent / register_server error reporting ────────────────────────


class TestRegisterErrorReporting:
    def test_register_agent_400_carries_body(self, monkeypatch) -> None:
        from minions.errors import BackendError
        from minions.lifecycle import eacn_client

        class FakeResp:
            status_code = 400
            text = '{"detail":"Server srv-xxx not registered"}'

            def json(self):
                return {"detail": "Server srv-xxx not registered"}

        monkeypatch.setattr(eacn_client.httpx, "post", lambda *a, **kw: FakeResp())
        with pytest.raises(BackendError) as ei:
            eacn_client.register_agent(port=37596, agent_id="gru", name="gru", server_id="srv-xxx")
        msg = str(ei.value)
        assert "HTTP 400" in msg
        assert "Server srv-xxx not registered" in msg
        assert "agent_id='gru'" in msg
