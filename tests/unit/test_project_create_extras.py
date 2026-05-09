"""Unit tests for project_create auxiliaries added to address client feedback:

- auto-generated project CLAUDE.md skeleton
- absolute workspace_path return value (fixes 'path was really the branch name')
- {project_workspace} expansion in experiment_targets workdir
- topic_doc / template_dir propagation
"""

from __future__ import annotations

import os

from minions.lifecycle.project import _render_project_agents_md, _render_project_claude_md
from minions.tools.experiment_ssh import _expand_workdir


def test_render_claude_md_contains_key_fields() -> None:
    md = _render_project_claude_md(
        port=37596,
        real_name="Grokking",
        venue="NeurIPS 2026",
        branch="minionsos/project-37596",
        workspace_abs="/autodl-fs/data/Grokking/project_37596/workspace",
        brief="Study phase transitions.",
        topic_doc="/autodl-fs/data/Grokking/Topic.md",
        template_dir="/autodl-fs/data/Grokking/Formatting_Instructions_For_NeurIPS_2026",
    )
    assert "# Grokking" in md
    assert "`37596`" in md
    assert "NeurIPS 2026" in md
    assert "/autodl-fs/data/Grokking/project_37596/workspace" in md
    assert "Topic.md" in md
    assert "Formatting_Instructions_For_NeurIPS_2026" in md
    assert "Study phase transitions." in md


def test_render_claude_md_with_no_brief_has_todo() -> None:
    md = _render_project_claude_md(
        port=1,
        real_name="X",
        venue=None,
        branch="b",
        workspace_abs="/tmp/ws",
        brief=None,
        topic_doc=None,
        template_dir=None,
    )
    assert "TODO" in md


def test_render_agents_md_points_to_shared_project_context() -> None:
    md = _render_project_agents_md("Grokking")
    assert "# Grokking" in md
    assert "CLAUDE.md" in md
    assert "Claude Code and Codex" in md


def test_expand_workdir_no_token_passthrough() -> None:
    assert _expand_workdir("/abs/path") == "/abs/path"


def test_expand_workdir_with_port_env(monkeypatch) -> None:
    monkeypatch.setenv("MINIONS_PROJECT_PORT", "37596")
    expanded = _expand_workdir("{project_workspace}/experiments")
    assert "{project_workspace}" not in expanded
    assert expanded.endswith("/project_37596/branches/main/experiments")
    assert os.path.isabs(expanded)


def test_expand_workdir_without_port_env_is_safe(monkeypatch) -> None:
    monkeypatch.delenv("MINIONS_PROJECT_PORT", raising=False)
    # Without the port env var we keep the literal token so misconfiguration
    # surfaces as an obvious error rather than silently falling back to cwd.
    assert _expand_workdir("{project_workspace}/exp") == "{project_workspace}/exp"
