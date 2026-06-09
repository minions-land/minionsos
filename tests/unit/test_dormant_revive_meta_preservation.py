"""Tests for preserving project runtime metadata across dormant / revive.

project_dormant and project_revive must keep runtime fields (backend_pid,
eacn3_server_id, eacn3_server_token, gru_agent_id, gru_agent_token,
topic_doc, template_dir) that live in meta.json outside the store entry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from minions.lifecycle import project as proj_mod
from minions.lifecycle import project_backend, project_lifecycle, project_metadata, project_paths
from minions.state.store import ProjectEntry, RoleEntry, StateStore


def _install_patches(
    monkeypatch: pytest.MonkeyPatch,
    pdir: Path,
    *,
    backend_pid: int,
    server_id: str,
    server_token: str,
    gru_token: str,
) -> None:
    """Patch all external-side-effect helpers in proj_mod."""
    monkeypatch.setattr(proj_mod, "project_dir", lambda p: pdir)
    monkeypatch.setattr(proj_mod, "project_logs_dir", lambda p: pdir / "logs")
    monkeypatch.setattr(proj_mod, "project_meta_json", lambda p: pdir / "meta.json")
    monkeypatch.setattr(proj_mod, "project_main_workspace", lambda p: pdir / "workspace")
    monkeypatch.setattr(proj_mod, "project_eacn_db", lambda p: pdir / "eacn3_data" / "eacn3.db")
    monkeypatch.setattr(proj_mod, "project_backend_log", lambda p: pdir / "logs" / "backend.log")

    # Patch project_metadata's project_meta_json helper.
    monkeypatch.setattr(project_metadata, "project_meta_json", lambda p: pdir / "meta.json")

    monkeypatch.setattr(
        proj_mod,
        "ensure_role_workspace",
        lambda p, role_name, base_branch=None: (
            f"minionsos/project-{p}/{role_name}",
            pdir / "workspace" / "roles" / role_name,
        ),
    )

    class _FakeProc:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def terminate(self) -> None:  # pragma: no cover - unused happy-path
            pass

    # Patch helpers used through project_backend.
    monkeypatch.setattr(project_backend, "start_backend", lambda port: _FakeProc(backend_pid))
    monkeypatch.setattr(project_backend, "wait_for_health", lambda port, timeout=None: None)
    monkeypatch.setattr(project_backend, "stop_backend", lambda port, pid=None: None)
    monkeypatch.setattr(project_backend, "register_server", lambda port: (server_id, server_token))

    # Patch backend helpers imported by project_lifecycle.
    monkeypatch.setattr(project_lifecycle, "start_backend", lambda port: _FakeProc(backend_pid))
    monkeypatch.setattr(project_lifecycle, "wait_for_health", lambda port, timeout=None: None)
    monkeypatch.setattr(project_lifecycle, "stop_backend", lambda port, pid=None: None)
    monkeypatch.setattr(
        project_lifecycle,
        "register_server",
        lambda port: (server_id, server_token),
    )
    # register_gru_eacn_agent returns (gru_agent_id, gru_agent_token);
    # keep the agent_id stable.
    monkeypatch.setattr(
        project_lifecycle,
        "register_gru_eacn_agent",
        lambda port, sid: ("gru", gru_token),
    )
    # Tests that need adopt_running_backend patch it explicitly.

    # Patch project_paths helpers.
    monkeypatch.setattr(project_paths, "git_tag", lambda port, tag: None)

    # Patch git_tag imported by project_lifecycle.
    monkeypatch.setattr(project_lifecycle, "git_tag", lambda port, tag: None)

    # Patch proj_mod helpers.
    monkeypatch.setattr(proj_mod, "upsert_agent_identity", lambda *args, **kwargs: {})
    monkeypatch.setattr(proj_mod, "identity_map_for_meta", lambda port: {})

    def _fake_register_agent(**kwargs: Any) -> tuple[str, list[str]]:
        return gru_token, []

    monkeypatch.setattr(proj_mod.eacn_client, "register_agent", _fake_register_agent)
    monkeypatch.setattr(proj_mod.eacn_client, "ensure_balance", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        proj_mod.eacn_client,
        "get_server_card",
        lambda port, sid, timeout=3.0: {"server_id": sid},
    )
    monkeypatch.setattr(proj_mod.eacn_client, "server_heartbeat", lambda *args, **kwargs: True)


def _seed_project(
    tmp_path: Path,
    *,
    port: int = 40101,
    backend_pid: int = 12345,
    server_id: str = "srv-abc",
    server_token: str = "srv-tok",
    gru_token: str = "gru-tok",
    topic_doc: str = "/tmp/topic.md",
    template_dir: str = "/tmp/tpl",
) -> tuple[StateStore, ProjectEntry, Path]:
    """Create an 'active' project entry in a fresh store + on-disk meta.json
    with the full runtime extras set, simulating the state after
    project_create."""
    # Use MINIONS_PROJECTS_ROOT from conftest
    import os

    projects_root = Path(os.environ.get("MINIONS_PROJECTS_ROOT", tmp_path))
    pdir = projects_root / f"project_{port}"
    (pdir / "logs").mkdir(parents=True, exist_ok=True)

    # Create parent_repo.git directory structure for git operations
    parent_repo = pdir / "parent_repo.git"
    parent_repo.mkdir(parents=True, exist_ok=True)
    (parent_repo / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    (parent_repo / "objects").mkdir(parents=True, exist_ok=True)
    (parent_repo / "HEAD").write_text("ref: refs/heads/main\n")

    store = StateStore(path=tmp_path / "projects.json")
    entry = ProjectEntry(
        port=port,
        real_name="Regression",
        status="active",
        created="2026-04-24T00:00:00+00:00",
        current_branch=f"minionsos/project-{port}",
        active_roles=[],
    )
    store.add_project(entry)

    meta = pdir / "meta.json"
    meta.write_text(
        json.dumps(
            {
                **entry.model_dump(),
                "backend_pid": backend_pid,
                "eacn3_server_id": server_id,
                "eacn3_server_token": server_token,
                "gru_agent_id": "gru",
                "gru_agent_token": gru_token,
                "topic_doc": topic_doc,
                "template_dir": template_dir,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return store, entry, pdir


def test_dormant_preserves_meta_extras(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    port = 40101
    store, _entry, pdir = _seed_project(tmp_path, port=port)
    _install_patches(
        monkeypatch,
        pdir,
        backend_pid=12345,
        server_id="srv-abc",
        server_token="srv-tok",
        gru_token="gru-tok",
    )

    proj_mod.project_dormant(port, store=store)

    meta = json.loads((pdir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "dormant"
    assert meta["backend_pid"] == 12345
    assert meta["eacn3_server_id"] == "srv-abc"
    assert meta["eacn3_server_token"] == "srv-tok"
    assert meta["gru_agent_id"] == "gru"
    assert meta["gru_agent_token"] == "gru-tok"
    assert meta["topic_doc"] == "/tmp/topic.md"
    assert meta["template_dir"] == "/tmp/tpl"


def test_revive_updates_and_preserves_meta_extras(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = 40102
    store, _entry, pdir = _seed_project(tmp_path, port=port)
    _install_patches(
        monkeypatch,
        pdir,
        backend_pid=99999,
        server_id="srv-new",
        server_token="tok-new",
        gru_token="gru-new",
    )

    proj_mod.project_dormant(port, store=store)
    # Dormant path keeps old extras; revive must install fresh backend/server
    # tokens while preserving unrelated extras (topic_doc, template_dir).
    proj_mod.project_revive(port, store=store)

    meta = json.loads((pdir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "active"
    assert meta["backend_pid"] == 99999
    assert meta["eacn3_server_id"] == "srv-new"
    assert meta["eacn3_server_token"] == "tok-new"
    assert meta["gru_agent_id"] == "gru"
    assert meta["gru_agent_token"] == "gru-new"
    assert meta["topic_doc"] == "/tmp/topic.md"
    assert meta["template_dir"] == "/tmp/tpl"


def test_revive_reconciles_existing_experiment_scheduler_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = 40114
    store, _entry, pdir = _seed_project(tmp_path, port=port)
    _install_patches(
        monkeypatch,
        pdir,
        backend_pid=99999,
        server_id="srv-new",
        server_token="tok-new",
        gru_token="gru-new",
    )
    scheduler_db = tmp_path / "scheduler.sqlite"
    scheduler_db.write_text("", encoding="utf-8")

    from minions.tools import experiment_scheduler

    monkeypatch.setattr(experiment_scheduler, "default_db_path", lambda project_port: scheduler_db)
    reconciled: list[int] = []

    class _FakeScheduler:
        def __init__(self, *, project_port: int) -> None:
            self.project_port = project_port

        def reconcile(self) -> dict[str, list[dict[str, object]]]:
            reconciled.append(self.project_port)
            return {
                "reaped": [{"run_id": "r-dead"}],
                "launched": [],
                "completed": [],
                "failed": [],
            }

    monkeypatch.setattr(experiment_scheduler, "ExperimentScheduler", _FakeScheduler)

    proj_mod.project_dormant(port, store=store)
    proj_mod.project_revive(port, store=store)

    assert reconciled == [port]


def test_revive_does_not_create_experiment_scheduler_db_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = 40115
    store, _entry, pdir = _seed_project(tmp_path, port=port)
    _install_patches(
        monkeypatch,
        pdir,
        backend_pid=99999,
        server_id="srv-new",
        server_token="tok-new",
        gru_token="gru-new",
    )
    scheduler_db = tmp_path / "missing" / "scheduler.sqlite"

    from minions.tools import experiment_scheduler

    monkeypatch.setattr(experiment_scheduler, "default_db_path", lambda project_port: scheduler_db)

    class _FailIfConstructed:
        def __init__(self, *, project_port: int) -> None:
            raise AssertionError("scheduler should not be constructed without an existing DB")

    monkeypatch.setattr(experiment_scheduler, "ExperimentScheduler", _FailIfConstructed)

    proj_mod.project_dormant(port, store=store)
    proj_mod.project_revive(port, store=store)

    assert not scheduler_db.exists()


def test_revive_adopts_running_backend_left_by_failed_kill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = 40112
    store, entry, pdir = _seed_project(tmp_path, port=port)
    dormant = entry.model_copy(update={"status": "dormant", "dormant_at": "x"})
    store.update_project(port, status="dormant", dormant_at="x")
    (pdir / "meta.json").write_text(
        json.dumps(
            {
                **dormant.model_dump(),
                "backend_pid": 111,
                "eacn3_server_id": "srv-old",
                "eacn3_server_token": "tok-old",
                "gru_agent_id": "gru",
                "gru_agent_token": "gru-old",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _install_patches(
        monkeypatch,
        pdir,
        backend_pid=99999,
        server_id="srv-adopted",
        server_token="tok-adopted",
        gru_token="gru-adopted",
    )
    monkeypatch.setattr(
        proj_mod,
        "_start_backend",
        lambda port: (_ for _ in ()).throw(proj_mod.BackendError("Port occupied")),
    )
    monkeypatch.setattr(
        proj_mod,
        "_adopt_running_backend",
        lambda port: proj_mod._AdoptedBackend(777),
    )
    # 也需要mock project_lifecycle中导入的函数
    from minions.errors import BackendError

    monkeypatch.setattr(
        project_lifecycle,
        "start_backend",
        lambda port: (_ for _ in ()).throw(BackendError("Port occupied")),
    )

    class _AdoptedProc:
        def __init__(self, pid):
            self.pid = pid

    monkeypatch.setattr(
        project_lifecycle,
        "adopt_running_backend",
        lambda port: _AdoptedProc(777),
    )

    proj_mod.project_revive(port, store=store)

    meta = json.loads((pdir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "active"
    assert meta["backend_pid"] == 777
    assert meta["eacn3_server_id"] == "srv-adopted"


def test_revive_restores_ethics_from_meta_cold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_git_operations
) -> None:
    port = 40113
    store, entry, pdir = _seed_project(tmp_path, port=port)
    store.update_project(port, status="dormant", dormant_at="x", active_roles=[])
    meta_role = RoleEntry(
        name="ethics",
        state="dismissed",
        pid=123,
        time_trigger_interval=None,
    )
    dormant = entry.model_copy(
        update={
            "status": "dormant",
            "dormant_at": "x",
            "active_roles": [meta_role],
        }
    )
    (pdir / "meta.json").write_text(
        json.dumps(
            {
                **dormant.model_dump(),
                "backend_pid": 111,
                "eacn3_server_id": "srv-old",
                "eacn3_server_token": "tok-old",
                "gru_agent_id": "gru",
                "gru_agent_token": "gru-old",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _install_patches(
        monkeypatch,
        pdir,
        backend_pid=4242,
        server_id="srv-role",
        server_token="tok-role",
        gru_token="gru-role",
    )

    registered: list[tuple[int, str, str]] = []

    def _register_role(port: int, role_name: str, *, server_id: str | None = None):
        registered.append((port, role_name, server_id or ""))
        return "ethics-token", []

    from minions.lifecycle import agent_registry

    monkeypatch.setattr(agent_registry, "register_project_role_agent", _register_role)

    proj_mod.project_revive(port, store=store)

    role = store.get_project(port).active_roles[0]  # type: ignore[union-attr]
    assert registered == [(port, "ethics", "srv-role")]
    assert role.name == "ethics"
    assert role.state == "sleeping"
    assert role.pid is None
    # Ethics is event-driven (mos_await_events), not a timer role.
    assert role.time_trigger_interval is None
    assert role.eacn_agent_token == "ethics-token"


def test_repair_gru_agent_works_after_dormant_revive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = 40103
    store, _entry, pdir = _seed_project(tmp_path, port=port)
    _install_patches(
        monkeypatch,
        pdir,
        backend_pid=42,
        server_id="srv-rev",
        server_token="tok-rev",
        gru_token="gru-rev",
    )

    proj_mod.project_dormant(port, store=store)
    proj_mod.project_revive(port, store=store)

    # Probe returns an empty agent list → repair must register gru fresh.
    monkeypatch.setattr(
        proj_mod.eacn_client, "probe_backend", lambda port, timeout=3.0: {"agents": []}
    )

    result = proj_mod.project_repair_gru_agent(port, store=store)
    assert result["status"] == "registered"
    assert result["gru_agent_id"] == "gru"
    assert result["gru_agent_token"] == "gru-rev"

    # And once gru is registered, repair is idempotent.
    monkeypatch.setattr(
        proj_mod.eacn_client,
        "probe_backend",
        lambda port, timeout=3.0: {"agents": [{"agent_id": "gru"}]},
    )
    again = proj_mod.project_repair_gru_agent(port, store=store)
    assert again["status"] == "already"


def test_project_repair_registers_missing_role_agents_and_clears_stale_pids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = 40104
    store, _entry, pdir = _seed_project(tmp_path, port=port)
    role = RoleEntry(
        name="expert",
        state="active",
        pid=99999,
        eacn_agent_id="expert",
        eacn_agent_token="old-token",
    )
    store.update_project(port, active_roles=[role])
    _install_patches(
        monkeypatch,
        pdir,
        backend_pid=42,
        server_id="srv-repair",
        server_token="tok-repair",
        gru_token="gru-repair",
    )
    monkeypatch.setattr(
        proj_mod.eacn_client,
        "probe_backend",
        lambda port, timeout=3.0: {"health": True, "agents": [{"agent_id": "gru"}]},
    )
    monkeypatch.setattr(proj_mod, "_pid_alive", lambda pid: False)

    registered: list[tuple[int, str, str]] = []

    def _register_role(port: int, role_name: str, *, server_id: str | None = None):
        registered.append((port, role_name, server_id or ""))
        return "expert-new-token", []

    from minions.lifecycle import agent_registry

    monkeypatch.setattr(agent_registry, "register_project_role_agent", _register_role)

    result = proj_mod.project_repair_eacn_agents(port, store=store)

    assert result["status"] == "repaired"
    assert result["gru_status"] == "already"
    assert result["role_agents_registered"] == ["expert"]
    assert result["stale_pids_cleared"] == ["expert"]
    assert registered == [(port, "expert", "srv-abc")]
    repaired_role = store.get_project(port).active_roles[0]  # type: ignore[union-attr]
    assert repaired_role.pid is None
    assert repaired_role.eacn_agent_token == "expert-new-token"


def test_project_repair_is_already_when_gru_and_roles_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = 40105
    store, _entry, pdir = _seed_project(tmp_path, port=port)
    role = RoleEntry(name="expert", state="active", eacn_agent_id="expert")
    store.update_project(port, active_roles=[role])
    _install_patches(
        monkeypatch,
        pdir,
        backend_pid=42,
        server_id="srv-repair",
        server_token="tok-repair",
        gru_token="gru-repair",
    )
    monkeypatch.setattr(
        proj_mod.eacn_client,
        "probe_backend",
        lambda port, timeout=3.0: {
            "health": True,
            "agents": [{"agent_id": "gru"}, {"agent_id": "expert"}],
        },
    )

    result = proj_mod.project_repair_eacn_agents(port, store=store)

    assert result["status"] == "already"
    assert result["gru_status"] == "already"
    assert result["role_agents_registered"] == []
    assert result["role_agents_already"] == ["expert"]


def test_project_repair_refreshes_missing_server_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_git_operations
) -> None:
    port = 40106
    store, _entry, pdir = _seed_project(tmp_path, port=port)
    _install_patches(
        monkeypatch,
        pdir,
        backend_pid=42,
        server_id="srv-new",
        server_token="tok-new",
        gru_token="gru-new",
    )
    monkeypatch.setattr(proj_mod.eacn_client, "get_server_card", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        proj_mod.eacn_client,
        "probe_backend",
        lambda port, timeout=3.0: {"health": True, "agents": []},
    )
    monkeypatch.setattr(
        proj_mod.eacn_client,
        "register_server",
        lambda port, **kwargs: ("srv-new", "tok-new"),
    )
    monkeypatch.setattr(
        proj_mod.eacn_client,
        "register_agent",
        lambda port, agent_id, **kwargs: ("gru-new", []),
    )

    result = proj_mod.project_repair_eacn_agents(port, store=store)

    assert result["status"] == "repaired"
    assert result["gru_status"] == "registered"
    meta = json.loads((pdir / "meta.json").read_text(encoding="utf-8"))
    assert meta["eacn3_server_id"] == "srv-new"
    assert meta["eacn3_server_token"] == "tok-new"
    assert meta["gru_agent_token"] == "gru-new"


def test_dormant_kills_role_tmux_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """project_dormant must kill every active role's tmux session before
    stopping the backend; otherwise resident claude processes keep polling
    a dead server."""
    port = 40114
    store, _entry, pdir = _seed_project(tmp_path, port=port)
    expert = RoleEntry(name="expert", state="active", eacn_agent_id="expert")
    ethics = RoleEntry(name="ethics", state="active", eacn_agent_id="ethics")
    store.update_project(port, active_roles=[expert, ethics])
    _install_patches(
        monkeypatch,
        pdir,
        backend_pid=12345,
        server_id="srv-x",
        server_token="srv-tok",
        gru_token="gru-tok",
    )

    killed: list[tuple[int, str]] = []

    from minions.lifecycle import role_launcher

    monkeypatch.setattr(
        role_launcher,
        "kill_session",
        lambda port_, role_name: killed.append((port_, role_name)) or True,
    )

    proj_mod.project_dormant(port, store=store)

    assert (port, "expert") in killed
    assert (port, "ethics") in killed
    assert len(killed) == 2


def test_revive_relaunches_roles_cold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_git_operations,
) -> None:
    """project_revive must call launch_role_process(..., resume=False) for
    every restored role. Resuming would reset Claude Code's prompt cache and
    replay the prior conversation as fresh uncached input; cold-starting and
    rebuilding context from Draft is strictly cheaper."""
    port = 40115
    store, entry, pdir = _seed_project(tmp_path, port=port)
    role = RoleEntry(name="expert", state="dismissed", eacn_agent_id="expert")
    store.update_project(port, status="dormant", dormant_at="x", active_roles=[role])
    dormant = entry.model_copy(
        update={"status": "dormant", "dormant_at": "x", "active_roles": [role]}
    )
    (pdir / "meta.json").write_text(
        json.dumps(
            {
                **dormant.model_dump(),
                "backend_pid": 111,
                "eacn3_server_id": "srv-old",
                "eacn3_server_token": "tok-old",
                "gru_agent_id": "gru",
                "gru_agent_token": "gru-old",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _install_patches(
        monkeypatch,
        pdir,
        backend_pid=22222,
        server_id="srv-new",
        server_token="tok-new",
        gru_token="gru-new",
    )

    launched: list[dict[str, object]] = []

    from minions.lifecycle import role_launcher

    def _fake_launch(role_entry, project_port, *, cfg=None, resume=False):
        launched.append(
            {
                "role": role_entry.name,
                "port": project_port,
                "resume": resume,
            }
        )
        return {
            "session_name": f"mos-{project_port}-{role_entry.name}",
            "started": True,
            "resumed": resume,
        }

    monkeypatch.setattr(role_launcher, "launch_role_process", _fake_launch)

    proj_mod.project_revive(port, store=store)

    assert launched == [{"role": "expert", "port": port, "resume": False}]
    role_after = store.get_project(port).active_roles[0]  # type: ignore[union-attr]
    assert role_after.state == "sleeping"
