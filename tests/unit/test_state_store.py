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

state_store = pytest.importorskip("minions.state.store")
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
        assert result.port == 37596
        assert result.real_name == "Test Project"

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
        assert active[0].port == 37596

    def test_list_filter_dormant(self, store: StateStore) -> None:
        store.add_project(_project(37596, status="active"))
        store.add_project(_project(37597, status="dormant"))
        dormant = store.list_projects(status="dormant")
        assert len(dormant) == 1
        assert dormant[0].port == 37597

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


class TestFindNextPort:
    def test_skips_existing_project_tree_on_disk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        projects_root = tmp_path / "projects"
        (projects_root / "project_37596" / "parent_repo.git").mkdir(parents=True)
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(projects_root))

        store = StateStore(root=tmp_path / "state")
        monkeypatch.setattr(store._allocator, "_is_free", lambda port: True)

        assert store.find_next_port() == 37597


class TestRemoveProject:
    def test_remove_existing_returns_true_and_drops_row(self, store: StateStore) -> None:
        store.add_project(_project(37596))
        assert store.remove_project(37596) is True
        assert store.get_project(37596) is None

    def test_remove_missing_returns_false(self, store: StateStore) -> None:
        assert store.remove_project(99999) is False

    def test_remove_retires_port_by_default(self, store: StateStore) -> None:
        store.add_project(_project(37596))
        store.remove_project(37596)
        assert store.is_port_retired(37596)

    def test_remove_can_skip_retirement(self, store: StateStore) -> None:
        store.add_project(_project(37596))
        store.remove_project(37596, retire=False)
        assert not store.is_port_retired(37596)

    def test_remove_leaves_other_rows_intact(self, store: StateStore) -> None:
        store.add_project(_project(37596))
        store.add_project(_project(37597))
        store.remove_project(37596)
        assert store.get_project(37596) is None
        assert store.get_project(37597) is not None

    def test_remove_persists_across_reopen(self, store: StateStore, tmp_path: Path) -> None:
        store.add_project(_project(37596))
        store.remove_project(37596)
        store2 = StateStore(root=tmp_path)
        assert store2.get_project(37596) is None
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


# ── New tests for P0 concurrency / corruption / atomic rename ────────────────

import multiprocessing as _mp  # noqa: E402
import os as _os  # noqa: E402
from unittest.mock import patch  # noqa: E402

from minions.errors import StateError  # noqa: E402


def _mp_worker(root_str: str, port: int) -> str:
    """Run in a subprocess: add one project. Returns '' on success or err repr."""
    from minions.state.store import StateStore as _SS

    try:
        s = _SS(root=Path(root_str))
        s.add_project(
            {
                "port": port,
                "real_name": f"Project-{port}",
                "status": "active",
                "created": "2026-01-01T00:00:00Z",
                "dormant_at": None,
                "closed_at": None,
                "venue": None,
                "upstream_branch": "main",
                "current_branch": f"minionsos/project-{port}",
                "active_roles": [],
            }
        )
        return ""
    except Exception as exc:  # pragma: no cover - surfaced via assertion
        return repr(exc)


class TestConcurrentProcesses:
    def test_multiprocess_add_no_torn_writes(self, tmp_path: Path) -> None:
        """N subprocesses each add a distinct project; all must persist intact."""
        ports = list(range(37596, 37596 + 16))
        ctx = _mp.get_context("spawn")
        with ctx.Pool(processes=8) as pool:
            errors = pool.starmap(_mp_worker, [(str(tmp_path), p) for p in ports])
        assert all(e == "" for e in errors), f"subprocess errors: {errors}"

        # File must be valid JSON and contain every port.
        raw = (tmp_path / "projects.json").read_text(encoding="utf-8")
        data = json.loads(raw)
        got = sorted(p["port"] for p in data["projects"])
        assert got == ports


class TestCorruptJson:
    def test_corrupt_projects_json_raises_stateerror(self, tmp_path: Path) -> None:
        (tmp_path / "projects.json").write_text("{not json", encoding="utf-8")
        store = StateStore(root=tmp_path)
        with pytest.raises(StateError):
            store.list_projects()


class TestAtomicRename:
    def test_write_uses_os_replace_on_tmp_in_same_dir(self, tmp_path: Path) -> None:
        store = StateStore(root=tmp_path)
        real_replace = _os.replace
        seen: list[tuple[str, str]] = []

        def spy(src, dst):  # type: ignore[no-untyped-def]
            seen.append((str(src), str(dst)))
            return real_replace(src, dst)

        with patch("minions.state.store.os.replace", side_effect=spy):
            store.add_project(_project(37596))

        assert seen, "os.replace was not called"
        src, dst = seen[-1]
        assert dst == str(tmp_path / "projects.json")
        assert Path(src).parent == tmp_path  # tmp must be in same dir for atomic rename
        assert src.endswith(".tmp")
        # And no tmp leftovers.
        assert list(tmp_path.glob("*.tmp")) == []


class TestLockfileSeparate:
    def test_lockfile_is_separate_stable_inode(self, tmp_path: Path) -> None:
        """Lockfile must not be the data file (inode must not change on replace)."""
        store = StateStore(root=tmp_path)
        store.add_project(_project(37596))
        lock = tmp_path / "projects.lock"
        assert lock.exists()
        inode_before = lock.stat().st_ino
        # Trigger another atomic replace on the data file.
        store.update_project(37596, real_name="Renamed")
        assert lock.stat().st_ino == inode_before
