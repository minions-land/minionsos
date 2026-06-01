"""Unit tests for _bootstrap_fixed_roles in project_create.

The function pre-spawns the profile-active subset of BOOTSTRAP_ROLES
(ethics) in parallel at project_create time so the live
Gru process does not have to issue a serial sequence of mos_spawn_role
MCP calls (~5 min of LLM deliberation for the scientific-paper profile).
The generalist Expert worker is bootstrapped on a separate path
(_bootstrap_generalist_expert via register_expert), not here.

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
    def test_scientific_paper_spawns_ethics(self) -> None:
        """Default profile pre-spawns the fixed role (ethics only).

        After the P3.5 Noter→Ethics merge, BOOTSTRAP_ROLES is ``{"ethics"}``.
        The generalist Expert is spawned separately via
        _bootstrap_generalist_expert (register_expert), so it must NOT
        appear in the fixed-role bootstrap wave even though the profile
        lists ``expert`` as active.
        """
        calls: list[str] = []

        def fake_register_role(*, project_port: int, role: str, store: object) -> dict:
            calls.append(role)
            return {"name": role}

        with patch("minions.lifecycle.role.register_role", side_effect=fake_register_role):
            results = project_mod._bootstrap_fixed_roles(
                port=37000,
                mission_profile=_profile(["gru", "ethics", "expert"]),
                store=object(),
            )

        # The single fixed role spawned exactly once. Expert is not a fixed
        # role — it goes through the generalist-expert path.
        assert sorted(calls) == ["ethics"]
        assert all(status == "ok" for _, status in results)
        assert {role for role, _ in results} == {"ethics"}

    def test_expert_excluded_from_fixed_bootstrap(self) -> None:
        """Expert is bootstrapped on a separate path — never in this wave.

        Even though the scientific-paper profile lists ``expert`` as
        active, the fixed-role bootstrap set is the literal
        ``BOOTSTRAP_ROLES = {"ethics"}`` defined in role.py. The
        generalist Expert is spawned via _bootstrap_generalist_expert
        (register_expert), so it must not appear in this fast-path wave.
        """
        calls: list[str] = []

        def fake_register_role(*, project_port: int, role: str, store: object) -> dict:
            calls.append(role)
            return {"name": role}

        with patch("minions.lifecycle.role.register_role", side_effect=fake_register_role):
            project_mod._bootstrap_fixed_roles(
                port=37002,
                mission_profile=_profile(["gru", "ethics", "expert"]),
                store=object(),
            )

        assert "expert" not in calls

    def test_per_role_failure_is_non_fatal(self) -> None:
        """A failing role spawn must not abort project_create.

        If register_role raises (e.g. EACN3 backend hiccup), the function
        records the error in the return value instead of propagating it;
        Gru's normal respawn path then handles the missing role.
        """

        def fake_register_role(*, project_port: int, role: str, store: object) -> dict:
            if role == "ethics":
                raise RuntimeError("EACN3 hiccup")
            return {"name": role}

        with patch("minions.lifecycle.role.register_role", side_effect=fake_register_role):
            results = project_mod._bootstrap_fixed_roles(
                port=37003,
                mission_profile=_profile(["gru", "ethics", "expert"]),
                store=object(),
            )

        result_map = dict(results)
        assert "EACN3 hiccup" in result_map["ethics"]

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

    def test_runs_on_thread_pool(self) -> None:
        """The fixed-role spawn runs through the thread-pool path.

        After the Noter→Ethics merge BOOTSTRAP_ROLES has a single member,
        so there is no longer a 2-wide concurrent wave to observe. We still
        verify the spawn is dispatched (not silently skipped) and completes
        quickly, guarding against an accidental serial-lock regression if
        the bootstrap set grows again.
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
            results = project_mod._bootstrap_fixed_roles(
                port=37005,
                mission_profile=_profile(["gru", "ethics", "expert"]),
                store=object(),
            )
            elapsed = time.monotonic() - t0

        # The single fixed role was dispatched and ran.
        assert max_active == 1, f"expected 1 concurrent spawn, saw {max_active}"
        assert {role for role, _ in results} == {"ethics"}
        # One spawn (~50ms) plus pool overhead; nowhere near a serial ceiling.
        assert elapsed < 0.09, f"unexpected slow bootstrap, elapsed={elapsed:.3f}s"


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
        # update this test. After the P3.5 Noter→Ethics merge the only
        # fixed bootstrap role is Ethics (merged curator + auditor).
        assert BOOTSTRAP_ROLES == {"ethics"}

        # Confirm the bootstrap function actually references it (rather
        # than e.g. hard-coding a list).
        import inspect

        src = inspect.getsource(project_mod._bootstrap_fixed_roles)
        assert "BOOTSTRAP_ROLES" in src, (
            "_bootstrap_fixed_roles must read BOOTSTRAP_ROLES so future "
            "additions to the bootstrap set automatically take effect."
        )
