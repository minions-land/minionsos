"""Unit tests for Noter terminal role filtering."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from minions.lifecycle.noter_terminal import NoterSnapshot, _render_roles
from minions.state.store import ProjectEntry, RoleEntry


def test_render_roles_hides_dismissed() -> None:
    """Dismissed roles should not appear in the Noter terminal role table."""
    project = ProjectEntry(
        port=37596,
        real_name="test-project",
        status="active",
        created="2026-05-26T00:00:00Z",
        active_roles=[
            RoleEntry(name="noter", state="active"),
            RoleEntry(name="coder", state="active"),
            RoleEntry(name="moe-arch", state="dismissed"),
            RoleEntry(name="triton-kernel", state="dismissed"),
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
    assert "noter" in output
    assert "coder" in output
    assert "expert-moe-arch" in output
    assert "expert-triton-kernel" in output

    # Dismissed roles should NOT appear in the table
    assert "moe-arch" not in output or "dismissed" not in output.split("moe-arch")[0]
    assert "triton-kernel" not in output or "dismissed" not in output.split("triton-kernel")[0]

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
            RoleEntry(name="noter", state="active"),
            RoleEntry(name="coder", state="sleeping"),
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

    assert "noter" in output
    assert "coder" in output
    assert "dismissed" not in output
