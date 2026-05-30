"""Unit tests for _bootstrap_fixed_roles in project_create.

The function pre-spawns the profile-active subset of BOOTSTRAP_ROLES
(noter / coder / ethics) in parallel at project_create time so the live
Gru process does not have to issue a serial sequence of mos_spawn_role
MCP calls (~5 min of LLM deliberation for the scientific-paper profile).

These tests use a stub `register_role` so they are tmux/EACN3-free.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from minions.lifecycle import project as project_mod


def _profile(roles_active: list[str]) -> SimpleNamespace:
    """Return a minimal mission-profile-shaped object."""
    return SimpleNamespace(roles_active=tuple(roles_active))


class TestBootstrapFixedRoles:
    def test_scientific_paper_spawns_noter_coder_ethics(self) -> None:
        """Default profile should pre-spawn all three fixed roles."""
        calls: list[str] = []

        def fake_register_role(*, project_port: int, role: str, store: object) -> dict:
            calls.append(role)
            return {"name": role}

        with patch("minions.lifecycle.role.register_role", side_effect=fake_register_role):
            results = project_mod._bootstrap_fixed_roles(
                port=37000,
                mission_profile=_profile(["gru", "noter", "coder", "ethics"]),
                store=object(),
            )

        # Each fixed role spawned exactly once, in parallel.
        assert sorted(calls) == ["coder", "ethics", "noter"]
        assert all(status == "ok" for _, status in results)
        assert {role for role, _ in results} == {"coder", "ethics", "noter"}

    def test_hle_answer_skips_noter_and_ethics(self) -> None:
        """hle-answer profile only has coder among the fixed roles."""
        calls: list[str] = []

        def fake_register_role(*, project_port: int, role: str, store: object) -> dict:
            calls.append(role)
            return {"name": role}

        with patch("minions.lifecycle.role.register_role", side_effect=fake_register_role):
            results = project_mod._bootstrap_fixed_roles(
                port=37001,
                mission_profile=_profile(["gru", "expert", "coder"]),
                store=object(),
            )

        assert calls == ["coder"]
        assert results == [("coder", "ok")]

    def test_writer_excluded_even_if_profile_active(self) -> None:
        """Writer is on-demand — never auto-spawned at project_create.

        Even if a profile lists ``writer`` as active, the bootstrap set
        is the literal ``BOOTSTRAP_ROLES = {"noter","coder","ethics"}``
        defined in role.py. A profile that wants Writer up immediately
        should rely on Gru's spawn path, not this fast-path.
        """
        calls: list[str] = []

        def fake_register_role(*, project_port: int, role: str, store: object) -> dict:
            calls.append(role)
            return {"name": role}

        with patch("minions.lifecycle.role.register_role", side_effect=fake_register_role):
            project_mod._bootstrap_fixed_roles(
                port=37002,
                mission_profile=_profile(["gru", "noter", "coder", "writer", "ethics"]),
                store=object(),
            )

        assert "writer" not in calls

    def test_per_role_failure_is_non_fatal(self) -> None:
        """A failing role spawn must not abort the others.

        If register_role raises for one role (e.g. EACN3 backend hiccup),
        the function records the error in the return value but keeps
        spawning the remaining roles. project_create then completes;
        Gru's normal respawn path handles the missing role.
        """
        succeeded: list[str] = []

        def fake_register_role(*, project_port: int, role: str, store: object) -> dict:
            if role == "coder":
                raise RuntimeError("EACN3 hiccup")
            succeeded.append(role)
            return {"name": role}

        with patch("minions.lifecycle.role.register_role", side_effect=fake_register_role):
            results = project_mod._bootstrap_fixed_roles(
                port=37003,
                mission_profile=_profile(["gru", "noter", "coder", "ethics"]),
                store=object(),
            )

        assert sorted(succeeded) == ["ethics", "noter"]
        result_map = dict(results)
        assert result_map["noter"] == "ok"
        assert result_map["ethics"] == "ok"
        assert "EACN3 hiccup" in result_map["coder"]

    def test_empty_intersection_short_circuits(self) -> None:
        """A profile with no fixed-role overlap returns immediately."""
        calls: list[str] = []

        def fake_register_role(*, project_port: int, role: str, store: object) -> dict:
            calls.append(role)
            return {"name": role}

        with patch("minions.lifecycle.role.register_role", side_effect=fake_register_role):
            results = project_mod._bootstrap_fixed_roles(
                port=37004,
                mission_profile=_profile(["gru", "expert"]),
                store=object(),
            )

        assert calls == []
        assert results == []

    def test_runs_in_parallel(self) -> None:
        """Three role spawns must overlap in time, not run serially.

        The whole point of this function is to collapse what was a
        ~5-minute serial Gru turn sequence into a ~30-60s parallel wave.
        Verify that the spawns actually run on a thread pool rather than
        accidentally serializing through some shared lock by checking
        that the wall-clock duration is closer to one spawn's latency
        than to three.
        """
        import threading
        import time

        active = 0
        max_active = 0
        lock = threading.Lock()

        def fake_register_role(*, project_port: int, role: str, store: object) -> dict:
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)  # simulate ~50ms per spawn
            with lock:
                active -= 1
            return {"name": role}

        with patch("minions.lifecycle.role.register_role", side_effect=fake_register_role):
            t0 = time.monotonic()
            project_mod._bootstrap_fixed_roles(
                port=37005,
                mission_profile=_profile(["gru", "noter", "coder", "ethics"]),
                store=object(),
            )
            elapsed = time.monotonic() - t0

        # All three must have been in flight at the same instant.
        assert max_active == 3, f"expected 3 concurrent spawns, saw {max_active}"
        # Wall-clock should be one spawn's latency (~50ms) plus pool
        # overhead, not 3× (which would be ~150ms+). 100ms is comfortably
        # below the serial ceiling and well above realistic CI noise.
        assert elapsed < 0.10, f"expected parallel speedup, elapsed={elapsed:.3f}s"


class TestBootstrapRolesConstant:
    def test_BOOTSTRAP_ROLES_is_imported_and_used(self) -> None:
        """Regression guard for the v15.50 fix: BOOTSTRAP_ROLES used to be
        defined in role.py but never imported anywhere — every role had
        to be spawned by Gru at runtime. _bootstrap_fixed_roles is the
        sole legitimate consumer; if a future refactor accidentally
        drops the import, project_create silently regresses to the
        ~5-minute Gru-deliberation cold-start.
        """
        from minions.lifecycle.role import BOOTSTRAP_ROLES

        # Sanity on the constant's shape; if these change deliberately,
        # update this test.
        assert BOOTSTRAP_ROLES == {"noter", "coder", "ethics"}

        # Confirm the bootstrap function actually references it (rather
        # than e.g. hard-coding a list).
        import inspect

        src = inspect.getsource(project_mod._bootstrap_fixed_roles)
        assert "BOOTSTRAP_ROLES" in src, (
            "_bootstrap_fixed_roles must read BOOTSTRAP_ROLES so future "
            "additions to the bootstrap set automatically take effect."
        )
