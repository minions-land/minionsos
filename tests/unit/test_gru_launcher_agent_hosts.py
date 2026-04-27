"""Gray-box tests for the top-level Gru launcher agent-host branches."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRU = ROOT / "minions" / "bin" / "gru"

FAKE_CODEX = r"""#!/usr/bin/env bash
set -u
echo "FAKE_GRU_CODEX_ARGV: $*" >&2
exit 0
"""

FAKE_CLAUDE = r"""#!/usr/bin/env bash
set -u
echo "FAKE_GRU_CLAUDE_ARGV: $*" >&2
exit 0
"""

FAKE_UV = r"""#!/usr/bin/env bash
set -u
if [[ "${1:-}" == "--version" ]]; then
  echo "uv 0.0.0-fake"
  exit 0
fi
if [[ "${1:-}" == "run" ]]; then
  shift
  if [[ "${1:-}" == "--project" ]]; then shift; shift; fi
  exec "$@"
fi
exec "$@"
"""


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _fake_bin(tmp_path: Path, *, codex: bool = False, claude: bool = False) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _write_executable(bindir / "uv", FAKE_UV)
    if codex:
        _write_executable(bindir / "codex", FAKE_CODEX)
    if claude:
        _write_executable(bindir / "claude", FAKE_CLAUDE)
    return bindir


def test_gru_launcher_codex_branch(tmp_path: Path) -> None:
    bindir = _fake_bin(tmp_path, codex=True)
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ.get('PATH', '')}",
        "MINIONS_AGENT_HOST": "codex",
        "GRU_VIZ": "0",
        "MINIONS_GRU_MONITOR": "0",
    }
    result = subprocess.run(
        [str(GRU), "hello codex"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "FAKE_GRU_CODEX_ARGV:" in result.stderr
    assert "--cd" in result.stderr
    assert str(ROOT) in result.stderr
    assert "Initial user request: hello codex" in result.stderr
    assert "--append-system-prompt" not in result.stderr


def test_gru_launcher_claude_branch_still_uses_claude_flags(tmp_path: Path) -> None:
    bindir = _fake_bin(tmp_path, claude=True)
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ.get('PATH', '')}",
        "MINIONS_AGENT_HOST": "claude",
        "GRU_VIZ": "0",
        "MINIONS_GRU_MONITOR": "0",
    }
    result = subprocess.run(
        [str(GRU)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "FAKE_GRU_CLAUDE_ARGV:" in result.stderr
    assert "--append-system-prompt" in result.stderr
    assert "--mcp-config" in result.stderr
    assert "--dangerously-skip-permissions" in result.stderr
