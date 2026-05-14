"""Prompt invariants that keep role behavior portable across agent hosts."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from minions.lifecycle import role as role_mod

ROOT = Path(__file__).resolve().parents[2]
ROLE_MARKDOWN = sorted((ROOT / "minions" / "roles").rglob("*.md"))
PORTABILITY_SURFACES = [
    *ROLE_MARKDOWN,
    ROOT / "minions" / "lifecycle" / "project.py",
    ROOT / "minions" / "tools" / "experiment_ssh.py",
]


def test_common_role_contract_documents_agent_host_portability() -> None:
    text = (ROOT / "minions" / "roles" / "SYSTEM.md").read_text(encoding="utf-8")

    assert "## Agent-host portability" in text
    assert "Claude Code and Codex" in text
    assert "host-native subagent mechanism" in text
    assert "self-contained" in text


def test_common_role_contract_requires_role_to_role_eacn() -> None:
    text = (ROOT / "minions" / "roles" / "SYSTEM.md").read_text(encoding="utf-8")

    assert "## Role-to-role collaboration first" in text
    assert "targeted task" in text
    assert "eacn3_create_task" in text
    assert "direct EACN" in text
    assert "not substitutes for registered project Roles" in text


def test_role_prompts_avoid_claude_only_subagent_and_skill_contracts() -> None:
    disallowed = [
        "/simplify",
        "role-owned `Task` mechanism",
        "Task-style",
        "Claude subprocess paths",
        "not a live Claude process",
    ]

    offenders: list[str] = []
    for path in PORTABILITY_SURFACES:
        text = path.read_text(encoding="utf-8")
        for needle in disallowed:
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {needle!r}")

    assert offenders == []


def test_codex_role_invocation_includes_discovered_skills(tmp_path: Path) -> None:
    fake_proc = MagicMock()
    fake_proc.pid = 4323

    with (
        patch.dict(os.environ, {"MINIONS_AGENT_HOST": "codex"}, clear=False),
        patch("minions.lifecycle.role.subprocess.Popen", return_value=fake_proc),
        patch("minions.lifecycle.role.project_workspace", return_value=tmp_path),
        patch("minions.lifecycle.role.project_role_log", return_value=tmp_path / "role-coder.log"),
        patch("minions.lifecycle.role.project_memory_dir", return_value=tmp_path / "memory"),
        patch(
            "minions.lifecycle.role.project_scratchpad",
            return_value=tmp_path / "memory" / "coder.md",
        ),
        patch("minions.lifecycle.agent_host.project_dir", return_value=tmp_path),
    ):
        role_mod.invoke_role_ephemeral(
            "coder",
            37596,
            [{"id": "e1", "content": "check skill injection"}],
        )

    stdin_payload = fake_proc.stdin.write.call_args[0][0].decode("utf-8")
    assert "# MinionsOS Codex Role Invocation" in stdin_payload
    assert "[Skills]" in stdin_payload
    assert "coding-methodology" in stdin_payload
    assert "minions/roles/coder/skills/{slug}.md" in stdin_payload
    assert "Intended role tool allowlist" in stdin_payload
    assert "`Task` means the current host's native subagent/delegation capability" in stdin_payload
