"""Gray-box smoke test for the Codex Role wake-up launcher."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path
from unittest.mock import patch

from minions.lifecycle import role as role_mod

FAKE_CODEX = r"""#!/usr/bin/env bash
set -u
ARGS=("$@")
if [[ "${ARGS[0]:-}" != "exec" ]]; then
  echo "fake-codex: missing exec subcommand" >&2
  exit 2
fi
has_stdin=0
for a in "${ARGS[@]}"; do
  if [[ "$a" == "-" ]]; then has_stdin=1; fi
  if [[ "$a" == "--append-system-prompt" || "$a" == "--allowed-tools" ]]; then
    echo "fake-codex: Claude-only flag $a leaked into codex argv" >&2
    exit 3
  fi
done
if [[ "$has_stdin" -ne 1 ]]; then
  echo "fake-codex: missing stdin prompt marker '-'" >&2
  exit 4
fi
echo "FAKE_CODEX_ARGV: ${ARGS[*]}" >&2
echo "FAKE_CODEX_STDIN_BEGIN" >&2
cat >&2
echo "" >&2
echo "FAKE_CODEX_STDIN_END" >&2
exit 0
"""


def _install_fake_codex(tmp_path: Path) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    codex = bindir / "codex"
    codex.write_text(FAKE_CODEX, encoding="utf-8")
    codex.chmod(codex.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def _wait_for_log(log_path: Path, needle: str, timeout: float = 5.0) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        if log_path.exists():
            last = log_path.read_text(encoding="utf-8", errors="replace")
            if needle in last:
                return last
        time.sleep(0.05)
    return last


def test_codex_launcher_uses_exec_stdin_pipeline(tmp_path: Path) -> None:
    bindir = _install_fake_codex(tmp_path)
    log_path = tmp_path / "role-noter.log"
    env_patch = {
        "PATH": f"{bindir}:{os.environ.get('PATH', '')}",
        "MINIONS_AGENT_HOST": "codex",
    }
    with (
        patch.dict(os.environ, env_patch, clear=False),
        patch("minions.lifecycle.role.project_workspace", return_value=tmp_path),
        patch("minions.lifecycle.role.project_role_log", return_value=log_path),
        patch("minions.lifecycle.role.project_memory_dir", return_value=tmp_path / "memory"),
        patch(
            "minions.lifecycle.role.project_scratchpad",
            return_value=tmp_path / "memory" / "noter.md",
        ),
        patch("minions.lifecycle.agent_host.project_dir", return_value=tmp_path),
    ):
        out = role_mod.invoke_role_ephemeral(
            "noter",
            37596,
            [{"id": "e1", "content": "hello codex"}],
            wait=True,
        )

    assert out["events"] == 1
    log = _wait_for_log(log_path, "FAKE_CODEX_STDIN_END")
    assert "FAKE_CODEX_ARGV" in log
    assert "Claude-only flag" not in log
    assert "MinionsOS Codex Role Invocation" in log
    assert "hello codex" in log
