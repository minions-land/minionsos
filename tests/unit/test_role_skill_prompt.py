"""Tests for Role wake-up skill prompt wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from minions.lifecycle import role as role_mod


def test_skill_block_uses_runtime_minions_root(tmp_path: Path) -> None:
    root = tmp_path / "MinionsOS"
    expected_common = (root / "minions" / "roles" / "common" / "skills" / "{slug}.md").resolve()
    expected_role = (root / "minions" / "roles" / "writer" / "skills" / "{slug}.md").resolve()

    with (
        patch.object(role_mod, "MINIONS_ROOT", root),
        patch.object(role_mod, "list_skills", return_value=[("paper-compile", "Compile paper.")]),
    ):
        msg = role_mod._format_event_message([{"id": "e1"}], role_name="writer")

    assert f"Read shared skill files at `{expected_common}`" in msg
    assert f"and role skill files at `{expected_role}`" in msg
    assert "`minions/roles/writer/skills/{slug}.md`" not in msg


def test_skill_block_maps_expert_alias_to_base_expert_dir(tmp_path: Path) -> None:
    root = tmp_path / "MinionsOS"
    expected_common = (root / "minions" / "roles" / "common" / "skills" / "{slug}.md").resolve()
    expected_role = (root / "minions" / "roles" / "expert" / "skills" / "{slug}.md").resolve()

    with (
        patch.object(role_mod, "MINIONS_ROOT", root),
        patch.object(role_mod, "list_skills", return_value=[("first-principles", "Reason.")]),
    ):
        msg = role_mod._format_event_message([{"id": "e1"}], role_name="expert-dl-arch")

    assert f"Read shared skill files at `{expected_common}`" in msg
    assert f"and role skill files at `{expected_role}`" in msg


def test_event_message_uses_native_eacn3_tools() -> None:
    with patch.object(role_mod, "list_skills", return_value=[]):
        msg = role_mod._format_event_message([{"id": "e1"}], role_name="gru")

    # The common wake header points roles at the native eacn3_* surface.
    assert "eacn3_send_message" in msg
    assert "eacn3_create_task" in msg
    # Removed wrapper names must not leak back in.
    assert "mos_await_events" not in msg
    assert "mos_send_message" not in msg
    assert "mos_create_task" not in msg
    assert "MOS Agent Pool" not in msg
