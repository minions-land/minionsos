"""Project metadata (meta.json) management.

Handles reading, writing, and validation of per-project meta.json files that
persist runtime state (backend PID, server tokens, role records) beyond what
lives in projects.json.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from minions.config import is_expert_role
from minions.errors import ProjectError
from minions.paths import project_meta_json
from minions.state.store import ProjectEntry, RoleEntry

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def write_meta(
    port: int,
    entry: ProjectEntry,
    extras: dict[str, object] | None = None,
) -> None:
    """Write meta.json for *port*, preserving any prior extra fields.

    ProjectEntry is configured with extra="allow" but runtime-only fields
    (backend_pid, eacn3_server_id, eacn3_server_token, gru_agent_id,
    gru_agent_token, topic_doc, template_dir, ...) are generally kept on
    disk rather than round-tripped through the store. To avoid silently
    dropping them on dormant / revive cycles, we read the existing
    meta.json first, overlay the current entry dump on top, and overlay
    explicit *extras* last.
    """
    path = project_meta_json(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    base: dict[str, object] = {}
    if path.exists():
        try:
            base = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(base, dict):
                base = {}
        except Exception:
            base = {}
    base.update(entry.model_dump())
    if extras:
        base.update(extras)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(base, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_meta_raw(port: int) -> dict[str, object]:
    """Read raw meta.json dict for *port*, preserving extras.

    Prefer this over constructing a ProjectEntry when you only need the
    on-disk dict (e.g. to read runtime-only fields like backend_pid that
    are stored on disk but not in projects.json).
    """
    path = project_meta_json(port)
    if not path.exists():
        raise ProjectError(f"meta.json not found for port {port}: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ProjectError(f"meta.json for port {port} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ProjectError(f"meta.json for port {port} is not an object.")
    return data


def role_entries_from_meta(raw: dict[str, object]) -> list[RoleEntry]:
    """Best-effort RoleEntry list from raw meta.json.

    Drops records whose names are neither in FIXED_ROLES nor pass
    is_expert_role — these are pre-fix bare-slug expert records
    (see GitHub Issue #44). The EACN registry already holds whatever
    identity was minted at original spawn, so silently coercing the name
    here would create a different agent than what's on EACN. Skip with
    a WARNING instead.

    state == "dismissed" is *not* a drop signal: project_dormant
    legitimately sets every role to "dismissed" as its dormant marker,
    and project_revive relies on those records to re-launch.
    """
    from minions.lifecycle.role import FIXED_ROLES

    raw_roles = raw.get("active_roles")
    if not isinstance(raw_roles, list):
        return []
    roles: list[RoleEntry] = []
    for item in raw_roles:
        if not isinstance(item, dict):
            continue
        try:
            role = RoleEntry.model_validate(item)
        except Exception as exc:
            logger.debug("Skipping invalid role entry from meta.json: %s", exc)
            continue
        if role.name not in FIXED_ROLES and not is_expert_role(role.name):
            logger.warning(
                "Skipping malformed role name %r from meta.json: "
                "not in FIXED_ROLES and not a valid expert role shape "
                "(see GitHub Issue #44; EACN identity preserved, no coercion)",
                role.name,
            )
            continue
        roles.append(role)
    return roles
