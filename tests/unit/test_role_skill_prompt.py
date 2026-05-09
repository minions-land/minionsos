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


def test_gru_event_message_uses_mos_pool_for_internal_and_eacn3_for_global() -> None:
    with patch.object(role_mod, "list_skills", return_value=[]):
        msg = role_mod._format_event_message([{"id": "e1"}], role_name="gru")

    # Gru's main coordination path is the MOS Agent Pool for internal work,
    # plus raw eacn3_* for Global EACN3 scope, plus gru_relay for cross-project.
    assert "MOS Agent Pool" in msg
    assert "mos_await_events" in msg
    assert "mos_send_message" in msg
    assert "mos_create_task" in msg
    assert "eacn3_*" in msg  # Global EACN3 carve-out must still be named.
    assert "gru_relay" in msg
