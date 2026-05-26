"""Tests for MinionsOS hook activation: the chain only fires under
MinionsOS-launched Claude/Role agents, never under a vanilla Claude session
in the user's parent repo or a per-role git worktree.

Three concerns:

1. ``minions/bin/gru`` exports ``MINIONS_ROOT`` so the launched Claude
   process and its hooks resolve against the real install rather than
   ``$(git rev-parse --show-toplevel)``.

2. ``role_launcher._role_env`` includes ``MINIONS_ROOT`` so role agents,
   whose cwd is a per-branch git worktree, do not silently fall back to
   the worktree path (which has no ``.venv`` or ``minions/hooks/``).

3. The shell gate inside ``.claude/settings.json`` ('s every hook command)
   skips silently (exit 0, no stdout/stderr) when neither MINIONS_ROOT is
   set nor cwd is a MinionsOS install — so a vanilla Claude session in
   the user's outer repo never blocks on a non-existent hook script.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SETTINGS_JSON = REPO_ROOT / ".claude" / "settings.json"


# --------------------------------------------------------------------------
# 1. minions/bin/gru exports MINIONS_ROOT
# --------------------------------------------------------------------------


class TestGruLauncherExportsMinionsRoot:
    """``./gru`` must export MINIONS_ROOT before launching the agent."""

    def test_export_line_present_in_launcher(self) -> None:
        gru_script = REPO_ROOT / "minions" / "bin" / "gru"
        text = gru_script.read_text(encoding="utf-8")
        assert 'export MINIONS_ROOT="$ROOT"' in text, (
            "minions/bin/gru must export MINIONS_ROOT so the agent's hook "
            "chain resolves against the real install. The export was missing."
        )


# --------------------------------------------------------------------------
# 2. role_launcher._role_env exposes MINIONS_ROOT
# --------------------------------------------------------------------------


class TestRoleEnvExposesMinionsRoot:
    def _build_env(self, tmp_path: Path) -> dict[str, str]:
        from minions.lifecycle.role_launcher import _role_env
        from minions.state.store import RoleEntry

        role = RoleEntry(name="writer", state="active", workspace_branch="feature/x")
        with (
            patch("minions.lifecycle.role_launcher.resolve_agent_id", return_value="writer"),
            patch("minions.lifecycle.role_launcher.plugin_state_dir") as plugin_dir,
            patch(
                "minions.lifecycle.role_launcher.project_workspace_root",
                return_value=tmp_path,
            ),
            patch(
                "minions.lifecycle.role_launcher.project_workspace",
                return_value=tmp_path,
            ),
        ):
            plugin_dir.return_value = tmp_path / "plugin"
            (tmp_path / "plugin").mkdir(parents=True, exist_ok=True)
            return _role_env(
                role_name="writer",
                project_port=37596,
                role_entry=role,
                workspace=tmp_path,
            )

    def test_minions_root_is_set(self, tmp_path: Path) -> None:
        from minions.paths import MINIONS_ROOT

        env = self._build_env(tmp_path)
        assert env.get("MINIONS_ROOT") == str(MINIONS_ROOT), (
            "Role agents need MINIONS_ROOT in env so their hook chain resolves "
            "against the real install instead of the per-role git worktree path."
        )

    def test_minions_root_points_at_install(self, tmp_path: Path) -> None:
        env = self._build_env(tmp_path)
        root = Path(env["MINIONS_ROOT"])
        assert (root / "minions" / "hooks").is_dir()
        assert (root / ".claude" / "settings.json").is_file()


# --------------------------------------------------------------------------
# 3. settings.json hook commands carry the MINIONS_ROOT gate
# --------------------------------------------------------------------------


class TestSettingsJsonHookGate:
    """Every hook command must use the same MINIONS_ROOT-or-toplevel gate
    and never fall through to a bare path that would crash or hang under a
    vanilla Claude session outside MinionsOS."""

    def _all_hook_commands(self) -> list[str]:
        data = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        commands: list[str] = []
        for event_rules in data.get("hooks", {}).values():
            for rule in event_rules:
                for hook in rule.get("hooks", []):
                    cmd = hook.get("command")
                    if isinstance(cmd, str):
                        commands.append(cmd)
        return commands

    def test_every_hook_command_starts_with_root_resolution(self) -> None:
        cmds = self._all_hook_commands()
        assert cmds, "no hook commands found in settings.json"
        for cmd in cmds:
            assert cmd.startswith('ROOT="${MINIONS_ROOT:-$(git rev-parse --show-toplevel'), (
                f"hook command does not start with the MINIONS_ROOT gate: {cmd!r}"
            )

    def test_every_hook_command_validates_venv_and_hook_file(self) -> None:
        cmds = self._all_hook_commands()
        for cmd in cmds:
            assert '[ -x "$ROOT/.venv/bin/python" ]' in cmd, (
                f"hook command does not check that the venv python exists: {cmd!r}"
            )
            assert '[ -f "$ROOT/minions/hooks/' in cmd, (
                f"hook command does not check that the hook file exists: {cmd!r}"
            )

    def test_every_hook_command_silently_exits_on_skip(self) -> None:
        cmds = self._all_hook_commands()
        for cmd in cmds:
            assert cmd.endswith(" || exit 0"), (
                f"hook command does not end with `|| exit 0` (silent skip): {cmd!r}"
            )


class TestSettingsJsonHookGateRuntime:
    """Behavioral test: the shell gate must skip silently when neither
    MINIONS_ROOT is set nor cwd is a MinionsOS install."""

    def _first_hook_command(self) -> str:
        data = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        for event_rules in data["hooks"].values():
            for rule in event_rules:
                for hook in rule.get("hooks", []):
                    cmd = hook.get("command")
                    if isinstance(cmd, str):
                        return cmd
        raise AssertionError("no hook command in settings.json")

    def test_skip_when_no_root_env_and_cwd_outside_minions(self, tmp_path: Path) -> None:
        cmd = self._first_hook_command()
        # Make sure cwd is not inside MinionsOS or any git repo, and
        # MINIONS_ROOT is not in env.
        env = {k: v for k, v in os.environ.items() if k != "MINIONS_ROOT"}
        result = subprocess.run(
            ["sh", "-c", cmd],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"gate should silently skip outside MinionsOS, got rc={result.returncode}, "
            f"stderr={result.stderr!r}"
        )
        assert result.stdout == ""
        assert result.stderr == ""

    def test_skip_when_root_env_points_at_non_minions_dir(self, tmp_path: Path) -> None:
        cmd = self._first_hook_command()
        env = {k: v for k, v in os.environ.items() if k != "MINIONS_ROOT"}
        env["MINIONS_ROOT"] = str(tmp_path)  # exists but is not a MinionsOS install
        result = subprocess.run(
            ["sh", "-c", cmd],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"gate should silently skip when MINIONS_ROOT points at a "
            f"non-install directory, got rc={result.returncode}, stderr={result.stderr!r}"
        )

    def test_fires_when_root_env_points_at_real_install(self, monkeypatch) -> None:
        """When MINIONS_ROOT points at the real install, the shell gate
        must reach the python invocation. We verify by replacing
        MINIONS_ROOT in env so the shell gate fires, but we cannot easily
        stub the hook script's behavior, so we settle for: the resolution
        succeeds (i.e. all preconditions of the gate are true)."""
        cmd = self._first_hook_command()
        # Strip the actual python invocation off, keep only the gate, so
        # we measure whether the AND chain reaches the action without
        # actually executing any hook script.
        gate_only = cmd.replace(
            ' && "$ROOT/.venv/bin/python" "$ROOT/minions/hooks/',
            ' && echo FIRE_OK; : "$ROOT/.venv/bin/python" "$ROOT/minions/hooks/',
        ).replace(" || exit 0", "; exit 0")
        venv_python = REPO_ROOT / ".venv" / "bin" / "python"
        if not venv_python.is_file():
            import pytest

            pytest.skip(".venv/bin/python missing; install.sh has not run")
        env = {k: v for k, v in os.environ.items()}
        env["MINIONS_ROOT"] = str(REPO_ROOT)
        result = subprocess.run(
            ["sh", "-c", gate_only],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert "FIRE_OK" in result.stdout, (
            f"gate did not fire under valid MINIONS_ROOT={REPO_ROOT}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )


# --------------------------------------------------------------------------
# 4. _seed_claude_settings mirrors the canonical settings.json
# --------------------------------------------------------------------------


class TestSeedClaudeSettings:
    """The role workspace must inherit the full hook surface, not a
    PreCompact/PostCompact-only stub."""

    def test_workspace_settings_match_canonical_byte_for_byte(self, tmp_path: Path) -> None:
        from minions.lifecycle.project import _seed_claude_settings

        workspace = tmp_path / "wk"
        workspace.mkdir()
        _seed_claude_settings(workspace)

        seeded = workspace / ".claude" / "settings.json"
        assert seeded.is_file(), "expected .claude/settings.json to be seeded"
        assert seeded.read_bytes() == SETTINGS_JSON.read_bytes(), (
            "seeded settings.json must mirror MinionsOS/.claude/settings.json "
            "byte-for-byte; otherwise role agents miss part of the hook surface."
        )

    def test_seeded_settings_has_all_event_types(self, tmp_path: Path) -> None:
        from minions.lifecycle.project import _seed_claude_settings

        workspace = tmp_path / "wk"
        workspace.mkdir()
        _seed_claude_settings(workspace)

        data = json.loads((workspace / ".claude" / "settings.json").read_text(encoding="utf-8"))
        # Regression for the prior stub that only seeded compact hooks.
        for event in ("PreToolUse", "PostToolUse", "PreCompact", "PostCompact"):
            assert event in data["hooks"], (
                f"role workspace seed lost {event} hooks (the previous "
                f"PreCompact-only stub did exactly this)."
            )

    def test_idempotent_when_already_present(self, tmp_path: Path) -> None:
        from minions.lifecycle.project import _seed_claude_settings

        workspace = tmp_path / "wk"
        (workspace / ".claude").mkdir(parents=True)
        custom = '{"hooks": {"_marker": "user-customized"}}\n'
        (workspace / ".claude" / "settings.json").write_text(custom)

        _seed_claude_settings(workspace)
        # Existing file must not be overwritten.
        assert (workspace / ".claude" / "settings.json").read_text() == custom
