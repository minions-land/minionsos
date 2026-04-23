"""Unit tests for minions.state.state_store (StateStore).

Tests: add/get/list projects, retire_port, atomic write, concurrent write safety.
Builder A owns the implementation; we use pytest.importorskip so these tests
are skipped gracefully until the module exists.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

state_store = pytest.importorskip("minions.state.state_store")
StateStore = state_store.StateStore


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path: Path) -> StateStore:
    """Fresh StateStore backed by a temp directory."""
    return StateStore(root=tmp_path)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _project(port: int, name: str = "Test Project", status: str = "active") -> dict:
    return {
        "port": port,
        "real_name": name,
        "status": status,
        "created": "2026-01-01T00:00:00Z",
        "dormant_at": None,
        "closed_at": None,
        "venue": None,
        "upstream_branch": "main",
        "current_branch": f"minionsos/project-{port}",
        "active_roles": [],
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestAddGet:
    def test_add_and_get(self, store: StateStore) -> None:
        p = _project(37596)
        store.add_project(p)
        result = store.get_project(37596)
        assert result is not None
        assert result["port"] == 37596
        assert result["real_name"] == "Test Project"

    def test_get_missing_returns_none(self, store: StateStore) -> None:
        assert store.get_project(99999) is None

    def test_add_duplicate_raises(self, store: StateStore) -> None:
        store.add_project(_project(37596))
        with pytest.raises(Exception):
            store.add_project(_project(37596))


class TestList:
    def test_list_all(self, store: StateStore) -> None:
        store.add_project(_project(37596, status="active"))
        store.add_project(_project(37597, status="dormant"))
        store.add_project(_project(37598, status="closed"))
        projects = store.list_projects()
        assert len(projects) == 3

    def test_list_filter_active(self, store: StateStore) -> None:
        store.add_project(_project(37596, status="active"))
        store.add_project(_project(37597, status="dormant"))
        active = store.list_projects(status="active")
        assert len(active) == 1
        assert active[0]["port"] == 37596

    def test_list_filter_dormant(self, store: StateStore) -> None:
        store.add_project(_project(37596, status="active"))
        store.add_project(_project(37597, status="dormant"))
        dormant = store.list_projects(status="dormant")
        assert len(dormant) == 1
        assert dormant[0]["port"] == 37597

    def test_list_empty(self, store: StateStore) -> None:
        assert store.list_projects() == []


class TestRetirePort:
    def test_retire_port_prevents_reuse(self, store: StateStore) -> None:
        store.add_project(_project(37596))
        store.retire_port(37596)
        assert store.is_port_retired(37596)

    def test_non_retired_port_not_flagged(self, store: StateStore) -> None:
        assert not store.is_port_retired(37596)

    def test_retire_idempotent(self, store: StateStore) -> None:
        store.retire_port(37596)
        store.retire_port(37596)  # should not raise
        assert store.is_port_retired(37596)

    def test_retired_ports_persisted(self, store: StateStore, tmp_path: Path) -> None:
        store.retire_port(37596)
        # Re-open the same store from disk
        store2 = StateStore(root=tmp_path)
        assert store2.is_port_retired(37596)


class TestAtomicWrite:
    def test_state_file_is_valid_json_after_write(self, store: StateStore, tmp_path: Path) -> None:
        store.add_project(_project(37596))
        state_file = tmp_path / "projects.json"
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert "projects" in data

    def test_no_tmp_file_left_behind(self, store: StateStore, tmp_path: Path) -> None:
        store.add_project(_project(37596))
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"Leftover tmp files: {tmp_files}"


class TestConcurrentWrites:
    def test_concurrent_add_no_data_loss(self, store: StateStore) -> None:
        """Multiple threads adding distinct projects must all persist."""
        ports = list(range(37596, 37616))  # 20 projects
        errors: list[Exception] = []

        def add(port: int) -> None:
            try:
                store.add_project(_project(port, name=f"Project-{port}"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=add, args=(p,)) for p in ports]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Errors during concurrent writes: {errors}"
        all_projects = store.list_projects()
        assert len(all_projects) == len(ports)
