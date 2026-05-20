"""Project phase policy helpers.

Pure or near-pure functions extracted from :mod:`minions.lifecycle.project`.
``project_set_phase`` lazily imports the orchestrator's ``_now_iso`` /
``_write_meta`` helpers to avoid an import cycle: ``project`` re-exports
the names below, and the orchestrator re-imports the module to keep its
own namespace stable for tests that monkeypatch related symbols.
"""

from __future__ import annotations

import logging

from minions.errors import ProjectError
from minions.state.store import (
    ProjectEntry,
    ProjectPhaseSnapshot,
    StateStore,
)

logger = logging.getLogger(__name__)


def project_phase_allows_role(entry: ProjectEntry, role_name: str) -> bool:
    """Return True when the current phase allows *role_name* to run.

    If no phase policy has been recorded yet, the project defaults to open
    scheduling.
    """
    allowed = {str(role).strip() for role in getattr(entry, "phase_allowed_roles", []) or []}
    if not allowed:
        return True
    if "*" in allowed or "all" in allowed:
        return True
    return role_name in allowed


def project_phase_online_role_names(entry: ProjectEntry) -> list[str]:
    """Return schedulable role names that are currently online-eligible."""
    allowed = {str(role).strip() for role in getattr(entry, "phase_allowed_roles", []) or []}
    online: list[str] = []
    for role in entry.active_roles:
        if role.state not in {"active", "sleeping"}:
            continue
        if role.name == "gru":
            continue
        if not allowed or "*" in allowed or "all" in allowed or role.name in allowed:
            online.append(role.name)
    return online


def project_phase_snapshot(entry: ProjectEntry) -> ProjectPhaseSnapshot:
    """Return a compact snapshot of the project's current phase state."""
    return ProjectPhaseSnapshot(
        {
            "current_phase": getattr(entry, "current_phase", None),
            "phase_version": int(getattr(entry, "phase_version", 0) or 0),
            "phase_allowed_roles": list(getattr(entry, "phase_allowed_roles", []) or []),
            "phase_online_roles": project_phase_online_role_names(entry),
        }
    )


def project_set_phase(
    port: int,
    phase: str | None,
    *,
    allowed_roles: list[str] | None = None,
    reason: str | None = None,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Record the current project phase in the registry and meta state."""
    # Lazy import to avoid a cycle with the project module.
    from minions.lifecycle.project import _now_iso, _write_meta

    _store = store or StateStore()
    entry = _store.get_project(port)
    if entry is None:
        raise ProjectError(f"Project {port} not found.")

    now = _now_iso()
    phase_allowed_roles = [role for role in (allowed_roles or []) if str(role).strip()]
    existing_allowed = [
        str(role).strip()
        for role in (getattr(entry, "phase_allowed_roles", []) or [])
        if str(role).strip()
    ]
    if phase == getattr(entry, "current_phase", None) and phase_allowed_roles == existing_allowed:
        logger.debug(
            "project_set_phase no-op: port=%d phase=%r allowed_roles=%s",
            port,
            phase,
            phase_allowed_roles,
        )
        return entry
    updated = _store.update_project(
        port,
        current_phase=phase,
        phase_version=int(getattr(entry, "phase_version", 0) or 0) + 1,
        phase_allowed_roles=phase_allowed_roles,
        phase_updated_at=now,
        phase_reason=reason,
    )
    _write_meta(
        port,
        updated,
        extras={
            "current_phase": phase,
            "phase_version": updated.phase_version,
            "phase_allowed_roles": phase_allowed_roles,
            "phase_updated_at": now,
            "phase_reason": reason,
        },
    )
    logger.info(
        "project_set_phase done: port=%d phase=%r allowed_roles=%s",
        port,
        phase,
        phase_allowed_roles,
    )
    return updated
