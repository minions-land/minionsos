"""Unit tests for the empty-upstream / bare-`ack` wedge detector (Issue #15)."""

from __future__ import annotations

import json
from pathlib import Path

from minions.lifecycle.wedge_detect import (
    find_session_jsonl,
    inspect_log_tail,
    inspect_role,
    inspect_session_tail,
    is_wedged,
)


def test_missing_log_returns_zero_signal(tmp_path: Path) -> None:
    missing = tmp_path / "role-expert.log"
    sig = inspect_log_tail(missing)
    assert sig.empty_marker_count == 0
    assert sig.ack_line_count == 0
    assert sig.sampled_lines == 0
    assert sig.log_path == missing
    assert not is_wedged(sig, threshold=4)


def test_clean_log_is_not_wedged(tmp_path: Path) -> None:
    log = tmp_path / "role-expert.log"
    log.write_text(
        "  Called minionsos (ctrl+o to expand)\n● Reading 1 file…\n● Done. Writing summary.\n"
    )
    sig = inspect_log_tail(log)
    assert sig.empty_marker_count == 0
    assert sig.ack_line_count == 0
    assert not is_wedged(sig, threshold=4)


def test_pure_keepalive_ack_loop_is_not_wedged(tmp_path: Path) -> None:
    """A long quiet ack loop without any empty-upstream marker is
    consistent with a healthy cache-keepalive cadence on a quiet project,
    and the watchdog must NOT kill it.
    """
    log = tmp_path / "role-ethics.log"
    log.write_text("\n".join(["● ack"] * 20) + "\n")
    sig = inspect_log_tail(log)
    assert sig.ack_line_count == 20
    assert sig.empty_marker_count == 0
    assert not is_wedged(sig, threshold=4)


def test_wedge_signature_is_detected(tmp_path: Path) -> None:
    log = tmp_path / "role-expert.log"
    log.write_text(
        "  Called minionsos (ctrl+o to expand)\n\n"
        "● ack\n\n"
        "  Called minionsos (ctrl+o to expand)\n\n"
        "●  ack\n\n"
        "  Called minionsos (ctrl+o to expand)\n\n"
        "● [upstream returned no content]\n\n"
        "● [upstream returned no content]\n\n"
        "● [upstream returned no content]\n\n"
        "● [upstream returned no content]\n\n"
        "✻ Brewed for 35m 26s\n"
    )
    sig = inspect_log_tail(log)
    assert sig.empty_marker_count == 4
    assert sig.ack_line_count == 2
    assert is_wedged(sig, threshold=4)


def test_ack_threshold_with_one_empty_marker_is_wedge(tmp_path: Path) -> None:
    log = tmp_path / "role-x.log"
    log.write_text("● [upstream returned no content]\n" + "\n".join(["● ack"] * 6) + "\n")
    sig = inspect_log_tail(log)
    assert sig.empty_marker_count == 1
    assert sig.ack_line_count == 6
    assert is_wedged(sig, threshold=4)


def test_ansi_escapes_do_not_hide_signature(tmp_path: Path) -> None:
    log = tmp_path / "role-y.log"
    log.write_bytes(
        b"\x1b[1m\xe2\x97\x8f\x1b[0m \x1b[2m[upstream returned no content]\x1b[0m\n" * 4
        + b"\x1b[1m\xe2\x97\x8f\x1b[0m ack\n"
    )
    sig = inspect_log_tail(log)
    assert sig.empty_marker_count == 4
    assert sig.ack_line_count == 1
    assert is_wedged(sig, threshold=4)


def test_tail_bytes_bounds_the_read(tmp_path: Path) -> None:
    """Old wedge patterns far back in the log must not trigger; only the
    recent tail counts."""
    log = tmp_path / "role-z.log"
    ancient_wedge = "● [upstream returned no content]\n● ack\n" * 50
    recent_healthy = "● Reading 1 file…\n● Writing changes…\n" * 50
    log.write_text(ancient_wedge + recent_healthy)
    sig = inspect_log_tail(log, tail_bytes=1024)
    assert sig.empty_marker_count == 0
    assert sig.ack_line_count == 0
    assert not is_wedged(sig, threshold=4)


# ---------------------------------------------------------------------------
# Session-JSONL signal (Issue #26)
# ---------------------------------------------------------------------------


def _write_session_turns(path: Path, turns: list[dict]) -> None:
    """Write a list of assistant-turn records to a JSONL session file.

    Each *turn* dict shape: ``{"text": str | None, "tool_use": bool}``.
    Wraps each into the actual Claude Code session shape.
    """
    with path.open("w", encoding="utf-8") as fh:
        # A few non-assistant control records — the inspector should ignore them.
        fh.write(json.dumps({"type": "custom-title", "customTitle": "p99/expert"}) + "\n")
        fh.write(json.dumps({"type": "agent-name", "agentName": "p99/expert"}) + "\n")
        for t in turns:
            content_parts: list[dict] = []
            if t.get("text") is not None:
                content_parts.append({"type": "text", "text": t["text"]})
            if t.get("tool_use"):
                content_parts.append(
                    {"type": "tool_use", "id": "toolu_x", "name": "mos_await_events", "input": {}}
                )
            fh.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "role": "assistant",
                            "content": content_parts,
                            "stop_reason": "tool_use" if t.get("tool_use") else "end_turn",
                        },
                    }
                )
                + "\n"
            )


def test_inspect_session_tail_missing_file_returns_zero(tmp_path: Path) -> None:
    sig = inspect_session_tail(tmp_path / "missing.jsonl")
    assert sig.empty_marker_count == 0
    assert sig.ack_line_count == 0
    assert sig.sampled_lines == 0


def test_inspect_session_tail_counts_empty_and_ack(tmp_path: Path) -> None:
    """The exact wedge signature from production: 8 ack-only turns
    that each call mos_await_events, mixed with 4 empty turns."""
    sess = tmp_path / "abc.jsonl"
    turns: list[dict] = []
    turns.extend([{"text": "ack", "tool_use": True}] * 8)
    turns.extend([{"text": "", "tool_use": False}] * 4)
    _write_session_turns(sess, turns)
    sig = inspect_session_tail(sess)
    assert sig.ack_line_count == 8
    assert sig.empty_marker_count == 4
    assert is_wedged(sig, threshold=4)


def test_inspect_session_tail_skips_substantive_turns(tmp_path: Path) -> None:
    """A normal working role: lots of substantive prose + tool calls.
    Must NOT register as wedge."""
    sess = tmp_path / "abc.jsonl"
    turns = [
        {"text": "Reading the draft to find pending plans.", "tool_use": True},
        {"text": "Found 3 hypotheses; running experiments.", "tool_use": True},
        {"text": "Logging results to Draft.", "tool_use": True},
        {"text": "ack", "tool_use": True},
        {"text": "Now reviewing what came back.", "tool_use": True},
    ]
    _write_session_turns(sess, turns)
    sig = inspect_session_tail(sess)
    assert sig.empty_marker_count == 0
    assert sig.ack_line_count == 1
    assert not is_wedged(sig, threshold=4)


def test_inspect_session_tail_pure_ack_is_not_wedge(tmp_path: Path) -> None:
    """A long quiet keepalive cadence (all ``ack`` + tool_use, no empty
    turns) is the prescribed byte-stable behavior for cache_keepalive
    cycles. Must not be killed."""
    sess = tmp_path / "abc.jsonl"
    turns = [{"text": "ack", "tool_use": True}] * 20
    _write_session_turns(sess, turns)
    sig = inspect_session_tail(sess)
    assert sig.ack_line_count == 20
    assert sig.empty_marker_count == 0
    assert not is_wedged(sig, threshold=4)


def test_inspect_session_tail_only_reads_last_n_turns(tmp_path: Path) -> None:
    """An old wedge surrounded by recent recovery must not register."""
    sess = tmp_path / "abc.jsonl"
    turns: list[dict] = []
    turns.extend([{"text": "ack", "tool_use": True}] * 16)
    turns.extend([{"text": "", "tool_use": False}] * 4)
    turns.extend([{"text": "Recovered, running experiment.", "tool_use": True}] * 16)
    _write_session_turns(sess, turns)
    sig = inspect_session_tail(sess, tail_turns=16)
    assert sig.empty_marker_count == 0
    assert sig.ack_line_count == 0


def test_inspect_session_tail_handles_malformed_lines(tmp_path: Path) -> None:
    """A corrupt JSON line must not crash; just skip it."""
    sess = tmp_path / "abc.jsonl"
    sess.write_text(
        "{not valid json\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "ack"}]},
            }
        )
        + "\n"
    )
    sig = inspect_session_tail(sess)
    assert sig.ack_line_count == 1


def test_find_session_jsonl_picks_newest(tmp_path: Path) -> None:
    """When multiple session files exist for the same cwd, pick the most
    recently modified — that's the live session."""
    cwd = Path("/Users/x/MinionsOS/branches/expert")
    slug = "-Users-x-MinionsOS-branches-expert"
    proj_root = tmp_path / "claude" / "projects"
    slug_dir = proj_root / slug
    slug_dir.mkdir(parents=True)
    older = slug_dir / "111.jsonl"
    newer = slug_dir / "222.jsonl"
    older.write_text("{}\n")
    newer.write_text("{}\n")
    import os

    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_800_000_000, 1_800_000_000))
    found = find_session_jsonl(cwd, projects_root=proj_root)
    assert found == newer


def test_find_session_jsonl_returns_none_when_dir_missing(tmp_path: Path) -> None:
    cwd = Path("/Users/x/MinionsOS/branches/nope")
    found = find_session_jsonl(cwd, projects_root=tmp_path / "claude" / "projects")
    assert found is None


def test_inspect_role_prefers_session_jsonl(tmp_path: Path) -> None:
    """When both signals are available, ``inspect_role`` must use the
    session JSONL (exact) and ignore the noisy pty log."""
    cwd = Path("/Users/x/MinionsOS/branches/expert")
    slug = "-Users-x-MinionsOS-branches-expert"
    proj_root = tmp_path / "claude" / "projects"
    slug_dir = proj_root / slug
    slug_dir.mkdir(parents=True)
    sess = slug_dir / "live.jsonl"
    _write_session_turns(
        sess,
        [{"text": "ack", "tool_use": True}] * 8 + [{"text": "", "tool_use": False}] * 4,
    )
    log = tmp_path / "role-expert.log"
    log.write_text("noise\nmore noise\n")  # pty log shows nothing
    sig = inspect_role(cwd=cwd, log_path=log, projects_root=proj_root)
    assert sig.log_path == sess
    assert sig.empty_marker_count == 4
    assert sig.ack_line_count == 8


def test_inspect_role_falls_back_to_log_when_no_session(tmp_path: Path) -> None:
    """Cold-started role: no session JSONL yet. Watchdog must still get
    a signal from the pty log."""
    cwd = Path("/Users/x/MinionsOS/branches/expert")
    proj_root = tmp_path / "claude" / "projects"
    proj_root.mkdir(parents=True)
    log = tmp_path / "role-expert.log"
    log.write_text("● [upstream returned no content]\n" * 4 + "● ack\n" * 4)
    sig = inspect_role(cwd=cwd, log_path=log, projects_root=proj_root)
    assert sig.log_path == log
    assert sig.empty_marker_count == 4
    assert sig.ack_line_count == 4


# ---------------------------------------------------------------------------
# MCP child dead — `MCP error -32000: Connection closed` (v15.23)
# ---------------------------------------------------------------------------


def _write_session_with_tool_results(path: Path, tool_results: list[str]) -> None:
    """Write a session JSONL containing only ``user`` records with
    ``tool_result`` content parts. Used to exercise the MCP-dead path
    without needing assistant turns."""
    with path.open("w", encoding="utf-8") as fh:
        for body in tool_results:
            fh.write(
                json.dumps(
                    {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": [
                                {"type": "tool_result", "tool_use_id": "x", "content": body}
                            ],
                        },
                    }
                )
                + "\n"
            )


def test_mcp_dead_in_session_marks_wedged(tmp_path: Path) -> None:
    """A single ``MCP error -32000`` in a recent tool_result is sufficient
    for the wedge predicate — the role's MCP child died and claude does
    not auto-reconnect, so every subsequent tool call hits the dead pipe."""
    sess = tmp_path / "abc.jsonl"
    _write_session_with_tool_results(
        sess,
        ["normal response", "MCP error -32000: Connection closed"],
    )
    sig = inspect_session_tail(sess)
    assert sig.mcp_error_count == 1
    assert is_wedged(sig, threshold=4)


def test_mcp_dead_in_pty_log_marks_wedged(tmp_path: Path) -> None:
    """Defense-in-depth: when there is no session JSONL, the pty-log
    fallback must also catch the marker."""
    log = tmp_path / "role-expert.log"
    log.write_text(
        "  ⎿ {result of tool}\n"
        "● Now calling mos_await_events…\n"
        "  ⎿ MCP error -32000: Connection closed\n"
    )
    sig = inspect_log_tail(log)
    assert sig.mcp_error_count == 1
    assert is_wedged(sig, threshold=4)


def test_mcp_dead_zero_when_absent(tmp_path: Path) -> None:
    """Healthy session with no MCP errors → mcp_error_count is zero."""
    sess = tmp_path / "abc.jsonl"
    _write_session_turns(sess, [{"text": "Working.", "tool_use": True}])
    sig = inspect_session_tail(sess)
    assert sig.mcp_error_count == 0
    assert not is_wedged(sig, threshold=4)
