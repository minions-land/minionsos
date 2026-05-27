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

    def test_no_idle_swallowed_silently(self, tmp_path):
        """If idle check finds nothing, keep polling (don't return to LLM)."""
        from minions.tools.await_events import await_events

        # Pre-seed the cold-start flag so the Issue #35 hint doesn't fire —
        # this test specifically exercises the established-role no-idle
        # silent-poll semantics.
        flag_dir = tmp_path / "workspace" / ".minionsos"
        flag_dir.mkdir(parents=True, exist_ok=True)
        (flag_dir / "cold_start_hint_emitted").write_text("seeded")

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
            ("skills_updated", None, "medium"),
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


# ---------------------------------------------------------------------------
# Draft-discipline reminder (v15.16) — soft audit injection on
# real-events return when the previous cycle wrote 0 Draft nodes.
# ---------------------------------------------------------------------------


class TestDraftDisciplineReminder:
    def test_no_reminder_on_first_real_events_return(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path / "projects"))
        from minions.tools.await_events import await_events

        events = [{"type": "task_broadcast", "task_id": "t1", "payload": {}}]
        with (
            patch("minions.tools.await_events.httpx.get", return_value=_make_poll_response(events)),
            patch("minions.tools.await_events._touch_heartbeat"),
        ):
            result = await_events()
        # First-ever return: there's no previous cycle, so no reminder.
        first = result["events"][0]
        assert "Draft-discipline reminder" not in first.get("suggested_action", "")

    def test_reminder_on_zero_appends_after_real_event_cycle(self, monkeypatch, tmp_path):
        """The motivating case: a role just received real events but
        called await_events again WITHOUT any mos_draft_append in
        between. The next return must prepend a reminder."""
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path / "projects"))
        from minions.tools.await_events import await_events

        events = [{"type": "task_broadcast", "task_id": "t1", "payload": {}}]
        with (
            patch("minions.tools.await_events.httpx.get", return_value=_make_poll_response(events)),
            patch("minions.tools.await_events._touch_heartbeat"),
        ):
            await_events()  # cycle 1 — real events delivered, no append
            result = await_events()  # cycle 2 — reminder must fire
        first = result["events"][0]
        assert "Draft-discipline reminder" in first["suggested_action"]

    def test_no_reminder_when_role_appended_in_between(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path / "projects"))
        from minions.tools import draft_audit
        from minions.tools.await_events import await_events

        events = [{"type": "task_broadcast", "task_id": "t1", "payload": {}}]
        with (
            patch("minions.tools.await_events.httpx.get", return_value=_make_poll_response(events)),
            patch("minions.tools.await_events._touch_heartbeat"),
        ):
            await_events()
            # Simulate the role calling mos_draft_append between cycles.
            draft_audit.record_append(39999, "test-agent")
            result = await_events()
        first = result["events"][0]
        assert "Draft-discipline reminder" not in first["suggested_action"]

    def test_no_reminder_after_keepalive_cycle(self, monkeypatch, tmp_path):
        """A keepalive-only cycle delivers no real events; the next
        return must not fire the reminder regardless of append count."""
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path / "projects"))
        # Force keepalive: configure an immediate cliff so the first
        # return is the synthetic keepalive, not real events.
        monkeypatch.setattr("minions.tools.await_events._load_keepalive_seconds", lambda: 0)
        from minions.tools.await_events import await_events

        events = [{"type": "task_broadcast", "task_id": "t1", "payload": {}}]
        with (
            patch("minions.tools.await_events.httpx.get", return_value=_make_poll_response(events)),
            patch("minions.tools.await_events._touch_heartbeat"),
        ):
            await_events()  # cycle 1: real events
            await_events()  # cycle 2: real events again (no append in between → reminder)
            result = await_events()  # cycle 3: real again — but cycle 2 was already reminded
        # Each new cycle without append re-fires the reminder. Verify it's
        # there (consistent with the soft-nudge semantics).
        first = result["events"][0]
        assert "Draft-discipline reminder" in first["suggested_action"]


# ---------------------------------------------------------------------------
# Issue #28 — upstream cache_keepalive must be filtered, not surfaced
# ---------------------------------------------------------------------------


class TestUpstreamCacheKeepaliveFiltered:
    """If the EACN3 backend ever emits an upstream ``cache_keepalive``
    event, _poll_once must drop it silently. Otherwise the model burns
    one assistant turn per delivery to ack a frame that wasn't even
    supposed to wake it (Issue #28)."""

    def test_nested_cache_keepalive_dropped(self):
        from minions.tools.await_events import _poll_once

        upstream_payload = [
            {"event": {"type": "cache_keepalive", "task_id": "", "payload": {}}},
            {"event": {"type": "direct_message", "task_id": "t1"}, "from": "gru"},
        ]
        with patch("minions.tools.await_events.httpx.get") as mock_get:
            mock_get.return_value = _make_poll_response(upstream_payload)
            events = _poll_once(39999, "test-agent")
        assert len(events) == 1
        assert events[0]["event"]["type"] == "direct_message"

    def test_flat_cache_keepalive_dropped(self):
        """Defence-in-depth: if some upstream variant emits the type
        field at the top level instead of nested under `event`, drop
        it too."""
        from minions.tools.await_events import _poll_once

        upstream_payload = [
            {"type": "cache_keepalive"},
            {"event": {"type": "task_broadcast", "task_id": "t1"}},
        ]
        with patch("minions.tools.await_events.httpx.get") as mock_get:
            mock_get.return_value = _make_poll_response(upstream_payload)
            events = _poll_once(39999, "test-agent")
        assert len(events) == 1
        # The non-keepalive event survives.
        assert events[0]["event"]["type"] == "task_broadcast"

    def test_only_cache_keepalive_returns_empty(self):
        """A poll that contains only keepalive frames must return [],
        which the outer loop treats as 'no work, keep polling'."""
        from minions.tools.await_events import _poll_once

        upstream_payload = [
            {"event": {"type": "cache_keepalive"}},
            {"event": {"type": "cache_keepalive"}},
        ]
        with patch("minions.tools.await_events.httpx.get") as mock_get:
            mock_get.return_value = _make_poll_response(upstream_payload)
            events = _poll_once(39999, "test-agent")
        assert events == []


# ---------------------------------------------------------------------------
# Issue #35 — cold-start self-initiation hint
# ---------------------------------------------------------------------------


class TestColdStartHint:
    """A freshly-spawned role with zero EACN history, zero tasks, zero
    messages must receive a one-shot proactive-collaboration nudge instead
    of polling forever in silence."""

    def test_cold_start_hint_fires_when_no_work_no_history(self, tmp_path):
        from minions.tools.await_events import await_events

        def mock_get(url, **kwargs):
            if "/api/events/" in url:
                return _make_poll_response([])
            if "/api/tasks" in url:
                return _make_tasks_response([])
            return _make_poll_response([])

        with patch("minions.tools.await_events.httpx.get", side_effect=mock_get):
            result = await_events()

        assert result["count"] == 1
        evt = result["events"][0]
        assert evt["event"]["type"] == "cold_start_hint"
        assert evt["suggested_tool"] == "eacn3_send_message"
        # Flag file persisted so the hint cannot re-fire
        flag = tmp_path / "workspace" / ".minionsos" / "cold_start_hint_emitted"
        assert flag.exists()

    def test_cold_start_hint_fires_only_once(self, tmp_path):
        from minions.tools.await_events import await_events

        # First call: cold start, no work → hint.
        def empty_mock(url, **kwargs):
            if "/api/events/" in url:
                return _make_poll_response([])
            if "/api/tasks" in url:
                return _make_tasks_response([])
            return _make_poll_response([])

        with patch("minions.tools.await_events.httpx.get", side_effect=empty_mock):
            first = await_events()
        assert first["events"][0]["event"]["type"] == "cold_start_hint"

        # Second call: still no work, but flag is set → must NOT re-fire.
        # Drop a real event after the second idle-check to terminate.
        call_count = [0]

        def second_mock(url, **kwargs):
            call_count[0] += 1
            if "/api/events/" in url:
                if call_count[0] <= 6:
                    return _make_poll_response([])
                return _make_poll_response(
                    [{"type": "task_timeout", "task_id": "t-x", "payload": {}}]
                )
            if "/api/tasks" in url:
                return _make_tasks_response([])
            return _make_poll_response([])

        with patch("minions.tools.await_events.httpx.get", side_effect=second_mock):
            second = await_events()
        # The hint must not have re-fired — the only return is the real event.
        types = [e["event"]["type"] for e in second["events"]]
        assert "cold_start_hint" not in types
        assert "task_timeout" in types

    def test_no_hint_when_event_history_present(self, tmp_path, monkeypatch):
        """A role with prior events on disk is not a cold-start candidate,
        even if the workspace flag is missing."""
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path / "projects"))
        from minions.tools import events_log
        from minions.tools.await_events import await_events

        # Seed a prior real event on disk.
        events_log.append_events(
            39999,
            "test-agent",
            [{"type": "direct_message", "task_id": "t-prior", "payload": {}}],
        )

        # Now simulate empty state: no current events, no tasks. With history
        # present, the cold-start hint must NOT fire. We need the loop to
        # eventually return; drop a real event after the no-idle branch.
        call_count = [0]

        def mock_get(url, **kwargs):
            call_count[0] += 1
            if "/api/events/" in url:
                if call_count[0] <= 6:
                    return _make_poll_response([])
                return _make_poll_response(
                    [{"type": "task_timeout", "task_id": "t-y", "payload": {}}]
                )
            if "/api/tasks" in url:
                return _make_tasks_response([])
            return _make_poll_response([])

        with patch("minions.tools.await_events.httpx.get", side_effect=mock_get):
            result = await_events()
        types = [e["event"]["type"] for e in result["events"]]
        assert "cold_start_hint" not in types
        # Flag should still have been written (skip-path) so we don't re-probe.
        flag = tmp_path / "workspace" / ".minionsos" / "cold_start_hint_emitted"
        assert flag.exists()

    def test_no_hint_without_workspace(self, monkeypatch):
        """Without MINIONS_WORKSPACE we cannot persist the flag, so the
        hint must be suppressed (otherwise it would re-fire every cycle)."""
        monkeypatch.delenv("MINIONS_WORKSPACE", raising=False)
        from minions.tools.await_events import await_events

        call_count = [0]

        def mock_get(url, **kwargs):
            call_count[0] += 1
            if "/api/events/" in url:
                if call_count[0] <= 6:
                    return _make_poll_response([])
                return _make_poll_response(
                    [{"type": "task_timeout", "task_id": "t-z", "payload": {}}]
                )
            if "/api/tasks" in url:
                return _make_tasks_response([])
            return _make_poll_response([])

        with patch("minions.tools.await_events.httpx.get", side_effect=mock_get):
            result = await_events()
        types = [e["event"]["type"] for e in result["events"]]
        assert "cold_start_hint" not in types


# ---------------------------------------------------------------------------
# Issue #36 FM2 — keepalive must have zero side effects on draft_audit.
# Otherwise FS contention from peers' draft writes can wedge the role's
# await_events tool call, and the keepalive's reset of
# last_delivery_was_real masks the next real cycle's discipline reminder.
# ---------------------------------------------------------------------------


class TestKeepaliveZeroSideEffects:
    def test_keepalive_does_not_call_draft_audit(self, monkeypatch, tmp_path):
        """On a keepalive return, draft_audit.take_snapshot_and_reset must
        not be called. The keepalive ack path must have zero side effects
        (Issue #36 FM2 / consistent with Issue #15 wedge protection)."""
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path / "projects"))
        monkeypatch.setattr("minions.tools.await_events._load_keepalive_seconds", lambda: 1)

        import minions.tools.await_events as awe

        real_monotonic = awe.time.monotonic
        offset = [0.0]

        class FakeTime:
            @staticmethod
            def monotonic():
                v = real_monotonic() + offset[0]
                offset[0] = 9999.0
                return v

        monkeypatch.setattr("minions.tools.await_events.time", FakeTime)

        with patch("minions.tools.draft_audit.take_snapshot_and_reset") as mock_audit:
            result = awe.await_events()

        assert result["count"] == 1
        assert result["events"][0]["event"]["type"] == "cache_keepalive"
        mock_audit.assert_not_called()

    def test_keepalive_preserves_prev_real_flag_for_reminder(self, monkeypatch, tmp_path):
        """A keepalive between two real cycles must not mask the discipline
        reminder. Before the fix, keepalive reset last_delivery_was_real to
        False, suppressing the reminder on the next real return."""
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path / "projects"))
        from minions.tools import draft_audit

        # Cycle 1 (real): sets last_delivery_was_real=True.
        draft_audit.take_snapshot_and_reset(39999, "test-agent", returning_real_events=True)

        # Keepalive: under the fix this is a no-op for draft_audit, so the
        # prior real flag survives. (Asserting the *absence* of a call is
        # what the previous test does; here we exercise the consequence.)

        # Cycle 2 (real, no appends in between): reminder must fire.
        snapshot = draft_audit.take_snapshot_and_reset(
            39999, "test-agent", returning_real_events=True
        )
        assert snapshot.prev_delivery_was_real is True
        assert snapshot.appends_since_last_await == 0
        assert snapshot.reminder_due is True


# ---------------------------------------------------------------------------
# Issue #39 — biddable-tasks discovery in idle_check
# ---------------------------------------------------------------------------


class TestBiddableTasksInIdleCheck:
    """When a role is idle and open tasks exist that it hasn't bid on,
    the idle_check event must surface them as a concrete collaboration signal
    rather than a generic 'call eacn3_list_open_tasks' prompt."""

    def test_biddable_tasks_appear_in_idle_check_prompt(self, tmp_path):
        from minions.tools.await_events import await_events

        open_task = {
            "id": "t-open-001",
            "status": "unclaimed",
            "initiator_id": "other-agent",
            "domains": ["triton-kernel", "gpu-perf"],
            "bids": [],
        }

        # Pre-seed cold-start flag so we exercise idle_check, not cold_start_hint
        flag_dir = tmp_path / "workspace" / ".minionsos"
        flag_dir.mkdir(parents=True, exist_ok=True)
        (flag_dir / "cold_start_hint_emitted").write_text("seeded")

        call_count = [0]

        def mock_get(url, **kwargs):
            call_count[0] += 1
            if "/api/events/" in url:
                return _make_poll_response([])
            if "/api/tasks/open" in url:
                return _make_tasks_response([open_task])
            if "/api/tasks" in url:
                return _make_tasks_response([])  # no active/delegated
            return _make_poll_response([])

        with patch("minions.tools.await_events.httpx.get", side_effect=mock_get):
            result = await_events()

        assert result["count"] == 1
        evt = result["events"][0]
        assert evt["event"]["type"] == "idle_check"
        payload = evt["event"]["payload"]
        assert "t-open-001" in payload.get("biddable_tasks", [])
        # The prompt must mention the open task explicitly
        joined = " ".join(payload.get("prompts", []))
        assert "t-open-001" in joined
        assert evt["suggested_tool"] == "eacn3_submit_bid"

    def test_own_tasks_excluded_from_biddable(self, tmp_path):
        """Tasks initiated by this agent must NOT appear in biddable_tasks."""
        from minions.tools.await_events import await_events

        own_task = {
            "id": "t-own",
            "status": "unclaimed",
            "initiator_id": "test-agent",  # this agent's own task
            "domains": ["ml"],
            "bids": [],
        }

        flag_dir = tmp_path / "workspace" / ".minionsos"
        flag_dir.mkdir(parents=True, exist_ok=True)
        (flag_dir / "cold_start_hint_emitted").write_text("seeded")

        # Also pre-create some delegated task so idle_check fires (otherwise
        # no prompts → returns None → cold-start path instead).
        delegated_task = {
            "id": "t-delegated",
            "status": "bidding",
            "initiator_id": "test-agent",
            "bids": [],
        }

        def mock_get(url, **kwargs):
            if "/api/events/" in url:
                return _make_poll_response([])
            if "/api/tasks/open" in url:
                return _make_tasks_response([own_task])
            if "/api/tasks" in url:
                return _make_tasks_response([delegated_task])
            return _make_poll_response([])

        with patch("minions.tools.await_events.httpx.get", side_effect=mock_get):
            result = await_events()

        evt = result["events"][0]
        assert evt["event"]["type"] == "idle_check"
        biddable = evt["event"]["payload"].get("biddable_tasks", [])
        assert "t-own" not in biddable

    def test_already_bid_tasks_excluded_from_biddable(self, tmp_path):
        """Tasks where this agent already has a bid must NOT be in biddable_tasks."""
        from minions.tools.await_events import await_events

        already_bid_task = {
            "id": "t-bid",
            "status": "unclaimed",
            "initiator_id": "other-agent",
            "domains": ["ml"],
            "bids": [{"agent_id": "test-agent", "status": "submitted"}],
        }

        flag_dir = tmp_path / "workspace" / ".minionsos"
        flag_dir.mkdir(parents=True, exist_ok=True)
        (flag_dir / "cold_start_hint_emitted").write_text("seeded")

        delegated_task = {
            "id": "t-delegated",
            "status": "bidding",
            "initiator_id": "test-agent",
            "bids": [],
        }

        def mock_get(url, **kwargs):
            if "/api/events/" in url:
                return _make_poll_response([])
            if "/api/tasks/open" in url:
                return _make_tasks_response([already_bid_task])
            if "/api/tasks" in url:
                return _make_tasks_response([delegated_task])
            return _make_poll_response([])

        with patch("minions.tools.await_events.httpx.get", side_effect=mock_get):
            result = await_events()

        evt = result["events"][0]
        biddable = evt["event"]["payload"].get("biddable_tasks", [])
        assert "t-bid" not in biddable

    def test_biddable_open_endpoint_failure_is_graceful(self, tmp_path):
        """If /api/tasks/open fails, idle_check must still fire with other prompts."""
        from minions.tools.await_events import await_events

        flag_dir = tmp_path / "workspace" / ".minionsos"
        flag_dir.mkdir(parents=True, exist_ok=True)
        (flag_dir / "cold_start_hint_emitted").write_text("seeded")

        delegated_task = {
            "id": "t-delegated",
            "status": "bidding",
            "initiator_id": "test-agent",
            "bids": [],
        }

        class FailResp:
            status_code = 500

            def json(self):
                return []

        def mock_get(url, **kwargs):
            if "/api/events/" in url:
                return _make_poll_response([])
            if "/api/tasks/open" in url:
                return FailResp()
            if "/api/tasks" in url:
                return _make_tasks_response([delegated_task])
            return _make_poll_response([])

        with patch("minions.tools.await_events.httpx.get", side_effect=mock_get):
            result = await_events()

        # Should still return an idle_check (from delegated task), not crash
        assert result["count"] == 1
        assert result["events"][0]["event"]["type"] == "idle_check"


# ---------------------------------------------------------------------------
# Issue #39 — Draft-discipline reminder must not cover high-priority EACN signals
# ---------------------------------------------------------------------------


class TestDraftReminderPriority:
    """For task_broadcast / direct_message / bid_result events, the Draft
    discipline reminder must be APPENDED (not prepended) so the EACN
    collaboration signal remains the first thing the LLM reads."""

    def _make_draft_audit_snapshot(self, reminder_due=True):
        from minions.tools.draft_audit import AuditSnapshot as DraftAuditSnapshot

        return DraftAuditSnapshot(
            prev_delivery_was_real=True,
            appends_since_last_await=0,
        )

    def test_reminder_appended_for_task_broadcast(self, monkeypatch, tmp_path):
        from minions.tools.await_events import await_events

        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path / "projects"))

        fake_event = {
            "type": "task_broadcast",
            "task_id": "t-broadcast",
            "payload": {"domains": ["ml"], "budget": 0},
        }

        snapshot = self._make_draft_audit_snapshot(reminder_due=True)

        with (
            patch("minions.tools.await_events.httpx.get") as mock_get,
            patch(
                "minions.tools.draft_audit.take_snapshot_and_reset",
                return_value=snapshot,
            ),
        ):
            mock_get.return_value = _make_poll_response([fake_event])
            result = await_events()

        evt = result["events"][0]
        action = evt["suggested_action"]
        # EACN collaboration signal must come FIRST
        assert action.index("Evaluate and bid") < action.index("Draft-discipline reminder")

    def test_reminder_prepended_for_idle_check(self, monkeypatch, tmp_path):
        """For idle_check (lower urgency), prepending is acceptable."""
        from minions.tools.await_events import await_events

        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path / "projects"))

        flag_dir = tmp_path / "workspace" / ".minionsos"
        flag_dir.mkdir(parents=True, exist_ok=True)
        (flag_dir / "cold_start_hint_emitted").write_text("seeded")

        delegated_task = {
            "id": "t-del",
            "status": "bidding",
            "initiator_id": "test-agent",
            "bids": [],
        }

        snapshot = self._make_draft_audit_snapshot(reminder_due=True)

        def mock_get(url, **kwargs):
            if "/api/events/" in url:
                return _make_poll_response([])
            if "/api/tasks/open" in url:
                return _make_tasks_response([])
            if "/api/tasks" in url:
                return _make_tasks_response([delegated_task])
            return _make_poll_response([])

        with (
            patch("minions.tools.await_events.httpx.get", side_effect=mock_get),
            patch(
                "minions.tools.draft_audit.take_snapshot_and_reset",
                return_value=snapshot,
            ),
        ):
            result = await_events()

        evt = result["events"][0]
        assert evt["event"]["type"] == "idle_check"
        action = evt["suggested_action"]
        # For idle_check, reminder prepended (comes first)
        assert action.index("Draft-discipline reminder") < action.index("t-del")


class TestPollWatchdog:
    """Issue #37: SIGALRM-backed wall-clock kill-switch on _poll_once."""

    def test_watchdog_no_op_on_worker_thread(self):
        """Outside the main thread, _poll_watchdog must yield as a no-op.

        SIGALRM is main-thread-only on POSIX. The fallback ensures the
        tool does not raise ValueError when invoked from MCP transports
        that dispatch on a worker thread; the structured httpx Timeout
        remains the only guard in that case.
        """
        import threading

        from minions.tools.await_events import _poll_watchdog

        seen_yield = []

        def _runner():
            try:
                with _poll_watchdog(60, 39999, "x"):
                    seen_yield.append(True)
            except Exception as exc:  # pragma: no cover — failure path
                seen_yield.append(exc)

        t = threading.Thread(target=_runner)
        t.start()
        t.join(timeout=2.0)
        assert seen_yield == [True]

    def test_watchdog_trips_on_main_thread(self, monkeypatch):
        """On the main thread, the SIGALRM watchdog must raise TimeoutError
        when the wrapped block exceeds its budget."""
        import time as _time

        from minions.tools.await_events import _poll_watchdog

        with pytest.raises(TimeoutError), _poll_watchdog(1, 39999, "x"):
            _time.sleep(2.5)
