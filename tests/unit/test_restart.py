"""Unit tests for the restart primitives (mos restart / post-upgrade refresh).

These cover the logic added to apply a `mos upgrade` to already-running
processes: cold-restarting Role tmux sessions and the Gru monitor sidecar.
The tmux/process side effects are mocked so the tests stay hermetic.
"""

from __future__ import annotations

import pytest

from minions.errors import RoleError
from minions.lifecycle import restart as restart_mod
from minions.state.store import ProjectEntry, RoleEntry


def _project(port: int, roles: list[RoleEntry]) -> ProjectEntry:
    return ProjectEntry(
        port=port,
        real_name=f"proj-{port}",
        status="active",
        created="2026-05-29T00:00:00Z",
        active_roles=roles,
    )


class _FakeStore:
    """Minimal StateStore stand-in returning a fixed project."""

    def __init__(self, entry: ProjectEntry | None) -> None:
        self._entry = entry

    def get_project(self, port: int) -> ProjectEntry | None:
        if self._entry is not None and self._entry.port == port:
            return self._entry
        return None

    def list_projects(self, filter=None, *, status=None):
        return [self._entry] if self._entry is not None else []


@pytest.fixture
def patched_launcher(monkeypatch):
    """Patch the launcher primitives restart_role calls; record invocations."""
    calls = {"killed": [], "launched": [], "alive": {}}

    def _kill(port, role):
        calls["killed"].append((port, role))
        return True

    def _launch(role_entry, port, *, resume=False):
        calls["launched"].append((port, role_entry.name, resume))
        return {"session_name": f"mos-{port}-{role_entry.name}", "started": True}

    def _alive(port, role):
        # Default: every role is considered alive unless a test overrides.
        return calls["alive"].get((port, role), True)

    monkeypatch.setattr(restart_mod.time, "sleep", lambda *_a, **_k: None)
    # restart_role imports these lazily from role_launcher; patch at source.
    import minions.lifecycle.role_launcher as rl

    monkeypatch.setattr(rl, "kill_session", _kill)
    monkeypatch.setattr(rl, "launch_role_process", _launch)
    monkeypatch.setattr(rl, "session_alive", _alive)
    return calls


class TestRestartRole:
    def test_cold_restart_uses_resume_false(self, patched_launcher):
        entry = _project(40000, [RoleEntry(name="expert", state="active")])
        store = _FakeStore(entry)
        result = restart_mod.restart_role(40000, "expert", store=store)
        assert result["role"] == "expert"
        assert result["killed"] is True
        assert result["started"] is True
        # The launch must be a cold start (resume=False) so the new process
        # rebuilds context from the Draft rather than replaying cached history.
        assert patched_launcher["launched"] == [(40000, "expert", False)]

    def test_unknown_project_raises(self, patched_launcher):
        store = _FakeStore(None)
        with pytest.raises(RoleError):
            restart_mod.restart_role(99999, "expert", store=store)

    def test_unknown_role_raises(self, patched_launcher):
        entry = _project(40000, [RoleEntry(name="expert", state="active")])
        store = _FakeStore(entry)
        with pytest.raises(RoleError):
            restart_mod.restart_role(40000, "ethics", store=store)

    def test_dismissed_role_refused(self, patched_launcher):
        entry = _project(40000, [RoleEntry(name="expert", state="dismissed")])
        store = _FakeStore(entry)
        with pytest.raises(RoleError):
            restart_mod.restart_role(40000, "expert", store=store)
        # No launch attempted for a dismissed role.
        assert patched_launcher["launched"] == []


class TestRestartProjectRoles:
    def test_restarts_only_active_roles(self, patched_launcher):
        entry = _project(
            40000,
            [
                RoleEntry(name="expert", state="active"),
                RoleEntry(name="ethics", state="active"),
                RoleEntry(name="expert-peer", state="dismissed"),
            ],
        )
        store = _FakeStore(entry)
        result = restart_mod.restart_project_roles(40000, store=store)
        restarted_names = {r["role"] for r in result["restarted"]}
        assert restarted_names == {"expert", "ethics"}
        assert result["skipped"] == ["expert-peer (dismissed)"]
        assert result["failed"] == []

    def test_named_subset(self, patched_launcher):
        entry = _project(
            40000,
            [
                RoleEntry(name="expert", state="active"),
                RoleEntry(name="ethics", state="active"),
            ],
        )
        store = _FakeStore(entry)
        result = restart_mod.restart_project_roles(40000, roles=["expert"], store=store)
        assert {r["role"] for r in result["restarted"]} == {"expert"}

    def test_only_live_roles_recycled(self, patched_launcher):
        """A stale `active` entry with no tmux session must NOT be launched.

        This is the safety property that makes `mos restart --all` safe against
        the hundreds of stale active registry entries a host accumulates.
        """
        entry = _project(
            40000,
            [
                RoleEntry(name="expert", state="active"),
                RoleEntry(name="ethics", state="active"),
            ],
        )
        store = _FakeStore(entry)
        # ethics is NOT running; expert is.
        patched_launcher["alive"][(40000, "ethics")] = False
        result = restart_mod.restart_project_roles(40000, store=store)  # only_if_alive default True
        assert {r["role"] for r in result["restarted"]} == {"expert"}
        assert any("ethics" in s for s in result["skipped"])
        # ethics must never have been launched.
        launched_names = {name for (_p, name, _r) in patched_launcher["launched"]}
        assert launched_names == {"expert"}

    def test_one_failure_does_not_abort_rest(self, patched_launcher, monkeypatch):
        entry = _project(
            40000,
            [
                RoleEntry(name="expert", state="active"),
                RoleEntry(name="ethics", state="active"),
            ],
        )
        store = _FakeStore(entry)
        import minions.lifecycle.role_launcher as rl

        def _flaky_launch(role_entry, port, *, resume=False):
            if role_entry.name == "expert":
                raise RuntimeError("boom")
            return {"session_name": f"mos-{port}-{role_entry.name}", "started": True}

        monkeypatch.setattr(rl, "launch_role_process", _flaky_launch)
        result = restart_mod.restart_project_roles(40000, store=store)
        assert {r["role"] for r in result["restarted"]} == {"ethics"}
        assert [f["role"] for f in result["failed"]] == ["expert"]


class TestGruMonitorStatus:
    def test_reports_not_running_when_pid_file_absent(self, monkeypatch, tmp_path):
        monkeypatch.setattr(restart_mod, "STATE_DIR", tmp_path)
        status = restart_mod.gru_monitor_status()
        assert status["running"] is False
        assert status["pid"] is None

    def test_reports_not_running_for_dead_pid(self, monkeypatch, tmp_path):
        monkeypatch.setattr(restart_mod, "STATE_DIR", tmp_path)
        # A PID that is almost certainly not alive.
        (tmp_path / "gru-monitor.pid").write_text("2147480000")
        (tmp_path / "gru-monitor.host").write_text("claude")
        status = restart_mod.gru_monitor_status()
        assert status["running"] is False
