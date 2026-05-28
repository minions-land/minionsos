"""Tests for the parked-prompt detector + kicker (Issue #29 safety net)."""
# ruff: noqa: RUF001, RUF002, RUF003
# The `❯` glyph is the actual Claude Code prompt cursor; matching it
# verbatim is the load-bearing part of the detection. We can't replace
# it with > without breaking the regex.

from __future__ import annotations

import subprocess
from unittest.mock import patch

from minions.lifecycle import parked_prompt

_PARKED_PANE_SAMPLE = (
    "  ## Resume_protocol\n"
    "  After this summary lands, your IMMEDIATE next tool call MUST be:\n"
    "    mos_draft_summary()\n"
    "    mos_await_events()\n"
    "  PostCompact hook completed successfully\n"
    "\n"
    "──────────────────────────────────── p37596/noter ──\n"
    "❯ \n"
    "────────────────────────────────────────────────────\n"
    "  ⏵⏵ bypass permissions on (shift+tab to cycle)\n"
)

_HEALTHY_PANE_SAMPLE = (
    "● Calling mos_draft_summary…\n"
    "● Found 3 pending plans\n"
    "● Calling mos_await_events…\n"
    "  ✻ Brewed for 12s\n"
)


def _fake_capture_pane(stdout: str):
    """Build a subprocess.CompletedProcess mock returning *stdout*."""

    def _run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=stdout, stderr=""
        )

    return _run


class TestDetectParkedPane:
    """Detection requires the ❯ cursor on its own line in the tail."""

    def test_parked_signature_is_detected(self) -> None:
        with patch.object(subprocess, "run", side_effect=_fake_capture_pane(_PARKED_PANE_SAMPLE)):
            sig = parked_prompt.detect_parked_pane("mos-37596-noter")
        assert sig.parked is True
        assert sig.session_name == "mos-37596-noter"
        assert sig.snapshot_lines > 0

    def test_healthy_pane_is_not_parked(self) -> None:
        with patch.object(subprocess, "run", side_effect=_fake_capture_pane(_HEALTHY_PANE_SAMPLE)):
            sig = parked_prompt.detect_parked_pane("mos-37596-coder")
        assert sig.parked is False

    def test_tmux_failure_returns_not_parked(self) -> None:
        def _run_fail(*args, **kwargs):
            return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="")

        with patch.object(subprocess, "run", side_effect=_run_fail):
            sig = parked_prompt.detect_parked_pane("mos-x-y")
        assert sig.parked is False

    def test_missing_tmux_binary_returns_not_parked(self) -> None:
        with patch.object(subprocess, "run", side_effect=FileNotFoundError("no tmux")):
            sig = parked_prompt.detect_parked_pane("mos-x-y")
        assert sig.parked is False

    def test_ansi_wrapped_cursor_is_still_detected(self) -> None:
        """The pane snapshot from real Claude Code sessions includes ANSI
        escape codes around the cursor — detection must strip ANSI first."""
        ansi_wrapped = (
            "\x1b[1m──────── p37596/noter ──\x1b[0m\n"
            "\x1b[38;5;174m❯\x1b[0m \n"
            "\x1b[1m────────────────────────\x1b[0m\n"
        )
        with patch.object(subprocess, "run", side_effect=_fake_capture_pane(ansi_wrapped)):
            sig = parked_prompt.detect_parked_pane("mos-37596-noter")
        assert sig.parked is True


class TestKickPane:
    """Kick = literal paste + Enter, mirroring `mos role kick`."""

    def test_kick_sends_both_paste_and_enter(self) -> None:
        calls: list[list[str]] = []

        def _run(args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")

        with patch.object(subprocess, "run", side_effect=_run):
            assert parked_prompt.kick_pane("mos-37596-noter") is True

        # First call: literal paste of the prompt — the /goal slash command
        # so Claude Code keeps the stopping rule active across turns.
        assert calls[0][:5] == ["tmux", "send-keys", "-t", "mos-37596-noter", "-l"]
        assert calls[0][5].startswith("/goal ")
        assert "mos_await_events" in calls[0][5]
        assert calls[0][5] == parked_prompt.DEFAULT_KICK_PROMPT
        # Second call: Enter.
        assert calls[1] == ["tmux", "send-keys", "-t", "mos-37596-noter", "Enter"]

    def test_kick_returns_false_on_paste_failure(self) -> None:
        def _run(args, **kwargs):
            return subprocess.CompletedProcess(args=args, returncode=1, stdout=b"", stderr=b"")

        with patch.object(subprocess, "run", side_effect=_run):
            assert parked_prompt.kick_pane("mos-x-y") is False

    def test_kick_returns_false_on_missing_tmux(self) -> None:
        with patch.object(subprocess, "run", side_effect=FileNotFoundError("no tmux")):
            assert parked_prompt.kick_pane("mos-x-y") is False

    def test_kick_accepts_custom_prompt(self) -> None:
        calls: list[list[str]] = []

        def _run(args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")

        with patch.object(subprocess, "run", side_effect=_run):
            parked_prompt.kick_pane("mos-37596-noter", prompt="Custom kick text")

        assert calls[0][5] == "Custom kick text"
