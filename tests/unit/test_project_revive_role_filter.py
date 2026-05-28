"""Regression tests for GitHub Issue #44.

``project_revive`` must drop ``dismissed`` records and refuse to resurrect
role entries whose names are neither in :data:`FIXED_ROLES` nor pass
:func:`is_expert_role`. The bug fix lives in
``minions.lifecycle.project._role_entries_from_meta`` /
``_roles_for_revive``. Coercing the name here would create a different
agent identity than the one EACN already minted at original spawn, so the
right move is to skip with a warning.
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


def test_roles_for_revive_filters_dismissed_and_bare_slug_experts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Mixed meta.json: valid expert + bare-slug + valid fixed + dismissed fixed."""
    raw_meta = {
        "active_roles": [
            {"name": "expert-foo", "state": "sleeping"},
            {"name": "moe-arch", "state": "sleeping"},  # bare-slug expert (broken)
            {"name": "noter", "state": "sleeping"},
            {"name": "gru", "state": "dismissed"},  # dismissed must be dropped
        ],
    }
    entry = _make_entry(active_roles=[])  # force meta fallback

    with caplog.at_level(logging.INFO, logger="minions.lifecycle.project"):
        roles = _roles_for_revive(entry, raw_meta)

    names = [r.name for r in roles]
    assert "expert-foo" in names
    assert "noter" in names
    assert "moe-arch" not in names
    assert "gru" not in names
    assert len(roles) == 2
    assert all(r.state == "sleeping" for r in roles)

    text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "dismissed role 'gru'" in text
    assert "malformed role name 'moe-arch'" in text


def test_role_entries_from_meta_directly_filters_same_records() -> None:
    """The filter is applied at the meta-parse seam itself."""
    raw_meta = {
        "active_roles": [
            {"name": "expert-foo", "state": "sleeping"},
            {"name": "moe-arch", "state": "sleeping"},
            {"name": "noter", "state": "sleeping"},
            {"name": "gru", "state": "dismissed"},
        ],
    }
    roles = _role_entries_from_meta(raw_meta)
    assert {r.name for r in roles} == {"expert-foo", "noter"}


def test_roles_for_revive_filters_active_roles_path_too(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """projects.json path also filters dismissed + malformed."""
    entry = _make_entry(
        active_roles=[
            RoleEntry(name="expert-bar", state="sleeping"),
            RoleEntry(name="writer", state="dismissed"),
            RoleEntry(name="coder", state="active"),
        ]
    )
    raw_meta: dict[str, object] = {}  # ignored when active_roles produces results

    with caplog.at_level(logging.INFO, logger="minions.lifecycle.project"):
        roles = _roles_for_revive(entry, raw_meta)

    names = [r.name for r in roles]
    assert names == ["expert-bar", "coder"]
    assert all(r.state == "sleeping" for r in roles)


def test_roles_for_revive_falls_back_to_meta_when_active_all_filtered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If projects.json yields zero valid roles, meta.json is consulted."""
    entry = _make_entry(
        active_roles=[RoleEntry(name="writer", state="dismissed")],
    )
    raw_meta = {
        "active_roles": [{"name": "noter", "state": "sleeping"}],
    }

    with caplog.at_level(logging.INFO, logger="minions.lifecycle.project"):
        roles = _roles_for_revive(entry, raw_meta)

    assert [r.name for r in roles] == ["noter"]
