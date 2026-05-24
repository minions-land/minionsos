"""Detect Role processes wedged in an empty-upstream / bare-`ack` loop.

GitHub Issue #15: a Role's tmux session stays alive, heartbeats refresh,
and tool calls fire — but every model turn is either
``[upstream returned no content]`` or a single-token ``ack``. The
cache-keepalive contract makes byte-stable ``ack`` looping the prescribed
behavior for genuine keepalive events, so the role can sit in the wedge
state indefinitely without breaking any contract.

The Gru-side watchdog cannot use heartbeat staleness (refreshed every
cycle by the PreToolUse hook) or event-log mtime (cache_keepalive events
are not appended). The only reliable signal is the role's tmux pane log,
which captures the empty-content marker and the bare ``ack`` lines
verbatim.

This module is a pure function over the log file: ``inspect_log_tail``
reads the last *tail_bytes* of the role log, strips ANSI escape
sequences, and counts ``[upstream returned no content]`` and bare ``ack``
occurrences. The Gru loop owns the policy of when a count is
"wedge enough" to act on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

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
