"""Unit tests for minions.lifecycle.mos_pool."""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.lifecycle import mos_pool

# ---------------------------------------------------------------------------
# Pending inbox file operations
# ---------------------------------------------------------------------------


def test_pending_path_is_under_role_branch_minionsos_inbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"project_{port}" / "branches" / role,
    )
    expected = (
        tmp_path / "project_37596" / "branches" / "coder" / ".minionsos" / "inbox" / "pending.jsonl"
    )
    assert mos_pool._pending_path(37596, "coder") == expected


def test_event_id_prefers_msg_id_then_id_then_fallback() -> None:
    assert mos_pool._event_id({"msg_id": "abc", "id": "xyz"}) == "abc"
    assert mos_pool._event_id({"id": "xyz"}) == "xyz"
    assert mos_pool._event_id({"event_id": "e1"}) == "e1"
    assert mos_pool._event_id({"task_id": "t1"}) == "t1"
    fallback = mos_pool._event_id({"type": "msg", "payload": {"v": 1}})
    assert fallback.startswith("{")  # JSON dump fallback


def test_mos_pending_read_empty_when_file_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )
    assert mos_pool.mos_pending_read(37596, "coder") == []


def test_append_and_read_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )
    events = [
        {"msg_id": "m1", "type": "direct_message", "payload": {}},
        {"msg_id": "m2", "type": "task_broadcast", "task_id": "t1"},
    ]
    mos_pool._append_pending(37596, "coder", events)
    assert mos_pool.mos_pending_read(37596, "coder") == events


def test_read_skips_malformed_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )
    path = mos_pool._pending_path(37596, "coder")
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"msg_id": "ok"}\nnot json\n\n"a string, not a dict"\n{"msg_id": "ok2"}\n',
        encoding="utf-8",
    )
    events = mos_pool.mos_pending_read(37596, "coder")
    assert [e["msg_id"] for e in events] == ["ok", "ok2"]


def test_ack_clear_removes_named_ids_and_keeps_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )
    mos_pool._append_pending(
        37596,
        "coder",
        [
            {"msg_id": "m1"},
            {"msg_id": "m2"},
            {"msg_id": "m3"},
        ],
    )
    removed = mos_pool.mos_ack_clear(37596, "coder", ["m1", "m3"])
    assert removed == 2
    remaining = mos_pool.mos_pending_read(37596, "coder")
    assert [e["msg_id"] for e in remaining] == ["m2"]


def test_ack_clear_removes_file_when_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )
    mos_pool._append_pending(37596, "coder", [{"msg_id": "m1"}, {"msg_id": "m2"}])
    path = mos_pool._pending_path(37596, "coder")
    assert path.exists()
    removed = mos_pool.mos_ack_clear(37596, "coder", ["m1", "m2"])
    assert removed == 2
    assert not path.exists()


def test_ack_clear_empty_ids_is_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )
    mos_pool._append_pending(37596, "coder", [{"msg_id": "m1"}])
    assert mos_pool.mos_ack_clear(37596, "coder", []) == 0
    assert [e["msg_id"] for e in mos_pool.mos_pending_read(37596, "coder")] == ["m1"]


def test_ack_clear_missing_file_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )
    assert mos_pool.mos_ack_clear(37596, "coder", ["m1"]) == 0


def test_pending_wipe_removes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )
    mos_pool._append_pending(37596, "coder", [{"msg_id": "m1"}])
    path = mos_pool._pending_path(37596, "coder")
    assert path.exists()
    mos_pool.mos_pending_wipe(37596, "coder")
    assert not path.exists()
    # Second call on an already-absent file is a no-op.
    mos_pool.mos_pending_wipe(37596, "coder")


# ---------------------------------------------------------------------------
# mos_await_events
# ---------------------------------------------------------------------------


def test_await_events_clamps_timeout_above_ceiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )
    captured: dict = {}

    def fake_poll(**kwargs):
        captured.update(kwargs)
        return {"events": [], "count": 0}

    monkeypatch.setattr(mos_pool.eacn_client, "poll_events", fake_poll)

    mos_pool.mos_await_events(37596, "coder", "coder-agent", timeout_seconds=9999)
    assert captured["timeout_secs"] == mos_pool.MOS_AWAIT_TIMEOUT_MAX_SEC


def test_await_events_clamps_negative_to_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )
    captured: dict = {}

    def fake_poll(**kwargs):
        captured.update(kwargs)
        return {"events": [], "count": 0}

    monkeypatch.setattr(mos_pool.eacn_client, "poll_events", fake_poll)

    mos_pool.mos_await_events(37596, "coder", "coder-agent", timeout_seconds=-5)
    assert captured["timeout_secs"] == 0


def test_await_events_persists_events_to_pending_inbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )

    def fake_poll(**kwargs):
        return {
            "events": [
                {"msg_id": "m1", "type": "direct_message"},
                {"msg_id": "m2", "type": "task_broadcast"},
            ],
            "count": 2,
        }

    monkeypatch.setattr(mos_pool.eacn_client, "poll_events", fake_poll)

    result = mos_pool.mos_await_events(37596, "coder", "coder-agent")

    assert result["count"] == 2
    assert result["timeout"] is False
    assert result["pending_count"] == 2

    pending = mos_pool.mos_pending_read(37596, "coder")
    assert [e["msg_id"] for e in pending] == ["m1", "m2"]


def test_await_events_empty_response_reports_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )
    monkeypatch.setattr(
        mos_pool.eacn_client,
        "poll_events",
        lambda **kw: {"events": [], "count": 0},
    )
    result = mos_pool.mos_await_events(37596, "coder", "coder-agent")
    assert result["timeout"] is True
    assert result["count"] == 0
    assert result["pending_count"] == 0


def test_await_events_filters_non_dict_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )
    monkeypatch.setattr(
        mos_pool.eacn_client,
        "poll_events",
        lambda **kw: {
            "events": [
                {"msg_id": "ok"},
                "not-a-dict",
                None,
                {"msg_id": "ok2"},
            ]
        },
    )
    result = mos_pool.mos_await_events(37596, "coder", "coder-agent")
    assert result["count"] == 2
    pending = mos_pool.mos_pending_read(37596, "coder")
    assert [e["msg_id"] for e in pending] == ["ok", "ok2"]


def test_await_events_accumulates_pending_across_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two back-to-back wakes that fail to ACK leave both batches on disk.

    This simulates a crash before the agent can call mos_ack_clear.
    """
    monkeypatch.setattr(
        mos_pool,
        "project_role_workspace",
        lambda port, role: tmp_path / f"p{port}" / role,
    )

    batches = [
        {"events": [{"msg_id": "m1"}]},
        {"events": [{"msg_id": "m2"}]},
    ]
    calls = iter(batches)
    monkeypatch.setattr(mos_pool.eacn_client, "poll_events", lambda **kw: next(calls))

    mos_pool.mos_await_events(37596, "coder", "coder-agent")
    result = mos_pool.mos_await_events(37596, "coder", "coder-agent")

    assert result["count"] == 1  # second drain only reports what EACN returned
    assert result["pending_count"] == 2  # but disk holds both un-acked rounds


# ---------------------------------------------------------------------------
# mos_send_message / mos_create_task — thin wrappers
# ---------------------------------------------------------------------------


def test_send_message_delegates_to_eacn_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_send(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(mos_pool.eacn_client, "send_message", fake_send)

    out = mos_pool.mos_send_message(
        port=37596,
        to_agent_id="coder",
        from_agent_id="gru",
        content="hi",
    )
    assert out == {"ok": True}
    assert captured["port"] == 37596
    assert captured["to_agent_id"] == "coder"
    assert captured["from_agent_id"] == "gru"
    assert captured["content"] == "hi"


def test_create_task_delegates_to_eacn_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return {"task_id": "t-new"}

    monkeypatch.setattr(mos_pool.eacn_client, "create_task", fake_create)

    out = mos_pool.mos_create_task(
        port=37596,
        description="run experiment",
        domains=["experiments"],
        initiator_id="gru",
        invited_agent_ids=["experimenter"],
    )
    assert out == {"task_id": "t-new"}
    assert captured["port"] == 37596
    assert captured["description"] == "run experiment"
    assert captured["domains"] == ["experiments"]
    assert captured["initiator_id"] == "gru"
    assert captured["invited_agent_ids"] == ["experimenter"]
