"""Regression tests for the Role launcher spawn path.

Two contracts these tests pin down (both came from the dispatch-eval e2e
on 2026-05-19, where the launcher silently failed to bring claude up):

1. The tmux ``new-session`` command must NOT shell-pipe claude through
   ``tee`` (or anything else). Claude Code 2.1+ detects a non-TTY stdout
   on a piped command and switches to ``--print`` mode, which then
   fails with "Input must be provided through stdin" because the
   launcher feeds its initial prompt via ``send-keys``, not stdin.
2. After spawning, the launcher must call ``tmux pipe-pane`` for log
   capture — that path preserves the TTY because the pty is already
   attached to claude when pipe-pane taps it.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


def _captured_calls() -> list[list[str]]:
    """Return a list to be filled with subprocess.run argv per call."""
    return []


def test_spawn_tmux_does_not_pipe_claude_through_tee(tmp_path: Path) -> None:
    """The tmux command-string must not contain ``| tee`` (or any pipe).

    A piped stdout makes Claude Code go into ``--print`` mode — the
    interactive REPL never starts and the role process dies on launch.
    """
    from minions.lifecycle import role_launcher

    captured: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        captured.append(list(argv))
        result = MagicMock()
        result.returncode = 0
        result.stderr = b""
        return result

    log_path = tmp_path / "logs" / "role-coder.log"
    with patch.object(role_launcher.subprocess, "run", side_effect=fake_run):
        role_launcher._spawn_tmux(
            session_name="mos-12345-coder",
            cwd=tmp_path,
            env={"FOO": "bar"},
            argv=["uv", "run", "claude", "--name", "test"],
            initial_prompt="hello",
            log_path=log_path,
        )

    new_session_calls = [c for c in captured if c[:2] == ["tmux", "new-session"]]
    assert len(new_session_calls) == 1, (
        f"expected one tmux new-session call, got {len(new_session_calls)}"
    )
    cmd_str = new_session_calls[0][-1]
    assert "tee" not in cmd_str, (
        f"tmux new-session command must not pipe claude through tee — got: {cmd_str!r}"
    )
    assert "|" not in cmd_str, (
        f"tmux new-session command must not pipe claude at all — got: {cmd_str!r}"
    )


def test_spawn_tmux_uses_pipe_pane_for_logging(tmp_path: Path) -> None:
    """Log capture must go through ``tmux pipe-pane``, not a shell pipe.

    pipe-pane taps the pty after claude has attached, so claude's
    is-a-TTY check passes and it stays in interactive REPL mode.
    """
    from minions.lifecycle import role_launcher

    captured: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        captured.append(list(argv))
        result = MagicMock()
        result.returncode = 0
        result.stderr = b""
        return result

    log_path = tmp_path / "logs" / "role-coder.log"
    with patch.object(role_launcher.subprocess, "run", side_effect=fake_run):
        role_launcher._spawn_tmux(
            session_name="mos-12345-coder",
            cwd=tmp_path,
            env={},
            argv=["claude"],
            initial_prompt="hi",
            log_path=log_path,
        )

    pipe_pane_calls = [c for c in captured if c[:2] == ["tmux", "pipe-pane"]]
    assert len(pipe_pane_calls) == 1, (
        f"expected exactly one tmux pipe-pane call, got {len(pipe_pane_calls)}"
    )
    pp = pipe_pane_calls[0]
    assert "-t" in pp and "mos-12345-coder" in pp, "pipe-pane must target the new session"
    # The shell command piped into pipe-pane should append to log_path
    shell_cmd = pp[-1]
    assert "cat" in shell_cmd
    assert ">>" in shell_cmd
    assert str(log_path) in shell_cmd


def test_send_initial_prompt_sends_two_enters(tmp_path: Path) -> None:
    """Claude Code's REPL needs an explicit second Enter to submit a paste.

    Without the second Enter, the multiline forever-loop prompt sits in
    the input field and the role never wakes — the cold-start failure
    mode observed in the dispatch-eval e2e on 2026-05-19.

    GitHub Issue #22: pasting via load-buffer + paste-buffer rather than
    send-keys -l, so prompts > 32 KB do not hit the tmux argv limit.
    """
    from minions.lifecycle import role_launcher

    captured: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        captured.append(list(argv))
        result = MagicMock()
        result.returncode = 0
        result.stderr = b""
        return result

    # Patch sleep so the test stays fast, AND short-circuit the new
    # poll-until-ready helper (Issue #2 fix) so we only exercise the
    # send-keys / Enter path here.
    with (
        patch.object(role_launcher.subprocess, "run", side_effect=fake_run),
        patch("time.sleep"),
        patch.object(role_launcher, "_wait_for_repl_ready", return_value=True),
    ):
        role_launcher._tmux_send_initial_prompt("mos-12345-coder", "hello world")

    enter_calls = [c for c in captured if c[:2] == ["tmux", "send-keys"] and c[-1] == "Enter"]
    assert len(enter_calls) == 2, (
        f"expected two Enter sends (commit paste + submit), got {len(enter_calls)}"
    )

    # GitHub Issue #22: paste must go through load-buffer + paste-buffer,
    # not `send-keys -l`, so prompts > 32 KB don't hit tmux argv limit.
    load_buffer_calls = [c for c in captured if c[:2] == ["tmux", "load-buffer"]]
    paste_buffer_calls = [c for c in captured if c[:2] == ["tmux", "paste-buffer"]]
    assert len(load_buffer_calls) == 1, "expected exactly one load-buffer call"
    assert len(paste_buffer_calls) == 1, "expected exactly one paste-buffer call"
    # Verify paste-buffer uses -d to clean up after itself.
    assert "-d" in paste_buffer_calls[0]
    # Verify the buffer name is referenced in both calls.
    buf_name = next(arg for arg in load_buffer_calls[0] if arg.startswith("minionsos_init_"))
    assert buf_name in paste_buffer_calls[0]


# ---------------------------------------------------------------------------
# GitHub Issue #2 — poll-until-ready before send-keys.
# Replaces the racy fixed time.sleep(3) with a capture-pane probe loop.
# ---------------------------------------------------------------------------


def test_wait_for_repl_ready_returns_immediately_when_marker_present() -> None:
    """When capture-pane already shows the Claude prompt glyph, the wait
    helper must return True without sleeping further."""
    from minions.lifecycle import role_launcher

    def fake_capture(_session: str) -> str:
        return "Welcome to Claude Code!\n\n❯ "

    with patch.object(role_launcher, "_capture_pane", side_effect=fake_capture):
        result = role_launcher._wait_for_repl_ready(
            "mos-12345-coder", timeout=1.0, poll_interval=0.01
        )
    assert result is True


def test_wait_for_repl_ready_times_out_when_marker_never_appears() -> None:
    """When capture-pane never shows a marker, the helper must give up
    after timeout and return False (best-effort fallback, not a raise)."""
    from minions.lifecycle import role_launcher

    with patch.object(role_launcher, "_capture_pane", return_value=""):
        result = role_launcher._wait_for_repl_ready("mos-stuck", timeout=0.05, poll_interval=0.01)
    assert result is False


def test_send_keys_runs_after_wait_for_repl_ready() -> None:
    """Order matters: the wait helper must fire BEFORE any send-keys,
    otherwise the original race (keystrokes against an unattached REPL)
    is back."""
    from minions.lifecycle import role_launcher

    call_order: list[str] = []

    def fake_wait(*_a, **_k):
        call_order.append("wait")
        return True

    def fake_run(argv, **_kw):
        if argv[:2] == ["tmux", "send-keys"]:
            call_order.append("send-keys")
        result = MagicMock()
        result.returncode = 0
        result.stderr = b""
        return result

    with (
        patch.object(role_launcher.subprocess, "run", side_effect=fake_run),
        patch("time.sleep"),
        patch.object(role_launcher, "_wait_for_repl_ready", side_effect=fake_wait),
    ):
        role_launcher._tmux_send_initial_prompt("mos-12345-coder", "hello world")

    assert call_order, "neither wait nor send-keys was invoked"
    assert call_order[0] == "wait", (
        f"_wait_for_repl_ready must run before any send-keys; got order {call_order}"
    )
    assert "send-keys" in call_order, "send-keys must still run after the wait"


def test_spawn_tmux_returns_before_prompt_delivery_completes(tmp_path: Path) -> None:
    """`_spawn_tmux` must not block on `_tmux_send_initial_prompt`.

    The full prompt delivery sequence (poll-until-REPL-ready up to 30 s
    + paste + commit + retry up to 3 attempts × 5 s activity check)
    can cost ~47 s of wall-clock per role. With Gru spawning ~7 roles
    at project bootstrap, that's ~5 min of pure synchronization. C
    moves delivery to a daemon thread so the launcher returns as soon
    as the tmux session is alive and the prompt is *queued*.

    This test simulates a slow REPL-ready (5 s wait) and asserts the
    caller returns within ~50 ms.
    """
    import threading
    import time

    from minions.lifecycle import role_launcher

    delivery_started = threading.Event()
    delivery_done = threading.Event()

    def fake_run(argv, **_kw):
        result = MagicMock()
        result.returncode = 0
        result.stderr = b""
        return result

    def slow_send(_session_name, _prompt):
        delivery_started.set()
        time.sleep(0.5)  # simulate slow REPL warmup
        delivery_done.set()

    log_path = tmp_path / "logs" / "role-coder.log"
    with (
        patch.object(role_launcher.subprocess, "run", side_effect=fake_run),
        patch.object(role_launcher, "_tmux_send_initial_prompt", side_effect=slow_send),
        # Default = async (no env var); explicit del to be defensive.
        patch.dict("os.environ", {}, clear=False),
    ):
        # Make sure sync override is OFF for this test.
        import os

        os.environ.pop("MINIONS_ROLE_LAUNCHER_SYNC", None)

        t0 = time.monotonic()
        role_launcher._spawn_tmux(
            session_name="mos-12345-coder",
            cwd=tmp_path,
            env={},
            argv=["claude"],
            initial_prompt="hi",
            log_path=log_path,
        )
        elapsed = time.monotonic() - t0

    # Caller must have returned WAY before the slow_send 0.5s sleep finished.
    assert elapsed < 0.2, (
        f"_spawn_tmux blocked on prompt delivery; elapsed={elapsed:.3f}s. "
        "C-fix is for it to return as soon as the tmux session is alive."
    )
    # And the daemon thread must actually deliver eventually.
    assert delivery_started.wait(timeout=2.0), "delivery thread never started"
    assert delivery_done.wait(timeout=2.0), "delivery thread never finished"


def test_spawn_tmux_blocks_on_delivery_when_sync_env_set(tmp_path: Path) -> None:
    """Tests that need synchronous delivery can opt in via the env switch.

    The env-gated sync path preserves the contract for any test that
    previously assumed `_spawn_tmux` had finished injecting the prompt
    by the time it returned.
    """
    import os
    import time

    from minions.lifecycle import role_launcher

    def fake_run(argv, **_kw):
        result = MagicMock()
        result.returncode = 0
        result.stderr = b""
        return result

    def slow_send(_session_name, _prompt):
        time.sleep(0.3)

    log_path = tmp_path / "logs" / "role-coder.log"
    with (
        patch.object(role_launcher.subprocess, "run", side_effect=fake_run),
        patch.object(role_launcher, "_tmux_send_initial_prompt", side_effect=slow_send),
        patch.dict(os.environ, {"MINIONS_ROLE_LAUNCHER_SYNC": "1"}),
    ):
        t0 = time.monotonic()
        role_launcher._spawn_tmux(
            session_name="mos-12345-coder",
            cwd=tmp_path,
            env={},
            argv=["claude"],
            initial_prompt="hi",
            log_path=log_path,
        )
        elapsed = time.monotonic() - t0

    # In sync mode the caller waits for delivery (~0.3 s).
    assert elapsed >= 0.25, (
        f"sync mode should block on delivery; elapsed={elapsed:.3f}s "
        "(expected ≥0.25s)"
    )
