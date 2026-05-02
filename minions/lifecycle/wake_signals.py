"""Hook-driven wake signal helpers for resident role sessions.

These helpers translate local MinionsOS lifecycle events into compact wake
signals that can be persisted in the per-role inbox. The role session later
reads the signal and decides when to go onto EACN3 and inspect the network
itself. No EACN3 payload is embedded here.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from minions.lifecycle import role_inbox
from minions.lifecycle.agent_registry import role_agent_domains
from minions.lifecycle.project import (
    ProjectPhaseSnapshot,
    project_phase_allows_role,
    project_phase_snapshot,
)
from minions.state.store import ProjectEntry, StateStore

logger = logging.getLogger(__name__)

_GENERIC_TASK_DOMAINS = {"minionsos", "project-local"}
_OPEN_TASK_EXCLUDED_ROLES = {"gru", "noter"}


def _now_key(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _project(port: int, store: StateStore | None = None) -> ProjectEntry | None:
    _store = store or StateStore()
    return _store.get_project(port)


def _role_match(port: int, agent_id: str, store: StateStore | None = None) -> str | None:
    project = _project(port, store=store)
    if project is None:
        return None
    for role in project.active_roles:
        if role.name == agent_id or role.eacn_agent_id == agent_id:
            return role.name
    return None


def _task_id(task: dict[str, Any]) -> str:
    value = task.get("id") or task.get("task_id")
    return str(value) if value else ""


def _task_domains(task: dict[str, Any]) -> set[str]:
    domains = task.get("domains") or []
    if not isinstance(domains, list):
        return set()
    return {str(d) for d in domains if str(d).strip()}


def _task_invited_agent_ids(task: dict[str, Any]) -> set[str]:
    invited = task.get("invited_agent_ids") or []
    if not isinstance(invited, list):
        return set()
    return {str(agent_id) for agent_id in invited if str(agent_id).strip()}


def _task_invited_roles(task: dict[str, Any]) -> set[str]:
    invited = task.get("invited_roles") or []
    if not isinstance(invited, list):
        return set()
    return {str(role_name) for role_name in invited if str(role_name).strip()}


def _role_task_domains(role_name: str) -> set[str]:
    return set(role_agent_domains(role_name)) - _GENERIC_TASK_DOMAINS


def _phase_state(project: ProjectEntry | None) -> ProjectPhaseSnapshot:
    if project is None:
        return ProjectPhaseSnapshot(
            {
                "current_phase": None,
                "phase_version": 0,
                "phase_allowed_roles": [],
                "phase_online_roles": [],
            }
        )
    return project_phase_snapshot(project)


def task_router_targets(project: ProjectEntry, task: dict[str, Any]) -> list[tuple[str, str]]:
    """Return router-matched candidate roles for *task*."""
    task_id = _task_id(task)
    invited_ids = _task_invited_agent_ids(task)
    invited_roles = _task_invited_roles(task)
    role_names = [
        role.name
        for role in project.active_roles
        if role.state in {"active", "sleeping"} and role.name not in _OPEN_TASK_EXCLUDED_ROLES
    ]
    matches: list[tuple[str, str]] = []
    if invited_ids or invited_roles:
        for role in project.active_roles:
            if role.state not in {"active", "sleeping"}:
                continue
            if role.name in invited_roles:
                matches.append((role.name, "invited_roles"))
                continue
            agent_id = getattr(role, "eacn_agent_id", None) or role.name
            if agent_id in invited_ids or role.name in invited_ids:
                matches.append((role.name, "invited_agent_ids"))
        return matches

    task_domains = _task_domains(task)
    for role_name in role_names:
        if task_domains & _role_task_domains(role_name):
            matches.append((role_name, "domain"))
    if matches:
        logger.debug(
            "Task %s matched roles on port %d: %s",
            task_id or "<missing>",
            project.port,
            ", ".join(f"{role}:{reason}" for role, reason in matches),
        )
    return matches


def _queue_signal(port: int, role_name: str, signal: dict[str, Any]) -> None:
    role_inbox.append_events(port, role_name, [signal])


def direct_message_signal(
    *,
    port: int,
    to_agent_id: str,
    from_agent_id: str,
    content: Any,
    source: str,
    store: StateStore | None = None,
    target_role_name: str | None = None,
) -> list[str]:
    """Persist a wake signal for the direct-message recipient, if local."""
    role_name = target_role_name or _role_match(port, to_agent_id, store=store)
    if role_name is None:
        return []
    project = _project(port, store=store)
    content_type = (
        content.get("type") if isinstance(content, dict) else type(content).__name__
    )
    phase_state = _phase_state(project)
    signal = {
        "type": "wake_signal",
        "kind": "direct_message",
        "id": f"dm:{port}:{role_name}:{_now_key(from_agent_id, to_agent_id, content)}",
        "port": port,
        "role_name": role_name,
        "source": source,
        "from_agent_id": from_agent_id,
        "to_agent_id": to_agent_id,
        "content_type": content_type,
        "reason": f"direct message from {from_agent_id}",
        "phase": phase_state["current_phase"],
        "phase_version": phase_state["phase_version"],
        "phase_allowed_roles": phase_state["phase_allowed_roles"],
        "phase_online_roles": phase_state["phase_online_roles"],
        "phase_allowed": project_phase_allows_role(project, role_name) if project else None,
    }
    _queue_signal(port, role_name, signal)
    return [role_name]


def task_signal(
    *,
    port: int,
    task: dict[str, Any],
    source: str,
    store: StateStore | None = None,
    target_role_names: list[str] | None = None,
) -> list[str]:
    """Persist compact wake signals for role candidates selected from *task*."""
    project = _project(port, store=store)
    if project is None and not target_role_names:
        return []
    task_id = _task_id(task)
    matched: list[str] = []
    if target_role_names:
        targets = [(role_name, "explicit_target") for role_name in target_role_names]
    else:
        if project is None:
            return matched
        targets = task_router_targets(project, task)
    phase_state = _phase_state(project)
    for role_name, matched_by in targets:
        task_key = _now_key(task_id, matched_by, task.get("initiator_id"))
        signal = {
            "type": "wake_signal",
            "kind": "task_router",
            "id": f"task:{port}:{role_name}:{task_key}",
            "port": port,
            "role_name": role_name,
            "source": source,
            "task_id": task_id,
            "matched_by": matched_by,
            "task_domains": sorted(_task_domains(task)),
            "task_level": task.get("level"),
            "initiator_id": task.get("initiator_id"),
            "reason": f"task {task_id or '<missing>'} matched by {matched_by}",
            "phase": phase_state["current_phase"],
            "phase_version": phase_state["phase_version"],
            "phase_allowed_roles": phase_state["phase_allowed_roles"],
            "phase_online_roles": phase_state["phase_online_roles"],
            "phase_allowed": project_phase_allows_role(project, role_name) if project else None,
        }
        _queue_signal(port, role_name, signal)
        matched.append(role_name)
    return matched


def phase_change_signal(
    *,
    port: int,
    phase: str | None,
    reason: str | None,
    store: StateStore | None = None,
) -> list[str]:
    """Wake online-eligible roles so they can reconcile against a phase change."""
    project = _project(port, store=store)
    if project is None:
        return []
    targets: list[str] = []
    phase_state = _phase_state(project)
    for role in project.active_roles:
        if role.state not in {"active", "sleeping"}:
            continue
        phase_allowed = project_phase_allows_role(project, role.name)
        if not phase_allowed:
            continue
        phase_key = _now_key(phase, reason, getattr(project, "phase_version", 0))
        signal = {
            "type": "wake_signal",
            "kind": "phase_change",
            "id": f"phase:{port}:{role.name}:{phase_key}",
            "port": port,
            "role_name": role.name,
            "source": "project_set_phase",
            "phase": phase,
            "reason": reason or "phase update",
            "current_phase": phase_state["current_phase"],
            "phase_version": phase_state["phase_version"],
            "phase_allowed_roles": phase_state["phase_allowed_roles"],
            "phase_online_roles": phase_state["phase_online_roles"],
            "phase_allowed": phase_allowed,
        }
        _queue_signal(port, role.name, signal)
        targets.append(role.name)
    return targets


def summarize_signal(signal: dict[str, Any]) -> str:
    """Return a compact human-readable summary for one wake signal."""
    kind = str(signal.get("kind") or signal.get("type") or "wake")
    if kind == "direct_message":
        return f"direct message from {signal.get('from_agent_id')}"
    if kind == "task_router":
        task_id = signal.get("task_id") or "<missing>"
        matched_by = signal.get("matched_by") or "unknown"
        domains = signal.get("task_domains") or []
        domain_text = f" domains={','.join(domains)}" if domains else ""
        return f"task {task_id} matched_by {matched_by}{domain_text}"
    if kind == "phase_change":
        phase = signal.get("phase") or signal.get("current_phase") or "unset"
        allowed = signal.get("phase_allowed")
        if allowed is None:
            return f"phase change -> {phase}"
        online = signal.get("phase_online_roles") or []
        online_text = f" online={len(online)}" if isinstance(online, list) else ""
        return f"phase change -> {phase} (allowed={str(bool(allowed)).lower()}{online_text})"
    if kind == "human_trigger":
        return str(signal.get("reason") or "human trigger")
    return str(signal.get("reason") or kind)


def is_wake_signal(event: dict[str, Any]) -> bool:
    """Return True when *event* is a hook-generated wake signal."""
    return event.get("type") == "wake_signal"
