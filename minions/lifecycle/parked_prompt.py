"""Detect Role processes parked at the input prompt after /compact.

GitHub Issue #29: after Claude Code's ``/compact`` runs, the role's
tmux pane shows the resume-protocol summary text and then the ``❯``
input cursor. The model never gets a turn to obey the resume protocol
because Claude Code returns control to the user prompt. The
``post_compact_draft`` hook tries to inject a kick on the way out, but
if that fails (tmux unavailable, race with redraw, etc.) the role
parks indefinitely.

This module is the Gru-side safety net: scan each role's tmux pane on
a cadence, detect the parked-at-prompt signature, and kick via the
same ``tmux send-keys -l`` path the hook uses. A cooldown prevents
re-kicking the same role on every tick — once we kick, the role gets
a turn, the heartbeat refreshes, and the sweep stops firing.

Detection signal (from the project_37596 capture):

    ────────────── p<port>/<role> ──
    ❯
    ──────────────────────────────────

The ``❯`` cursor on a line of its own, surrounded by the bordered
status bar. We tail the pane snapshot, strip ANSI, and look for the
pattern. False positives are bounded by also requiring that the role's
heartbeat file is at least ``min_age_seconds`` stale — a healthy role
that just happens to render a momentary cursor between turns won't
trigger.
"""
# ruff: noqa: RUF001, RUF002, RUF003
# The `❯` glyph is the literal Claude Code prompt cursor — matching it
# verbatim is the load-bearing part of detection. Keep the docstring,
# comment, regex, and string-literal forms verbatim so future readers
# grep for the same byte that appears in pane snapshots.

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass

from minions.tools.utils import strip_ansi_escapes

logger = logging.getLogger(__name__)

# The Claude Code TUI's input cursor. Captured verbatim from project_37596
# pane snapshots — a single ❯ glyph followed by whitespace and end-of-line.
_PROMPT_CURSOR_RE = re.compile(r"^\s*❯\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ParkedSignal:
    """Result of scanning a role's tmux pane."""

    parked: bool
    snapshot_lines: int
    session_name: str


def _capture_pane(session_name: str, *, lines: int = 40) -> str | None:
    """Return the last *lines* of *session_name*'s pane, ANSI-stripped.

    Returns None on tmux failure (no server, dead session, etc.).
    """
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p", "-S", f"-{lines}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        logger.debug("parked_prompt: capture-pane failed for %s: %s", session_name, exc)
        return None
    if result.returncode != 0:
        return None
    return strip_ansi_escapes(result.stdout or "")


def detect_parked_pane(session_name: str, *, lines: int = 40) -> ParkedSignal:
    """Probe *session_name*'s pane for the parked-at-prompt signature.

    Looks for the ``❯`` cursor on its own line in the recent tail. The
    cursor naturally appears for a moment between turns, which is why
    this signal must be combined with a heartbeat-age check at the
    caller — see ``_sweep_parked_roles`` in the Gru loop.
    """
    snapshot = _capture_pane(session_name, lines=lines)
    if snapshot is None:
        return ParkedSignal(parked=False, snapshot_lines=0, session_name=session_name)
    sample = snapshot.splitlines()
    parked = bool(_PROMPT_CURSOR_RE.search(snapshot))
    return ParkedSignal(parked=parked, snapshot_lines=len(sample), session_name=session_name)


# The recovery kick. We send a Claude Code ``/goal`` slash command rather than
# a plain-text "Continue per resume protocol." sentence, because the slash
# command goes into a different UI state than user messages: Claude Code
# renders ``◎ /goal active (Ns)`` in the TUI footer for the entire goal
# lifetime, so the model sees the stopping rule at every subsequent turn
# boundary and cannot "decide to stop" while the goal is unsatisfied. Plain
# text was a one-shot user message that got read, ack'd, and forgotten —
# observed empirically against this project's roles when 0/7 plain-text kicks
# woke any role, while 6/7 ``/goal`` kicks woke them within 30s. See
# GitHub Issue #64 for the empirical study and the original ``/goal`` insight
# from the project author. The stopping rule names ``mos_await_events`` so
# the goal exits cleanly when a real EACN event finally arrives.
DEFAULT_KICK_PROMPT = (
    "/goal Continue your event loop: stopping rule = your next "
    "mos_await_events() call returns with a real EACN event. Do not stop "
    "before then. Heartbeat must stay <60 s."
)


def kick_pane(session_name: str, *, prompt: str = DEFAULT_KICK_PROMPT) -> bool:
    """Send the recovery kick (literal paste + Enter) to *session_name*.

    Mirrors the post-compact hook's ``_kick_own_pane`` shape but runs
    synchronously — the Gru sweep tick is already on a thread, so a
    half-second blocking sleep+Enter is fine. Returns True on success.
    """
    try:
        rc = subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "-l", prompt],
            check=False,
            capture_output=True,
            timeout=2.0,
        ).returncode
        if rc != 0:
            return False
        # Brief pause for the TUI to commit the literal paste before Enter.
        time.sleep(0.5)
        rc = subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "Enter"],
            check=False,
            capture_output=True,
            timeout=2.0,
        ).returncode
        return rc == 0
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        logger.debug("parked_prompt: kick failed for %s: %s", session_name, exc)
        return False
