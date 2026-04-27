"""Generic project-local EACN adapter for MinionsOS runtimes."""

from __future__ import annotations

from typing import Any

from minions.config import load_gru_config
from minions.lifecycle import eacn_client
from minions.lifecycle.agent_registry import role_agent_domains
from minions.lifecycle.eacn_identity import resolve_agent_id


def _default_initiator(port: int) -> str:
    try:
        configured = load_gru_config().gru_eacn_agent_id
    except Exception:
        configured = "gru"
    return resolve_agent_id(port, configured)


def _role_base(role_name: str) -> str:
    return "expert" if role_name.startswith("expert") else role_name


def _merge_domains(base: list[str] | None, invited_roles: list[str]) -> list[str]:
    domains = list(base or ["minionsos", "project-local", "coordination"])
    for role_name in invited_roles:
        for domain in role_agent_domains(role_name):
            if domain not in domains:
                domains.append(domain)
        role_domain = f"role:{_role_base(role_name)}"
        if role_domain not in domains:
            domains.append(role_domain)
    return domains


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
    return {
        "ok": True,
        "port": port,
        "task": task,
        "initiator_id": initiator,
        "invited_agent_ids": resolved_invites,
        "domains": task_domains,
    }
