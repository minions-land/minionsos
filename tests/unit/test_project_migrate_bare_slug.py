"""Tests for ``project_migrate_bare_slug_experts`` (issue #49).

Older versions of ``register_expert`` accepted bare-slug names (e.g.
``"foo"``) and persisted them verbatim into ``meta.json``'s ``active_roles``.
The migration helper rewrites meta.json in place, dropping anything that is
neither a fixed role nor an expert role.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from minions.errors import ProjectError
from minions.lifecycle import project as proj_mod
from minions.state.store import ProjectEntry, StateStore


def _make_store(tmp_path: Path, *, port: int = 8123) -> StateStore:
    store = StateStore(path=tmp_path / "projects.json")
    store.add_project(
        ProjectEntry(
            port=port,
            real_name="migrate-test",
            status="active",
            created="2026-05-01T00:00:00Z",
            current_branch=f"minionsos/project-{port}",
            active_roles=[],
        )
    )
    return store


def _seed_meta(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    active_roles: list[dict[str, Any]],
    *,
    port: int = 8123,
) -> Path:
    meta_path = tmp_path / f"project_{port}_meta.json"
    meta_path.write_text(
        json.dumps({"phase": "design", "active_roles": active_roles}, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(proj_mod, "project_meta_json", lambda p: meta_path)
    return meta_path


def test_dry_run_returns_plan_without_mutating_meta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _make_store(tmp_path)
    seed = [
        {"name": "foo-bar"},  # bare slug -> should be removed
        {"name": "expert-data"},  # legit expert
        {"name": "ethics"},  # fixed role
    ]
    meta_path = _seed_meta(monkeypatch, tmp_path, seed)

    out = proj_mod.project_migrate_bare_slug_experts(
        8123, dry_run=True, store=store
    )

    assert out["port"] == 8123
    assert out["dry_run"] is True
    assert out["removed"] == ["foo-bar"]
    assert out["kept"] == 2
    # meta.json is untouched on dry-run
    on_disk = json.loads(meta_path.read_text(encoding="utf-8"))
    assert on_disk["active_roles"] == seed


def test_non_dry_run_removes_bare_slug_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _make_store(tmp_path)
    seed = [
        {"name": "foo-bar"},
        {"name": "expert-data"},
        {"name": "ethics"},
        {"name": "random-thing"},
    ]
    meta_path = _seed_meta(monkeypatch, tmp_path, seed)

    out = proj_mod.project_migrate_bare_slug_experts(
        8123, dry_run=False, store=store
    )

    assert out["dry_run"] is False
    assert sorted(out["removed"]) == ["foo-bar", "random-thing"]
    assert out["kept"] == 2

    on_disk = json.loads(meta_path.read_text(encoding="utf-8"))
    kept_names = [r["name"] for r in on_disk["active_roles"]]
    assert kept_names == ["expert-data", "ethics"]


def test_fixed_and_expert_roles_survive_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from minions.lifecycle.role import FIXED_ROLES

    store = _make_store(tmp_path)
    seed = (
        [{"name": r} for r in FIXED_ROLES]
        + [
            {"name": "expert-foo"},
            {"name": "foo-expert"},
            {"name": "expert"},
        ]
    )
    meta_path = _seed_meta(monkeypatch, tmp_path, seed)

    out = proj_mod.project_migrate_bare_slug_experts(
        8123, dry_run=False, store=store
    )

    assert out["removed"] == []
    assert out["kept"] == len(seed)

    on_disk = json.loads(meta_path.read_text(encoding="utf-8"))
    assert on_disk["active_roles"] == seed


def test_unknown_port_raises_project_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _make_store(tmp_path)  # only port=8123

    with pytest.raises(ProjectError):
        proj_mod.project_migrate_bare_slug_experts(
            9999, dry_run=True, store=store
        )
