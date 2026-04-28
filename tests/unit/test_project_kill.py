"""Tests for hard-stopping project runtime without wiping EACN state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minions.lifecycle import project as proj_mod
from minions.state.store import ProjectEntry, RoleEntry, StateStore


def test_project_kill_stops_runtime_and_preserves_eacn_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = 40121
    pdir = tmp_path / f"project_{port}"
    eacn_db = pdir / "eacn3_data" / "eacn3.db"
    eacn_db.parent.mkdir(parents=True)
    eacn_db.write_text("keep", encoding="utf-8")

    store = StateStore(path=tmp_path / "projects.json")
    entry = ProjectEntry(
        port=port,
        real_name="Kill Runtime",
        status="active",
        created="2026-04-28T00:00:00+00:00",
        current_branch=f"minionsos/project-{port}",
        active_roles=[
            RoleEntry(name="coder", state="active", pid=222, spawned_at="x"),
            RoleEntry(name="writer", state="sleeping", pid=None),
        ],
    )
    store.add_project(entry)

    meta = pdir / "meta.json"
    meta.write_text(
        json.dumps(
            {
                **entry.model_dump(),
                "backend_pid": 111,
                "eacn3_server_id": "srv-abc",
                "eacn3_server_token": "srv-token",
                "gru_agent_id": "gru",
                "gru_agent_token": "gru-token",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    stopped_backends: list[tuple[int, int | None]] = []
    stopped_roles: list[tuple[int, str, int | None]] = []
    monkeypatch.setattr(proj_mod, "project_meta_json", lambda p: pdir / "meta.json")
    monkeypatch.setattr(
        proj_mod,
        "_stop_backend",
        lambda p, pid=None: stopped_backends.append((p, pid)),
    )
    monkeypatch.setattr(
        proj_mod,
        "_stop_role_process",
        lambda p, role, pid=None: stopped_roles.append((p, role, pid)) or "terminated",
    )

    result = proj_mod.project_kill(port, store=store)

    assert result["status"] == "dormant"
    assert stopped_backends == [(port, 111)]
    assert stopped_roles == [(port, "coder", 222)]
    assert eacn_db.read_text(encoding="utf-8") == "keep"
    assert not store.is_port_retired(port)

    updated = store.get_project(port)
    assert updated is not None
    assert updated.status == "dormant"
    assert [role.state for role in updated.active_roles] == ["dismissed", "dismissed"]
    assert [role.pid for role in updated.active_roles] == [None, None]

    updated_meta = json.loads(meta.read_text(encoding="utf-8"))
    assert updated_meta["status"] == "dormant"
    assert updated_meta["backend_pid"] is None
    assert updated_meta["eacn3_server_id"] == "srv-abc"
    assert updated_meta["gru_agent_token"] == "gru-token"


def test_project_kill_rejects_closed_project(tmp_path: Path) -> None:
    port = 40122
    store = StateStore(path=tmp_path / "projects.json")
    store.add_project(
        ProjectEntry(
            port=port,
            real_name="Closed",
            status="closed",
            created="2026-04-28T00:00:00+00:00",
            current_branch=f"minionsos/project-{port}",
        )
    )

    with pytest.raises(proj_mod.ProjectError, match="already closed"):
        proj_mod.project_kill(port, store=store)
