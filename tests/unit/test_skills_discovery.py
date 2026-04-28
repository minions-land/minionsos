"""Unit tests for minions.lifecycle.skills."""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.lifecycle import skills as skills_mod


@pytest.fixture
def fake_roles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    monkeypatch.setattr(skills_mod, "ROLES_DIR", roles_dir)
    return roles_dir


def _write_skill(roles_dir: Path, role: str, slug: str, text: str) -> None:
    d = roles_dir / role / "skills"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text(text, encoding="utf-8")


def test_empty_when_no_dir(fake_roles: Path) -> None:
    assert skills_mod.list_skills("noter") == []


def test_standard_h1_plus_summary(fake_roles: Path) -> None:
    _write_skill(
        fake_roles,
        "experimenter",
        "execution-guide",
        "# Skill - Execution Guide\n\nA disciplined procedure for running experiments.\n"
        "\n## Core move\n...",
    )
    result = skills_mod.list_skills("experimenter")
    assert result == [("execution-guide", "A disciplined procedure for running experiments.")]


def test_no_h1_uses_first_line(fake_roles: Path) -> None:
    _write_skill(fake_roles, "writer", "x", "Just a summary line without title.\n\nbody")
    assert skills_mod.list_skills("writer") == [("x", "Just a summary line without title.")]


def test_h1_only_falls_back_to_title(fake_roles: Path) -> None:
    _write_skill(fake_roles, "writer", "x", "# My Title\n\n## Next heading only\n")
    assert skills_mod.list_skills("writer") == [("x", "My Title")]


def test_truncates_long_summary(fake_roles: Path) -> None:
    long = "x" * 200
    _write_skill(fake_roles, "writer", "x", f"# T\n\n{long}\n")
    [(slug, summary)] = skills_mod.list_skills("writer")
    assert slug == "x"
    assert len(summary) <= 100


def test_expert_aliases_resolve_to_expert_dir(fake_roles: Path) -> None:
    _write_skill(fake_roles, "expert", "first-principles", "# First\n\nReason from primitives.\n")
    assert skills_mod.list_skills("expert-dl-arch") == [
        ("first-principles", "Reason from primitives.")
    ]


def test_common_skills_are_listed_before_role_skills(fake_roles: Path) -> None:
    _write_skill(fake_roles, "common", "eacn-network", "# EACN\n\nUse the network.\n")
    _write_skill(fake_roles, "writer", "paper-compile", "# Compile\n\nBuild the paper.\n")

    assert skills_mod.list_skills("writer") == [
        ("eacn-network", "Use the network."),
        ("paper-compile", "Build the paper."),
    ]


def test_common_skill_slug_wins_over_role_duplicate(fake_roles: Path) -> None:
    _write_skill(fake_roles, "common", "shared", "# Shared\n\nCommon version.\n")
    _write_skill(fake_roles, "writer", "shared", "# Shared\n\nWriter version.\n")

    assert skills_mod.list_skills("writer") == [("shared", "Common version.")]


def test_sorted_and_skips_non_markdown(fake_roles: Path) -> None:
    _write_skill(fake_roles, "writer", "b-two", "# B\n\nSecond.\n")
    _write_skill(fake_roles, "writer", "a-one", "# A\n\nFirst.\n")
    (fake_roles / "writer" / "skills" / "note.txt").write_text("ignored", encoding="utf-8")
    result = skills_mod.list_skills("writer")
    assert [s for s, _ in result] == ["a-one", "b-two"]


def test_empty_file_returns_empty_summary(fake_roles: Path) -> None:
    _write_skill(fake_roles, "writer", "x", "")
    assert skills_mod.list_skills("writer") == [("x", "")]
