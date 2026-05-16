"""Unit tests for minions.tools.await_events."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _env_vars(monkeypatch, tmp_path):
    monkeypatch.setenv("MINIONS_PROJECT_PORT", "39999")
    monkeypatch.setenv("MINIONS_AGENT_ID", "test-agent")
    monkeypatch.setenv("MINIONS_WORKSPACE", str(tmp_path / "workspace"))
    (tmp_path / "workspace").mkdir()
    monkeypatch.chdir(tmp_path)


def _make_poll_response(events):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"events": events, "count": len(events)}

    return FakeResp()


def _make_tasks_response(tasks):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return tasks

    return FakeResp()


class TestBlocksUntilEvents:
    def test_returns_on_first_nonempty_poll(self):
        from minions.tools.await_events import await_events

        fake_event = {
            "type": "task_broadcast",
            "task_id": "t-1",
            "payload": {"domains": ["x"], "budget": 0},
        }
        with patch("minions.tools.await_events.httpx.get") as mock_get:
            mock_get.return_value = _make_poll_response([fake_event])
            result = await_events()

        assert result["count"] == 1
        assert result["events"][0]["event"]["task_id"] == "t-1"

    def test_skips_empty_polls_until_events(self):
        from minions.tools.await_events import await_events

        fake_event = {
            "type": "direct_message",
            "task_id": "t-2",
            "payload": {"from": "gru", "content": "hello"},
        }
        responses = [
            _make_poll_response([]),
            _make_poll_response([]),
            _make_poll_response([fake_event]),
        ]
        with patch("minions.tools.await_events.httpx.get", side_effect=responses):
            result = await_events()

        assert result["count"] == 1
        assert result["events"][0]["suggested_tool"] == "eacn3_send_message"

    def test_never_returns_count_zero(self):
        from minions.tools.await_events import await_events

        fake_event = {"type": "task_timeout", "task_id": "t-3", "payload": {}}
        with patch("minions.tools.await_events.httpx.get") as mock_get:
            mock_get.return_value = _make_poll_response([fake_event])
            result = await_events()

        assert result["count"] > 0


class TestIdleCheck:
    def test_idle_check_fires_after_threshold(self):
        """After 5 empty polls, idle check queries tasks and returns synthetic event."""
        from minions.tools.await_events import await_events

        delegated_task = {
            "id": "t-delegated",
            "status": "bidding",
            "initiator_id": "test-agent",
            "bids": [],
        }

        call_count = [0]

        def mock_get(url, **kwargs):
            call_count[0] += 1
            if "/api/events/" in url:
                return _make_poll_response([])
            elif "/api/tasks" in url:
                return _make_tasks_response([delegated_task])
            return _make_poll_response([])

        with patch("minions.tools.await_events.httpx.get", side_effect=mock_get):
            result = await_events()

        assert result["count"] == 1
        assert result["events"][0]["event"]["type"] == "idle_check"
        assert "t-delegated" in result["events"][0]["event"]["payload"]["delegated_tasks"]

    def test_no_idle_swallowed_silently(self):
        """If idle check finds nothing, keep polling (don't return to LLM)."""
        from minions.tools.await_events import await_events

        call_count = [0]

        def mock_get(url, **kwargs):
            call_count[0] += 1
            if "/api/events/" in url:
                # First 5+5 polls empty, then return an event
                if call_count[0] <= 12:  # 5 polls + 1 task query + 5 polls + 1 task query
                    return _make_poll_response([])
                return _make_poll_response(
                    [
                        {
                            "type": "task_broadcast",
                            "task_id": "t-finally",
                            "payload": {"domains": ["x"], "budget": 0},
                        }
                    ]
                )
            elif "/api/tasks" in url:
                return _make_tasks_response([])  # no-idle: nothing to do
            return _make_poll_response([])

        with patch("minions.tools.await_events.httpx.get", side_effect=mock_get):
            result = await_events()

        # Should have skipped the no-idle and continued until real event
        assert result["events"][0]["event"]["type"] == "task_broadcast"
        assert result["events"][0]["event"]["task_id"] == "t-finally"


class TestHeartbeat:
    def test_heartbeat_written_every_cycle(self, tmp_path):
        from minions.tools.await_events import await_events

        workspace = tmp_path / "workspace"
        responses = [
            _make_poll_response([]),
            _make_poll_response([{"type": "task_timeout", "task_id": "t-z", "payload": {}}]),
        ]
        with patch("minions.tools.await_events.httpx.get", side_effect=responses):
            await_events()

        hb = workspace / ".minionsos" / "heartbeat"
        assert hb.exists()
        data = json.loads(hb.read_text())
        assert data["agent_id"] == "test-agent"
        assert "alive_at" in data

    def test_no_crash_without_workspace(self, monkeypatch):
        monkeypatch.delenv("MINIONS_WORKSPACE", raising=False)
        from minions.tools.await_events import await_events

        fake_event = {"type": "task_timeout", "task_id": "t-z", "payload": {}}
        with patch("minions.tools.await_events.httpx.get") as mock_get:
            mock_get.return_value = _make_poll_response([fake_event])
            result = await_events()

        assert result["count"] == 1


class TestSuggestedActions:
    @pytest.mark.parametrize(
        "event_type,expected_tool,expected_urgency",
        [
            ("task_broadcast", "eacn3_submit_bid", "high"),
            ("direct_message", "eacn3_send_message", "high"),
            ("subtask_completed", "eacn3_get_task_results", "high"),
            ("bid_request_confirmation", "eacn3_confirm_budget", "high"),
            ("result_submitted", "eacn3_get_task_results", "high"),
            ("task_collected", "eacn3_get_task_results", "medium"),
            ("discussion_update", "eacn3_get_task", "medium"),
            ("task_timeout", None, "low"),
        ],
    )
    def test_event_type_mapping(self, event_type, expected_tool, expected_urgency):
        from minions.tools.await_events import _build_suggested_action

        event = {
            "type": event_type,
            "task_id": "t-test",
            "payload": {
                "from": "x",
                "content": "y",
                "domains": ["d"],
                "budget": 0,
                "subtask_id": "t-sub",
                "agent_id": "a",
            },
        }
        result = _build_suggested_action(event)
        assert result["suggested_tool"] == expected_tool
        assert result["urgency"] == expected_urgency

    def test_bid_result_accepted(self):
        from minions.tools.await_events import _build_suggested_action

        event = {"type": "bid_result", "task_id": "t-1", "payload": {"accepted": True}}
        result = _build_suggested_action(event)
        assert result["urgency"] == "high"

    def test_bid_result_rejected(self):
        from minions.tools.await_events import _build_suggested_action

        event = {
            "type": "bid_result",
            "task_id": "t-1",
            "payload": {"accepted": False, "reason": "low rep"},
        }
        result = _build_suggested_action(event)
        assert result["urgency"] == "low"


class TestEnvValidation:
    def test_missing_port_raises(self, monkeypatch):
        monkeypatch.delenv("MINIONS_PROJECT_PORT", raising=False)
        from minions.tools.await_events import await_events

        with pytest.raises(RuntimeError, match="MINIONS_PROJECT_PORT"):
            await_events()

    def test_missing_agent_id_raises(self, monkeypatch):
        monkeypatch.delenv("MINIONS_AGENT_ID", raising=False)
        from minions.tools.await_events import await_events

        with pytest.raises(RuntimeError, match="MINIONS_AGENT_ID"):
            await_events()
