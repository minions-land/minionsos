"""Unit tests for observatory terminal role filtering."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from minions.lifecycle.noter_terminal import NoterSnapshot, _render_roles
from minions.state.store import ProjectEntry, RoleEntry


def test_render_roles_hides_dismissed() -> None:
    """Dismissed roles should not appear in the observatory terminal role table."""
    project = ProjectEntry(
        port=37596,
        real_name="test-project",
        status="active",
        created="2026-05-26T00:00:00Z",
        active_roles=[
            RoleEntry(name="ethics", state="active"),
            RoleEntry(name="expert-general", state="active"),
            RoleEntry(name="expert-dismissed-moe", state="dismissed"),
            RoleEntry(name="expert-dismissed-triton", state="dismissed"),
            RoleEntry(name="expert-moe-arch", state="active"),
            RoleEntry(name="expert-triton-kernel", state="active"),
        ],
    )
    snapshot = NoterSnapshot(
        project=project,
        health={},
        tasks=[],
        notes=[],
        current_phase=None,
        phase_allowed_roles=[],
        phase_online_roles=[],
        errors=[],
        captured_at="2026-05-26T14:51:32Z",
    )
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    _render_roles(snapshot, console)
    output = buf.getvalue()

    # Active roles should appear
    assert "ethics" in output
    assert "expert-general" in output
    assert "expert-moe-arch" in output
    assert "expert-triton-kernel" in output

    # Dismissed roles should NOT appear in the table
    assert "expert-dismissed-moe" not in output
    assert "expert-dismissed-triton" not in output

    # Footer should mention 2 dismissed roles
    assert "2 dismissed roles hidden" in output


def test_render_roles_no_footer_when_all_active() -> None:
    """No dismissed-roles footer when all roles are active."""
    project = ProjectEntry(
        port=37596,
        real_name="test-project",
        status="active",
        created="2026-05-26T00:00:00Z",
        active_roles=[
            RoleEntry(name="ethics", state="active"),
            RoleEntry(name="expert-general", state="sleeping"),
        ],
    )
    snapshot = NoterSnapshot(
        project=project,
        health={},
        tasks=[],
        notes=[],
        current_phase=None,
        phase_allowed_roles=[],
        phase_online_roles=[],
        errors=[],
        captured_at="2026-05-26T14:51:32Z",
    )
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    _render_roles(snapshot, console)
    output = buf.getvalue()

    assert "ethics" in output
    assert "expert-general" in output
    assert "dismissed" not in output
