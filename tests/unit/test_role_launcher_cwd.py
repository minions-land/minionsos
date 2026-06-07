"""Unit tests for the agent-host cwd hard-fail contract (common §10.1).

Covers the regression introduced when the silent fallback in
``build_role_invocation`` (cwd → MINIONS_ROOT when the role's branch
doesn't exist) leaked Workflow / Task / subagent scratchpads into the
developer-shared ``/Users/mjm/MinionsOS/.claude/`` directory.

The contract: ``build_role_invocation`` must raise ``RoleError`` BEFORE
any tmux session can be spawned when the resolved cwd does not exist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.config import GruConfig
from minions.errors import RoleError
from minions.lifecycle.agent_host import build_role_invocation


def _kwargs(workspace: Path, system: Path, **overrides) -> dict:
    base: dict = {
        "cfg": GruConfig(agent_host="claude"),
        "role_name": "expert",
        "project_port": 37596,
        "project_agent_id": "expert",
        "system_path": system,
        "allowed_tools": "Read,Write",
        "workspace": workspace,
        "session_name": "p37596/expert",
    }
    base.update(overrides)
    return base


def test_missing_workspace_raises_role_error(tmp_path: Path) -> None:
    """A non-existent workspace must surface a RoleError, not silently fall
    back to MINIONS_ROOT."""
    system = tmp_path / "SYSTEM.md"
    system.write_text("role system", encoding="utf-8")

    missing = tmp_path / "branches" / "expert"  # not created
    assert not missing.exists()

    with pytest.raises(RoleError) as exc_info:
        build_role_invocation(**_kwargs(missing, system))

    msg = str(exc_info.value)
    assert "effective cwd does not exist" in msg
    assert "MINIONS_ROOT" in msg, "error must explain why fallback was rejected"


def test_existing_workspace_returns_invocation(tmp_path: Path) -> None:
    """Sanity: an existing workspace still produces an invocation."""
    system = tmp_path / "SYSTEM.md"
    system.write_text("role system", encoding="utf-8")

    workspace = tmp_path / "branches" / "expert"
    workspace.mkdir(parents=True)

    invocation = build_role_invocation(**_kwargs(workspace, system))
    assert invocation.cwd == workspace


def test_missing_hermetic_cwd_raises_role_error(tmp_path: Path) -> None:
    """When hermetic_cwd is provided but doesn't exist, the same hard-fail
    fires — hermetic mode must not paper over a missing stub by silently
    falling back to MINIONS_ROOT."""
    system = tmp_path / "SYSTEM.md"
    system.write_text("role system", encoding="utf-8")

    workspace = tmp_path / "branches" / "expert"
    workspace.mkdir(parents=True)

    missing_hermetic = tmp_path / "hermetic" / "p37596" / "expert"  # not created
    assert not missing_hermetic.exists()

    with pytest.raises(RoleError):
        build_role_invocation(**_kwargs(workspace, system, hermetic_cwd=missing_hermetic))


def test_role_error_fires_before_tmux_spawn(tmp_path: Path) -> None:
    """The hard-fail must raise BEFORE any process is spawned. We verify
    this is part of build_role_invocation's contract by confirming the
    function raises rather than returning a partial object."""
    system = tmp_path / "SYSTEM.md"
    system.write_text("role system", encoding="utf-8")

    missing = tmp_path / "nope"
    with pytest.raises(RoleError):
        result = build_role_invocation(**_kwargs(missing, system))
        # If we reached here the contract is broken regardless of result
        # shape — the test fails on the missing exception.
        assert result is None  # pragma: no cover
