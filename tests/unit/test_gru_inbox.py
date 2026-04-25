"""Unit tests for the Gru passive-mailbox inbox and WakeupScheduler integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from unittest.mock import patch

import pytest

from minions.lifecycle import gru_inbox
from minions.lifecycle.wakeup import WakeupScheduler


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


# ─── WakeupScheduler gru-drain integration ──────────────────────────────────


class TestWakeupGruDrain:
    def test_drain_appends_to_inbox(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )
        project = FakeProject(port=37596, active_roles=[])
        store = FakeStore([project])

        # Simulate: poll_events returns 2 events for the "gru" agent,
        # nothing for roles (there are none).
        def fake_poll(port, agent_id, timeout_secs=0, http_timeout=5.0):
            if agent_id == "gru":
                return {"events": [{"id": "m1", "text": "ping"}, {"id": "m2", "text": "pong"}]}
            return {"events": []}

        sched = WakeupScheduler(store=store, invoke_fn=lambda *a, **kw: None)
        with patch("minions.lifecycle.wakeup.poll_events", side_effect=fake_poll):
            asyncio.run(sched.tick_once())

        unread = gru_inbox.read_unread(37596)
        assert [e["event"]["id"] for e in unread] == ["m1", "m2"]

    def test_drain_dedupes(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )
        project = FakeProject(port=37596, active_roles=[])
        store = FakeStore([project])

        def fake_poll(port, agent_id, timeout_secs=0, http_timeout=5.0):
            if agent_id == "gru":
                return {"events": [{"id": "m1"}]}
            return {"events": []}

        sched = WakeupScheduler(store=store, invoke_fn=lambda *a, **kw: None)
        with patch("minions.lifecycle.wakeup.poll_events", side_effect=fake_poll):
            asyncio.run(sched.tick_once())
            # Force the gru inbox cadence gate open for the second tick so we
            # re-enter _drain_gru_inbox and exercise the LRU dedup path.
            sched._last_poll_ts.clear()
            asyncio.run(sched.tick_once())

        unread = gru_inbox.read_unread(37596)
        # Same event id m1 returned twice, but dedup keeps it to one.
        assert len(unread) == 1

    def test_drain_respects_cadence(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "minions.lifecycle.gru_inbox.project_logs_dir",
            lambda port: tmp_path / f"p{port}" / "logs",
        )
        project = FakeProject(port=37596, active_roles=[])
        store = FakeStore([project])

        calls = {"n": 0}

        def fake_poll(port, agent_id, timeout_secs=0, http_timeout=5.0):
            if agent_id == "gru":
                calls["n"] += 1
            return {"events": []}

        sched = WakeupScheduler(store=store, invoke_fn=lambda *a, **kw: None)
        with patch("minions.lifecycle.wakeup.poll_events", side_effect=fake_poll):
            asyncio.run(sched.tick_once())
            asyncio.run(sched.tick_once())
            asyncio.run(sched.tick_once())
        # Second and third ticks should be gated off; only the first call polls.
        assert calls["n"] == 1


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
