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

    new_session_calls = [
        c for c in captured if c[:2] == ["tmux", "new-session"]
    ]
    assert len(new_session_calls) == 1, (
        f"expected one tmux new-session call, got {len(new_session_calls)}"
    )
    cmd_str = new_session_calls[0][-1]
    assert "tee" not in cmd_str, (
        f"tmux new-session command must not pipe claude through tee — "
        f"got: {cmd_str!r}"
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
    """
    from minions.lifecycle import role_launcher

    captured: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        captured.append(list(argv))
        result = MagicMock()
        result.returncode = 0
        result.stderr = b""
        return result

    # Patch sleep so the test stays fast.
    with (
        patch.object(role_launcher.subprocess, "run", side_effect=fake_run),
        patch("time.sleep"),
    ):
        role_launcher._tmux_send_initial_prompt("mos-12345-coder", "hello world")

    enter_calls = [
        c
        for c in captured
        if c[:2] == ["tmux", "send-keys"] and c[-1] == "Enter"
    ]
    assert len(enter_calls) == 2, (
        f"expected two Enter sends (commit paste + submit), got {len(enter_calls)}"
    )

    paste_calls = [
        c
        for c in captured
        if c[:2] == ["tmux", "send-keys"] and "-l" in c
    ]
    assert len(paste_calls) == 1
    assert "hello world" in paste_calls[0]
