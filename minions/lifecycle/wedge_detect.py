"""Detect Role processes wedged in an empty-upstream / bare-`ack` loop.

GitHub Issue #15: a Role's tmux session stays alive, heartbeats refresh,
and tool calls fire — but every model turn is either
``[upstream returned no content]`` or a single-token ``ack``. The
cache-keepalive contract makes byte-stable ``ack`` looping the prescribed
behavior for genuine keepalive events, so the role can sit in the wedge
state indefinitely without breaking any contract.

The Gru-side watchdog cannot use heartbeat staleness (refreshed every
cycle by the PreToolUse hook) or event-log mtime (cache_keepalive events
are not appended). Two signals exist:

1. **Session JSONL** (``inspect_session_tail`` — *primary*) — Claude Code
   writes every assistant turn to ``~/.claude/projects/<cwd-slug>/<sid>.jsonl``
   as structured records. Counting empty-content and bare-``ack`` assistant
   turns there is exact and not affected by terminal styling. This is the
   path GitHub Issue #26 prescribes.
2. **Tmux pty log** (``inspect_log_tail`` — *fallback*) — when no session
   JSONL is locatable yet (e.g. very early in cold-start before the first
   turn is written), the watchdog falls back to scanning the pty stream
   with ANSI escapes stripped. This used to be the only signal but missed
   the live wedge in production because the pty log is ANSI-wrapped TUI
   redraws — see #26 for the failure mode. We keep it as defense-in-depth.

The Gru loop owns the policy of when a count is "wedge enough" to act on.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Claude Code prints assistant turn markers as `●`. A bare `ack` turn
# looks like `● ack` (sometimes with leading whitespace). Match the
# whole-line pattern so we don't false-positive on `ack`-substrings
# inside narrative text.
_ACK_LINE_RE = re.compile(r"^\s*●\s*ack\s*$")
_EMPTY_MARKER = "[upstream returned no content]"
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


@dataclass(frozen=True)
class WedgeSignal:
    """Counts extracted from a role-log tail for wedge detection."""

    empty_marker_count: int
    ack_line_count: int
    sampled_lines: int
    log_path: Path

    @property
    def total(self) -> int:
        return self.empty_marker_count + self.ack_line_count


def inspect_log_tail(log_path: Path, *, tail_bytes: int = 16384) -> WedgeSignal:
    """Read the last *tail_bytes* of *log_path* and count wedge markers.

    Returns zeros when the file is missing or unreadable. Does not raise:
    the caller is the watchdog and should keep ticking even if a single
    role's log is temporarily unreadable.
    """
    if not log_path.is_file():
        return WedgeSignal(0, 0, 0, log_path)
    try:
        size = log_path.stat().st_size
        with log_path.open("rb") as fh:
            if size > tail_bytes:
                fh.seek(size - tail_bytes)
            raw = fh.read()
    except OSError:
        return WedgeSignal(0, 0, 0, log_path)

    text = raw.decode("utf-8", errors="replace")
    text = _ANSI_ESCAPE_RE.sub("", text)
    lines = text.splitlines()
    empty_count = sum(1 for line in lines if _EMPTY_MARKER in line)
    ack_count = sum(1 for line in lines if _ACK_LINE_RE.match(line))
    return WedgeSignal(
        empty_marker_count=empty_count,
        ack_line_count=ack_count,
        sampled_lines=len(lines),
        log_path=log_path,
    )


def is_wedged(signal: WedgeSignal, *, threshold: int) -> bool:
    """Wedge predicate: enough markers in the recent tail to act on.

    The predicate is intentionally permissive on the *kind* of marker:
    either pattern alone hitting threshold is enough, since both indicate
    the role made no productive progress for that many recent turns. We
    also require at least one of each to land — a long run of pure
    `ack`s with zero upstream-empty markers is consistent with a healthy
    cache-keepalive loop on a quiet project, and we don't want to kill
    that.
    """
    if signal.empty_marker_count == 0 and signal.ack_line_count == 0:
        return False
    # Strong signal: empty-upstream marker AND ack lines both present
    # multiple times in the tail.
    if signal.empty_marker_count >= threshold and signal.ack_line_count >= 1:
        return True
    return signal.ack_line_count >= threshold and signal.empty_marker_count >= 1


# ---------------------------------------------------------------------------
# Session-JSONL signal (primary — Issue #26)
# ---------------------------------------------------------------------------


def _cwd_slug(cwd: Path) -> str:
    """Convert a cwd Path to the Claude Code projects-dir slug.

    Claude Code derives the slug by replacing ``/`` with ``-``, leaving a
    leading ``-`` for the absolute root. Example:
    ``/Users/mjm/MinionsOS`` → ``-Users-mjm-MinionsOS``. We mirror that
    rule rather than guessing — wrong slug means wrong dir means false
    "no session found" and a watchdog blind spot.
    """
    return str(cwd).replace("/", "-")


def find_session_jsonl(
    cwd: Path,
    *,
    projects_root: Path | None = None,
) -> Path | None:
    """Return the most recently modified session ``.jsonl`` for *cwd*.

    Returns ``None`` when the projects directory does not exist or holds
    no ``.jsonl`` file. We pick the newest file by ``st_mtime`` because a
    Role process that resumes via ``--resume`` will append to its existing
    session, while a cold-started Role creates a fresh one — either way
    the freshest mtime is the live session.
    """
    root = projects_root or Path(os.path.expanduser("~/.claude/projects"))
    slug_dir = root / _cwd_slug(cwd)
    if not slug_dir.is_dir():
        return None
    candidates = [p for p in slug_dir.glob("*.jsonl") if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def inspect_session_tail(
    session_jsonl: Path,
    *,
    tail_turns: int = 32,
) -> WedgeSignal:
    """Count empty / bare-``ack`` assistant turns in the last *tail_turns*.

    Reads the JSONL line by line, keeps only ``type == "assistant"``
    records, and inspects each turn's ``message.content`` list:

    - **empty turn** = no ``text`` parts (or all ``text`` parts blank)
      AND no ``tool_use`` parts. This is the JSONL form of the
      ``[upstream returned no content]`` marker — the assistant produced
      no output at all.
    - **bare-``ack`` turn** = exactly the literal text ``ack`` (case-
      insensitive, whitespace-stripped) and no ``tool_use`` parts. The
      ``mos_await_events`` keepalive ack contract makes this the
      prescribed turn for byte-stable cache replay; many in a row is
      the wedge signature.

    Tool-using turns and turns with substantive prose are healthy
    progress, even if a brief ``ack`` is bundled in — those do not count.
    """
    if not session_jsonl.is_file():
        return WedgeSignal(0, 0, 0, session_jsonl)
    try:
        with session_jsonl.open("r", encoding="utf-8") as fh:
            assistant_records: list[dict] = []
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") == "assistant":
                    assistant_records.append(rec)
    except OSError:
        return WedgeSignal(0, 0, 0, session_jsonl)

    tail = assistant_records[-tail_turns:]
    empty = ack = 0
    for rec in tail:
        msg = rec.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            text = (content or "").strip() if isinstance(content, str) else ""
            if not text:
                empty += 1
            elif text.lower() == "ack":
                ack += 1
            continue
        text_parts: list[str] = []
        tool_uses = 0
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype == "text":
                text_parts.append(part.get("text", ""))
            elif ptype == "tool_use":
                tool_uses += 1
        joined = "".join(text_parts).strip()
        # Empty marker = no text content AND no tool call (the
        # ``[upstream returned no content]`` case in the pty log; a
        # JSONL assistant record with empty content list).
        if not joined and tool_uses == 0:
            empty += 1
        # Bare-ack = text is exactly "ack". A turn that says only "ack"
        # and then calls ``mos_await_events`` is the keepalive cadence —
        # one or two of these is healthy, ``threshold`` of them with at
        # least one empty marker mixed in is the wedge signature.
        elif joined.lower() == "ack":
            ack += 1
    return WedgeSignal(
        empty_marker_count=empty,
        ack_line_count=ack,
        sampled_lines=len(tail),
        log_path=session_jsonl,
    )


def inspect_role(
    *,
    cwd: Path,
    log_path: Path,
    tail_turns: int = 32,
    tail_bytes: int = 16384,
    projects_root: Path | None = None,
) -> WedgeSignal:
    """Highest-level inspector: prefer session JSONL, fall back to pty log.

    The watchdog calls this with the role's worktree (cwd) and pty log.
    Returns the session-JSONL signal when a session file exists, since it
    is exact; falls back to the ANSI-stripped pty log otherwise so cold-
    started roles (no session file yet) still get a signal.
    """
    session_jsonl = find_session_jsonl(cwd, projects_root=projects_root)
    if session_jsonl is not None:
        return inspect_session_tail(session_jsonl, tail_turns=tail_turns)
    return inspect_log_tail(log_path, tail_bytes=tail_bytes)
