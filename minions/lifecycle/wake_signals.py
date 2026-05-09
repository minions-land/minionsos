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
from minions.lifecycle.project import (
    ProjectPhaseSnapshot,
    project_phase_allows_role,
    project_phase_snapshot,
)
from minions.state.store import ProjectEntry, StateStore

logger = logging.getLogger(__name__)


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


def _role_by_name(project: ProjectEntry | None, role_name: str) -> bool:
    if project is None:
        return False
    return any(role.name == role_name for role in project.active_roles)


def _task_id(task: dict[str, Any]) -> str:
    value = task.get("id") or task.get("task_id")
    return str(value) if value else ""


def _str_set_field(task: dict[str, Any], key: str) -> set[str]:
    values = task.get(key) or []
    if not isinstance(values, list):
        return set()
    return {str(v) for v in values if str(v).strip()}


def _task_domains(task: dict[str, Any]) -> set[str]:
    return _str_set_field(task, "domains")


def _task_invited_agent_ids(task: dict[str, Any]) -> set[str]:
    return _str_set_field(task, "invited_agent_ids")


def _task_invited_roles(task: dict[str, Any]) -> set[str]:
    return _str_set_field(task, "invited_roles")


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


def task_explicit_targets(project: ProjectEntry, task: dict[str, Any]) -> list[tuple[str, str]]:
    """Return only explicitly invited task targets.

    EACN3 owns task routing by domains and broadcasts native ``task_broadcast``
    or ``adjudication_task`` events to each candidate agent queue. MinionsOS
    must not reproduce that router locally. The only task targets this helper
    derives are explicit EACN-native invitations already present on the task.
    """
    invited_ids = _task_invited_agent_ids(task)
    invited_roles = _task_invited_roles(task)
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
    content_type = content.get("type") if isinstance(content, dict) else type(content).__name__
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
    """Persist compact wake signals for explicit EACN task targets.

    Public task/domain routing is intentionally not performed here. For public
    tasks, EACN3 writes native broadcast events to candidate agent queues; the
    MinionsOS wake layer may only observe that queue state.
    """
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
        targets = task_explicit_targets(project, task)
    phase_state = _phase_state(project)
    for role_name, matched_by in targets:
        task_key = _now_key(task_id, matched_by, task.get("initiator_id"))
        signal = {
            "type": "wake_signal",
            "kind": "task_invitation",
            "id": f"task:{port}:{role_name}:{task_key}",
            "port": port,
            "role_name": role_name,
            "source": source,
            "task_id": task_id,
            "matched_by": matched_by,
            "task_domains": sorted(_task_domains(task)),
            "task_level": task.get("level"),
            "initiator_id": task.get("initiator_id"),
            "reason": f"task {task_id or '<missing>'} explicitly targeted by {matched_by}",
            "phase": phase_state["current_phase"],
            "phase_version": phase_state["phase_version"],
            "phase_allowed_roles": phase_state["phase_allowed_roles"],
            "phase_online_roles": phase_state["phase_online_roles"],
            "phase_allowed": project_phase_allows_role(project, role_name) if project else None,
        }
        _queue_signal(port, role_name, signal)
        matched.append(role_name)
    return matched


def eacn_queue_pending_signal(
    *,
    port: int,
    agent_id: str,
    pending_count: int,
    source: str,
    store: StateStore | None = None,
) -> list[str]:
    """Wake the local role whose native EACN3 queue has pending events.

    This signal is based on EACN3's own per-agent queue state. It does not infer
    task candidates from domains and it does not contain message/task payloads.
    """
    role_name = _role_match(port, agent_id, store=store)
    if role_name is None:
        return []
    project = _project(port, store=store)
    phase_state = _phase_state(project)
    signal = {
        "type": "wake_signal",
        "kind": "eacn_queue_pending",
        "id": f"eacnq:{port}:{role_name}:{_now_key(agent_id, pending_count)}",
        "port": port,
        "role_name": role_name,
        "source": source,
        "agent_id": agent_id,
        "pending_count": pending_count,
        "reason": f"EACN3 queue has {pending_count} pending event(s)",
        "phase": phase_state["current_phase"],
        "phase_version": phase_state["phase_version"],
        "phase_allowed_roles": phase_state["phase_allowed_roles"],
        "phase_online_roles": phase_state["phase_online_roles"],
        "phase_allowed": project_phase_allows_role(project, role_name) if project else None,
    }
    _queue_signal(port, role_name, signal)
    return [role_name]


def eacn_queue_pending_signals(
    *,
    port: int,
    counts: dict[str, int],
    source: str,
    store: StateStore | None = None,
) -> list[str]:
    """Wake all local roles that EACN3 reports as having pending events."""
    project = _project(port, store=store)
    if project is None:
        return []
    matched: list[str] = []
    for agent_id, pending_count in counts.items():
        if pending_count <= 0:
            continue
        role_name = _role_match(port, agent_id, store=store)
        if role_name is None or not _role_by_name(project, role_name):
            continue
        matched.extend(
            eacn_queue_pending_signal(
                port=port,
                agent_id=agent_id,
                pending_count=pending_count,
                source=source,
                store=store,
            )
        )
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
    if kind == "task_invitation":
        task_id = signal.get("task_id") or "<missing>"
        matched_by = signal.get("matched_by") or "unknown"
        domains = signal.get("task_domains") or []
        domain_text = f" domains={','.join(domains)}" if domains else ""
        return f"task {task_id} explicit_target {matched_by}{domain_text}"
    if kind == "eacn_queue_pending":
        return f"EACN3 queue pending ({signal.get('pending_count', '?')})"
    if kind == "gru_eacn_activity":
        return f"Gru EACN activity ({signal.get('pending_count', '?')} pending)"
    if kind == "gru_autonomous_drive":
        return "Gru autonomous EACN drive"
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


# ---------------------------------------------------------------------------
# Hook handlers
# ---------------------------------------------------------------------------
#
# Register the signal emitters as handlers on the shared hook registry so
# lifecycle callers can fire an event instead of importing these helpers
# directly. ``hooks.fire(...)`` swallows-and-logs handler exceptions, so the
# old ``contextlib.suppress(Exception)`` wrappers around direct calls are no
# longer needed at the call site.


def _handle_wake_direct_message(data: dict[str, Any]) -> None:
    direct_message_signal(
        port=int(data["port"]),
        to_agent_id=str(data["to_agent_id"]),
        from_agent_id=str(data["from_agent_id"]),
        content=data.get("content"),
        source=str(data.get("source") or "hook:wake_direct_message"),
        store=data.get("store"),
        target_role_name=data.get("target_role_name"),
    )


def _handle_wake_task_invitation(data: dict[str, Any]) -> None:
    task_signal(
        port=int(data["port"]),
        task=data["task"],
        source=str(data.get("source") or "hook:wake_task_invitation"),
        store=data.get("store"),
        target_role_names=data.get("target_role_names"),
    )


def _handle_wake_eacn_queue_pending(data: dict[str, Any]) -> None:
    counts = data.get("counts")
    if counts is None:
        from minions.lifecycle.eacn_client import pending_event_counts

        counts = pending_event_counts(int(data["port"]), timeout=float(data.get("timeout", 1.0)))
    eacn_queue_pending_signals(
        port=int(data["port"]),
        counts=counts,
        source=str(data.get("source") or "hook:wake_eacn_queue_pending"),
        store=data.get("store"),
    )


def _handle_wake_phase_change(data: dict[str, Any]) -> None:
    phase_change_signal(
        port=int(data["port"]),
        phase=data.get("phase"),
        reason=data.get("reason"),
        store=data.get("store"),
    )


def install_default_handlers() -> None:
    """Register wake-signal emitters on the shared hook registry."""
    from minions.lifecycle.hooks import LifecycleEvent, registry

    registry.register(LifecycleEvent.wake_direct_message, _handle_wake_direct_message)
    registry.register(LifecycleEvent.wake_task_invitation, _handle_wake_task_invitation)
    registry.register(LifecycleEvent.wake_eacn_queue_pending, _handle_wake_eacn_queue_pending)
    registry.register(LifecycleEvent.wake_phase_change, _handle_wake_phase_change)


install_default_handlers()
