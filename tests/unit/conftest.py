"""Unit-test-only fixtures.

Unit tests must be hermetic: no real ``claude`` subprocess, no real ``tmux``
session, no outbound HTTP. Integration / smoke tests opt into the real
launcher under ``tests/integration/`` and ``tests/smoke/``.
"""

from __future__ import annotations

import importlib
import os
import subprocess
from typing import Any

import pytest


class HermeticityViolation(AssertionError):
    """A unit test attempted to spawn ``claude`` or create a ``tmux`` session.

    Unit tests must stay hermetic so they pass on contributor laptops, in
    CI, and on machines without a configured ``ANTHROPIC_BASE_URL`` or
    installed ``claude`` CLI. If you actually need the real launcher, move
    the test to ``tests/integration/`` or ``tests/smoke/``.
    """


_BANNED_BINARIES = {"claude"}


def _is_banned_subprocess(argv: object) -> str | None:
    """Return a violation reason, or ``None`` if the call is allowed.

    Allowed: anything that isn't ``claude`` and isn't ``tmux new-session``.
    The unit-test suite legitimately invokes ``git``, ``ruff``, ``python``,
    etc. and the test conftest itself runs ``tmux ls`` / ``tmux
    kill-session`` for cleanup — those must continue to work.
    """
    if isinstance(argv, str):
        head, *rest = argv.split()
    elif isinstance(argv, (list, tuple)) and argv:
        head = str(argv[0])
        rest = [str(a) for a in argv[1:]]
    else:
        return None
    basename = os.path.basename(head)
    if basename in _BANNED_BINARIES:
        return f"unit test attempted to spawn {basename!r} subprocess"
    if basename == "tmux":
        # Block only session-creating verbs. ``tmux ls`` / ``kill-session``
        # / ``has-session`` are fine — they read or clean up state.
        for arg in rest:
            if arg.startswith("-"):
                continue
            if arg in {"new-session", "new"}:
                return "unit test attempted to create a new tmux session"
            break
    return None


@pytest.fixture(autouse=True)
def _forbid_real_subprocess_leaks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hard-fail any unit test that tries to spawn ``claude`` or a tmux session.

    Pairs with :func:`_stub_launch_role_process`: the stub plugs the known
    leak path, this guard catches new leaks the moment they appear instead
    of letting them burn API credits silently.
    """
    real_popen = subprocess.Popen
    real_run = subprocess.run

    class GuardedPopen:
        @classmethod
        def __class_getitem__(cls, item: Any) -> Any:
            return cls

        def __new__(cls, argv, *args, **kwargs):  # type: ignore[no-untyped-def]
            reason = _is_banned_subprocess(argv)
            if reason:
                raise HermeticityViolation(f"{reason}: argv={argv!r}")
            return real_popen(argv, *args, **kwargs)

    def guarded_run(argv, *args, **kwargs):  # type: ignore[no-untyped-def]
        reason = _is_banned_subprocess(argv)
        if reason:
            raise HermeticityViolation(f"{reason}: argv={argv!r}")
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", GuardedPopen)
    monkeypatch.setattr(subprocess, "run", guarded_run)


@pytest.fixture(autouse=True)
def _stub_launch_role_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Replace ``launch_role_process`` with a noop that mimics its return shape.

    Several lifecycle entrypoints (``project_create``, ``project_revive``,
    ``mos_spawn_role``) transitively call ``launch_role_process``, which in
    turn spawns a real ``claude`` CLI under ``tmux`` against whatever
    ``ANTHROPIC_BASE_URL`` the dev shell exports. Unit tests that exercise
    these entrypoints must never reach the real subprocess — they should
    test the surrounding Python logic, not the launcher itself. Smoke /
    integration tests that genuinely need launcher behaviour live elsewhere
    and stub the spawn primitive (``_spawn_tmux``) directly.

    A test can override this default by re-patching ``launch_role_process``
    inside its body — the later ``monkeypatch.setattr`` wins.
    """
    from minions.lifecycle import role_launcher

    fake_root = tmp_path_factory.mktemp("role-launcher-noop")

    def fake_launch_role_process(
        role_entry: Any,
        project_port: int,
        *,
        cfg: Any | None = None,
        resume: bool = False,
    ) -> dict[str, object]:
        role_name = getattr(role_entry, "name", "role")
        name = f"mos-{project_port}-{role_name}"
        log_path = fake_root / f"p{project_port}" / f"role-{role_name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.touch()
        cwd = fake_root / f"p{project_port}" / role_name
        cwd.mkdir(parents=True, exist_ok=True)
        return {
            "session_name": name,
            "started": True,
            "resumed": bool(resume),
            "cwd": str(cwd),
            "log_path": str(log_path),
            "attach_cmd": ["tmux", "attach", "-t", name],
        }

    monkeypatch.setattr(role_launcher, "launch_role_process", fake_launch_role_process)

    # Some call sites import the symbol directly into another module's
    # namespace at import time (e.g. ``from .role_launcher import
    # launch_role_process``). Patch those re-exports too so the stub takes
    # effect regardless of which name was bound.
    for module_name in (
        "minions.lifecycle.project",
        "minions.lifecycle.role",
        "minions.gru.loop",
    ):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        if hasattr(module, "launch_role_process"):
            monkeypatch.setattr(
                module, "launch_role_process", fake_launch_role_process, raising=False
            )
