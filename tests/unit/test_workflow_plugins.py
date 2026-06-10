"""Unit tests for workflow-plugin MCP and project-local skill mounting helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.lifecycle import workflow_plugins


def test_inject_skills_to_workspace_renders_project_local_skill_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugins = tmp_path / "workflow-plugins"
    skills = plugins / "evoany" / "skills"
    skills.mkdir(parents=True)
    (skills / "drive-evolution-loop.md").write_text(
        "# Drive Evolution Loop\n\n"
        "One-line: Orchestrate a full EvoAny generation cycle.\n\n"
        "## Procedure\n\n1. Check status.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(workflow_plugins, "WORKFLOW_PLUGINS_DIR", plugins)
    manifest = workflow_plugins.WorkflowPluginManifest(
        slug="evoany",
        name="evoany",
        description="Evolution workflow",
    )
    workspace = tmp_path / "workspace"

    workflow_plugins.inject_skills_to_workspace(manifest, workspace)

    skill_md = (
        workspace
        / ".claude"
        / "skills"
        / "workflow-plugin-evoany-drive-evolution-loop"
        / "SKILL.md"
    )
    assert skill_md.exists()
    text = skill_md.read_text(encoding="utf-8")
    assert "name: workflow-plugin-evoany-drive-evolution-loop" in text
    assert 'description: "Orchestrate a full EvoAny generation cycle."' in text
    assert "# Drive Evolution Loop" in text
    assert not (
        workspace / ".claude" / "skills" / "workflow-plugin-evoany-drive-evolution-loop.md"
    ).exists()


def test_render_claude_skill_bundle_uses_summary_without_leaking_role_metadata() -> None:
    source = (
        "---\n"
        "slug: think-then-act\n"
        "summary: Think before acting.\n"
        "tools: eacn3_send_message, codex\n"
        "---\n\n"
        "# Think Then Act\n\n"
        "Procedure body.\n"
    )

    rendered = workflow_plugins._render_claude_skill_bundle(
        "workflow-plugin-demo-think-then-act", source
    )
    frontmatter = rendered.split("---", 2)[1]

    assert "name: workflow-plugin-demo-think-then-act" in frontmatter
    assert 'description: "Think before acting."' in frontmatter
    assert "slug:" not in frontmatter
    assert "tools:" not in frontmatter
    assert "# Think Then Act" in rendered
