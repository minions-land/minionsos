"""Canonical path constants for MinionsOS.

All runtime code must import paths from here — never construct paths by
string concatenation or relative ``..`` traversal.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------

# This file lives at  minions/paths.py  inside the MinionsOS checkout.
# MINIONS_ROOT is the repo root (parent of the ``minions/`` package dir).
MINIONS_ROOT: Path = Path(__file__).parent.parent.resolve()

# Allow override via env var for testing / unusual layouts.
if _env_root := os.environ.get("MINIONS_ROOT"):
    MINIONS_ROOT = Path(_env_root).resolve()

# ---------------------------------------------------------------------------
# Package-internal directories
# ---------------------------------------------------------------------------

PACKAGE_DIR: Path = MINIONS_ROOT / "minions"
ROLES_DIR: Path = PACKAGE_DIR / "roles"
DOMAINS_DIR: Path = PACKAGE_DIR / "domains"
CONFIG_DIR: Path = PACKAGE_DIR / "config"
STATE_DIR: Path = PACKAGE_DIR / "state"
LOGS_DIR: Path = STATE_DIR / "logs"

# ---------------------------------------------------------------------------
# State files
# ---------------------------------------------------------------------------

PROJECTS_JSON: Path = STATE_DIR / "projects.json"
GRU_LOG: Path = LOGS_DIR / "gru.log"

# ---------------------------------------------------------------------------
# Per-project helpers
# ---------------------------------------------------------------------------


def _resolve_path_setting(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = MINIONS_ROOT / path
    return path.resolve()


def _safe_component(value: str) -> str:
    """Return a filesystem-safe path component."""
    cleaned = "".join(c if c.isalnum() or c in {"-", "_", "."} else "_" for c in value)
    return cleaned.strip("._") or "default"


def _gru_yaml_value(key: str) -> Any | None:
    path = CONFIG_DIR / "gru.yaml"
    if not path.exists():
        return None
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data.get(key)


def _configured_path(key: str, env_name: str) -> Path | None:
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return _resolve_path_setting(env_value)
    value = _gru_yaml_value(key)
    if isinstance(value, str) and value.strip():
        return _resolve_path_setting(value.strip())
    return None


def projects_root() -> Path:
    """Return the directory that contains ``project_<port>/`` trees."""
    return _configured_path("projects_root", "MINIONS_PROJECTS_ROOT") or MINIONS_ROOT.parent


def configured_project_parent_repo() -> Path | None:
    """Return the configured source git repo for project worktrees, if any."""
    return _configured_path("project_parent_repo", "MINIONS_PROJECT_PARENT_REPO")


def project_dir(port: int) -> Path:
    """Return the top-level directory for a project running on *port*.

    By default this is beside ``MINIONS_ROOT``. It can be overridden with
    ``MINIONS_PROJECTS_ROOT`` or ``gru.yaml:projects_root``.
    """
    return projects_root() / f"project_{port}"


def project_workspace_root(port: int) -> Path:
    """Return the branch-dir container for *port*.

    Layout (MinionsOS post-restructure):
        project_{port}/branches/
            main/        # Gru — the main branch checkout
            coder/       # one checkout per role, one-to-one with a git branch
            writer/
            ...
            shared/      # cross-role handoffs (not a branch)

    The historical name ``project_workspace_root`` is kept so older callers
    compile; new code should treat the returned directory as "branches".
    """
    return project_dir(port) / "branches"


def project_main_workspace(port: int) -> Path:
    """Return the main branch checkout (Gru's branch dir) for *port*."""
    return project_workspace_root(port) / "main"


def project_roles_workspace_dir(port: int) -> Path:
    """Return the branches container (flat layout: one dir per role)."""
    return project_workspace_root(port)


def project_shared_workspace(port: int) -> Path:
    """Return the shared cross-role handoff directory for *port*."""
    return project_workspace_root(port) / "shared"


def project_role_branch_leaf(role_name: str) -> str:
    """Return the leaf folder name under ``branches/`` for *role_name*.

    Gru lives on ``branches/main/``; every other role lives on
    ``branches/{role}/``.
    """
    if role_name == "gru":
        return "main"
    return _safe_component(role_name)


def project_role_workspace(port: int, role_name: str) -> Path:
    """Return the branch-dir (git worktree) for *role_name* in *port*.

    ``role_name == "gru"`` resolves to the main branch checkout; all other
    roles resolve to ``branches/<role>/``.
    """
    return project_workspace_root(port) / project_role_branch_leaf(role_name)


def project_workspace(port: int) -> Path:
    """Backward-compatible alias for the canonical main workspace."""
    return project_main_workspace(port)


def project_state_dir(port: int) -> Path:
    """Return the runtime state directory for *port*."""
    return project_dir(port) / "state"


def project_session_ledger(port: int) -> Path:
    """Return the session ledger file for *port*."""
    return project_state_dir(port) / "session-ledger.json"


def project_session_name(port: int, role_name: str) -> str:
    """Return a stable session name for *role_name* in *port*."""
    return f"p{port}/{_safe_component(role_name)}"


def project_branch_name(port: int, role_name: str | None = None) -> str:
    """Return the canonical git branch name for *port* and optional role.

    Gru owns the project's main branch (``minionsos/project-{port}``); every
    other role gets a derived branch ``minionsos/project-{port}-{role}``.
    """
    base = f"minionsos/project-{port}"
    if role_name is None or role_name in {"main", "gru"}:
        return base
    return f"{base}-{_safe_component(role_name)}"


def project_eacn_db(port: int) -> Path:
    """Return the EACN3 SQLite DB path for *port*."""
    return project_dir(port) / "eacn3_data" / "eacn3.db"


def project_meta_json(port: int) -> Path:
    """Return the ``meta.json`` path for *port*."""
    return project_dir(port) / "meta.json"


def project_claude_md(port: int) -> Path:
    """Return the ``CLAUDE.md`` path for *port*."""
    return project_dir(port) / "CLAUDE.md"


def project_logs_dir(port: int) -> Path:
    """Return the ``logs/`` directory for *port*."""
    return project_dir(port) / "logs"


def project_backend_log(port: int) -> Path:
    """Return the EACN3 backend log path for *port*."""
    return project_logs_dir(port) / "backend.log"


def project_role_log(port: int, role_name: str) -> Path:
    """Return the subprocess log path for a named role in *port*."""
    return project_logs_dir(port) / f"role-{role_name}.log"


def project_artifacts_dir(port: int) -> Path:
    """Return the ``artifacts/`` directory for *port*."""
    return project_dir(port) / "artifacts"


def project_memory_dir(port: int) -> Path:
    """Legacy per-project scratchpad directory (pre-branches restructure).

    Kept so one-shot migration code can still find the old ``memory/{role}.md``
    files. New writes must go through ``project_scratchpad`` which targets
    ``branches/<role>/.minionsos/scratchpad.md``.
    """
    return project_dir(port) / "memory"


def project_role_state_dir(port: int, role_name: str) -> Path:
    """Return the per-role MinionsOS state subdir inside the role branch dir.

    Holds hidden, system-layer files that belong to the role's branch:
    scratchpad (compact memory), local wake intent recovery, etc. The name is
    lowercase ``.minionsos`` to stay case-safe on Linux/macOS/GitHub.
    """
    return project_role_workspace(port, role_name) / ".minionsos"


def project_scratchpad(port: int, role_name: str) -> Path:
    """Return the scratchpad markdown path for *role_name* in *port*.

    Location: ``project_{port}/branches/<role-branch>/.minionsos/scratchpad.md``.
    Tracked by git on the role's branch so ``/compact`` snapshots become part
    of the branch history.
    """
    return project_role_state_dir(port, role_name) / "scratchpad.md"


def project_legacy_scratchpad(port: int, role_name: str) -> Path:
    """Return the pre-restructure scratchpad path (used only for migration)."""
    return project_memory_dir(port) / f"{role_name}.md"


def role_system_md(role: str) -> Path:
    """Return the SYSTEM.md path for a built-in role template."""
    return ROLES_DIR / role / "SYSTEM.md"


def common_role_system_md() -> Path:
    """Return the shared SYSTEM.md path injected into every role."""
    return ROLES_DIR / "SYSTEM.md"


def domain_pack(slug: str) -> Path:
    """Return the domain pack markdown path for *slug*."""
    return DOMAINS_DIR / f"{slug}.md"
