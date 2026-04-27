"""Thin HTTP client for the EACN3 backend.

Centralises the URL conventions and request payloads used by the MinionsOS
lifecycle layer so that they stay consistent across project/role/relay.

All functions are synchronous and use ``httpx``.  They raise
``minions.errors.BackendError`` on failure.
"""

from __future__ import annotations

import logging
import uuid
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
    except Exception as exc:
        raise BackendError(f"register_server POST to {url} failed (transport): {exc}") from exc
    if resp.status_code >= 400:
        raise BackendError(
            f"register_server port={port} HTTP {resp.status_code}: {resp.text!r} "
            f"(payload keys={sorted(payload)})"
        )
    data = resp.json()
    return str(data["server_id"]), str(data.get("token", ""))


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
    except Exception as exc:
        raise BackendError(f"register_agent POST to {url} failed (transport): {exc}") from exc
    if resp.status_code >= 400:
        raise BackendError(
            f"register_agent agent_id={agent_id!r} port={port} HTTP "
            f"{resp.status_code}: {resp.text!r} "
            f"(payload keys={sorted(payload)}, server_id={server_id!r}, "
            f"domains={payload['domains']})"
        )
    data = resp.json()
    return str(data.get("token", "")), list(data.get("seeds", []))


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
# Diagnostics
# ---------------------------------------------------------------------------


def probe_backend(
    port: int,
    timeout: float = 3.0,
    server_id: str | None = None,
) -> dict[str, Any]:
    """Best-effort snapshot of what the EACN3 backend on *port* currently holds.

    Returns a dict with keys: ``health``, ``servers``, ``agents``, ``errors``,
    ``queue_depth``, ``pending_events``.
    Never raises; failures are captured in ``errors``. Used by ``./mos doctor``
    and by callers diagnosing register_* 4xx responses.
    """
    result: dict[str, Any] = {
        "port": port,
        "health": False,
        "servers": [],
        "agents": [],
        "errors": [],
        "queue_depth": 0,
        "pending_events": [],
    }
    base = base_url(port)
    try:
        r = httpx.get(f"{base}/health", timeout=timeout)
        result["health"] = r.status_code == 200
    except Exception as exc:
        result["errors"].append(f"/health: {exc}")
    agents_by_id: dict[str, dict[str, Any]] = {}
    agent_queries: list[dict[str, str]] = (
        [{"server_id": server_id}]
        if server_id
        else [{"domain": "minionsos"}, {"domain": "coordination"}]
    )
    for query in agent_queries:
        try:
            r = httpx.get(f"{base}/api/discovery/agents", params=query, timeout=timeout)
            if r.status_code == 200:
                for agent in r.json():
                    if isinstance(agent, dict) and agent.get("agent_id"):
                        agents_by_id[str(agent["agent_id"])] = agent
            else:
                result["errors"].append(f"GET /agents {query} HTTP {r.status_code}: {r.text!r}")
        except Exception as exc:
            result["errors"].append(f"GET /agents {query}: {exc}")
    result["agents"] = list(agents_by_id.values())
    try:
        r = httpx.get(
            f"{base}/api/tasks/open",
            timeout=timeout,
        )
        if r.status_code == 200:
            tasks = r.json()
            result["queue_depth"] = len(tasks)
            result["pending_events"] = tasks
        else:
            result["errors"].append(f"GET /tasks/open HTTP {r.status_code}: {r.text!r}")
    except Exception as exc:
        result["errors"].append(f"GET /tasks/open: {exc}")
    return result


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def list_tasks(
    port: int,
    status: str | None = None,
    initiator_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """Return tasks from a project-local EACN3 backend."""
    url = f"{base_url(port)}/api/tasks"
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if status:
        params["status"] = status
    if initiator_id:
        params["initiator_id"] = initiator_id
    try:
        resp = httpx.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise BackendError(f"list_tasks on port {port} failed: {exc}") from exc
    if not isinstance(data, list):
        raise BackendError(f"list_tasks on port {port} returned non-list payload.")
    return [dict(item) for item in data if isinstance(item, dict)]


def list_open_tasks(
    port: int,
    domains: list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
    timeout: float = 3.0,
) -> list[dict[str, Any]]:
    """Return open EACN3 tasks, optionally filtered by domain overlap."""
    url = f"{base_url(port)}/api/tasks/open"
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if domains:
        params["domains"] = ",".join(domains)
    try:
        resp = httpx.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise BackendError(f"list_open_tasks on port {port} failed: {exc}") from exc
    if not isinstance(data, list):
        raise BackendError(f"list_open_tasks on port {port} returned non-list payload.")
    return [dict(item) for item in data if isinstance(item, dict)]


def create_task(
    port: int,
    description: str,
    domains: list[str],
    initiator_id: str = "gru",
    budget: float = 0.0,
    expected_output: dict[str, Any] | None = None,
    deadline: str | None = None,
    max_concurrent_bidders: int | None = None,
    max_depth: int | None = None,
    level: str | None = None,
    invited_agent_ids: list[str] | None = None,
    task_id: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Publish a task to the project-local EACN3 network."""
    url = f"{base_url(port)}/api/tasks"
    payload: dict[str, Any] = {
        "task_id": task_id or f"t-{uuid.uuid4().hex[:12]}",
        "initiator_id": initiator_id,
        "content": {"description": description},
        "domains": domains,
        "budget": budget,
        "invited_agent_ids": invited_agent_ids or [],
    }
    if expected_output:
        payload["content"]["expected_output"] = expected_output
    if deadline:
        payload["deadline"] = deadline
    if max_concurrent_bidders is not None:
        payload["max_concurrent_bidders"] = max_concurrent_bidders
    if max_depth is not None:
        payload["max_depth"] = max_depth
    if level:
        payload["level"] = level
    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return dict(resp.json())
    except Exception as exc:
        raise BackendError(f"create_task on port {port} failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------


def get_agent_card(
    port: int,
    agent_id: str,
    timeout: float = 3.0,
) -> dict[str, Any] | None:
    """Return the project-local AgentCard for *agent_id*, or None on 404."""
    url = f"{base_url(port)}/api/discovery/agents/{agent_id}"
    try:
        resp = httpx.get(url, timeout=timeout)
    except Exception as exc:
        raise BackendError(f"get_agent_card {agent_id!r} on port {port} failed: {exc}") from exc
    if resp.status_code == 404:
        return None
    if resp.status_code >= 400:
        raise BackendError(
            f"get_agent_card {agent_id!r} on port {port} HTTP {resp.status_code}: {resp.text!r}"
        )
    data = resp.json()
    if not isinstance(data, dict):
        raise BackendError(f"get_agent_card {agent_id!r} on port {port} returned non-object.")
    return dict(data)


def require_agent(
    port: int,
    agent_id: str,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Return AgentCard for *agent_id*, raising if the target is not registered."""
    card = get_agent_card(port, agent_id, timeout=timeout)
    if card is None:
        raise BackendError(
            f"Cannot send project-local EACN message on port {port}: "
            f"target agent {agent_id!r} is not registered."
        )
    return card


def _post_message_raw(
    port: int,
    to_agent_id: str,
    from_agent_id: str,
    content: Any,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Send a direct message via ``POST /api/messages`` without local validation."""
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
        raise BackendError(f"post_message to {to_agent_id!r} on port {port} failed: {exc}") from exc


def _mirror_message_to_noter(
    port: int,
    to_agent_id: str,
    from_agent_id: str,
    content: Any,
) -> None:
    """Best-effort MinionsOS audit mirror for direct EACN messages.

    EACN3 direct messages are intentionally per-agent queues. MinionsOS adds
    this optional mirror so the project-local Noter can observe direct
    communications sent through this adapter without changing EACN3 itself.
    """
    if to_agent_id == "noter":
        return
    try:
        if get_agent_card(port, "noter", timeout=1.0) is None:
            return
        _post_message_raw(
            port=port,
            to_agent_id="noter",
            from_agent_id="network-audit",
            content={
                "type": "network_audit_message",
                "source": "minionsos.eacn_client.send_message",
                "from_agent_id": from_agent_id,
                "to_agent_id": to_agent_id,
                "content": content,
            },
            timeout=1.0,
        )
    except Exception as exc:
        logger.debug("Noter audit mirror failed port=%d target=%s: %s", port, to_agent_id, exc)


def send_message(
    port: int,
    to_agent_id: str,
    from_agent_id: str,
    content: Any,
    timeout: float = DEFAULT_TIMEOUT,
    *,
    validate_target: bool = True,
    audit_to_noter: bool = True,
) -> dict[str, Any]:
    """Send a direct project-local EACN message.

    EACN3 queues messages for any ``to_agent_id``. MinionsOS wraps that API
    with target AgentCard validation so typoed role names fail before they
    become ghost queues. A best-effort copy is also sent to Noter when present
    to provide a project-level audit stream for direct messages.
    """
    if validate_target:
        require_agent(port, to_agent_id, timeout=min(timeout, 3.0))
    result = _post_message_raw(
        port=port,
        to_agent_id=to_agent_id,
        from_agent_id=from_agent_id,
        content=content,
        timeout=timeout,
    )
    if audit_to_noter:
        _mirror_message_to_noter(port, to_agent_id, from_agent_id, content)
    return result


def post_message(
    port: int,
    to_agent_id: str,
    from_agent_id: str,
    content: Any,
    timeout: float = DEFAULT_TIMEOUT,
    *,
    validate_target: bool = True,
    audit_to_noter: bool = True,
) -> dict[str, Any]:
    """Backward-compatible alias for :func:`send_message`."""
    return send_message(
        port=port,
        to_agent_id=to_agent_id,
        from_agent_id=from_agent_id,
        content=content,
        timeout=timeout,
        validate_target=validate_target,
        audit_to_noter=audit_to_noter,
    )


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
        raise BackendError(f"poll_events {agent_id!r} on port {port} failed: {exc}") from exc
