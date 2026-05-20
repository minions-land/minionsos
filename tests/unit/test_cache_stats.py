"""Unit tests for minions.tools.cache_stats."""

from __future__ import annotations

import json
from pathlib import Path

from minions.tools.cache_stats import (
    _cold_starts,
    _discover_sessions_for_cwd,
    _format_report,
    _format_role_report,
    _load_session,
    _load_turns,
    _role_cwd,
)


def _write_session(path: Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


def test_loads_assistant_turns_and_skips_others(tmp_path: Path) -> None:
    p = tmp_path / "s.jsonl"
    _write_session(
        p,
        [
            {"type": "user", "timestamp": "2026-05-18T00:00:00Z"},
            {
                "type": "assistant",
                "timestamp": "2026-05-18T00:00:01Z",
                "message": {
                    "usage": {
                        "cache_read_input_tokens": 1000,
                        "cache_creation_input_tokens": 50,
                        "cache_creation": {
                            "ephemeral_5m_input_tokens": 50,
                            "ephemeral_1h_input_tokens": 0,
                        },
                    }
                },
            },
            {"type": "summary", "timestamp": "2026-05-18T00:00:02Z"},
        ],
    )
    turns = _load_turns(p)
    assert len(turns) == 1
    assert turns[0].cache_read == 1000
    assert turns[0].ephemeral_5m == 50


def test_format_report_recommends_keepalive_when_hit_rate_low(tmp_path: Path) -> None:
    """A session with mostly cache_create and little cache_read should
    trigger the 'set cache_keepalive_seconds: 270' recommendation."""
    p = tmp_path / "s.jsonl"
    entries = []
    for i in range(5):
        entries.append(
            {
                "type": "assistant",
                "timestamp": f"2026-05-18T00:0{i}:00Z",
                "message": {
                    "usage": {
                        "cache_read_input_tokens": 100,
                        "cache_creation_input_tokens": 10000,
                        "cache_creation": {
                            "ephemeral_5m_input_tokens": 10000,
                            "ephemeral_1h_input_tokens": 0,
                        },
                    }
                },
            }
        )
    _write_session(p, entries)
    turns = _load_turns(p)
    report = _format_report(p, turns)
    assert "hit rate is low" in report
    assert "cache_keepalive_seconds: 270" in report


def test_format_report_keeps_default_when_hit_rate_high(tmp_path: Path) -> None:
    p = tmp_path / "s.jsonl"
    entries = []
    for i in range(5):
        entries.append(
            {
                "type": "assistant",
                "timestamp": f"2026-05-18T00:0{i}:00Z",
                "message": {
                    "usage": {
                        "cache_read_input_tokens": 10000,
                        "cache_creation_input_tokens": 50,
                        "cache_creation": {
                            "ephemeral_5m_input_tokens": 50,
                            "ephemeral_1h_input_tokens": 0,
                        },
                    }
                },
            }
        )
    _write_session(p, entries)
    report = _format_report(p, _load_turns(p))
    assert "cache hit rate is healthy" in report
    assert "ENABLE_PROMPT_CACHING_1H" in report  # gateway-honors note


def test_format_report_reports_1h_when_present(tmp_path: Path) -> None:
    p = tmp_path / "s.jsonl"
    entry = {
        "type": "assistant",
        "timestamp": "2026-05-18T00:00:00Z",
        "message": {
            "usage": {
                "cache_read_input_tokens": 10000,
                "cache_creation_input_tokens": 100,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": 0,
                    "ephemeral_1h_input_tokens": 100,
                },
            }
        },
    }
    _write_session(p, [entry])
    report = _format_report(p, _load_turns(p))
    assert "ephemeral_1h_input_tokens > 0" in report
    assert "raise cache_keepalive_seconds" in report


# ----------------------------------------------------------------------------
# Role-aggregation tests
# ----------------------------------------------------------------------------


def _make_role_session(
    path: Path,
    cwd: str,
    session_id: str,
    turns: list[dict],
) -> None:
    """Write a fixture jsonl with a cwd-bearing entry and N assistant turns."""
    entries = [
        {
            "type": "user",
            "timestamp": turns[0]["timestamp"] if turns else "2026-05-18T00:00:00Z",
            "sessionId": session_id,
            "cwd": cwd,
        }
    ]
    for t in turns:
        entries.append(
            {
                "type": "assistant",
                "timestamp": t["timestamp"],
                "sessionId": session_id,
                "cwd": cwd,
                "message": {
                    "usage": {
                        "cache_read_input_tokens": t.get("read", 0),
                        "cache_creation_input_tokens": t.get("create", 0),
                        "input_tokens": t.get("input", 0),
                        "output_tokens": t.get("output", 0),
                        "cache_creation": {
                            "ephemeral_5m_input_tokens": t.get("create", 0),
                            "ephemeral_1h_input_tokens": 0,
                        },
                    }
                },
            }
        )
    _write_session(path, entries)


def test_load_session_extracts_cwd_and_session_id(tmp_path: Path) -> None:
    """A jsonl with cwd + sessionId fields populates _Session correctly."""
    p = tmp_path / "s.jsonl"
    _make_role_session(
        p,
        cwd="/Users/mjm/MinionsOS/project_37596/branches/coder",
        session_id="aaa-111",
        turns=[{"timestamp": "2026-05-18T00:00:01Z", "read": 100, "create": 10}],
    )
    sess = _load_session(p)
    assert sess is not None
    assert sess.cwd == "/Users/mjm/MinionsOS/project_37596/branches/coder"
    assert sess.session_id == "aaa-111"
    assert len(sess.turns) == 1


def test_role_cwd_construction(tmp_path: Path) -> None:
    """_role_cwd builds the expected project_{port}/branches/{role}/ path."""
    cwd = _role_cwd(37596, "coder", tmp_path)
    assert cwd == tmp_path / "project_37596" / "branches" / "coder"


def test_discover_sessions_filters_by_cwd(tmp_path: Path) -> None:
    """Only sessions whose first cwd matches target are returned."""
    claude_root = tmp_path / "claude" / "projects"
    target_role = tmp_path / "project_37596" / "branches" / "writer"

    # Two sessions for the target role
    role_slug = claude_root / "Users-mjm-fake-writer"
    role_slug.mkdir(parents=True)
    _make_role_session(
        role_slug / "s1.jsonl",
        cwd=str(target_role.resolve()),
        session_id="sess-1",
        turns=[
            {"timestamp": "2026-05-18T00:00:01Z", "read": 0, "create": 5000},
            {"timestamp": "2026-05-18T00:01:00Z", "read": 5000, "create": 200},
        ],
    )
    _make_role_session(
        role_slug / "s2.jsonl",
        cwd=str(target_role.resolve()),
        session_id="sess-2",
        turns=[
            {"timestamp": "2026-05-18T01:00:00Z", "read": 0, "create": 5500},
        ],
    )

    # One session for a different cwd that should NOT match
    other_slug = claude_root / "Users-mjm-fake-other"
    other_slug.mkdir(parents=True)
    _make_role_session(
        other_slug / "x.jsonl",
        cwd=str((tmp_path / "project_37596" / "branches" / "coder").resolve()),
        session_id="sess-x",
        turns=[{"timestamp": "2026-05-18T02:00:00Z", "read": 100, "create": 10}],
    )

    sessions = _discover_sessions_for_cwd(target_role, claude_root)
    assert len(sessions) == 2
    assert {s.session_id for s in sessions} == {"sess-1", "sess-2"}
    # Sorted by first turn time
    assert sessions[0].session_id == "sess-1"
    assert sessions[1].session_id == "sess-2"


def test_cold_starts_count(tmp_path: Path) -> None:
    """Each session whose first turn has cache_read=0 is one cold start."""
    claude_root = tmp_path / "claude" / "projects"
    target = tmp_path / "project_37596" / "branches" / "writer"
    slug = claude_root / "fake-slug"
    slug.mkdir(parents=True)
    _make_role_session(
        slug / "cold1.jsonl",
        cwd=str(target.resolve()),
        session_id="c1",
        turns=[{"timestamp": "2026-05-18T00:00:01Z", "read": 0, "create": 8000}],
    )
    _make_role_session(
        slug / "cold2.jsonl",
        cwd=str(target.resolve()),
        session_id="c2",
        turns=[{"timestamp": "2026-05-18T01:00:01Z", "read": 0, "create": 7500}],
    )
    _make_role_session(
        slug / "warm.jsonl",
        cwd=str(target.resolve()),
        session_id="w",
        # First turn has cache_read>0 — not a cold start
        turns=[{"timestamp": "2026-05-18T02:00:01Z", "read": 50000, "create": 100}],
    )
    sessions = _discover_sessions_for_cwd(target, claude_root)
    assert _cold_starts(sessions) == 2


def test_format_role_report_no_sessions(tmp_path: Path) -> None:
    target = tmp_path / "project_37596" / "branches" / "noter"
    report = _format_role_report(37596, "noter", target, sessions=[])
    assert "No session jsonl files found" in report
    assert "noter" in report


def test_format_role_report_with_data(tmp_path: Path) -> None:
    """End-to-end: discovery → format. Validates totals + cold-start summary."""
    claude_root = tmp_path / "claude" / "projects"
    target = tmp_path / "project_37596" / "branches" / "ethics"
    slug = claude_root / "fake"
    slug.mkdir(parents=True)
    _make_role_session(
        slug / "s.jsonl",
        cwd=str(target.resolve()),
        session_id="e1",
        turns=[
            {"timestamp": "2026-05-18T00:00:01Z", "read": 0, "create": 20000},
            {"timestamp": "2026-05-18T00:00:30Z", "read": 20000, "create": 500},
        ],
    )
    sessions = _discover_sessions_for_cwd(target, claude_root)
    report = _format_role_report(37596, "ethics", target, sessions)
    # Totals appear
    assert "ethics" in report
    assert "Sessions: 1" in report
    assert "Total turns: 2" in report
    # Hit rate ≈ 20000/(20000+20500) ≈ 49%
    assert "49." in report or "48." in report
    # Cold-start summary
    assert "Cold-start sessions: 1 of 1" in report


# --------------------------------------------------------------------------
# Dispatch posture
# --------------------------------------------------------------------------


def test_classify_tool_buckets() -> None:
    from minions.tools.cache_stats import _classify_tool

    # Subagent dispatch
    assert _classify_tool("Task") == "dispatch"
    assert _classify_tool("Agent") == "dispatch"
    assert _classify_tool("codex") == "dispatch"
    assert _classify_tool("mcp__codex-subagent__codex") == "dispatch"

    # Coordination (lightweight, not heavy work)
    assert _classify_tool("mcp__minionsos__mos_scratchpad_append") == "coord"
    assert _classify_tool("mcp__eacn3__eacn3_send_message") == "coord"

    # Heavy self-execution (the canary)
    assert _classify_tool("Bash") == "heavy_self"
    assert _classify_tool("Edit") == "heavy_self"
    assert _classify_tool("Write") == "heavy_self"
    assert _classify_tool("MultiEdit") == "heavy_self"
    assert _classify_tool("NotebookEdit") == "heavy_self"

    # Reads (still in-context but no mutation)
    assert _classify_tool("Read") == "read_self"
    assert _classify_tool("Grep") == "read_self"
    assert _classify_tool("Glob") == "read_self"
    assert _classify_tool("WebSearch") == "read_self"

    # Anything else
    assert _classify_tool("ToolSearch") == "misc"
    assert _classify_tool("UnknownTool") == "misc"


def test_posture_aggregation_and_pct() -> None:
    from minions.tools.cache_stats import _posture_from_tool_names

    posture = _posture_from_tool_names(
        [
            "Bash",
            "Bash",
            "Edit",  # 3 heavy_self
            "Read",
            "Read",  # 2 read_self
            "Task",  # 1 dispatch
            "ToolSearch",  # 1 misc
            "mcp__minionsos__mos_scratchpad_append",  # 1 coord
        ]
    )
    assert posture.heavy_self == 3
    assert posture.read_self == 2
    assert posture.dispatch == 1
    assert posture.misc == 1
    assert posture.coord == 1
    assert posture.total() == 8
    assert posture.heavy_self_pct() == 3 / 8


def test_compute_dispatch_posture_extracts_from_jsonl(tmp_path: Path) -> None:
    from minions.tools.cache_stats import compute_dispatch_posture

    p = tmp_path / "s.jsonl"
    _write_session(
        p,
        [
            {
                "type": "assistant",
                "timestamp": "2026-05-18T00:00:01Z",
                "message": {
                    "usage": {
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    },
                    "content": [
                        {"type": "tool_use", "name": "Bash"},
                        {"type": "tool_use", "name": "Read"},
                        {"type": "text", "text": "thinking"},
                    ],
                },
            },
            {
                "type": "assistant",
                "timestamp": "2026-05-18T00:00:02Z",
                "message": {
                    "usage": {
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    },
                    "content": [
                        {"type": "tool_use", "name": "Task"},
                    ],
                },
            },
            # non-assistant entries with tool_use must be ignored
            {
                "type": "user",
                "message": {"content": [{"type": "tool_use", "name": "Bash"}]},
            },
        ],
    )
    posture = compute_dispatch_posture([p])
    assert posture.heavy_self == 1
    assert posture.read_self == 1
    assert posture.dispatch == 1
    assert posture.total() == 3


def test_dispatch_posture_handles_missing_files() -> None:
    """Nonexistent paths must not raise — audit must stay best-effort."""
    from minions.tools.cache_stats import compute_dispatch_posture

    posture = compute_dispatch_posture([Path("/nonexistent/never/here.jsonl")])
    assert posture.total() == 0
