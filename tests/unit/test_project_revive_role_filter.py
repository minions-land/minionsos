"""Regression tests for GitHub Issue #44.

``project_revive`` must refuse to resurrect role entries whose names are
neither in :data:`FIXED_ROLES` nor pass :func:`is_expert_role`. The bug
fix lives in ``minions.lifecycle.project._role_entries_from_meta`` /
``_roles_for_revive``. Coercing the name here would create a different
agent identity than the one EACN already minted at original spawn, so the
right move is to skip with a warning.

Note: ``state == "dismissed"`` is *not* a filter trigger.
``project_dormant`` legitimately marks every active role as ``dismissed``
when transitioning a project to dormant; ``project_revive`` then re-launches
those records cold. Filtering on dismissed would break the dormant/revive
lifecycle.
"""

from __future__ import annotations

import logging

import pytest

from minions.lifecycle.project import _role_entries_from_meta, _roles_for_revive
from minions.state.store import ProjectEntry, RoleEntry


def _make_entry(active_roles: list[RoleEntry] | None = None) -> ProjectEntry:
    return ProjectEntry(
        port=37596,
        real_name="test-project",
        status="dormant",
        created="2026-05-27T00:00:00+00:00",
        active_roles=active_roles or [],
    )


def test_roles_for_revive_filters_bare_slug_experts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Mixed meta.json: valid expert + bare-slug + valid fixed (dismissed kept)."""
    raw_meta = {
        "active_roles": [
            {"name": "expert-foo", "state": "sleeping"},
            {"name": "moe-arch", "state": "sleeping"},  # bare-slug expert (broken)
            {"name": "noter", "state": "sleeping"},
            {"name": "coder", "state": "dismissed"},  # dormant marker — must be kept
        ],
    }
    entry = _make_entry(active_roles=[])  # force meta fallback

    with caplog.at_level(logging.WARNING, logger="minions.lifecycle.project"):
        roles = _roles_for_revive(entry, raw_meta)

    names = [r.name for r in roles]
    assert "expert-foo" in names
    assert "noter" in names
    assert "coder" in names  # dismissed-state preserved through revive
    assert "moe-arch" not in names
    assert len(roles) == 3

    text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "malformed role name 'moe-arch'" in text


def test_role_entries_from_meta_directly_filters_same_records() -> None:
    """The filter is applied at the meta-parse seam itself."""
    raw_meta = {
        "active_roles": [
            {"name": "expert-foo", "state": "sleeping"},
            {"name": "moe-arch", "state": "sleeping"},
            {"name": "noter", "state": "sleeping"},
            {"name": "coder", "state": "dismissed"},
        ],
    }
    roles = _role_entries_from_meta(raw_meta)
    # Only the malformed bare-slug record is dropped; "dismissed" is kept.
    assert {r.name for r in roles} == {"expert-foo", "noter", "coder"}


def test_roles_for_revive_filters_active_roles_path_too(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """projects.json path also filters malformed names but keeps dismissed."""
    entry = _make_entry(
        active_roles=[
            RoleEntry(name="expert-bar", state="sleeping"),
            RoleEntry(name="writer", state="dismissed"),
            RoleEntry(name="coder", state="active"),
            RoleEntry(name="moe-arch", state="sleeping"),  # bare-slug — drop
        ]
    )
    raw_meta: dict[str, object] = {}

    with caplog.at_level(logging.WARNING, logger="minions.lifecycle.project"):
        roles = _roles_for_revive(entry, raw_meta)

    names = [r.name for r in roles]
    assert names == ["expert-bar", "writer", "coder"]


def test_roles_for_revive_falls_back_to_meta_when_active_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If projects.json yields zero valid roles, meta.json is consulted."""
    entry = _make_entry(
        active_roles=[RoleEntry(name="moe-arch", state="sleeping")],  # all-malformed
    )
    raw_meta = {
        "active_roles": [{"name": "noter", "state": "sleeping"}],
    }

    with caplog.at_level(logging.WARNING, logger="minions.lifecycle.project"):
        roles = _roles_for_revive(entry, raw_meta)

    assert [r.name for r in roles] == ["noter"]
