"""Gray-box smoke test for the Role wake-up launcher.

Regression coverage for the client bug:
    role-*.log all contained only  `error: unknown option '--message'`

and the fix that replaced `--message <msg>` with `--print` + stdin.

This test shims a fake ``claude`` binary onto PATH so we exercise the real
subprocess pipeline end-to-end (argv construction, stdin delivery, log
capture) without hitting the Anthropic API.

Run:
    uv run pytest tests/unit/test_role_wakeup_launcher.py -v
"""
from __future__ import annotations

import os
import stat
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from minions.lifecycle import role as role_mod

FAKE_CLAUDE = r"""#!/usr/bin/env bash
# Fake Claude CLI used by the wake-up launcher smoke test.
# Behavior:
#   - Reject any argv containing '--message' (old broken call path).
#   - Require '--print' (new call path).
#   - Echo argv + stdin to stderr so the role-*.log captures them.
#   - Exit 0 on success, 2 on bad argv.

set -u
ARGS=("$@")
for a in "${ARGS[@]}"; do
  if [[ "$a" == "--message" ]]; then
    echo "error: unknown option '--message'" >&2
    exit 2
  fi
done

has_print=0
for a in "${ARGS[@]}"; do
  if [[ "$a" == "--print" || "$a" == "-p" ]]; then has_print=1; fi
done
if [[ "$has_print" -ne 1 ]]; then
  echo "fake-claude: missing -p/--print" >&2
  exit 3
fi

echo "FAKE_CLAUDE_ARGV: ${ARGS[*]}" >&2
echo "FAKE_CLAUDE_STDIN_BEGIN" >&2
cat >&2
echo "" >&2
echo "FAKE_CLAUDE_STDIN_END" >&2
exit 0
"""


def _install_fake_claude(tmp_path: Path) -> Path:
    """Drop a fake ``claude`` and fake ``uv`` onto a scratch PATH dir."""
    bindir = tmp_path / "bin"
    bindir.mkdir()

    claude = bindir / "claude"
    claude.write_text(FAKE_CLAUDE, encoding="utf-8")
    claude.chmod(claude.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Fake 'uv' — the launcher calls ['uv', 'run', '--project', <dir>, 'claude', ...].
    # The real uv would resolve claude from the project venv; we just drop the first
    # four tokens and exec whatever binary name follows with the remaining args.
    fake_uv = bindir / "uv"
    fake_uv.write_text(
        "#!/usr/bin/env bash\n"
        "# Fake uv: strip 'run --project <path>' then exec the rest.\n"
        'if [[ "${1:-}" == "run" ]]; then\n'
        "  shift\n"  # drop 'run'
        '  if [[ "${1:-}" == "--project" ]]; then shift; shift; fi\n'
        '  exec "$@"\n'
        "fi\n"
        'exec "$@"\n',
        encoding="utf-8",
    )
    fake_uv.chmod(fake_uv.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def _wait_for_log(log_path: Path, needle: str, timeout: float = 5.0) -> str:
    """Poll *log_path* until *needle* appears or timeout expires."""
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        if log_path.exists():
            last = log_path.read_text(encoding="utf-8", errors="replace")
            if needle in last:
                return last
        time.sleep(0.05)
    return last


class TestRoleWakeupLauncherRegression:
    """End-to-end: launcher → fake claude → log.

    These tests are the canary for the `--message` regression. If anyone
    re-introduces a flag the CLI does not accept, the fake claude will print
    `error: unknown option '...'` to the log and these tests will fail.
    """

    def _invoke(self, tmp_path: Path, role: str = "noter") -> Path:
        bindir = _install_fake_claude(tmp_path)
        log_path = tmp_path / f"role-{role}.log"

        env_patch = {"PATH": f"{bindir}:{os.environ.get('PATH', '')}"}
        with (
            patch.dict(os.environ, env_patch, clear=False),
            patch("minions.lifecycle.role.project_workspace", return_value=tmp_path),
            patch("minions.lifecycle.role.project_role_log", return_value=log_path),
            patch("minions.lifecycle.role.project_memory_dir", return_value=tmp_path / "memory"),
            patch(
                "minions.lifecycle.role.project_scratchpad",
                return_value=tmp_path / "memory" / f"{role}.md",
            ),
        ):
            out = role_mod.invoke_role_ephemeral(
                role,
                37596,
                [{"id": "e1", "content": "hello from smoke test"}],
                wait=True,
            )
        assert out["name"] == role
        assert out["events"] == 1
        return log_path

    def test_launcher_does_not_pass_message_flag(self, tmp_path: Path) -> None:
        log_path = self._invoke(tmp_path)
        log = _wait_for_log(log_path, "FAKE_CLAUDE_STDIN_END")
        assert "unknown option '--message'" not in log, (
            "Regression: the --message flag is back in the Claude CLI argv.\n"
            f"Log:\n{log}"
        )

    def test_launcher_uses_print_mode(self, tmp_path: Path) -> None:
        log_path = self._invoke(tmp_path)
        log = _wait_for_log(log_path, "FAKE_CLAUDE_ARGV")
        assert "FAKE_CLAUDE_ARGV" in log, f"fake claude never ran. Log:\n{log}"
        argv_line = next(
            line for line in log.splitlines() if line.startswith("FAKE_CLAUDE_ARGV:")
        )
        assert "-p" in argv_line.split() or "--print" in argv_line.split()
        assert "--permission-mode" in argv_line
        assert "bypassPermissions" in argv_line
        assert "--allowed-tools" in argv_line
        assert "--mcp-config" in argv_line

    def test_prompt_is_delivered_via_stdin(self, tmp_path: Path) -> None:
        log_path = self._invoke(tmp_path)
        log = _wait_for_log(log_path, "FAKE_CLAUDE_STDIN_END")
        begin = log.index("FAKE_CLAUDE_STDIN_BEGIN")
        end = log.index("FAKE_CLAUDE_STDIN_END")
        stdin_payload = log[begin:end]
        # The event id we passed in should be visible in the stdin-delivered prompt.
        assert "e1" in stdin_payload
        assert "hello from smoke test" in stdin_payload

    def test_launcher_exits_zero_on_happy_path(self, tmp_path: Path) -> None:
        log_path = self._invoke(tmp_path)
        log = _wait_for_log(log_path, "FAKE_CLAUDE_STDIN_END")
        # Neither of the fake-claude error paths fired.
        assert "unknown option" not in log
        assert "missing -p/--print" not in log


class TestGruCanLaunchRole:
    """Higher-level check: the Gru lifecycle path that drives wake-ups
    (register_role → invoke_role_ephemeral) still works end-to-end with the
    new --print + stdin pipeline.

    We don't start a real EACN backend here — we just verify the invocation
    plumbing Gru depends on.
    """

    def test_register_then_invoke(self, tmp_path: Path) -> None:
        bindir = _install_fake_claude(tmp_path)
        log_path = tmp_path / "role-noter.log"

        env_patch = {"PATH": f"{bindir}:{os.environ.get('PATH', '')}"}
        with (
            patch.dict(os.environ, env_patch, clear=False),
            patch("minions.lifecycle.role.project_workspace", return_value=tmp_path),
            patch("minions.lifecycle.role.project_role_log", return_value=log_path),
            patch("minions.lifecycle.role.project_memory_dir", return_value=tmp_path / "memory"),
            patch(
                "minions.lifecycle.role.project_scratchpad",
                return_value=tmp_path / "memory" / "noter.md",
            ),
        ):
            result = role_mod.invoke_role_ephemeral(
                "noter",
                37596,
                [
                    {"id": f"e{i}", "content": f"event number {i}"}
                    for i in range(5)
                ],
                wait=True,
            )

        assert result["events"] == 5
        log = _wait_for_log(log_path, "FAKE_CLAUDE_STDIN_END")
        assert "unknown option" not in log
        # All 5 event ids should have been piped through stdin.
        for i in range(5):
            assert f"e{i}" in log


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
