"""Unit tests for scratchpad_isolation_guard PreToolUse hook (common §10.1).

Validates the four enforcement cases:

  - Legal scratchpad path → exit 0.
  - Non-.claude path → exit 0 (out of scope).
  - Path-shaped tool targeting forbidden .claude → exit 2.
  - Bash command writing into forbidden .claude → exit 2.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / "minions" / "hooks" / "scratchpad_isolation_guard.py"


def _run(payload: dict, env_overrides: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # Strip any inherited Role identity so we control the test environment.
    for key in (
        "MINIONS_ROLE_BRANCH",
        "MINIONS_ROLE_NAME",
        "MINIONS_ROLE_HERMETIC_DIR",
        "MINIONS_ROLE_WORKSPACE",
    ):
        env.pop(key, None)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        timeout=10,
        check=False,
    )


def test_no_role_env_passes_through(tmp_path: Path) -> None:
    """Without MINIONS_ROLE_BRANCH the hook must not enforce — keeps
    developer sessions outside a Role process unaffected."""
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": "/Users/mjm/MinionsOS/.claude/foo"},
    }
    result = _run(payload)
    assert result.returncode == 0


def test_legal_scratchpad_write_allowed(tmp_path: Path) -> None:
    branch = tmp_path / "branches" / "expert"
    branch.mkdir(parents=True)
    legal = branch / ".claude" / "scratchpad" / "session-1" / "foo.txt"
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(legal)}}
    result = _run(payload, {"MINIONS_ROLE_BRANCH": str(branch), "MINIONS_ROLE_NAME": "expert"})
    assert result.returncode == 0


def test_non_dotclaude_path_passes_through(tmp_path: Path) -> None:
    branch = tmp_path / "branches" / "expert"
    branch.mkdir(parents=True)
    notes = branch / "notes" / "foo.md"
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(notes)}}
    result = _run(payload, {"MINIONS_ROLE_BRANCH": str(branch), "MINIONS_ROLE_NAME": "expert"})
    assert result.returncode == 0


def test_repo_dotclaude_blocked(tmp_path: Path) -> None:
    """Writing into the dev-shared MinionsOS .claude/ must block."""
    branch = tmp_path / "branches" / "expert"
    branch.mkdir(parents=True)
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": "/Users/mjm/MinionsOS/.claude/scratchpad/foo"},
    }
    result = _run(payload, {"MINIONS_ROLE_BRANCH": str(branch), "MINIONS_ROLE_NAME": "expert"})
    assert result.returncode == 2
    stderr = result.stderr.decode()
    assert "scratchpad_isolation_guard" in stderr


def test_host_dotclaude_blocked(tmp_path: Path) -> None:
    """Writing into ~/.claude/ must block — cross-session contamination."""
    branch = tmp_path / "branches" / "expert"
    branch.mkdir(parents=True)
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(Path.home() / ".claude" / "settings.json")},
    }
    result = _run(payload, {"MINIONS_ROLE_BRANCH": str(branch), "MINIONS_ROLE_NAME": "expert"})
    assert result.returncode == 2


def test_cross_role_branch_blocked(tmp_path: Path) -> None:
    """Expert writing into another Expert branch .claude/ must block."""
    expert_branch = tmp_path / "branches" / "expert-a"
    peer_branch = tmp_path / "branches" / "expert-b"
    expert_branch.mkdir(parents=True)
    peer_branch.mkdir(parents=True)
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(peer_branch / ".claude" / "scratchpad" / "leak"),
        },
    }
    result = _run(
        payload,
        {"MINIONS_ROLE_BRANCH": str(expert_branch), "MINIONS_ROLE_NAME": "expert-a"},
    )
    assert result.returncode == 2


def test_bash_redirect_to_dotclaude_blocked(tmp_path: Path) -> None:
    branch = tmp_path / "branches" / "expert"
    branch.mkdir(parents=True)
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello > /Users/mjm/MinionsOS/.claude/foo"},
    }
    result = _run(payload, {"MINIONS_ROLE_BRANCH": str(branch), "MINIONS_ROLE_NAME": "expert"})
    assert result.returncode == 2


def test_hermetic_legal_scratchpad_allowed(tmp_path: Path) -> None:
    """Under hermetic mode, the hermetic stub's scratchpad is also legal."""
    branch = tmp_path / "branches" / "expert"
    hermetic = tmp_path / "hermetic" / "p37596" / "expert"
    branch.mkdir(parents=True)
    hermetic.mkdir(parents=True)
    legal = hermetic / ".claude" / "scratchpad" / "session-1" / "foo.txt"
    payload = {"tool_name": "Workflow", "tool_input": {"file_path": str(legal)}}
    result = _run(
        payload,
        {
            "MINIONS_ROLE_BRANCH": str(branch),
            "MINIONS_ROLE_HERMETIC_DIR": str(hermetic),
            "MINIONS_ROLE_NAME": "expert",
        },
    )
    assert result.returncode == 0
