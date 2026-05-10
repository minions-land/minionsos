"""Unit tests for the pending-inbox injection block in _format_event_message."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from minions.lifecycle import role as role_mod


def test_no_pending_means_no_preamble_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with (
        patch.object(role_mod, "list_skills", return_value=[]),
        patch.object(role_mod, "_read_pending_safely", return_value=[]),
    ):
        msg = role_mod._format_event_message(
            [{"id": "e-fresh"}],
            project_port=37596,
            role_name="coder",
            workspace_path=tmp_path,
        )

    assert "[Pending from previous wake]" not in msg


def test_non_empty_pending_is_surfaced_with_retirement_instructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pending = [
        {
            "msg_id": "m-leftover-1",
            "type": "direct_message",
            "payload": {"from": "writer", "content": "ping"},
        },
        {
            "msg_id": "m-leftover-2",
            "type": "task_broadcast",
            "task_id": "t-stale-99",
        },
    ]
    with (
        patch.object(role_mod, "list_skills", return_value=[]),
        patch.object(role_mod, "_read_pending_safely", return_value=pending),
    ):
        msg = role_mod._format_event_message(
            [{"id": "e-fresh"}],
            project_port=37596,
            role_name="coder",
            workspace_path=tmp_path,
        )

    assert "[Pending from previous wake]" in msg
    assert "previous wake drained 2 event(s)" in msg
    # Each pending entry appears as a bullet with its event id.
    assert "event_id=`m-leftover-1`" in msg
    assert "event_id=`m-leftover-2`" in msg
    # task_id is surfaced when it differs from event id.
    assert "task_id=`t-stale-99`" in msg
    # The retirement path is explicit so the inbox can drain next wake.
    assert "mos_ack_clear" in msg
    # The recovery procedure lives in the common SYSTEM.md — don't inline it.
    assert "Pending-inbox recovery" in msg


def test_pending_block_omitted_when_project_port_missing(tmp_path: Path) -> None:
    with (
        patch.object(role_mod, "list_skills", return_value=[]),
        patch.object(role_mod, "_read_pending_safely") as reader,
    ):
        msg = role_mod._format_event_message(
            [{"id": "e1"}],
            role_name="coder",
            workspace_path=tmp_path,
        )
    # Without a project port we cannot route to the right pending file;
    # we must not attempt to read it, and the block must stay out of the
    # prompt entirely.
    reader.assert_not_called()
    assert "[Pending from previous wake]" not in msg


def test_pending_read_failure_degrades_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with (
        patch.object(role_mod, "list_skills", return_value=[]),
        patch.object(role_mod, "_read_pending_safely", return_value=[]),
    ):
        # _read_pending_safely already swallows exceptions; the block
        # should simply be absent when nothing comes back.
        msg = role_mod._format_event_message(
            [{"id": "e1"}],
            project_port=37596,
            role_name="coder",
            workspace_path=tmp_path,
        )
    assert "[Pending from previous wake]" not in msg


def test_summarize_pending_entry_handles_missing_identifiers() -> None:
    # No event id -> render a placeholder rather than crashing.
    line = role_mod._summarize_pending_entry({"type": "weird_event"})
    assert "event_id=`<missing>`" in line
    assert "type=`weird_event`" in line


def test_summarize_pending_entry_surfaces_direct_message_sender() -> None:
    entry = {
        "msg_id": "m1",
        "type": "direct_message",
        "payload": {"from": "writer", "content": "hi"},
    }
    line = role_mod._summarize_pending_entry(entry)
    assert "event_id=`m1`" in line
    assert "type=`direct_message`" in line
    assert "from=`writer`" in line


def test_read_pending_safely_propagates_mos_pool_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from minions.lifecycle import mos_pool

    events = [{"msg_id": "real-1"}]

    def fake_pending_read(port: int, role: str) -> list:
        return events

    monkeypatch.setattr(mos_pool, "mos_pending_read", fake_pending_read)
    got = role_mod._read_pending_safely(37596, "coder")
    assert got == events


def test_read_pending_safely_swallows_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    from minions.lifecycle import mos_pool

    def explode(port: int, role: str) -> list:
        raise RuntimeError("disk is sad")

    monkeypatch.setattr(mos_pool, "mos_pending_read", explode)
    # Must not raise; must return an empty list.
    assert role_mod._read_pending_safely(37596, "coder") == []
