"""Python-level event-driven wakeup scheduler for Roles.

Polls the EACN3 events endpoint on behalf of each registered Role at a
fixed cadence (from `gru.yaml: poll_interval_default` or a per-role
override). When events arrive, spawns a SHORT-LIVED Claude subprocess
for that Role via ``invoke_role_ephemeral``. When no events arrive,
nothing is spawned — the Role consumes zero Claude context on idle.

Design notes:
- Duplicate events are deduplicated via an in-memory LRU set keyed by
  ``(port, role, event_id)``.
- The loop is cooperatively cancellable; ``stop()`` sets a flag and
  ``run_async`` exits at the next sleep boundary.
- Short-poll only; long-poll support is intentionally not added here
  (EACN3 is not modified).
"""

from __future__ import annotations

import asyncio
import enum
import json
import logging
import time as _time_mod
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from minions.config import GruConfig, load_gru_config, parse_duration
from minions.lifecycle import gru_inbox, role_inbox
from minions.lifecycle.agent_registry import role_agent_domains
from minions.lifecycle.eacn_client import list_open_tasks, poll_events, send_message
from minions.paths import project_memory_dir, project_scratchpad
from minions.state.store import StateStore

logger = logging.getLogger(__name__)

_DEDUP_MAX = 2048
_GENERIC_TASK_DOMAINS = {"minionsos", "project-local"}


class WakeupClass(enum.Enum):
    """Classification of what triggered a role wakeup."""

    event = "event"
    time = "time"
    human = "human"


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: len/4 (±20% error vs. true BPE tokenizers)."""
    return len(text) // 4


def _compute_thresholds(cfg: GruConfig) -> tuple[int, int, int]:
    """Compute (soft, hard, veto) scratchpad token thresholds from config.

    Thresholds are percentages of the model context window so they auto-scale
    when the underlying model's window changes. Defaults (1M window):
    soft=100k, hard=150k, veto=200k.
    """
    win = cfg.model_context_window_tokens
    return (
        int(win * cfg.scratchpad_soft_pct),
        int(win * cfg.scratchpad_hard_pct),
        int(win * cfg.scratchpad_veto_pct),
    )


def _scratchpad_status(
    port: int,
    role_name: str,
    thresholds: tuple[int, int, int],
) -> tuple[str, int]:
    """Return (status, tokens) for the role's scratchpad.

    status: ``ok`` | ``soft`` | ``hard`` | ``veto``.
    *thresholds* is ``(soft, hard, veto)`` in tokens.
    """
    soft, hard, veto = thresholds
    path = project_scratchpad(port, role_name)
    if not path.exists():
        return "ok", 0
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return "ok", 0
    tokens = _estimate_tokens(text)
    if tokens >= veto:
        return "veto", tokens
    if tokens >= hard:
        return "hard", tokens
    if tokens >= soft:
        return "soft", tokens
    return "ok", tokens


class _EventDedup:
    """Bounded LRU set used to drop duplicate events across polls."""

    def __init__(self, capacity: int = _DEDUP_MAX) -> None:
        self._seen: OrderedDict[tuple[int, str, str], None] = OrderedDict()
        self._cap = capacity

    def is_new(self, port: int, role: str, event_id: str) -> bool:
        key = (port, role, event_id)
        if key in self._seen:
            self._seen.move_to_end(key)
            return False
        self._seen[key] = None
        if len(self._seen) > self._cap:
            self._seen.popitem(last=False)
        return True

    def forget(self, port: int, role: str, event_id: str) -> None:
        """Drop a key from the dedup cache so the event may be re-processed."""
        self._seen.pop((port, role, event_id), None)


def _interval_seconds(interval: str | None) -> int:
    if not interval:
        try:
            interval = load_gru_config().poll_interval_default
        except Exception:
            interval = "1m"
    try:
        return max(5, parse_duration(interval))
    except Exception:
        return 60


def _role_schedulable(role: Any) -> bool:
    return getattr(role, "state", None) in {"active", "sleeping"}


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


def _role_task_domains(role_name: str) -> set[str]:
    return set(role_agent_domains(role_name)) - _GENERIC_TASK_DOMAINS


def _task_match_reason(task: dict[str, Any], role_name: str) -> str | None:
    if role_name in _task_invited_agent_ids(task):
        return "invited_agent_ids"
    domains = _task_domains(task)
    if domains & _role_task_domains(role_name):
        return "domain"
    return None


def _event_task_id(event: dict[str, Any]) -> str:
    direct = event.get("task_id") or event.get("id")
    if direct and str(direct).startswith(("t-", "gru-")):
        return str(direct)
    payload = event.get("payload")
    if isinstance(payload, dict):
        task_id = payload.get("task_id")
        if task_id:
            return str(task_id)
        content = payload.get("content")
        if isinstance(content, dict) and content.get("task_id"):
            return str(content["task_id"])
        task = payload.get("task")
        if isinstance(task, dict):
            return _task_id(task)
    content = event.get("content")
    if isinstance(content, dict) and content.get("task_id"):
        return str(content["task_id"])
    return ""


def _open_task_event(task: dict[str, Any], role_name: str, matched_by: str) -> dict[str, Any]:
    task_id = _task_id(task)
    return {
        "type": "task_broadcast",
        "id": f"open-task:{task_id}:{role_name}",
        "task_id": task_id,
        "payload": {
            "source": "tasks_open_scan",
            "matched_by": matched_by,
            "content": task.get("content") or {},
            "domains": list(_task_domains(task)),
            "budget": task.get("budget"),
            "deadline": task.get("deadline"),
            "max_concurrent_bidders": task.get("max_concurrent_bidders"),
            "invited_agent_ids": task.get("invited_agent_ids") or [],
            "task": task,
        },
    }


InvokeFn = Callable[[str, int, list[dict[str, Any]]], Awaitable[None] | None]


class WakeupScheduler:
    """Polls EACN on behalf of registered Roles; dispatches ephemeral invocations.

    Args:
        store: StateStore (optional; one is created if omitted).
        invoke_fn: Coroutine or function called as
            ``invoke_fn(role_name, port, events)`` when events arrive.
            Defaults to :func:`minions.lifecycle.role.invoke_role_ephemeral`.
        default_interval: fallback poll cadence string (e.g. ``"1m"``).
    """

    def __init__(
        self,
        store: StateStore | None = None,
        invoke_fn: InvokeFn | None = None,
        default_interval: str | None = None,
        config: GruConfig | None = None,
        *,
        state_store: StateStore | None = None,
        cooldown_seconds: int | None = None,
    ) -> None:
        # Accept `state_store=` as an alias for `store=` (the docs and some
        # callers use the longer name). Reject passing both at once.
        if state_store is not None and store is not None:
            raise TypeError("WakeupScheduler: pass either 'store' or 'state_store', not both.")
        self._store = store or state_store or StateStore()
        self._invoke_fn = invoke_fn
        self._default_interval = default_interval
        self._dedup = _EventDedup()
        self._stopped = False
        self._last_poll_ts: dict[tuple[int, str], float] = {}
        self._last_open_task_scan_ts: dict[int, float] = {}
        # Resolve scratchpad thresholds once per scheduler instance from
        # config (percentages of the model context window). Stored as
        # (soft, hard, veto) token counts.
        cfg = config
        if cfg is None:
            try:
                cfg = load_gru_config()
            except Exception:
                cfg = GruConfig()
        self._scratchpad_thresholds: tuple[int, int, int] = _compute_thresholds(cfg)
        # Per-role cooldown: minimum seconds between any dispatch.
        self._cooldown_seconds: int = (
            cooldown_seconds if cooldown_seconds is not None else cfg.role_cooldown_seconds
        )
        # Tracks last dispatch time per (port, role) for cooldown enforcement.
        self._last_dispatch_ts: dict[tuple[int, str], float] = {}
        # Tracks last time-trigger dispatch per (port, role).
        self._last_time_trigger_ts: dict[tuple[int, str], float] = {}
        # Set of (port, role) for which a veto warning has already been posted
        # to Gru; cleared when the scratchpad drops below the veto threshold.
        self._veto_warned: set[tuple[int, str]] = set()
        # Legacy in-memory view for diagnostics only. Durable deferrals live in
        # role_inbox so scheduler restarts do not drop drained EACN events.
        self._pending: dict[tuple[int, str], list[dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def stop(self) -> None:
        self._stopped = True

    async def run_async(self, tick_seconds: float = 1.0) -> None:
        """Run the scheduler until :meth:`stop` is called."""
        logger.info("WakeupScheduler started (tick=%.1fs).", tick_seconds)
        while not self._stopped:
            try:
                await self._tick()
            except Exception as exc:
                logger.error("WakeupScheduler tick error: %s", exc, exc_info=True)
            await asyncio.sleep(tick_seconds)
        logger.info("WakeupScheduler stopped.")

    async def tick_once(self) -> int:
        """Run one tick; return number of ephemeral invocations triggered."""
        return await self._tick()

    def trigger_role(
        self,
        port: int,
        role_name: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Immediately dispatch a human-triggered wakeup for a role.

        Respects cooldown and in-flight guards. Raises ``ValueError`` if the
        role is not found or not dispatchable.
        """
        project = self._store.get_project(port)
        if project is None:
            raise ValueError(f"Project {port} not found.")
        role = next(
            (r for r in project.active_roles if r.name == role_name and _role_schedulable(r)),
            None,
        )
        if role is None:
            raise ValueError(f"Active/sleeping role {role_name!r} on port {port} not found.")

        key = (port, role_name)
        if not self._is_cooled_down(key):
            logger.info(
                "trigger_role: cooldown active for role=%s port=%d; skipped.",
                role_name,
                port,
            )
            return {"triggered": False, "reason": "cooldown"}

        try:
            from minions.lifecycle.role import is_inflight

            if is_inflight(port, role_name):
                logger.info(
                    "trigger_role: role=%s port=%d in flight; skipped.",
                    role_name,
                    port,
                )
                return {"triggered": False, "reason": "in_flight"}
        except Exception:
            pass

        synthetic = [
            {
                "type": "human_trigger",
                "id": f"human-{_time_mod.monotonic():.0f}",
                "reason": reason or "manual trigger",
            }
        ]

        fn = self._invoke_fn
        if fn is None:
            from minions.lifecycle.role import invoke_role_ephemeral

            fn = invoke_role_ephemeral  # type: ignore[assignment]

        project_memory_dir(port).mkdir(parents=True, exist_ok=True)
        status, _tokens = _scratchpad_status(port, role_name, self._scratchpad_thresholds)
        if status == "veto":
            logger.warning("trigger_role: scratchpad veto for role=%s port=%d", role_name, port)
            return {"triggered": False, "reason": "scratchpad_veto"}

        logger.info(
            "Wakeup: dispatching role=%s port=%d wakeup_class=human reason=%r",
            role_name,
            port,
            reason,
        )
        try:
            fn(  # type: ignore[misc]
                role_name,
                port,
                synthetic,
                extra_env={
                    "MINIONS_SCRATCHPAD_STATUS": status,
                    "MINIONS_WAKEUP_CLASS": "human",
                },
            )
        except TypeError:
            fn(role_name, port, synthetic)  # type: ignore[misc]
        self._last_dispatch_ts[key] = _time_mod.monotonic()
        return {"triggered": True, "wakeup_class": "human"}

    def _is_cooled_down(self, key: tuple[int, str]) -> bool:
        """Return True if enough time has passed since the last dispatch."""
        if self._cooldown_seconds <= 0:
            return True
        last = self._last_dispatch_ts.get(key)
        if last is None:
            return True
        return (_time_mod.monotonic() - last) >= self._cooldown_seconds

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _tick(self) -> int:
        now = _time_mod.monotonic()
        triggered = 0
        projects = self._store.list_projects(filter="active")
        for project in projects:
            try:
                await asyncio.to_thread(self._drain_gru_inbox, project.port)
            except Exception as exc:
                logger.debug("gru inbox drain failed port=%d: %s", project.port, exc)

            roles = [role for role in project.active_roles if _role_schedulable(role)]
            open_task_events = await self._open_task_events_for_roles(project.port, roles, now)

            for role in roles:
                key = (project.port, role.name)
                buffered = await asyncio.to_thread(role_inbox.read_events, project.port, role.name)
                events = list(buffered)
                event_ids = {_event_id(e) for e in events}
                known_task_ids = {_event_task_id(e) for e in events if _event_task_id(e)}

                interval = _interval_seconds(role.poll_interval or self._default_interval)
                last = self._last_poll_ts.get(key)
                if last is None or now - last >= interval:
                    self._last_poll_ts[key] = now
                    polled = await asyncio.to_thread(self._safe_poll, project.port, role.name)
                    for event in polled:
                        event_id = _event_id(event)
                        if event_id in event_ids:
                            continue
                        if self._dedup.is_new(project.port, role.name, event_id):
                            events.append(event)
                            event_ids.add(event_id)
                            task_id = _event_task_id(event)
                            if task_id:
                                known_task_ids.add(task_id)

                for event in open_task_events.get(role.name, []):
                    task_id = _event_task_id(event)
                    if task_id and task_id in known_task_ids:
                        continue
                    event_id = _event_id(event)
                    if event_id in event_ids:
                        continue
                    if self._dedup.is_new(project.port, role.name, event_id):
                        events.append(event)
                        event_ids.add(event_id)
                        if task_id:
                            known_task_ids.add(task_id)

                new_events = [e for e in events if isinstance(e, dict)]

                if new_events:
                    # Persist before dispatch. If the scheduler crashes after
                    # draining EACN but before launching the role, the next tick
                    # replays the same batch from disk.
                    role_inbox.replace_events(project.port, role.name, new_events)
                    result = await self._try_dispatch(
                        project.port,
                        role.name,
                        new_events,
                        WakeupClass.event,
                        reason=f"{len(new_events)} EACN event(s)",
                    )
                    if result == "dispatched":
                        role_inbox.clear(project.port, role.name)
                        self._pending.pop((project.port, role.name), None)
                        triggered += 1
                    continue

                # Time-triggered wakeup: fire even without EACN events.
                time_interval_str = getattr(role, "time_trigger_interval", None)
                if not time_interval_str:
                    continue
                try:
                    time_interval = max(5, parse_duration(time_interval_str))
                except Exception:
                    continue
                tt_key = (project.port, role.name)
                last_tt = self._last_time_trigger_ts.get(tt_key)
                if last_tt is not None and now - last_tt < time_interval:
                    continue
                synthetic = [
                    {
                        "type": "time_trigger",
                        "id": f"time-{now:.0f}",
                        "interval": time_interval_str,
                    }
                ]
                role_inbox.replace_events(project.port, role.name, synthetic)
                result = await self._try_dispatch(
                    project.port,
                    role.name,
                    synthetic,
                    WakeupClass.time,
                    reason=f"periodic {time_interval_str} timer",
                )
                if result == "dispatched":
                    role_inbox.clear(project.port, role.name)
                    self._pending.pop((project.port, role.name), None)
                    self._last_time_trigger_ts[tt_key] = now
                    triggered += 1
        return triggered

    async def _try_dispatch(
        self,
        port: int,
        role_name: str,
        events: list[dict[str, Any]],
        wakeup_class: WakeupClass,
        reason: str = "",
    ) -> str:
        """Gate checks then dispatch. Returns 'dispatched', 'deferred', or 'blocked'."""
        key = (port, role_name)

        try:
            from minions.lifecycle.role import is_inflight

            if is_inflight(port, role_name):
                logger.info(
                    "Wakeup: role=%s port=%d still in flight; deferring %d event(s) to next tick.",
                    role_name,
                    port,
                    len(events),
                )
                self._buffer_role_events(port, role_name, events)
                return "deferred"
        except Exception as exc:
            logger.debug("is_inflight check failed: %s", exc)

        if not self._is_cooled_down(key):
            logger.info(
                "Wakeup: role=%s port=%d cooldown active; deferring %d event(s) to next tick.",
                role_name,
                port,
                len(events),
            )
            self._buffer_role_events(port, role_name, events)
            return "deferred"

        project_memory_dir(port).mkdir(parents=True, exist_ok=True)
        status, tokens = _scratchpad_status(port, role_name, self._scratchpad_thresholds)
        if status == "veto":
            if key not in self._veto_warned:
                self._post_veto_warning(port, role_name, tokens)
                self._veto_warned.add(key)
            self._buffer_role_events(port, role_name, events)
            return "blocked"
        else:
            self._veto_warned.discard(key)

        logger.info(
            "Wakeup: dispatching %d event(s) to role=%s port=%d wakeup_class=%s reason=%r",
            len(events),
            role_name,
            port,
            wakeup_class.value,
            reason,
        )
        try:
            res = await self._dispatch(role_name, port, events, status, wakeup_class)
        except Exception as exc:
            logger.error(
                "Wakeup: dispatch failed role=%s port=%d; buffering %d event(s): %s",
                role_name,
                port,
                len(events),
                exc,
            )
            self._buffer_role_events(port, role_name, events)
            return "deferred"
        if isinstance(res, dict) and res.get("deferred"):
            self._buffer_role_events(port, role_name, events)
            return "deferred"
        for event in events:
            self._dedup.is_new(port, role_name, _event_id(event))
        self._last_dispatch_ts[key] = _time_mod.monotonic()
        return "dispatched"

    def _buffer_role_events(
        self,
        port: int,
        role_name: str,
        events: list[dict[str, Any]],
    ) -> None:
        role_inbox.replace_events(port, role_name, events)
        self._pending[(port, role_name)] = list(events)
        for event in events:
            self._dedup.forget(port, role_name, _event_id(event))

    async def _open_task_events_for_roles(
        self,
        port: int,
        roles: list[Any],
        now: float,
    ) -> dict[str, list[dict[str, Any]]]:
        if not roles:
            return {}
        interval = _interval_seconds(self._default_interval or "1m")
        last = self._last_open_task_scan_ts.get(port)
        if last is not None and now - last < interval:
            return {}
        self._last_open_task_scan_ts[port] = now
        tasks = await asyncio.to_thread(self._safe_list_open_tasks, port)
        if not tasks:
            return {}

        by_role: dict[str, list[dict[str, Any]]] = {role.name: [] for role in roles}
        role_names = [role.name for role in roles]
        for task in tasks:
            task_id = _task_id(task)
            if not task_id:
                continue
            matches: list[tuple[str, str]] = []
            invited = _task_invited_agent_ids(task)
            if invited:
                matches = [
                    (role_name, "invited_agent_ids")
                    for role_name in role_names
                    if role_name in invited
                ]
            else:
                matches = [
                    (
                        role_name,
                        "domain"
                        if _task_match_reason(task, role_name) == "domain"
                        else "public_open_task",
                    )
                    for role_name in role_names
                ]
            for role_name, reason in matches:
                by_role.setdefault(role_name, []).append(_open_task_event(task, role_name, reason))
        return by_role

    def _safe_poll(self, port: int, agent_id: str) -> list[dict[str, Any]]:
        try:
            payload = poll_events(port, agent_id, timeout_secs=0, http_timeout=5.0)
        except Exception as exc:
            logger.debug("poll_events failed role=%s port=%d: %s", agent_id, port, exc)
            return []
        events = payload.get("events") or payload.get("messages") or []
        return list(events) if isinstance(events, list) else []

    def _safe_list_open_tasks(self, port: int) -> list[dict[str, Any]]:
        try:
            return list_open_tasks(port, limit=100, timeout=1.0)
        except Exception as exc:
            logger.debug("list_open_tasks failed port=%d: %s", port, exc)
            return []

    def _drain_gru_inbox(self, port: int) -> int:
        """Poll the project's ``gru`` agent and append new events to the on-disk inbox.

        Deduplicates via the same LRU as role events (keyed by agent ``"gru"``).
        Rate-limited per-project by ``_default_interval`` so we don't hammer
        the backend. Returns number of events appended.
        """
        import time as _t

        try:
            gru_id = load_gru_config().gru_eacn_agent_id
        except Exception:
            gru_id = "gru"
        key = (port, f"__inbox__{gru_id}")
        now = _t.monotonic()
        last = self._last_poll_ts.get(key)
        interval = _interval_seconds(self._default_interval or "1m")
        if last is not None and now - last < interval:
            return 0
        self._last_poll_ts[key] = now

        events = self._safe_poll(port, gru_id)
        if not events:
            return 0
        new_events = [e for e in events if self._dedup.is_new(port, gru_id, _event_id(e))]
        if not new_events:
            return 0
        n = gru_inbox.append_events(port, new_events)
        logger.info("gru inbox: appended %d event(s) port=%d", n, port)
        return n

    async def _dispatch(
        self,
        role_name: str,
        port: int,
        events: list[dict[str, Any]],
        scratchpad_status: str = "ok",
        wakeup_class: WakeupClass = WakeupClass.event,
    ) -> Any:
        fn = self._invoke_fn
        if fn is None:
            from minions.lifecycle.role import invoke_role_ephemeral

            fn = invoke_role_ephemeral  # type: ignore[assignment]
        extra_env = {
            "MINIONS_SCRATCHPAD_STATUS": scratchpad_status,
            "MINIONS_WAKEUP_CLASS": wakeup_class.value,
        }
        try:
            res = fn(  # type: ignore[misc]
                role_name,
                port,
                events,
                extra_env=extra_env,
            )
        except TypeError:
            # Backwards-compatible: test doubles may accept only 3 args.
            res = fn(role_name, port, events)  # type: ignore[misc]
        if asyncio.iscoroutine(res):
            return await res
        return res

    def _post_veto_warning(self, port: int, role_name: str, tokens: int) -> None:
        veto = self._scratchpad_thresholds[2]
        msg = (
            f"Scratchpad for role={role_name} port={port} exceeds "
            f"{veto} tokens (actual: {tokens}); aborted "
            "wake-up. Compress scratchpad manually or dismiss+re-register the role."
        )
        logger.warning(msg)
        try:
            gru_agent_id = load_gru_config().gru_eacn_agent_id
        except Exception:
            gru_agent_id = "gru"
        try:
            send_message(port, to_agent_id=gru_agent_id, from_agent_id="wakeup", content=msg)
        except Exception as exc:
            logger.error("Failed to post scratchpad veto warning to Gru: %s", exc)


def _event_id(event: dict[str, Any]) -> str:
    for key in ("id", "event_id", "message_id", "uuid"):
        v = event.get(key)
        if v:
            return str(v)
    # Fallback: stable hash of the JSON body.
    try:
        return str(hash(json.dumps(event, sort_keys=True, default=str)))
    except Exception:
        return str(id(event))
