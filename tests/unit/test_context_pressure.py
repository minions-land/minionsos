"""Unit tests for minions.tools.context_pressure.

Tests cover:
  - threshold-based level classification (low / medium / high)
  - cooldown suppression after a recent compact event
  - annotate_event preserves original suggested_action
  - end-to-end empirical replay against the issue #38 reference data
    (long session with monotonic cache_read growth → high pressure;
    short session → low pressure)
  - memo cache invalidates on file mtime change
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from minions.tools import context_pressure as cp


def _write_session(path: Path, cr_values: list[int]) -> None:
    """Write a fake Claude Code session jsonl with the given per-turn cr."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for i, cr in enumerate(cr_values):
        lines.append(
            json.dumps(
                {
                    "type": "assistant",
                    "timestamp": f"2026-05-27T00:0{i % 10}:0{i % 10}Z",
                    "sessionId": "fake-session",
                    "cwd": "/fake",
                    "message": {
                        "usage": {
                            "cache_read_input_tokens": cr,
                            "cache_creation_input_tokens": 100,
                            "input_tokens": 1000,
                            "output_tokens": 100,
                        }
                    },
                }
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _setup_workspace(
    tmp_path: Path,
    cr_values: list[int],
    *,
    monkeypatch: pytest.MonkeyPatch,
    role_name: str = "expert-foo",
) -> Path:
    """Create a fake workspace + session file under a fake $HOME."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MINIONS_ROLE_NAME", role_name)

    workspace = tmp_path / "project_99999" / "branches" / role_name
    workspace.mkdir(parents=True)

    slug = cp._slug_for_workspace(workspace)
    session_dir = home / ".claude" / "projects" / slug
    session_dir.mkdir(parents=True)
    _write_session(session_dir / "s.jsonl", cr_values)

    cp.reset_memo()
    return workspace


def test_low_pressure_for_short_session(tmp_path: Path, monkeypatch) -> None:
    """Short session at floor cache_read: no advisory."""
    ws = _setup_workspace(tmp_path, [45_000, 50_000, 55_000, 60_000], monkeypatch=monkeypatch)
    p = cp.probe(workspace=ws)
    assert p.level == "low"
    assert p.avg_cr_recent < cp.DEFAULT_THRESHOLD_MEDIUM


def test_medium_pressure_above_70k(tmp_path: Path, monkeypatch) -> None:
    """Approaching the high threshold: medium hint."""
    ws = _setup_workspace(
        tmp_path, [70_000, 75_000, 80_000, 85_000, 80_000], monkeypatch=monkeypatch
    )
    p = cp.probe(workspace=ws)
    assert p.level == "medium"


def test_high_pressure_above_100k(tmp_path: Path, monkeypatch) -> None:
    """Past the high threshold: hard advisory."""
    ws = _setup_workspace(
        tmp_path,
        [100_000, 110_000, 120_000, 130_000, 140_000, 150_000, 160_000, 170_000, 180_000, 190_000],
        monkeypatch=monkeypatch,
    )
    p = cp.probe(workspace=ws)
    assert p.level == "high"
    assert p.avg_cr_recent >= cp.DEFAULT_THRESHOLD_HIGH


def test_cooldown_demotes_high_to_medium(tmp_path: Path, monkeypatch) -> None:
    """A recent compact event suppresses 'high' to 'medium' to avoid loop."""
    ws = _setup_workspace(
        tmp_path,
        [120_000] * 10,
        monkeypatch=monkeypatch,
    )
    # Write a recent compact entry to the shared journal.
    shared_journal = ws.parent / "shared" / "draft" / "journal.jsonl"
    shared_journal.parent.mkdir(parents=True)
    from datetime import UTC, datetime

    shared_journal.write_text(
        json.dumps(
            {
                "op": "compact",
                "role": "expert-foo",
                "reason": "test",
                "timestamp": datetime.now(tz=UTC).isoformat(),
            }
        )
        + "\n"
    )
    cp.reset_memo()
    p = cp.probe(workspace=ws)
    assert p.on_cooldown is True
    assert p.level == "medium"  # downgraded from high
    assert p.cooldown_remaining_s > 0


def test_cooldown_expires_allows_high(tmp_path: Path, monkeypatch) -> None:
    """Old compact event (older than cooldown) does not suppress."""
    ws = _setup_workspace(tmp_path, [120_000] * 10, monkeypatch=monkeypatch)
    shared_journal = ws.parent / "shared" / "draft" / "journal.jsonl"
    shared_journal.parent.mkdir(parents=True)
    from datetime import UTC, datetime, timedelta

    old_ts = datetime.now(tz=UTC) - timedelta(seconds=600)
    shared_journal.write_text(
        json.dumps(
            {
                "op": "compact",
                "role": "expert-foo",
                "timestamp": old_ts.isoformat(),
            }
        )
        + "\n"
    )
    cp.reset_memo()
    p = cp.probe(workspace=ws, cooldown_seconds=300)
    assert p.on_cooldown is False
    assert p.level == "high"


def test_annotate_high_inserts_compact_directive() -> None:
    pressure = cp.ContextPressure(
        level="high",
        avg_cr_recent=150_000,
        window_turns=10,
        threshold_high=100_000,
        threshold_medium=70_000,
        on_cooldown=False,
        cooldown_remaining_s=0,
        session_path="/fake.jsonl",
    )
    event = {"type": "msg", "suggested_action": "Reply to peer."}
    cp.annotate_event(event, pressure)
    assert "mos_compact_context" in event["suggested_action"]
    assert "CONTEXT PRESSURE HIGH" in event["suggested_action"]
    assert event["original_suggested_action"] == "Reply to peer."
    assert event["context_pressure"]["level"] == "high"


def test_annotate_medium_appends_hint() -> None:
    pressure = cp.ContextPressure(
        level="medium",
        avg_cr_recent=80_000,
        window_turns=10,
        threshold_high=100_000,
        threshold_medium=70_000,
        on_cooldown=False,
        cooldown_remaining_s=0,
        session_path="/fake.jsonl",
    )
    event = {"type": "msg", "suggested_action": "Reply to peer."}
    cp.annotate_event(event, pressure)
    assert "Reply to peer." in event["suggested_action"]
    assert "context advisory" in event["suggested_action"]
    assert "mos_compact_context" in event["suggested_action"]


def test_annotate_low_is_noop() -> None:
    pressure = cp.ContextPressure(
        level="low",
        avg_cr_recent=50_000,
        window_turns=10,
        threshold_high=100_000,
        threshold_medium=70_000,
        on_cooldown=False,
        cooldown_remaining_s=0,
        session_path="/fake.jsonl",
    )
    event = {"type": "msg", "suggested_action": "Reply to peer."}
    cp.annotate_event(event, pressure)
    assert event["suggested_action"] == "Reply to peer."
    assert "context_pressure" not in event


def test_no_session_yields_low(tmp_path: Path, monkeypatch) -> None:
    """First wake on a fresh process: no jsonl yet → low pressure (no advisory)."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    workspace = tmp_path / "project_99999" / "branches" / "expert-foo"
    workspace.mkdir(parents=True)
    cp.reset_memo()
    p = cp.probe(workspace=workspace)
    assert p.level == "low"
    assert p.session_path is None


def test_window_uses_only_recent_turns(tmp_path: Path, monkeypatch) -> None:
    """Old high-cr turns shouldn't dominate avg if recent ones are low.

    This is the regression case: a session that compacted, dropped back
    to floor, and shouldn't immediately re-fire the high-pressure flag.
    """
    cr_values = [180_000] * 50 + [50_000] * 10  # recent 10 are floor-level
    ws = _setup_workspace(tmp_path, cr_values, monkeypatch=monkeypatch)
    p = cp.probe(workspace=ws)
    # avg over LAST 10 turns = 50K → low
    assert p.level == "low"
    assert p.avg_cr_recent == 50_000
    assert p.window_turns == 10


def test_memo_invalidates_on_file_change(tmp_path: Path, monkeypatch) -> None:
    """The per-process memo must invalidate when the session file is appended."""
    ws = _setup_workspace(tmp_path, [50_000] * 10, monkeypatch=monkeypatch)
    p1 = cp.probe(workspace=ws)
    assert p1.level == "low"

    # Append high-cr turns and bump mtime explicitly.
    slug = cp._slug_for_workspace(ws)
    session_file = Path(os.environ["HOME"]) / ".claude" / "projects" / slug / "s.jsonl"
    high_lines = []
    for i in range(10):
        high_lines.append(
            json.dumps(
                {
                    "type": "assistant",
                    "timestamp": f"2026-05-27T01:00:0{i}Z",
                    "message": {
                        "usage": {"cache_read_input_tokens": 150_000},
                    },
                }
            )
        )
    with session_file.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(high_lines) + "\n")
    # Bump mtime forward so the memo key changes.
    new_mtime = session_file.stat().st_mtime + 100
    os.utime(session_file, (new_mtime, new_mtime))

    p2 = cp.probe(workspace=ws)
    assert p2.level == "high"


# ─── Pattern B integration tests (await_events entry-probe path) ────────────
# These exercise the preemptive-compact path inside await_events. We patch the
# external dependencies (poll, tmux) and check that the right path was taken.


def _setup_eacn_role(tmp_path: Path, cr_values, monkeypatch):
    """Set up a workspace, session jsonl, and the env vars await_events reads."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MINIONS_ROLE_NAME", "expert-foo")
    monkeypatch.setenv("MINIONS_PROJECT_PORT", "55555")
    monkeypatch.setenv("MINIONS_AGENT_ID", "expert-foo")

    workspace = tmp_path / "project_55555" / "branches" / "expert-foo"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("MINIONS_WORKSPACE", str(workspace))
    # publish.py uses project_shared_subdir(port, "draft") to find shared dir;
    # MINIONS_ROOT-derived path would point elsewhere. Patch the helper.

    slug = cp._slug_for_workspace(workspace)
    session_dir = home / ".claude" / "projects" / slug
    session_dir.mkdir(parents=True)
    _write_session(session_dir / "s.jsonl", cr_values)
    cp.reset_memo()
    return workspace


def test_pattern_b_preempts_compact_when_idle_and_high(tmp_path, monkeypatch):
    """Pattern B: high pressure + empty queue → schedule compact + return synthetic."""
    workspace = _setup_eacn_role(tmp_path, [120_000] * 10, monkeypatch=monkeypatch)

    # Patch project_shared_subdir so journal lands in our tmp_path
    from minions import paths as _paths

    monkeypatch.setattr(
        _paths,
        "project_shared_subdir",
        lambda port, sub: workspace.parent / "shared" / sub,
    )

    # Patch _poll_once to return [] (empty queue)
    from minions.tools import await_events as ae

    monkeypatch.setattr(ae, "_poll_once", lambda port, agent_id: [])
    # Replace _schedule_preemptive_compact wholesale so we don't need tmux
    tmux_calls = []

    def _fake_schedule(port, agent_id):
        tmux_calls.append((port, agent_id))
        # Mimic the real helper's journal write so cooldown sees it
        import json as _j
        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        from minions import paths as _p

        d = _p.project_shared_subdir(port, "draft")
        d.mkdir(parents=True, exist_ok=True)
        (d / "journal.jsonl").open("a").write(
            _j.dumps(
                {
                    "op": "compact",
                    "role": "expert-foo",
                    "reason": "context_pressure_preemptive",
                    "timestamp": _dt.now(_UTC).isoformat(),
                }
            )
            + "\n"
        )
        return True

    monkeypatch.setattr(ae, "_schedule_preemptive_compact", _fake_schedule)
    # Disable keepalive cliff to avoid interference
    monkeypatch.setattr(ae, "_load_keepalive_seconds", lambda: 0)
    # Make heartbeat a no-op (no events_log import paths needed)
    monkeypatch.setattr(ae, "_touch_heartbeat", lambda ws, aid: None)

    result = ae.await_events()
    assert result["count"] == 1
    evt = result["events"][0]
    assert evt["event"]["type"] == "context_pressure_compact", f"Got event: {evt}"
    assert "compact" in evt["suggested_action"].lower()
    # _schedule_preemptive_compact ran exactly once
    assert len(tmux_calls) == 1

    # Journal entry was written so subsequent probe sees cooldown
    journal = workspace.parent / "shared" / "draft" / "journal.jsonl"
    assert journal.exists()
    lines = journal.read_text().splitlines()
    assert any('"op": "compact"' in ln for ln in lines)


def test_pattern_b_falls_through_when_queue_has_events(tmp_path, monkeypatch):
    """Pattern B aborts and Pattern A path runs when queue has events."""
    workspace = _setup_eacn_role(tmp_path, [120_000] * 10, monkeypatch=monkeypatch)
    from minions import paths as _paths

    monkeypatch.setattr(
        _paths,
        "project_shared_subdir",
        lambda port, sub: workspace.parent / "shared" / sub,
    )

    fake_evt = {"event_id": "e1", "event_type": "message", "sender_id": "peer"}
    from minions.tools import await_events as ae

    monkeypatch.setattr(ae, "_poll_once", lambda port, agent_id: [fake_evt])
    monkeypatch.setattr(ae, "_load_keepalive_seconds", lambda: 0)
    monkeypatch.setattr(ae, "_touch_heartbeat", lambda ws, aid: None)
    # Stub events_log.append_events so the test doesn't need the real module
    import sys as _sys
    import types as _types

    fake_log = _types.ModuleType("minions.tools.events_log")
    fake_log.append_events = lambda port, agent_id, events: None
    monkeypatch.setitem(_sys.modules, "minions.tools.events_log", fake_log)

    # Stub draft_audit too (used inside _return)
    fake_audit = _types.ModuleType("minions.tools.draft_audit")

    class _Snap:
        reminder_due = False
        prev_delivery_was_real = False

    fake_audit.take_snapshot_and_reset = lambda *a, **k: _Snap()
    monkeypatch.setitem(_sys.modules, "minions.tools.draft_audit", fake_audit)

    result = ae.await_events()
    assert result["count"] == 1
    evt = result["events"][0]
    # Pattern A annotation should fire (high pressure + real event)
    assert evt["event_id"] == "e1"
    assert "context_pressure" in evt
    assert evt["context_pressure"]["level"] == "high"
    assert "mos_compact_context" in evt["suggested_action"]


def test_pattern_b_skipped_when_pressure_low(tmp_path, monkeypatch):
    """Low pressure: no preemptive compact, normal poll path runs."""
    _setup_eacn_role(tmp_path, [50_000] * 10, monkeypatch=monkeypatch)

    fake_evt = {"event_id": "e1", "event_type": "message"}
    from minions.tools import await_events as ae

    monkeypatch.setattr(ae, "_poll_once", lambda port, agent_id: [fake_evt])
    tmux_calls = []
    monkeypatch.setattr(
        ae,
        "_schedule_preemptive_compact",
        lambda port, agent_id: tmux_calls.append((port, agent_id)) or True,
    )
    monkeypatch.setattr(ae, "_load_keepalive_seconds", lambda: 0)
    monkeypatch.setattr(ae, "_touch_heartbeat", lambda ws, aid: None)
    import sys as _sys
    import types as _types

    fake_log = _types.ModuleType("minions.tools.events_log")
    fake_log.append_events = lambda *a, **k: None
    monkeypatch.setitem(_sys.modules, "minions.tools.events_log", fake_log)
    fake_audit = _types.ModuleType("minions.tools.draft_audit")

    class _Snap:
        reminder_due = False
        prev_delivery_was_real = False

    fake_audit.take_snapshot_and_reset = lambda *a, **k: _Snap()
    monkeypatch.setitem(_sys.modules, "minions.tools.draft_audit", fake_audit)

    result = ae.await_events()
    assert result["count"] == 1
    # Low pressure → no annotation, no tmux calls, no compact
    evt = result["events"][0]
    assert "context_pressure" not in evt
    assert all("/compact" not in str(c) for c in tmux_calls)


class _MockResult:
    returncode = 0
