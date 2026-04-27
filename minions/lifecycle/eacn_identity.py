"""Project-local EACN identity mapping and plugin-state sync."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from minions.paths import project_dir, project_meta_json

AgentKind = Literal["role", "gru_mailbox", "system"]

MAP_VERSION = 1
PLUGIN_VERSION = "0.5.1"


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _safe_name(value: str) -> str:
    return "".join(c if c.isalnum() or c in {"-", "_", "."} else "_" for c in value)


def identity_map_path(port: int) -> Path:
    """Return the canonical MinionsOS role/EACN identity map path."""
    return project_dir(port) / "eacn3_data" / "agent_map.json"


def plugin_state_dir(port: int, agent_id: str) -> Path:
    """Return the EACN3 MCP plugin state dir for one project-local agent."""
    return project_dir(port) / "eacn3_data" / f"plugin-{_safe_name(agent_id)}"


def network_endpoint(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def load_identity_map(port: int) -> dict[str, Any]:
    """Load the project identity map, returning an empty map if absent."""
    path = identity_map_path(port)
    if not path.exists():
        return {"version": MAP_VERSION, "project_port": port, "agents": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": MAP_VERSION, "project_port": port, "agents": {}}
    if not isinstance(data, dict):
        return {"version": MAP_VERSION, "project_port": port, "agents": {}}
    agents = data.get("agents")
    if not isinstance(agents, dict):
        data["agents"] = {}
    data.setdefault("version", MAP_VERSION)
    data.setdefault("project_port", port)
    return data


def _write_identity_map(port: int, data: dict[str, Any]) -> None:
    data["version"] = MAP_VERSION
    data["project_port"] = port
    data.setdefault("agents", {})
    _atomic_write_json(identity_map_path(port), data)
    _sync_meta_map(port, data)


def _sync_meta_map(port: int, data: dict[str, Any]) -> None:
    """Mirror non-authoritative mapping metadata into meta.json when present."""
    path = project_meta_json(port)
    if not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(raw, dict):
        return
    raw["eacn_agent_map"] = data.get("agents", {})
    _atomic_write_json(path, raw)


def identity_map_for_meta(port: int) -> dict[str, Any]:
    """Return the current map payload suitable for embedding in meta.json."""
    return dict(load_identity_map(port).get("agents", {}))


def resolve_agent_id(port: int, role_or_agent_id: str) -> str:
    """Resolve a MinionsOS role name to its project-local EACN agent id.

    If *role_or_agent_id* is already an EACN agent id or no mapping exists, it
    is returned unchanged. This keeps the current ``role == agent_id`` default
    but removes that assumption from callers.
    """
    data = load_identity_map(port)
    agents = data.get("agents", {})
    if isinstance(agents, dict):
        entry = agents.get(role_or_agent_id)
        if isinstance(entry, dict) and entry.get("agent_id"):
            return str(entry["agent_id"])
        for item in agents.values():
            if isinstance(item, dict) and item.get("agent_id") == role_or_agent_id:
                return role_or_agent_id
    return role_or_agent_id


def resolve_role_name(port: int, agent_id: str) -> str | None:
    """Return the MinionsOS role name for a project-local EACN agent id."""
    data = load_identity_map(port)
    agents = data.get("agents", {})
    if not isinstance(agents, dict):
        return None
    for role_name, item in agents.items():
        if isinstance(item, dict) and item.get("agent_id") == agent_id:
            return str(role_name)
    return None


def upsert_agent_identity(
    port: int,
    *,
    role_name: str,
    agent_id: str,
    kind: AgentKind,
    server_id: str,
    agent_token: str | None = None,
    domains: list[str] | None = None,
    tier: str = "general",
    description: str = "",
    name: str | None = None,
    registered_at: str | None = None,
    sync_plugin: bool = True,
) -> dict[str, Any]:
    """Record the role/agent mapping and seed the EACN3 plugin state."""
    now = registered_at or _now_iso()
    state_dir = plugin_state_dir(port, agent_id)
    entry: dict[str, Any] = {
        "role_name": role_name,
        "agent_id": agent_id,
        "kind": kind,
        "server_id": server_id,
        "domains": list(domains or []),
        "tier": tier,
        "description": description,
        "name": name or role_name,
        "plugin_state_dir": str(state_dir.resolve()),
        "registered_at": now,
        "verified_at": now,
    }
    if agent_token is not None:
        entry["agent_token"] = agent_token

    data = load_identity_map(port)
    agents = data.setdefault("agents", {})
    if not isinstance(agents, dict):
        agents = {}
        data["agents"] = agents
    agents[role_name] = entry
    _write_identity_map(port, data)

    if sync_plugin:
        sync_plugin_state(
            port,
            role_name=role_name,
            agent_id=agent_id,
            server_id=server_id,
            domains=domains or [],
            tier=tier,
            description=description,
            name=name or role_name,
            state_dir=state_dir,
        )
    return entry


def sync_plugin_state(
    port: int,
    *,
    role_name: str,
    agent_id: str,
    server_id: str,
    domains: list[str],
    tier: str,
    description: str,
    name: str | None = None,
    state_dir: Path | None = None,
) -> None:
    """Write the EACN3 MCP plugin state files needed for claim/resume."""
    base = state_dir or plugin_state_dir(port, agent_id)
    agents_dir = base / "agents"
    endpoint = network_endpoint(port)
    server_payload = {
        "server_card": {
            "server_id": server_id,
            "version": PLUGIN_VERSION,
            "endpoint": endpoint,
            "owner": "minionsos",
            "status": "online",
        },
        "network_endpoint": endpoint,
    }
    _atomic_write_json(base / "server.json", server_payload)

    agent_payload = {
        "agent_id": agent_id,
        "name": name or role_name,
        "tier": tier,
        "domains": list(domains),
        "skills": [
            {
                "name": f"minionsos.{role_name}",
                "description": description,
                "parameters": {"role": role_name, "project_port": port},
            }
        ],
        "url": endpoint,
        "server_id": server_id,
        "network_id": "",
        "description": description,
    }

    agent_file = agents_dir / f"{agent_id}.json"
    existing: dict[str, Any] = {}
    if agent_file.exists():
        try:
            raw = json.loads(agent_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except (OSError, json.JSONDecodeError):
            existing = {}

    local_tasks = (
        existing.get("local_tasks") if isinstance(existing.get("local_tasks"), dict) else {}
    )
    data = {
        "agent": agent_payload,
        "local_tasks": local_tasks,
        "reputation_cache": (
            existing.get("reputation_cache")
            if isinstance(existing.get("reputation_cache"), dict)
            else {agent_id: 0}
        ),
        "active_sessions": (
            existing.get("active_sessions")
            if isinstance(existing.get("active_sessions"), dict)
            else {}
        ),
        "teams": existing.get("teams") if isinstance(existing.get("teams"), dict) else {},
    }
    _atomic_write_json(agent_file, data)
