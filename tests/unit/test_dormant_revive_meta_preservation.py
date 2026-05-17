"""Regression tests: project_dormant / project_revive must not drop extra
runtime fields (backend_pid, eacn3_server_id, eacn3_server_token,
gru_agent_id, gru_agent_token, topic_doc, template_dir) from meta.json.

See bug: _write_meta previously used ProjectEntry.model_dump_json() which,
although the model has ``extra="allow"``, was never populated with runtime
extras — those lived only in the on-disk meta.json. The dormant path
overwrote the file with the store entry (losing extras), and the revive
path depended on reading the now-missing fields, so project_repair_gru_agent
raised ProjectError after any dormant→revive cycle.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from minions.lifecycle import project as proj_mod
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

    monkeypatch.setattr(proj_mod, "_start_backend", lambda port: _FakeProc(backend_pid))
    monkeypatch.setattr(proj_mod, "_wait_for_health", lambda port, timeout=None: None)
    monkeypatch.setattr(proj_mod, "_stop_backend", lambda port, pid=None: None)
    monkeypatch.setattr(proj_mod, "_git_tag", lambda port, tag: None)
    monkeypatch.setattr(proj_mod, "_register_server", lambda port: (server_id, server_token))
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
    pdir = tmp_path / f"project_{port}"
    (pdir / "logs").mkdir(parents=True, exist_ok=True)
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

    proj_mod.project_revive(port, store=store)

    meta = json.loads((pdir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "active"
    assert meta["backend_pid"] == 777
    assert meta["eacn3_server_id"] == "srv-adopted"


def test_revive_restores_noter_from_meta_and_repairs_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = 40113
    store, entry, pdir = _seed_project(tmp_path, port=port)
    store.update_project(port, status="dormant", dormant_at="x", active_roles=[])
    meta_role = RoleEntry(
        name="noter",
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
        return "noter-token", []

    from minions.lifecycle import agent_registry

    monkeypatch.setattr(agent_registry, "register_project_role_agent", _register_role)

    proj_mod.project_revive(port, store=store)

    role = store.get_project(port).active_roles[0]  # type: ignore[union-attr]
    assert registered == [(port, "noter", "srv-role")]
    assert role.name == "noter"
    assert role.state == "sleeping"
    assert role.pid is None
    assert role.time_trigger_interval == "30m"
    assert role.eacn_agent_token == "noter-token"


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
        name="coder",
        state="active",
        pid=99999,
        eacn_agent_id="coder",
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
        return "coder-new-token", []

    from minions.lifecycle import agent_registry

    monkeypatch.setattr(agent_registry, "register_project_role_agent", _register_role)

    result = proj_mod.project_repair_eacn_agents(port, store=store)

    assert result["status"] == "repaired"
    assert result["gru_status"] == "already"
    assert result["role_agents_registered"] == ["coder"]
    assert result["stale_pids_cleared"] == ["coder"]
    assert registered == [(port, "coder", "srv-abc")]
    repaired_role = store.get_project(port).active_roles[0]  # type: ignore[union-attr]
    assert repaired_role.pid is None
    assert repaired_role.eacn_agent_token == "coder-new-token"


def test_project_repair_is_already_when_gru_and_roles_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = 40105
    store, _entry, pdir = _seed_project(tmp_path, port=port)
    role = RoleEntry(name="coder", state="active", eacn_agent_id="coder")
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
            "agents": [{"agent_id": "gru"}, {"agent_id": "coder"}],
        },
    )

    result = proj_mod.project_repair_eacn_agents(port, store=store)

    assert result["status"] == "already"
    assert result["gru_status"] == "already"
    assert result["role_agents_registered"] == []
    assert result["role_agents_already"] == ["coder"]


def test_project_repair_refreshes_missing_server_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
    coder = RoleEntry(name="coder", state="active", eacn_agent_id="coder")
    writer = RoleEntry(name="writer", state="active", eacn_agent_id="writer")
    store.update_project(port, active_roles=[coder, writer])
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

    assert (port, "coder") in killed
    assert (port, "writer") in killed
    assert len(killed) == 2


def test_revive_relaunches_roles_with_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """project_revive must call launch_role_process(..., resume=True) for
    every restored role so prior conversation history is reattached."""
    port = 40115
    store, entry, pdir = _seed_project(tmp_path, port=port)
    role = RoleEntry(name="coder", state="dismissed", eacn_agent_id="coder")
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

    assert launched == [{"role": "coder", "port": port, "resume": True}]
    role_after = store.get_project(port).active_roles[0]  # type: ignore[union-attr]
    assert role_after.state == "sleeping"
