"""Backward-compatible wrappers for generic project-local EACN actions."""

from __future__ import annotations

from typing import Any

from minions.lifecycle.project_eacn import project_eacn_create_task, project_eacn_send_message


def gru_send_message(
    port: int,
    to_agent_id: str,
    content: Any,
    from_agent_id: str | None = None,
) -> dict[str, Any]:
    """Deprecated: use ``project_eacn_send_message``."""
    return project_eacn_send_message(
        port=port,
        content=content,
        to_agent_id=to_agent_id,
        from_agent_id=from_agent_id,
    )


def gru_publish_task(
    port: int,
    description: str,
    domains: list[str] | None = None,
    target_role: str | None = None,
    budget: float = 0.0,
    expected_output: dict[str, Any] | None = None,
    deadline: str | None = None,
    level: str | None = None,
    task_id: str | None = None,
    notify_target: bool = True,
) -> dict[str, Any]:
    """Deprecated: use ``project_eacn_create_task``."""
    _ = notify_target
    result = project_eacn_create_task(
        port=port,
        description=description,
        domains=domains,
        invited_roles=[target_role] if target_role else [],
        budget=budget,
        expected_output=expected_output,
        deadline=deadline,
        level=level,
        task_id=task_id,
    )
    return {
        "ok": True,
        "port": port,
        "task": result["task"],
        "target_role": target_role,
        "notification": None,
    }
