"""Hermetic Role process isolation.

Two opt-in tiers, both off by default to keep this branch safe to merge while
coworkers iterate on the rest of the system.

Tier 1 — ``MINIONS_ROLE_HERMETIC_CWD=1``: launch the Role's ``claude`` from a
stable per-(project, role) directory under ``~/.minionsos/role-cwd/`` instead of
the worktree. Stops Claude Code's CLAUDE.md walk before it reaches
``MinionsOS/CLAUDE.md`` or ``minions/CLAUDE.md`` (both dev-view files) and
``~/CLAUDE.md`` (host operator view). The worktree, project shared tree,
``MINIONS_ROOT``, and ``MANUAL`` are added back via ``--add-dir`` so the Role
keeps full read/write/edit access.

Tier 2 — ``MINIONS_ROLE_HERMETIC_HOME=1`` (requires Tier 1): also set ``HOME``
to a per-(project, role) fake home so host-level personal Claude instructions
and skills are not loaded. Pre-flight
refuses to enable Tier 2 without ``ANTHROPIC_AUTH_TOKEN`` /
``ANTHROPIC_API_KEY`` because changing ``HOME`` cuts the macOS-keychain auth
path that a stock ``claude`` CLI otherwise uses.

Cache contract: hermetic paths are stable across process restarts. The cwd is
part of Claude Code's dynamic system prompt, so a per-launch unique path would
break the prompt cache on every respawn. Embedding only ``port`` and
``role`` keeps the path byte-identical for repeated launches of the same Role,
preserving prompt-cache reuse across watchdog restarts and revives.
"""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Mapping
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_HERMETIC_CWD = "MINIONS_ROLE_HERMETIC_CWD"
ENV_HERMETIC_HOME = "MINIONS_ROLE_HERMETIC_HOME"

# Stable host-level base dir. Outside MinionsOS so Claude Code's CLAUDE.md
# walk from cwd never reaches a MinionsOS dev-view file.
_HERMETIC_BASE = Path.home() / ".minionsos" / "role-cwd"

# The seeded CLAUDE.md inside a hermetic cwd is intentionally a tiny stub
# pointing the Role at the project narrative (loaded into context separately
# via the role-specific contract block). Keeping it small means cwd-walk
# discovery costs near zero tokens.
_CWD_CLAUDE_MD_STUB = """\
# Role-process working directory

This is a hermetic working directory for one MinionsOS Role process. The
project narrative, common contract, and role-specific contract are loaded
through ``--append-system-prompt`` and the first user message — not through
this file.

Real worktree, project shared tree, MinionsOS code, and MANUAL are reachable
via ``--add-dir``. Use ``$MINIONS_WORKSPACE`` to address your worktree
explicitly (e.g. ``git -C $MINIONS_WORKSPACE add ...``); plain ``git`` from
this directory is not inside any worktree.
"""


def hermetic_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Whether Tier 1 (hermetic cwd) is requested."""
    src = env if env is not None else os.environ
    return src.get(ENV_HERMETIC_CWD, "0") == "1"


def hermetic_home_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Whether Tier 2 (hermetic HOME) is requested. Implies Tier 1."""
    src = env if env is not None else os.environ
    return src.get(ENV_HERMETIC_HOME, "0") == "1" and hermetic_enabled(src)


def hermetic_cwd_path(project_port: int, role_name: str) -> Path:
    """Stable per-(project, role) hermetic working directory.

    The path is restart-stable on purpose: cwd lives in Claude Code's dynamic
    system prompt, and a path that changes per launch would break the prompt
    cache on every Role respawn. Watchdog restarts and ``project_revive``
    therefore reuse the same path and inherit warm cache.
    """
    return _HERMETIC_BASE / f"project_{project_port}" / role_name


def fake_home_path(project_port: int, role_name: str) -> Path:
    """Stable per-(project, role) fake HOME for Tier 2."""
    return hermetic_cwd_path(project_port, role_name) / ".fake-home"


def prepare_hermetic_cwd(project_port: int, role_name: str) -> Path:
    """Create the hermetic cwd if missing and seed its CLAUDE.md stub.

    Idempotent: safe to call on every launch. The seeded CLAUDE.md is
    overwritten only if its content drifts from the canonical stub, so a
    user editing it manually for debugging is preserved across launches
    only if they change content (warning logged).
    """
    cwd = hermetic_cwd_path(project_port, role_name)
    cwd.mkdir(parents=True, exist_ok=True)
    claude_md = cwd / "CLAUDE.md"
    if not claude_md.exists():
        claude_md.write_text(_CWD_CLAUDE_MD_STUB, encoding="utf-8")
    elif claude_md.read_text(encoding="utf-8") != _CWD_CLAUDE_MD_STUB:
        logger.debug(
            "hermetic cwd CLAUDE.md at %s diverges from canonical stub; "
            "leaving operator edit in place",
            claude_md,
        )
    return cwd


def cleanup_hermetic_cwd(project_port: int, role_name: str | None = None) -> list[Path]:
    """Remove hermetic cwd(s) for one role or the whole project.

    Called from ``project_close``. Returns the paths actually removed, in
    case a caller wants to log them.
    """
    base = _HERMETIC_BASE / f"project_{project_port}"
    removed: list[Path] = []
    if role_name is None:
        if base.exists():
            shutil.rmtree(base, ignore_errors=True)
            removed.append(base)
        return removed
    target = base / role_name
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
        removed.append(target)
    return removed


class HermeticHomeAuthError(RuntimeError):
    """Raised when Tier 2 is requested but no env-based auth is available.

    Tier 2 sets HOME to a per-Role fake directory; a stock ``claude`` CLI
    otherwise reads OAuth from macOS keychain via the operator's real HOME.
    With HOME swapped, the only auth path left is the env var.
    """


_AUTH_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
)


def assert_tier2_auth_available(env: dict[str, str] | None = None) -> None:
    """Pre-flight: refuse Tier 2 without env-based auth.

    Avoids a confusing post-launch failure where the role process boots,
    can't reach macOS keychain (HOME differs from operator HOME), and dies
    with an opaque "Invalid API key" error.
    """
    src = env if env is not None else os.environ
    for key in _AUTH_ENV_KEYS:
        if src.get(key):
            return
    raise HermeticHomeAuthError(
        f"{ENV_HERMETIC_HOME}=1 requires env-based auth — none of "
        f"{', '.join(_AUTH_ENV_KEYS)} is set. With HOME swapped to the "
        "fake home, the stock claude CLI cannot reach macOS keychain. "
        "Either export ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) "
        f"before launching, or unset {ENV_HERMETIC_HOME}."
    )


def prepare_fake_home(project_port: int, role_name: str) -> Path:
    """Build the per-(project, role) fake HOME for Tier 2.

    Layout::

        ~/.minionsos/role-cwd/project_<port>/<role>/.fake-home/
        └── .claude/                    # empty by default; settings flow
                                        # through env + --settings/--mcp-config

    The fake home deliberately ships *no* ``CLAUDE.md`` and no ``skills/``.
    User-level operator skills (``minionsos-push``, ``dev-log``, etc.) live in
    the operator's host-level personal skills and have triggers that target
    operator workflows, not Role workflows. Excluding them is part of the
    point of Tier 2.
    """
    home = fake_home_path(project_port, role_name)
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    return home


def hermetic_add_dirs(
    *,
    workspace: Path,
    workspace_main: Path,
    workspace_shared: Path,
    minions_root: Path,
) -> list[Path]:
    """Build the ``--add-dir`` list for a hermetic-mode Role.

    Order matters only for human readability — Claude Code unions the set.

    * ``workspace``: the role's own branch worktree (writable by the Role).
    * ``workspace_main`` / ``workspace_shared``: peer worktrees the Role
      reads cross-role.
    * ``minions_root``: MinionsOS source tree — needed for ``MANUAL/``,
      ``minions/roles/``, role skills, hook scripts.

    Duplicates are removed; non-existent paths are dropped (safer than
    passing a missing path on the CLI).
    """
    candidates = [workspace, workspace_main, workspace_shared, minions_root]
    seen: set[Path] = set()
    out: list[Path] = []
    for raw in candidates:
        if raw is None:
            continue
        p = Path(raw)
        if not p.exists():
            continue
        # resolve() so equality on symlinks is correct.
        resolved = p.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(p)
    return out
