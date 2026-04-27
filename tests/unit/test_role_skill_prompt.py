"""Tests for Role wake-up skill prompt wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from minions.lifecycle import role as role_mod


def test_skill_block_uses_runtime_minions_root(tmp_path: Path) -> None:
    root = tmp_path / "MinionsOS"
    expected = (root / "minions" / "roles" / "writer" / "skills" / "{slug}.md").resolve()

    with (
        patch.object(role_mod, "MINIONS_ROOT", root),
        patch.object(role_mod, "list_skills", return_value=[("paper-compile", "Compile paper.")]),
    ):
        msg = role_mod._format_event_message([{"id": "e1"}], role_name="writer")

    assert f"Read full skill files at `{expected}`" in msg
    assert "`minions/roles/writer/skills/{slug}.md`" not in msg


def test_skill_block_maps_expert_alias_to_base_expert_dir(tmp_path: Path) -> None:
    root = tmp_path / "MinionsOS"
    expected = (root / "minions" / "roles" / "expert" / "skills" / "{slug}.md").resolve()

    with (
        patch.object(role_mod, "MINIONS_ROOT", root),
        patch.object(role_mod, "list_skills", return_value=[("first-principles", "Reason.")]),
    ):
        msg = role_mod._format_event_message([{"id": "e1"}], role_name="expert-dl-arch")

    assert f"Read full skill files at `{expected}`" in msg
