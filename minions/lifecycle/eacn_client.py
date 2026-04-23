"""Thin HTTP client for the EACN3 backend.

Centralises the URL conventions and request payloads used by the MinionsOS
lifecycle layer so that they stay consistent across project/role/relay.

All functions are synchronous and use ``httpx``.  They raise
``minions.errors.BackendError`` on failure.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from minions.errors import BackendError

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT: float = 10.0


def base_url(port: int) -> str:
    """Return the EACN3 backend base URL for *port*."""
    return f"http://127.0.0.1:{port}"


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


def register_server(
    port: int,
    owner: str = "minionsos",
    version: str = "1.0",
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[str, str]:
    """Register a MinionsOS server record. Returns ``(server_id, token)``."""
    url = f"{base_url(port)}/api/discovery/servers"
    payload = {
        "version": version,
        "endpoint": base_url(port),
        "owner": owner,
    }
    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return str(data["server_id"]), str(data.get("token", ""))
    except Exception as exc:
        raise BackendError(
            f"register_server failed on port {port}: {exc}"
        ) from exc


def delete_server(
    port: int,
    server_id: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Unregister a server (cascades agents). Swallows 404."""
    url = f"{base_url(port)}/api/discovery/servers/{server_id}"
    try:
        resp = httpx.delete(url, timeout=timeout)
        if resp.status_code not in (200, 404):
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("delete_server port=%d id=%s failed: %s", port, server_id, exc)


def server_heartbeat(
    port: int,
    server_id: str,
    timeout: float = 3.0,
) -> bool:
    """Best-effort server heartbeat. Returns True on 200."""
    url = f"{base_url(port)}/api/discovery/servers/{server_id}/heartbeat"
    try:
        resp = httpx.post(url, timeout=timeout)
        return resp.status_code == 200
    except Exception as exc:
        logger.debug("server_heartbeat port=%d failed: %s", port, exc)
        return False


# ---------------------------------------------------------------------------
# Agent lifecycle
# ---------------------------------------------------------------------------

_DEFAULT_SKILL = [
    {"name": "minionsos.role", "description": "MinionsOS role agent", "parameters": {}}
]


def register_agent(
    port: int,
    agent_id: str,
    name: str,
    server_id: str,
    domains: list[str] | None = None,
    skills: list[dict[str, Any]] | None = None,
    description: str = "",
    tier: str = "general",
    url_hint: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[str, list[str]]:
    """Register an agent with the EACN3 backend.

    Returns ``(agent_token, seeds)``.
    """
    url = f"{base_url(port)}/api/discovery/agents"
    payload = {
        "agent_id": agent_id,
        "name": name,
        "domains": domains or ["coordination"],
        "skills": skills or _DEFAULT_SKILL,
        "url": url_hint or base_url(port),
        "server_id": server_id,
        "description": description,
        "tier": tier,
    }
    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("token", "")), list(data.get("seeds", []))
    except Exception as exc:
        raise BackendError(
            f"register_agent {agent_id!r} on port {port} failed: {exc}"
        ) from exc


def unregister_agent(
    port: int,
    agent_id: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Best-effort agent unregister; swallows 404."""
    url = f"{base_url(port)}/api/discovery/agents/{agent_id}"
    try:
        resp = httpx.delete(url, timeout=timeout)
        if resp.status_code not in (200, 404):
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("unregister_agent port=%d id=%s failed: %s", port, agent_id, exc)


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------


def post_message(
    port: int,
    to_agent_id: str,
    from_agent_id: str,
    content: Any,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Send a direct message via ``POST /api/messages``."""
    url = f"{base_url(port)}/api/messages"
    payload = {
        "to": {"agent_id": to_agent_id, "server_id": "", "network_id": ""},
        "from": {"agent_id": from_agent_id, "server_id": "", "network_id": ""},
        "content": content,
    }
    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return dict(resp.json())
    except Exception as exc:
        raise BackendError(
            f"post_message to {to_agent_id!r} on port {port} failed: {exc}"
        ) from exc


def poll_events(
    port: int,
    agent_id: str,
    timeout_secs: int = 0,
    http_timeout: float = 10.0,
) -> dict[str, Any]:
    """Drain events for *agent_id* via ``GET /api/events/{agent_id}``."""
    url = f"{base_url(port)}/api/events/{agent_id}"
    try:
        resp = httpx.get(
            url,
            params={"timeout": timeout_secs},
            timeout=http_timeout + timeout_secs,
        )
        resp.raise_for_status()
        return dict(resp.json())
    except Exception as exc:
        raise BackendError(
            f"poll_events {agent_id!r} on port {port} failed: {exc}"
        ) from exc
