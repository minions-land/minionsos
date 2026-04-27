"""Canonical path constants for MinionsOS V2.

All runtime code must import paths from here — never construct paths by
string concatenation or relative ``..`` traversal.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------

# This file lives at  minions/paths.py  inside the MinionsOS_V2 checkout.
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


def project_dir(port: int) -> Path:
    """Return the top-level directory for a project running on *port*.

    The directory lives **inside the parent repo** (the author's research
    repo), which is the parent of ``MINIONS_ROOT``.  Per the spec, MinionsOS
    itself only tracks ``minions/``, ``EACN3/``, and root scripts; the
    ``project_*/`` trees live in the parent repo's working tree.
    """
    parent_repo: Path = MINIONS_ROOT.parent
    return parent_repo / f"project_{port}"


def project_workspace(port: int) -> Path:
    """Return the ``workspace/`` git-worktree path for *port*."""
    return project_dir(port) / "workspace"


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
    """Return the per-role scratchpad ``memory/`` directory for *port*."""
    return project_dir(port) / "memory"


def project_scratchpad(port: int, role_name: str) -> Path:
    """Return the scratchpad markdown path for *role_name* in *port*."""
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
