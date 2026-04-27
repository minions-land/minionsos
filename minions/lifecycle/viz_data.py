"""Read-only viz data producers for the Observatory dashboard.

These functions produce viz-ready dicts from project state. They never
modify EACN3, drain queues, or write to any store.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from minions.lifecycle.health import backend_health

logger = logging.getLogger(__name__)


def viz_project_snapshot(port: int, store: Any) -> dict[str, Any] | None:
    """Produce a viz-ready snapshot for a single project. Returns None if not found."""
    project = store.get_project(port)
    if project is None:
        return None
    alive = False
    with contextlib.suppress(Exception):
        alive = backend_health(port, timeout=2.0)
    roles = []
    for r in getattr(project, "active_roles", []):
        roles.append(
            {
                "name": r.name,
                "state": r.state,
                "last_seen": getattr(r, "last_seen", None),
                "current_task": getattr(r, "current_task", None),
            }
        )
    return {
        "port": port,
        "name": getattr(project, "real_name", str(port)),
        "status": getattr(project, "status", "unknown"),
        "backend_alive": alive,
        "agents": [],
        "roles": roles,
    }


def viz_all_projects(store: Any) -> list[dict[str, Any]]:
    """Produce viz snapshots for all projects."""
    projects = store.list_projects(filter="all")
    results = []
    for p in projects:
        snap = viz_project_snapshot(p.port, store)
        if snap is not None:
            results.append(snap)
    return results
