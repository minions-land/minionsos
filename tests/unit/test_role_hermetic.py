"""Unit tests for the hermetic Role process isolation tiers.

Covers:
- Tier 1 cwd path stability (cache invariant — must not include session id)
- prepare_hermetic_cwd seeds CLAUDE.md and is idempotent
- cleanup_hermetic_cwd removes per-role and per-project trees
- hermetic_add_dirs filters non-existent paths and dedupes via resolve()
- ENV switches default OFF (legacy command shape preserved)
- Tier 2 auth pre-flight refuses when no env auth is present
- build_role_invocation surfaces hermetic_cwd + add_dirs into argv only
  when hermetic mode is enabled (legacy mode emits no --add-dir)

These are pure-Python tests; they do NOT spawn ``claude``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.config import GruConfig
from minions.lifecycle import role_hermetic
from minions.lifecycle.agent_host import build_role_invocation


@pytest.fixture
def hermetic_base(tmp_path, monkeypatch):
    """Redirect the hermetic base dir to a tmp path for the test."""
    base = tmp_path / "minionsos-test-hermetic"
    monkeypatch.setattr(role_hermetic, "_HERMETIC_BASE", base)
    return base


def _stub_config(tmp_path: Path) -> GruConfig:
    """Minimal GruConfig surface used by build_role_invocation.

    build_role_invocation does ``del cfg`` immediately, so the value is
    structurally unused — we just need an object the type accepts.
    """
    return GruConfig.model_validate(
        {
            "agent_host": "claude",
            "projects_root": str(tmp_path / "projects"),
        }
    )


# ---------------------------------------------------------------------------
# Tier 1 — cwd path stability and seeding
# ---------------------------------------------------------------------------


def test_hermetic_cwd_path_is_stable_for_cache_reuse(hermetic_base):
    """Same (port, role) must yield byte-identical paths across calls.

    The cwd shows up in Claude Code's dynamic system prompt; a non-stable
    path would invalidate the prompt cache on every Role respawn.
    """
    a = role_hermetic.hermetic_cwd_path(37596, "coder")
    b = role_hermetic.hermetic_cwd_path(37596, "coder")
    assert a == b
    assert "session" not in str(a)
    # No timestamp leakage
    assert not any(part.isdigit() and len(part) >= 8 for part in a.parts[-2:])


def test_hermetic_cwd_path_is_outside_minionsos(hermetic_base):
    """Path must not sit under MinionsOS/ — that would defeat the walk-stop."""
    p = role_hermetic.hermetic_cwd_path(37596, "coder")
    assert "MinionsOS" not in str(p)


def test_prepare_hermetic_cwd_seeds_claude_md(hermetic_base):
    cwd = role_hermetic.prepare_hermetic_cwd(37596, "coder")
    assert cwd.is_dir()
    claude_md = cwd / "CLAUDE.md"
    assert claude_md.exists()
    body = claude_md.read_text(encoding="utf-8")
    assert "hermetic working directory" in body
    assert "$MINIONS_WORKSPACE" in body  # explicit guidance for git access


def test_prepare_hermetic_cwd_is_idempotent(hermetic_base):
    a = role_hermetic.prepare_hermetic_cwd(37596, "coder")
    mtime_before = (a / "CLAUDE.md").stat().st_mtime_ns
    b = role_hermetic.prepare_hermetic_cwd(37596, "coder")
    mtime_after = (b / "CLAUDE.md").stat().st_mtime_ns
    assert a == b
    # Idempotent: file is not rewritten on the second call (operator edits
    # are preserved if they diverge from the canonical stub).
    assert mtime_after == mtime_before


def test_prepare_hermetic_cwd_preserves_operator_edit(hermetic_base):
    cwd = role_hermetic.prepare_hermetic_cwd(37596, "coder")
    (cwd / "CLAUDE.md").write_text("# operator override\n", encoding="utf-8")
    role_hermetic.prepare_hermetic_cwd(37596, "coder")
    assert (cwd / "CLAUDE.md").read_text(encoding="utf-8") == "# operator override\n"


def test_cleanup_hermetic_cwd_removes_role_dir(hermetic_base):
    cwd = role_hermetic.prepare_hermetic_cwd(37596, "coder")
    assert cwd.exists()
    removed = role_hermetic.cleanup_hermetic_cwd(37596, "coder")
    assert removed == [cwd]
    assert not cwd.exists()


def test_cleanup_hermetic_cwd_removes_whole_project(hermetic_base):
    role_hermetic.prepare_hermetic_cwd(37596, "coder")
    role_hermetic.prepare_hermetic_cwd(37596, "writer")
    project_base = hermetic_base / "project_37596"
    assert project_base.exists()
    removed = role_hermetic.cleanup_hermetic_cwd(37596)
    assert removed == [project_base]
    assert not project_base.exists()


# ---------------------------------------------------------------------------
# add_dirs filtering
# ---------------------------------------------------------------------------


def test_hermetic_add_dirs_drops_missing_and_dedupes(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    shared = tmp_path / "shared"
    shared.mkdir()
    minions_root = tmp_path / "minions_root"
    minions_root.mkdir()
    missing = tmp_path / "does-not-exist"

    # workspace_main intentionally points at the same dir as workspace
    # (simulating the role-branch == main fallback in role_launcher).
    out = role_hermetic.hermetic_add_dirs(
        workspace=workspace,
        workspace_main=workspace,
        workspace_shared=shared,
        minions_root=minions_root,
    )
    assert workspace in out
    assert shared in out
    assert minions_root in out
    # workspace dedup'd (only one entry)
    assert sum(1 for p in out if p == workspace) == 1
    # missing dir is filtered out
    assert missing not in out


# ---------------------------------------------------------------------------
# ENV switches default OFF
# ---------------------------------------------------------------------------


def test_hermetic_disabled_by_default(monkeypatch):
    monkeypatch.delenv(role_hermetic.ENV_HERMETIC_CWD, raising=False)
    monkeypatch.delenv(role_hermetic.ENV_HERMETIC_HOME, raising=False)
    assert role_hermetic.hermetic_enabled() is False
    assert role_hermetic.hermetic_home_enabled() is False


def test_hermetic_home_requires_tier1(monkeypatch):
    """Tier 2 alone (without Tier 1) is treated as off — both must be on."""
    monkeypatch.setenv(role_hermetic.ENV_HERMETIC_HOME, "1")
    monkeypatch.delenv(role_hermetic.ENV_HERMETIC_CWD, raising=False)
    assert role_hermetic.hermetic_home_enabled() is False


def test_hermetic_home_requires_both_flags(monkeypatch):
    monkeypatch.setenv(role_hermetic.ENV_HERMETIC_CWD, "1")
    monkeypatch.setenv(role_hermetic.ENV_HERMETIC_HOME, "1")
    assert role_hermetic.hermetic_enabled() is True
    assert role_hermetic.hermetic_home_enabled() is True


# ---------------------------------------------------------------------------
# Tier 2 auth pre-flight
# ---------------------------------------------------------------------------


def test_tier2_auth_refuses_without_env_key(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(role_hermetic.HermeticHomeAuthError) as exc_info:
        role_hermetic.assert_tier2_auth_available()
    msg = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in msg
    assert "keychain" in msg


def test_tier2_auth_accepts_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    role_hermetic.assert_tier2_auth_available()  # no raise


def test_tier2_auth_accepts_auth_token(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-test")
    role_hermetic.assert_tier2_auth_available()  # no raise


def test_prepare_fake_home_has_empty_claude_dir(hermetic_base):
    home = role_hermetic.prepare_fake_home(37596, "coder")
    assert home.is_dir()
    claude_dir = home / ".claude"
    assert claude_dir.is_dir()
    # Operator skills live in real ~/.claude/skills — fake home ships none.
    assert not (claude_dir / "skills").exists()
    # No CLAUDE.md leaked from operator's real home.
    assert not (claude_dir / "CLAUDE.md").exists()


# ---------------------------------------------------------------------------
# build_role_invocation integration
# ---------------------------------------------------------------------------


def test_build_role_invocation_legacy_mode_emits_no_add_dir(tmp_path):
    """Legacy mode (no hermetic_cwd, no add_dirs) must keep argv shape stable."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    cfg = _stub_config(tmp_path)
    invocation = build_role_invocation(
        cfg=cfg,
        role_name="coder",
        project_port=37596,
        project_agent_id="coder@37596",
        system_path=None,
        allowed_tools="Read,Edit",
        workspace=workspace,
        session_name="mos-37596-coder",
    )
    assert "--add-dir" not in invocation.command
    assert invocation.cwd == workspace


def test_build_role_invocation_hermetic_emits_add_dirs(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    shared = tmp_path / "shared"
    shared.mkdir()
    cwd = tmp_path / "hermetic"
    cwd.mkdir()
    cfg = _stub_config(tmp_path)
    invocation = build_role_invocation(
        cfg=cfg,
        role_name="coder",
        project_port=37596,
        project_agent_id="coder@37596",
        system_path=None,
        allowed_tools="Read,Edit",
        workspace=workspace,
        session_name="mos-37596-coder",
        hermetic_cwd=cwd,
        add_dirs=[workspace, shared],
    )
    assert "--add-dir" in invocation.command
    # Each add_dir argument follows its --add-dir flag
    cmd = invocation.command
    add_dir_indices = [i for i, a in enumerate(cmd) if a == "--add-dir"]
    assert len(add_dir_indices) == 2
    add_dir_values = {cmd[i + 1] for i in add_dir_indices}
    assert str(workspace) in add_dir_values
    assert str(shared) in add_dir_values
    assert invocation.cwd == cwd


def test_build_role_invocation_hermetic_hard_fails_when_cwd_missing(tmp_path):
    """If hermetic_cwd path doesn't exist on disk, raise RoleError.

    The silent-fallback-to-MINIONS_ROOT path was retired in v17 because it
    leaked Workflow scratchpads into the dev workspace .claude/. The
    launcher must surface the misconfiguration loudly via RoleError before
    spawning any tmux session. See common SYSTEM.md §10.1.
    """
    from minions.errors import RoleError

    workspace = tmp_path / "ws"
    workspace.mkdir()
    cwd = tmp_path / "does-not-exist"
    # NOTE: cwd not created
    cfg = _stub_config(tmp_path)
    with pytest.raises(RoleError) as exc_info:
        build_role_invocation(
            cfg=cfg,
            role_name="coder",
            project_port=37596,
            project_agent_id="coder@37596",
            system_path=None,
            allowed_tools="Read,Edit",
            workspace=workspace,
            session_name="mos-37596-coder",
            hermetic_cwd=cwd,
        )
    assert "effective cwd does not exist" in str(exc_info.value)
    assert "MINIONS_ROOT" in str(exc_info.value), (
        "error must explain why fallback was rejected"
    )


# ---------------------------------------------------------------------------
# Sanity: imports compose
# ---------------------------------------------------------------------------


def test_role_launcher_imports_compose():
    """role_launcher must import cleanly with the new helpers wired in."""
    from minions.lifecycle import role_launcher

    assert hasattr(role_launcher, "_hermetic_cwd_for")
    assert hasattr(role_launcher, "_hermetic_add_dirs_for")
