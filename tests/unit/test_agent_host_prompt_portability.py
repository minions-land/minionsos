"""Prompt invariants that keep role behavior portable across agent hosts."""

from __future__ import annotations

from pathlib import Path

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
    assert "any agent host" in text
    assert "host-native subagent mechanism" in text
    assert "self-contained" in text


def test_common_role_contract_requires_role_to_role_eacn() -> None:
    text = (ROOT / "minions" / "roles" / "SYSTEM.md").read_text(encoding="utf-8")

    assert "## Role-to-role collaboration first" in text
    assert "targeted task" in text
    assert "eacn3_create_task" in text
    assert "direct EACN" in text
    assert "Do not route ordinary cross-role work through Gru" in text


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
