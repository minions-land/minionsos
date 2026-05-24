"""Tests for the Draft-discipline audit tracker (B)."""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.tools import draft_audit


@pytest.fixture()
def port_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """Set MINIONS_PROJECTS_ROOT so project_state_dir resolves under tmp."""
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    return 39999


def test_initial_state_no_appends_no_prior_real_events(port_root: int) -> None:
    snap = draft_audit.take_snapshot_and_reset(port_root, "agent-x", returning_real_events=False)
    assert snap.appends_since_last_await == 0
    assert snap.prev_delivery_was_real is False
    assert snap.reminder_due is False


def test_record_append_increments_counter(port_root: int) -> None:
    draft_audit.record_append(port_root, "agent-x")
    draft_audit.record_append(port_root, "agent-x", count=2)
    snap = draft_audit.take_snapshot_and_reset(port_root, "agent-x", returning_real_events=True)
    assert snap.appends_since_last_await == 3


def test_take_snapshot_resets_counter(port_root: int) -> None:
    draft_audit.record_append(port_root, "agent-x")
    draft_audit.take_snapshot_and_reset(port_root, "agent-x", returning_real_events=True)
    # Second snapshot should see counter reset to 0.
    snap = draft_audit.take_snapshot_and_reset(port_root, "agent-x", returning_real_events=False)
    assert snap.appends_since_last_await == 0


def test_reminder_due_when_real_events_followed_by_zero_appends(
    port_root: int,
) -> None:
    """Cycle 1: real events delivered, role wrote 0 appends.
    Cycle 2: at the next await return, reminder must fire.
    """
    # Cycle 1 starts with a real-events delivery.
    draft_audit.take_snapshot_and_reset(port_root, "agent-x", returning_real_events=True)
    # Role writes nothing, then await_events returns again.
    snap = draft_audit.take_snapshot_and_reset(port_root, "agent-x", returning_real_events=False)
    assert snap.prev_delivery_was_real is True
    assert snap.appends_since_last_await == 0
    assert snap.reminder_due is True


def test_reminder_not_due_when_role_appended(port_root: int) -> None:
    draft_audit.take_snapshot_and_reset(port_root, "agent-x", returning_real_events=True)
    draft_audit.record_append(port_root, "agent-x")
    snap = draft_audit.take_snapshot_and_reset(port_root, "agent-x", returning_real_events=True)
    assert snap.reminder_due is False


def test_reminder_not_due_when_prev_delivery_was_keepalive(port_root: int) -> None:
    """Pure keepalive cycles should never trigger the reminder, even
    with zero appends — that's the byte-stable ack path."""
    draft_audit.take_snapshot_and_reset(port_root, "agent-x", returning_real_events=False)
    snap = draft_audit.take_snapshot_and_reset(port_root, "agent-x", returning_real_events=False)
    assert snap.reminder_due is False


def test_per_agent_isolation(port_root: int) -> None:
    """Counters for different agent_ids must not collide."""
    draft_audit.record_append(port_root, "agent-a", count=2)
    draft_audit.record_append(port_root, "agent-b", count=5)
    snap_a = draft_audit.take_snapshot_and_reset(port_root, "agent-a", returning_real_events=True)
    snap_b = draft_audit.take_snapshot_and_reset(port_root, "agent-b", returning_real_events=True)
    assert snap_a.appends_since_last_await == 2
    assert snap_b.appends_since_last_await == 5


def test_zero_count_record_is_noop(port_root: int) -> None:
    draft_audit.record_append(port_root, "agent-x", count=0)
    snap = draft_audit.take_snapshot_and_reset(port_root, "agent-x", returning_real_events=True)
    assert snap.appends_since_last_await == 0
