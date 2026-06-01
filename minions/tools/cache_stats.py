"""Diagnose prompt-cache and token usage for MinionsOS Roles.

Reads Claude Code session jsonls under ``~/.claude/projects/<slug>/`` and
produces token-cost / cache-hit reports at three levels:

1. Single session jsonl (existing behavior, lowest level).
2. Per-Role rollup across all sessions for one (port, role).
3. Per-project rollup across all Roles for one port.

The Role and project rollups discover sessions by reading each jsonl's
first ``cwd`` field instead of trying to decode the ``-Users-mjm-...``
slug — slug encoding is lossy (any non-alphanumeric character becomes
``-``), but ``cwd`` is recorded verbatim inside the file.

Reset boundaries are inferred per-session: the first assistant turn of
each new session jsonl is a cold start (cache_read=0). Counting these
across a Role's sessions tells you how many ``mos_reset_context`` /
crash respawns happened.

Usage::

    # Single session (existing)
    uv run python -m minions.tools.cache_stats --session <path.jsonl>

    # Per-Role rollup
    uv run python -m minions.tools.cache_stats --port 37596 --role coder

    # Per-project rollup (all Roles)
    uv run python -m minions.tools.cache_stats --port 37596

Reads ``message.usage.cache_read_input_tokens`` /
``cache_creation_input_tokens`` (and the ``ephemeral_5m`` /
``ephemeral_1h`` breakdown) for every assistant turn.
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import sys
from pathlib import Path
from typing import NamedTuple

from minions.paths import MINIONS_ROOT, project_dir


class _Turn(NamedTuple):
    when: dt.datetime
    cache_read: int
    cache_create: int
    input_tokens: int
    output_tokens: int
    ephemeral_5m: int
    ephemeral_1h: int


class _Session(NamedTuple):
    """One ~/.claude/projects/<slug>/<id>.jsonl file's worth of data."""

    path: Path
    cwd: str
    session_id: str
    turns: list[_Turn]


_BUCKETS: list[tuple[str, float, float]] = [
    ("<5min", 0, 300),
    ("5-15min", 300, 900),
    ("15-60min", 900, 3600),
    ("1-4hr", 3600, 14400),
    (">4hr", 14400, float("inf")),
]


# --------------------------------------------------------------------------
# Session loading
# --------------------------------------------------------------------------


def _load_session(path: Path) -> _Session | None:
    """Parse one jsonl file. Returns None if it has no assistant turns.

    Pulls the session's cwd from the first user/assistant entry that has
    one (these entries record the working directory the Role was launched
    in). Returns the session_id from the same entry's sessionId.
    """
    cwd = ""
    session_id = ""
    turns: list[_Turn] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not cwd and isinstance(obj.get("cwd"), str):
                cwd = obj["cwd"]
            if not session_id and isinstance(obj.get("sessionId"), str):
                session_id = obj["sessionId"]
            if obj.get("type") != "assistant":
                continue
            ts = obj.get("timestamp")
            if not ts:
                continue
            usage = (obj.get("message") or {}).get("usage") or {}
            creation_breakdown = usage.get("cache_creation") or {}
            turns.append(
                _Turn(
                    when=dt.datetime.fromisoformat(ts.replace("Z", "+00:00")),
                    cache_read=int(usage.get("cache_read_input_tokens") or 0),
                    cache_create=int(usage.get("cache_creation_input_tokens") or 0),
                    input_tokens=int(usage.get("input_tokens") or 0),
                    output_tokens=int(usage.get("output_tokens") or 0),
                    ephemeral_5m=int(creation_breakdown.get("ephemeral_5m_input_tokens") or 0),
                    ephemeral_1h=int(creation_breakdown.get("ephemeral_1h_input_tokens") or 0),
                )
            )
    if not turns:
        return None
    return _Session(path=path, cwd=cwd, session_id=session_id, turns=turns)


def _load_turns(path: Path) -> list[_Turn]:
    """Backward-compatible single-session loader (used by the existing tests)."""
    sess = _load_session(path)
    return sess.turns if sess else []


def _discover_sessions_for_cwd(target_cwd: Path, claude_root: Path) -> list[_Session]:
    """Find every session jsonl that ran with cwd == *target_cwd*.

    Walks ``~/.claude/projects/*/`*.jsonl`` and matches by the cwd field
    embedded in each file's first user/assistant entry. Slug-decoding is
    not used — the slug is lossy — so this is robust to any path with
    underscores, special chars, etc.
    """
    target = str(target_cwd.resolve())
    matches: list[_Session] = []
    if not claude_root.exists():
        return matches
    for slug_dir in claude_root.iterdir():
        if not slug_dir.is_dir():
            continue
        for jsonl in slug_dir.glob("*.jsonl"):
            sess = _load_session(jsonl)
            if sess is None:
                continue
            if sess.cwd == target:
                matches.append(sess)
    matches.sort(key=lambda s: s.turns[0].when)
    return matches


def _role_cwd(port: int, role: str, repo_root: Path) -> Path:
    """Compute the Role's runtime cwd: ``projects/project_{port}/branches/{role}/``.

    When ``repo_root`` is the canonical ``MINIONS_ROOT`` we route through
    ``minions.paths.project_dir`` so a custom ``MINIONS_PROJECTS_ROOT``
    or ``gru.yaml:projects_root`` is honored. When the caller passes a
    different root (e.g. tests pointing at a tmp_path), we honor that
    explicit override and append the new ``projects/`` segment so the
    layout matches a real MinionsOS install.
    """
    if repo_root == MINIONS_ROOT:
        return project_dir(port) / "branches" / role
    return repo_root / "projects" / f"project_{port}" / "branches" / role


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


def _bucket_summary(turns: list[_Turn]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {
        name: {"turns": 0, "hits": 0, "read": 0, "create": 0} for name, _, _ in _BUCKETS
    }
    for prev, curr in itertools.pairwise(turns):
        gap = (curr.when - prev.when).total_seconds()
        for name, lo, hi in _BUCKETS:
            if lo <= gap < hi:
                bucket = summary[name]
                bucket["turns"] += 1
                bucket["read"] += curr.cache_read
                bucket["create"] += curr.cache_create
                if curr.cache_read > 0:
                    bucket["hits"] += 1
                break
    return summary


def _totals(turns: list[_Turn]) -> dict[str, int]:
    return {
        "turns": len(turns),
        "cache_read": sum(t.cache_read for t in turns),
        "cache_create": sum(t.cache_create for t in turns),
        "input": sum(t.input_tokens for t in turns),
        "output": sum(t.output_tokens for t in turns),
        "ephemeral_5m": sum(t.ephemeral_5m for t in turns),
        "ephemeral_1h": sum(t.ephemeral_1h for t in turns),
    }


def _hit_rate(turns: list[_Turn]) -> float:
    total_read = sum(t.cache_read for t in turns)
    total_create = sum(t.cache_create for t in turns)
    denom = total_read + total_create
    return total_read / denom if denom else 0.0


def _cold_starts(sessions: list[_Session]) -> int:
    """Count sessions that paid a full prompt-cache write on their first turn.

    A "cold start" for our purposes is a session where the first assistant
    turn had ``cache_read == 0`` AND ``cache_create > 0`` — meaning the
    process had to encode the system prompt + tool defs into prompt cache
    from scratch. This approximates ``mos_reset_context`` calls plus any
    watchdog respawns plus the original launch.

    A first turn with ``cache_read > 0`` from the start (typical of
    long-lived Roles started while another instance had recently primed
    the same prefix on this gateway) is not a "cold start" in the cost
    sense — that Role inherited a server-side cached prefix.
    """
    return sum(
        1
        for s in sessions
        if s.turns and s.turns[0].cache_read == 0 and s.turns[0].cache_create > 0
    )


def _avg_cold_start_cost(sessions: list[_Session]) -> int:
    """Mean cache_creation tokens of the first turn in each cold-start session."""
    first_turn_creates = [
        s.turns[0].cache_create
        for s in sessions
        if s.turns and s.turns[0].cache_read == 0 and s.turns[0].cache_create > 0
    ]
    if not first_turn_creates:
        return 0
    return sum(first_turn_creates) // len(first_turn_creates)


# --------------------------------------------------------------------------
# Report formatting
# --------------------------------------------------------------------------


def _format_session_report(path: Path, turns: list[_Turn]) -> str:
    if not turns:
        return f"No assistant turns found in {path}."
    summary = _bucket_summary(turns)
    totals = _totals(turns)
    overall = _hit_rate(turns)
    lines = [
        f"Session: {path.name}",
        f"Assistant turns: {totals['turns']}",
        f"Overall cache hit ratio: {overall:.1%}  "
        f"(read={totals['cache_read']:,}, create={totals['cache_create']:,})",
        f"Cache TTL split: 5m_creation={totals['ephemeral_5m']:,}  "
        f"1h_creation={totals['ephemeral_1h']:,}",
        "",
        f"{'gap bucket':<11} {'turns':>6} {'hit_rate':>10} {'avg_read':>11} {'avg_create':>11}",
    ]
    for name, _, _ in _BUCKETS:
        b = summary[name]
        n = b["turns"]
        if n == 0:
            lines.append(f"{name:<11} {0:>6} {'—':>10} {'—':>11} {'—':>11}")
            continue
        hit_rate = b["hits"] / n
        avg_read = b["read"] // n
        avg_create = b["create"] // n
        lines.append(f"{name:<11} {n:>6} {hit_rate:>10.1%} {avg_read:>11,} {avg_create:>11,}")
    lines.append("")
    lines.append(_recommendation(overall, totals))
    return "\n".join(lines)


def _format_role_report(port: int, role: str, target_cwd: Path, sessions: list[_Session]) -> str:
    if not sessions:
        return (
            f"No session jsonl files found for Role {role!r} on port {port}.\n"
            f"Expected cwd: {target_cwd}\n"
            f"Searched ~/.claude/projects/*/ for files whose first cwd entry matches."
        )
    all_turns: list[_Turn] = [t for s in sessions for t in s.turns]
    totals = _totals(all_turns)
    overall = _hit_rate(all_turns)
    cold = _cold_starts(sessions)
    avg_cold_cost = _avg_cold_start_cost(sessions)

    first_when = sessions[0].turns[0].when
    last_when = sessions[-1].turns[-1].when
    span_hours = (last_when - first_when).total_seconds() / 3600 if len(all_turns) > 1 else 0

    lines = [
        f"Role: {role}  (port={port})",
        f"cwd: {target_cwd}",
        f"Sessions: {len(sessions)}  Total turns: {totals['turns']}  "
        f"Span: {span_hours:.1f}h  ({first_when.date()} → {last_when.date()})",
        "",
        "Token totals across all sessions:",
        f"  cache_read   : {totals['cache_read']:>14,}  (free re-use)",
        f"  cache_create : {totals['cache_create']:>14,}  (write-through, ~1.25x base)",
        f"  input        : {totals['input']:>14,}  (uncached new content)",
        f"  output       : {totals['output']:>14,}",
        f"  ephemeral_5m : {totals['ephemeral_5m']:>14,}",
        f"  ephemeral_1h : {totals['ephemeral_1h']:>14,}",
        "",
        f"Overall cache hit ratio: {overall:.1%}",
        f"Cold-start sessions: {cold} of {len(sessions)}  "
        f"(avg cache_create on first turn: {avg_cold_cost:,} tokens)",
        "",
    ]
    if all_turns:
        lines.append(
            f"{'gap bucket':<11} {'turns':>6} {'hit_rate':>10} {'avg_read':>11} {'avg_create':>11}"
        )
        summary = _bucket_summary(all_turns)
        for name, _, _ in _BUCKETS:
            b = summary[name]
            n = b["turns"]
            if n == 0:
                lines.append(f"{name:<11} {0:>6} {'—':>10} {'—':>11} {'—':>11}")
                continue
            lines.append(
                f"{name:<11} {n:>6} {b['hits'] / n:>10.1%} "
                f"{b['read'] // n:>11,} {b['create'] // n:>11,}"
            )
        lines.append("")
    lines.append(_recommendation(overall, totals))
    if cold > 1:
        lines.append(
            f"Reset cost: ~{cold * avg_cold_cost:,} tokens of cache_create attributable "
            f"to cold starts ({cold} x {avg_cold_cost:,}). Each reset re-encodes the "
            f"system prompt + tool defs into prompt cache."
        )
    posture = compute_dispatch_posture([s.path for s in sessions])
    if posture.total() > 0:
        lines.append("")
        lines.append(_format_dispatch_posture(posture))
        if posture.heavy_self_pct() > 0.15:
            lines.append(
                f"Note: heavy_self {100 * posture.heavy_self_pct():.1f}% > 15% baseline. "
                "Main role is doing work itself instead of dispatching to a "
                "Task subagent. See dispatcher-discipline skill."
            )
    return "\n".join(lines)


def _format_project_report(port: int, repo_root: Path, claude_root: Path) -> str:
    """List every Role under ``projects/project_{port}/branches/`` and roll each up."""
    if repo_root == MINIONS_ROOT:
        branches_root = project_dir(port) / "branches"
    else:
        branches_root = repo_root / "projects" / f"project_{port}" / "branches"
    if not branches_root.exists():
        return (
            f"No project found at {branches_root}. Was the project created and have any Roles run?"
        )
    rows = []
    for role_dir in sorted(branches_root.iterdir()):
        if not role_dir.is_dir() or role_dir.name == "shared" or role_dir.name == "main":
            continue
        sessions = _discover_sessions_for_cwd(role_dir, claude_root)
        if not sessions:
            rows.append((role_dir.name, 0, 0, 0.0, 0))
            continue
        all_turns = [t for s in sessions for t in s.turns]
        rows.append(
            (
                role_dir.name,
                len(sessions),
                len(all_turns),
                _hit_rate(all_turns),
                _cold_starts(sessions),
            )
        )
    if not rows:
        return f"No Role branches found under {branches_root}."
    lines = [f"Project port {port} — Role token observations", ""]
    lines.append(f"{'role':<20} {'sessions':>9} {'turns':>7} {'hit_rate':>10} {'cold_starts':>12}")
    for name, sessions, turns, hr, cold in rows:
        if turns == 0:
            lines.append(f"{name:<20} {sessions:>9} {turns:>7} {'—':>10} {cold:>12}")
        else:
            lines.append(f"{name:<20} {sessions:>9} {turns:>7} {hr:>10.1%} {cold:>12}")
    return "\n".join(lines)


def _recommendation(overall: float, totals: dict[str, int]) -> str:
    if totals["turns"] == 0:
        return ""
    parts = []
    if overall >= 0.90:
        parts.append(
            "Recommendation: cache hit rate is healthy; keep cache_keepalive_seconds: 0 (default)."
        )
    elif overall >= 0.70:
        parts.append(
            "Recommendation: borderline. Inspect 5-15min and 15-60min buckets; "
            "if those drop below 70%, consider cache_keepalive_seconds: 270."
        )
    else:
        parts.append(
            "Recommendation: hit rate is low. Set cache_keepalive_seconds: 270 in "
            "gru.yaml so mos_await_events fires a stable ack just before the cliff."
        )
    if totals["ephemeral_1h"] > 0:
        parts.append(
            "Note: ephemeral_1h_input_tokens > 0 — your gateway honors "
            "ENABLE_PROMPT_CACHING_1H. You can raise cache_keepalive_seconds to "
            "~3300 (55min) to amortize the keepalive cost over a 1-hour TTL."
        )
    elif totals["ephemeral_5m"] > 0:
        parts.append(
            "Note: only ephemeral_5m_input_tokens observed. Your gateway does "
            "not appear to honor ENABLE_PROMPT_CACHING_1H; the 5-min TTL is "
            "what you actually have."
        )
    return "\n".join(parts)


# Backward-compat shim: keep the name the existing tests import.
_format_report = _format_session_report


# --------------------------------------------------------------------------
# Dispatch posture
# --------------------------------------------------------------------------
#
# Orthogonal to token cost: tells us how often the main role agent
# *self-executed* (Bash/Edit/Write) vs *dispatched* (Task subagent). The
# `dispatcher-discipline` skill says the main role must be a pure
# dispatcher; this metric checks whether real session traffic agrees.
#
# Buckets:
#   dispatch    — Task / Agent (a real subagent)
#   coord       — eacn3_* / mcp__minionsos__* (project coordination, not heavy)
#   heavy_self  — Bash / Edit / Write / MultiEdit / NotebookEdit (main does work)
#   read_self   — Read / Grep / Glob / WebSearch / WebFetch (main reads)
#   misc        — anything else (ToolSearch, etc.)
#
# heavy_self is the canary: anything > a low threshold means the main
# session is leaking work into its own context, which is the largest
# uncached-input cost driver per empirical measurement on real Roles.

_DISPATCH_NAMES = frozenset({"Task", "Agent"})
_DISPATCH_PREFIXES: tuple[str, ...] = ()
_COORD_PREFIXES = ("mcp__minionsos__", "mcp__eacn3__")
_HEAVY_SELF = frozenset({"Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"})
_READ_SELF = frozenset({"Read", "Grep", "Glob", "WebSearch", "WebFetch"})

_POSTURE_BUCKETS = ("dispatch", "coord", "heavy_self", "read_self", "misc")


class _DispatchPosture(NamedTuple):
    """Tool-use bucket counts for one or more sessions.

    Aggregations sum the bucket fields directly. Use ``.total()`` and
    ``.heavy_self_pct()`` rather than recomputing — keeps the threshold
    semantics in one place.
    """

    dispatch: int
    coord: int
    heavy_self: int
    read_self: int
    misc: int

    def total(self) -> int:
        return self.dispatch + self.coord + self.heavy_self + self.read_self + self.misc

    def heavy_self_pct(self) -> float:
        t = self.total()
        return self.heavy_self / t if t else 0.0

    def as_dict(self) -> dict[str, int]:
        return {b: getattr(self, b) for b in _POSTURE_BUCKETS}


def _classify_tool(name: str) -> str:
    """Map one tool_use name to its posture bucket."""
    if name in _DISPATCH_NAMES or name.startswith(_DISPATCH_PREFIXES):
        return "dispatch"
    if name.startswith(_COORD_PREFIXES):
        return "coord"
    if name in _HEAVY_SELF:
        return "heavy_self"
    if name in _READ_SELF:
        return "read_self"
    return "misc"


def _posture_from_tool_names(names: list[str]) -> _DispatchPosture:
    """Pure aggregator. Given an iterable of tool_use names, bucket them."""
    counts = dict.fromkeys(_POSTURE_BUCKETS, 0)
    for name in names:
        counts[_classify_tool(name)] += 1
    return _DispatchPosture(**counts)


def _tool_names_from_jsonl(path: Path) -> list[str]:
    """Extract every tool_use name an assistant emitted in *path*.

    Robust to malformed lines and non-assistant entries; never raises.
    """
    names: list[str] = []
    try:
        fh = path.open(encoding="utf-8")
    except OSError:
        return names
    with fh:
        for line in fh:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "assistant":
                continue
            content = (obj.get("message") or {}).get("content") or []
            if not isinstance(content, list):
                continue
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    n = c.get("name")
                    if isinstance(n, str):
                        names.append(n)
    return names


def compute_dispatch_posture(paths: list[Path]) -> _DispatchPosture:
    """Aggregate posture across many jsonl files."""
    names: list[str] = []
    for p in paths:
        names.extend(_tool_names_from_jsonl(p))
    return _posture_from_tool_names(names)


def _format_dispatch_posture(posture: _DispatchPosture) -> str:
    total = posture.total()
    if total == 0:
        return "Dispatch posture: no tool_use telemetry."
    lines = ["Dispatch posture (tool_use distribution across these sessions):"]
    for bucket in _POSTURE_BUCKETS:
        n = getattr(posture, bucket)
        pct = 100 * n / total if total else 0.0
        lines.append(f"  {bucket:<11} {n:>6}  {pct:>5.1f}%")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


_DEFAULT_REPO_ROOT = MINIONS_ROOT
_DEFAULT_CLAUDE_ROOT = Path.home() / ".claude" / "projects"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session",
        type=Path,
        help="Path to a single ~/.claude/projects/<slug>/<id>.jsonl",
    )
    parser.add_argument("--port", type=int, help="Project port for Role/project rollup.")
    parser.add_argument("--role", type=str, help="Role name within the project.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_DEFAULT_REPO_ROOT,
        help=f"MinionsOS repo root (default: {_DEFAULT_REPO_ROOT}).",
    )
    parser.add_argument(
        "--claude-root",
        type=Path,
        default=_DEFAULT_CLAUDE_ROOT,
        help="Path to ~/.claude/projects/.",
    )
    parser.add_argument(
        "session_jsonl",
        nargs="?",
        type=Path,
        help="Backward-compat positional path to a single session jsonl.",
    )
    args = parser.parse_args(argv)

    if args.session_jsonl and not args.session:
        args.session = args.session_jsonl

    if args.session:
        if not args.session.exists():
            print(f"file not found: {args.session}", file=sys.stderr)
            return 2
        turns = _load_turns(args.session)
        print(_format_session_report(args.session, turns))
        return 0

    if args.port is not None and args.role:
        target = _role_cwd(args.port, args.role, args.repo_root)
        sessions = _discover_sessions_for_cwd(target, args.claude_root)
        print(_format_role_report(args.port, args.role, target, sessions))
        return 0

    if args.port is not None:
        print(_format_project_report(args.port, args.repo_root, args.claude_root))
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
