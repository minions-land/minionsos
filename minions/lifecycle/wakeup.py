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
import json
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from minions.config import GruConfig, load_gru_config, parse_duration
from minions.lifecycle import gru_inbox, role_inbox
from minions.lifecycle.eacn_client import poll_events, post_message
from minions.paths import project_memory_dir, project_scratchpad
from minions.state.store import StateStore

logger = logging.getLogger(__name__)

_DEDUP_MAX = 2048


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
        # Set of (port, role) for which a veto warning has already been posted
        # to Gru; cleared when the scratchpad drops below the veto threshold.
        self._veto_warned: set[tuple[int, str]] = set()
        # Deferred event batches when (port, role) is still in-flight from a
        # previous tick. Merged into the next tick's events so nothing is
        # dropped.
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

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _tick(self) -> int:
        import time

        now = time.monotonic()
        triggered = 0
        projects = self._store.list_projects(filter="active")
        for project in projects:
            # Drain the gru passive-mailbox inbox for this project (no
            # Claude subprocess: Gru consumes via gru_inbox_poll MCP tool).
            try:
                await asyncio.to_thread(self._drain_gru_inbox, project.port)
            except Exception as exc:
                logger.debug("gru inbox drain failed port=%d: %s", project.port, exc)
            for role in project.active_roles:
                if role.state != "active":
                    continue
                interval = _interval_seconds(role.poll_interval or self._default_interval)
                key = (project.port, role.name)
                last = self._last_poll_ts.get(key)
                # First tick for this (port, role) is always eligible; we
                # compare against an explicit 'last' only on subsequent ticks.
                # Using a default of 0.0 here would be wrong on short-uptime
                # hosts (e.g. GitHub Actions runners) where time.monotonic()
                # is itself smaller than the poll interval.
                if last is not None and now - last < interval:
                    continue
                self._last_poll_ts[key] = now

                # Drain any events that a previous tick's veto gate parked
                # on disk; process them BEFORE polling EACN3 again so we
                # don't widen the gap between fetch and dispatch.
                buffered = await asyncio.to_thread(role_inbox.drain, project.port, role.name)
                events = await asyncio.to_thread(self._safe_poll, project.port, role.name)
                if buffered:
                    events = buffered + list(events)
                new_events = [
                    e
                    for e in (events or [])
                    if self._dedup.is_new(project.port, role.name, _event_id(e))
                ]
                # Prepend events deferred from a previous tick (in-flight guard).
                pending = self._pending.pop((project.port, role.name), [])
                new_events = pending + new_events
                if not new_events:
                    continue
                # In-flight guard: do NOT launch a second ephemeral process for
                # the same (port, role) while the previous is still running.
                # Defer to next tick; do not drop.
                try:
                    from minions.lifecycle.role import is_inflight

                    if is_inflight(project.port, role.name):
                        logger.info(
                            "Wakeup: role=%s port=%d still in flight; deferring "
                            "%d event(s) to next tick.",
                            role.name,
                            project.port,
                            len(new_events),
                        )
                        self._pending[(project.port, role.name)] = new_events
                        continue
                except Exception as exc:
                    logger.debug("is_inflight check failed: %s", exc)
                logger.info(
                    "Wakeup: dispatching %d event(s) to role=%s port=%d",
                    len(new_events),
                    role.name,
                    project.port,
                )
                # Scratchpad gate before dispatch.
                project_memory_dir(project.port).mkdir(parents=True, exist_ok=True)
                status, tokens = _scratchpad_status(
                    project.port, role.name, self._scratchpad_thresholds
                )
                pr_key = (project.port, role.name)
                if status == "veto":
                    if pr_key not in self._veto_warned:
                        self._post_veto_warning(project.port, role.name, tokens)
                        self._veto_warned.add(pr_key)
                    # Do NOT dispatch. Persist events to an on-disk buffer
                    # so the next tick re-delivers them (the EACN3 poll we
                    # already issued was destructive), and forget them from
                    # the dedup cache so they don't get suppressed on replay.
                    role_inbox.append_events(project.port, role.name, new_events)
                    for e in new_events:
                        self._dedup.forget(project.port, role.name, _event_id(e))
                    continue
                else:
                    self._veto_warned.discard(pr_key)
                await self._dispatch(role.name, project.port, new_events, status)
                triggered += 1
        return triggered

    def _safe_poll(self, port: int, agent_id: str) -> list[dict[str, Any]]:
        try:
            payload = poll_events(port, agent_id, timeout_secs=0, http_timeout=5.0)
        except Exception as exc:
            logger.debug("poll_events failed role=%s port=%d: %s", agent_id, port, exc)
            return []
        events = payload.get("events") or payload.get("messages") or []
        return list(events) if isinstance(events, list) else []

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
    ) -> None:
        fn = self._invoke_fn
        if fn is None:
            from minions.lifecycle.role import invoke_role_ephemeral

            fn = invoke_role_ephemeral  # type: ignore[assignment]
        try:
            res = fn(  # type: ignore[misc]
                role_name,
                port,
                events,
                extra_env={"MINIONS_SCRATCHPAD_STATUS": scratchpad_status},
            )
        except TypeError:
            # Backwards-compatible: test doubles may accept only 3 args.
            res = fn(role_name, port, events)  # type: ignore[misc]
        if asyncio.iscoroutine(res):
            await res

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
            post_message(port, to_agent_id=gru_agent_id, from_agent_id="wakeup", content=msg)
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
