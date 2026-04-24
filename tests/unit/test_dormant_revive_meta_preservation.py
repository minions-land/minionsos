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
from minions.state.store import ProjectEntry, StateStore


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
    monkeypatch.setattr(proj_mod, "project_workspace", lambda p: pdir / "workspace")
    monkeypatch.setattr(proj_mod, "project_eacn_db", lambda p: pdir / "eacn3_data" / "eacn3.db")
    monkeypatch.setattr(proj_mod, "project_backend_log", lambda p: pdir / "logs" / "backend.log")

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

    def _fake_register_agent(**kwargs: Any) -> tuple[str, list[str]]:
        return gru_token, []

    monkeypatch.setattr(proj_mod.eacn_client, "register_agent", _fake_register_agent)


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
