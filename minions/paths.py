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
REVIEW_DIR: Path = PACKAGE_DIR / "review"
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


def configured_author_repo() -> Path | None:
    """Return the configured author source repo, if any.

    The author repo is the working tree the user `cd`'d into before placing
    MinionsOS underneath it (e.g. ``ABC/``). It is the *seed source* for new
    projects — ``project_create`` imports its current HEAD into a per-project
    bare repo. After seeding, the author repo is no longer touched: project
    branches live entirely inside ``project_{port}/parent_repo.git/`` and
    never bleed back into the author's ``.git``.

    Configurable via ``MINIONS_AUTHOR_REPO`` or ``gru.yaml:author_repo``.
    Defaults to ``MINIONS_ROOT.parent`` (the directory MinionsOS sits inside).
    """
    return _configured_path("author_repo", "MINIONS_AUTHOR_REPO")


def project_dir(port: int) -> Path:
    """Return the top-level directory for a project running on *port*.

    By default this is beside ``MINIONS_ROOT``. It can be overridden with
    ``MINIONS_PROJECTS_ROOT`` or ``gru.yaml:projects_root``.
    """
    return projects_root() / f"project_{port}"


def project_parent_repo_dir(port: int) -> Path:
    """Return the per-project bare git repo for *port*.

    Every project owns a private bare repo at
    ``project_{port}/parent_repo.git/``. ``project_create`` seeds it once
    from the author repo's current HEAD (excluding ``MinionsOS/`` and large
    files). All worktrees — main, role, shared — branch off this repo, so
    project history is fully isolated from the author's own ``.git``.
    """
    return project_dir(port) / "parent_repo.git"


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
    """Return the cross-role shared worktree for *port*.

    Layout under ``branches/shared/`` (a git worktree on branch
    ``minionsos/project-{port}-shared``):

    - ``exploration/dag.json``        Noter-curated Exploration DAG
    - ``notes/``                      Noter staged reports
    - ``ethics/``                     Ethics published audit reports (flat)
    - ``exp/``                        Experimenter result bundles
    - ``reviews/round-<n>/``          ``mos_review_run`` output
    - ``handoffs/``                   free-form cross-role handoffs

    Roles do **not** ``Write`` to this tree directly. All writes go through
    ``mos_publish_to_shared`` which holds a project-local flock and commits
    each publish on the shared branch. The exception is ``mos_review_run``
    which owns ``reviews/round-<n>/`` directly.
    """
    return project_workspace_root(port) / "shared"


def project_shared_subdir(port: int, subdir: str) -> Path:
    """Return a subdirectory under ``branches/shared/`` for *port*."""
    return project_shared_workspace(port) / _safe_component(subdir)


def project_shared_dag_json(port: int) -> Path:
    """Return the canonical Exploration DAG path for *port*.

    Lives at ``branches/shared/exploration/dag.json`` so DAG state is
    durable, shared, and committed periodically by Noter on a cron.
    """
    return project_shared_subdir(port, "exploration") / "dag.json"


def project_shared_branch_name(port: int) -> str:
    """Return the canonical git branch name for the shared worktree."""
    return f"minionsos/project-{port}-shared"


def project_shared_lock(port: int) -> Path:
    """Return the per-project flock path that serializes shared writes."""
    return project_state_dir(port) / "shared.lock"


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
    """DEPRECATED: ``artifacts/`` is gone. Returns the shared worktree.

    Kept as a transitional alias so any straggling caller hitting this
    function lands on the new shared tree rather than at a missing path.
    New code should call :func:`project_shared_workspace` or
    :func:`project_shared_subdir` directly.
    """
    return project_shared_workspace(port)


def project_reviews_dir(port: int) -> Path:
    """Return ``branches/shared/reviews/`` (formerly ``artifacts/reviews/``)."""
    return project_shared_subdir(port, "reviews")


def project_reset_markers_dir(port: int) -> Path:
    """Return the per-role reset-marker directory for *port*.

    Markers live under ``project_{port}/state/.reset_markers/`` so they
    stay gitignored runtime control state, separate from the audited
    shared tree.
    """
    return project_state_dir(port) / ".reset_markers"


def role_system_md(role: str) -> Path:
    """Return the SYSTEM.md path for a built-in role template."""
    return ROLES_DIR / role / "SYSTEM.md"


def common_role_system_md() -> Path:
    """Return the shared SYSTEM.md path injected into every role."""
    return ROLES_DIR / "SYSTEM.md"


def project_exploration_dir(port: int) -> Path:
    """Return the Exploration DAG directory for *port*.

    Lives under ``branches/shared/exploration/`` so DAG state is captured
    in git on the shared branch. Use :func:`project_shared_dag_json` for
    the canonical ``dag.json`` path directly.
    """
    return project_shared_subdir(port, "exploration")


def project_events_dir(port: int) -> Path:
    """Return the per-agent EACN event-log directory for *port*.

    Layout: ``project_{port}/events/{agent_id}.jsonl`` plus
    ``{agent_id}.last_seen`` (Gru's read pointer). Audit trail only — Roles
    do not read these files in normal operation; they are kept for
    post-mortem reconstruction of the project's full event flow.
    """
    return project_dir(port) / "events"


def domain_pack(slug: str) -> Path:
    """Return the domain pack markdown path for *slug*."""
    return DOMAINS_DIR / f"{slug}.md"
