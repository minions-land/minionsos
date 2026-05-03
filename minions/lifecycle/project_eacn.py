"""Generic project-local EACN adapter for MinionsOS runtimes."""

from __future__ import annotations

import contextlib
from typing import Any

from minions.config import load_gru_config
from minions.lifecycle import eacn_client
from minions.lifecycle.eacn_identity import resolve_agent_id
from minions.lifecycle.wake_signals import (
    direct_message_signal,
    eacn_queue_pending_signals,
)
from minions.state.store import StateStore


def _default_initiator(port: int) -> str:
    try:
        configured = load_gru_config().gru_eacn_agent_id
    except Exception:
        configured = "gru"
    return resolve_agent_id(port, configured)


def _merge_domains(base: list[str] | None, invited_roles: list[str]) -> list[str]:
    """Return domains for an EACN3 task without reproducing router logic.

    ``invited_roles`` is accepted by the MinionsOS adapter as a convenience for
    resolving role names to native EACN3 ``invited_agent_ids``. It must not
    broaden the task's public routing domains; EACN3 owns domain discovery and
    task broadcasts.
    """
    _ = invited_roles
    return list(base or ["minionsos", "project-local", "coordination"])


def project_eacn_send_message(
    *,
    port: int,
    content: Any,
    to_agent_id: str | None = None,
    to_role: str | None = None,
    from_agent_id: str | None = None,
    from_role: str | None = None,
) -> dict[str, Any]:
    """Send a generic direct message on one project's Local EACN network."""
    if bool(to_agent_id) == bool(to_role):
        raise ValueError("Pass exactly one of to_agent_id or to_role.")
    target = to_agent_id or resolve_agent_id(port, str(to_role))
    sender = from_agent_id or (
        resolve_agent_id(port, from_role) if from_role else _default_initiator(port)
    )
    result = eacn_client.send_message(
        port=port,
        to_agent_id=str(target),
        from_agent_id=str(sender),
        content=content,
    )
    with contextlib.suppress(Exception):
        direct_message_signal(
            port=port,
            to_agent_id=str(target),
            from_agent_id=str(sender),
            content=content,
            source="minions.lifecycle.project_eacn.project_eacn_send_message",
            store=StateStore(),
        )
    return {
        "ok": True,
        "port": port,
        "from_agent_id": str(sender),
        "to_agent_id": str(target),
        "delivery": result,
    }


def project_eacn_create_task(
    *,
    port: int,
    description: str,
    domains: list[str] | None = None,
    invited_agent_ids: list[str] | None = None,
    invited_roles: list[str] | None = None,
    initiator_agent_id: str | None = None,
    initiator_role: str | None = None,
    budget: float = 0.0,
    expected_output: dict[str, Any] | None = None,
    deadline: str | None = None,
    level: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Publish a generic task on one project's Local EACN network."""
    roles = list(invited_roles or [])
    resolved_invites = [resolve_agent_id(port, role) for role in roles]
    resolved_invites.extend(invited_agent_ids or [])
    for agent_id in resolved_invites:
        eacn_client.require_agent(port, agent_id)

    if initiator_agent_id:
        initiator = initiator_agent_id
    elif initiator_role:
        initiator = resolve_agent_id(port, initiator_role)
    else:
        initiator = _default_initiator(port)

    task_domains = _merge_domains(domains, roles)
    task = eacn_client.create_task(
        port=port,
        description=description,
        domains=task_domains,
        initiator_id=initiator,
        budget=budget,
        expected_output=expected_output,
        deadline=deadline,
        level=level,
        invited_agent_ids=resolved_invites,
        task_id=task_id,
    )
    with contextlib.suppress(Exception):
        eacn_queue_pending_signals(
            port=port,
            counts=eacn_client.pending_event_counts(port, timeout=1.0),
            source="minions.lifecycle.project_eacn.project_eacn_create_task",
            store=StateStore(),
        )
    return {
        "ok": True,
        "port": port,
        "task": task,
        "initiator_id": initiator,
        "invited_agent_ids": resolved_invites,
        "domains": task_domains,
    }
