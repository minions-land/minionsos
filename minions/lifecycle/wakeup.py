"""Per-(port, role) EACN3 long-poll scheduler.

This is the only encapsulation MinionsOS puts in front of EACN3. For each
registered role on each active project, the scheduler runs one asyncio task
that:

1. Long-polls ``GET /api/events/{agent_id}`` in 60s chunks (EACN3's hard cap).
2. When events arrive, spawns one role subprocess with those events in its
   init prompt, then awaits the subprocess exit before looping back.
3. When the role has a configured time-trigger cadence (e.g. Noter's periodic
   summary), fires a synthetic ``time_trigger`` event once the interval
   elapses with no EACN events.

The scheduler does not ACK or journal events. If a role subprocess crashes
mid-wake, those events are gone — MinionsOS's HTTP path through EACN3 is
drain-on-read, and we accept that on purpose rather than growing a second
communication system.

Public surface used by callers (``minions.gru.loop``, tests):

* ``WakeupScheduler(store=..., invoke_fn=..., config=..., cooldown_seconds=...)``
* ``await sched.run_async()`` — drive the scheduler until ``stop()`` is called.
* ``sched.stop()`` — cooperative cancellation.
* ``sched.trigger_role(port, role_name, reason="")`` — synchronous human trigger.
* ``WakeupClass`` — tag for logging / env propagation.
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
import logging
import time as _time_mod
from collections.abc import Awaitable, Callable
from typing import Any

from minions.config import GruConfig, load_gru_config, parse_duration
from minions.lifecycle.eacn_client import poll_events, send_message
from minions.paths import project_memory_dir, project_scratchpad
from minions.state.store import StateStore

logger = logging.getLogger(__name__)

# EACN3's /api/events/{agent_id}?timeout=N is capped at 60s server-side.
EACN3_POLL_CHUNK_SEC = 60
# If an agent's loop crashes for a transient reason, pause before restarting.
_LOOP_RESTART_BACKOFF_SEC = 5.0
# Scratchpad compaction cooldown to avoid hammering the role with maintenance wakes.
_VETO_COMPACTION_COOLDOWN_SECONDS = 10 * 60


class WakeupClass(enum.Enum):
    """Classification of what triggered a role wakeup (kept for logging/env tags)."""

    event = "event"
    time = "time"
    human = "human"
    maintenance = "maintenance"


InvokeFn = Callable[..., Awaitable[Any] | Any]


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: len/4 (±20% vs true BPE tokenizers)."""
    return len(text) // 4


def _compute_thresholds(cfg: GruConfig) -> tuple[int, int, int]:
    """Compute (soft, hard, veto) scratchpad token thresholds from config."""
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


def _role_schedulable(role: Any) -> bool:
    return getattr(role, "state", None) in {"active", "sleeping"}


class WakeupScheduler:
    """Drives one asyncio loop per (port, role) that long-polls EACN3 and wakes the role.

    Args:
        store: StateStore (optional; one is created if omitted).
        invoke_fn: Callable invoked as ``invoke_fn(role_name, port, events, extra_env=...)``
            when events arrive. Defaults to ``invoke_role_ephemeral``. May be
            sync or async; may return a coroutine. Expected to block until the
            role subprocess exits (or to return a dispatch handle that we then
            await via ``wait=True``).
        config: Optional GruConfig override (mostly for tests).
        cooldown_seconds: Minimum seconds between dispatches for the same role.
    """

    def __init__(
        self,
        store: StateStore | None = None,
        invoke_fn: InvokeFn | None = None,
        config: GruConfig | None = None,
        *,
        state_store: StateStore | None = None,
        cooldown_seconds: int | None = None,
    ) -> None:
        if state_store is not None and store is not None:
            raise TypeError("WakeupScheduler: pass either 'store' or 'state_store', not both.")
        self._store = store or state_store or StateStore()
        self._invoke_fn = invoke_fn
        self._stopped = False
        cfg = config
        if cfg is None:
            try:
                cfg = load_gru_config()
            except Exception:
                cfg = GruConfig()
        self._cfg = cfg
        self._scratchpad_thresholds: tuple[int, int, int] = _compute_thresholds(cfg)
        self._cooldown_seconds: int = (
            cooldown_seconds if cooldown_seconds is not None else cfg.role_cooldown_seconds
        )
        self._last_dispatch_ts: dict[tuple[int, str], float] = {}
        self._last_veto_compaction_ts: dict[tuple[int, str], float] = {}
        self._veto_warned: set[tuple[int, str]] = set()
        # Per-(port, role) async loop tasks. Keyed task is alive as long as
        # the role is registered. When the role is dismissed or the project
        # closes, we cancel the task and drop the entry.
        self._tasks: dict[tuple[int, str], asyncio.Task[None]] = {}
        # Supervisor scan cadence: how often we refresh the registered-role set
        # and start / cancel per-role loop tasks accordingly.
        self._supervisor_interval_sec: float = 2.0

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def stop(self) -> None:
        self._stopped = True

    async def run_async(self) -> None:
        """Supervise per-(port, role) loops until :meth:`stop` is called."""
        logger.info("WakeupScheduler started.")
        try:
            while not self._stopped:
                try:
                    self._reconcile_tasks()
                except Exception as exc:
                    logger.error("WakeupScheduler reconcile error: %s", exc, exc_info=True)
                await asyncio.sleep(self._supervisor_interval_sec)
        finally:
            await self._cancel_all_tasks()
        logger.info("WakeupScheduler stopped.")

    def trigger_role(
        self,
        port: int,
        role_name: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Immediately dispatch a human-triggered wakeup for a role.

        Runs inline (no loop interaction). Respects cooldown and in-flight guards.
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

        project_memory_dir(port).mkdir(parents=True, exist_ok=True)
        status, _tokens = _scratchpad_status(port, role_name, self._scratchpad_thresholds)
        if status == "veto":
            logger.warning("trigger_role: scratchpad veto for role=%s port=%d", role_name, port)
            return {"triggered": False, "reason": "scratchpad_veto"}

        synthetic = [
            {
                "type": "human_trigger",
                "id": f"human-{_time_mod.monotonic():.0f}",
                "reason": reason or "manual trigger",
            }
        ]
        logger.info(
            "Wakeup: dispatching role=%s port=%d wakeup_class=human reason=%r",
            role_name,
            port,
            reason,
        )
        fn = self._resolve_invoke_fn()
        try:
            fn(
                role_name,
                port,
                synthetic,
                extra_env={
                    "MINIONS_SCRATCHPAD_STATUS": status,
                    "MINIONS_WAKEUP_CLASS": "human",
                },
            )
        except TypeError:
            fn(role_name, port, synthetic)
        self._last_dispatch_ts[key] = _time_mod.monotonic()
        return {"triggered": True, "wakeup_class": "human"}

    # ------------------------------------------------------------------
    # Task supervision
    # ------------------------------------------------------------------

    def _reconcile_tasks(self) -> None:
        """Start loops for newly registered roles and cancel loops for retired ones."""
        projects = self._store.list_projects(filter="active")
        live_keys: set[tuple[int, str]] = set()
        for project in projects:
            for role in project.active_roles:
                if not _role_schedulable(role):
                    continue
                agent_id = getattr(role, "eacn_agent_id", None) or role.name
                key = (int(project.port), role.name)
                live_keys.add(key)
                existing = self._tasks.get(key)
                if existing is not None and not existing.done():
                    continue
                self._tasks[key] = asyncio.create_task(
                    self._role_loop(
                        port=int(project.port),
                        role_name=role.name,
                        agent_id=str(agent_id),
                    ),
                    name=f"wakeup:{project.port}:{role.name}",
                )
        # Cancel any task whose role is no longer present / schedulable.
        for key in list(self._tasks.keys()):
            if key in live_keys:
                continue
            task = self._tasks.pop(key, None)
            if task is not None and not task.done():
                task.cancel()

    async def _cancel_all_tasks(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()

    # ------------------------------------------------------------------
    # Per-role loop
    # ------------------------------------------------------------------

    async def _role_loop(self, port: int, role_name: str, agent_id: str) -> None:
        """Long-poll EACN3 and dispatch wakes until cancelled."""
        time_interval = self._resolve_time_trigger_interval(port, role_name)
        time_budget_remaining = time_interval  # None when role has no timer
        try:
            while not self._stopped:
                try:
                    events = await asyncio.to_thread(
                        self._safe_poll, port, agent_id, EACN3_POLL_CHUNK_SEC
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "Wakeup loop: poll failed port=%d role=%s: %s; backing off.",
                        port,
                        role_name,
                        exc,
                    )
                    await asyncio.sleep(_LOOP_RESTART_BACKOFF_SEC)
                    continue

                if events:
                    await self._dispatch_wake(
                        port=port,
                        role_name=role_name,
                        events=events,
                        wakeup_class=WakeupClass.event,
                        reason=f"{len(events)} EACN event(s)",
                    )
                    # After a wake, reset the time trigger budget.
                    time_budget_remaining = time_interval
                    continue

                # Empty 60s chunk — advance time-trigger budget if configured.
                if time_interval is None or time_budget_remaining is None:
                    continue
                time_budget_remaining -= EACN3_POLL_CHUNK_SEC
                if time_budget_remaining > 0:
                    continue
                synthetic = [
                    {
                        "type": "time_trigger",
                        "id": f"time-{int(_time_mod.monotonic())}",
                        "interval_seconds": time_interval,
                    }
                ]
                await self._dispatch_wake(
                    port=port,
                    role_name=role_name,
                    events=synthetic,
                    wakeup_class=WakeupClass.time,
                    reason=f"periodic {time_interval}s timer",
                )
                time_budget_remaining = time_interval
        except asyncio.CancelledError:
            logger.debug("Wakeup loop cancelled port=%d role=%s", port, role_name)
            raise
        except Exception as exc:
            logger.error(
                "Wakeup loop crashed port=%d role=%s: %s",
                port,
                role_name,
                exc,
                exc_info=True,
            )

    def _resolve_time_trigger_interval(self, port: int, role_name: str) -> int | None:
        """Look up the role's time_trigger cadence in seconds, or None."""
        try:
            project = self._store.get_project(port)
        except Exception:
            return None
        if project is None:
            return None
        role = next((r for r in project.active_roles if r.name == role_name), None)
        if role is None:
            return None
        raw = getattr(role, "time_trigger_interval", None)
        if not raw:
            return None
        try:
            secs = parse_duration(raw)
        except Exception:
            return None
        return secs if secs > 0 else None

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def _dispatch_wake(
        self,
        *,
        port: int,
        role_name: str,
        events: list[dict[str, Any]],
        wakeup_class: WakeupClass,
        reason: str,
    ) -> None:
        """Apply cooldown / scratchpad gates and invoke the role; await subprocess exit."""
        key = (port, role_name)

        # Cooldown. When tripped we drop the event batch; the role will
        # receive the next EACN event on its next long-poll iteration.
        if not self._is_cooled_down(key):
            logger.info(
                "Wakeup: role=%s port=%d cooldown active; dropping %d event(s).",
                role_name,
                port,
                len(events),
            )
            return

        project_memory_dir(port).mkdir(parents=True, exist_ok=True)
        status, tokens = _scratchpad_status(port, role_name, self._scratchpad_thresholds)
        if status == "veto":
            if key not in self._veto_warned:
                self._post_veto_warning(port, role_name, tokens)
                self._veto_warned.add(key)
            await self._try_dispatch_veto_compaction(port, role_name, tokens)
            return
        self._veto_warned.discard(key)

        logger.info(
            "Wakeup: dispatching %d event(s) to role=%s port=%d wakeup_class=%s reason=%r",
            len(events),
            role_name,
            port,
            wakeup_class.value,
            reason,
        )
        self._last_dispatch_ts[key] = _time_mod.monotonic()
        await self._invoke_and_wait(
            role_name=role_name,
            port=port,
            events=events,
            scratchpad_status=status,
            wakeup_class=wakeup_class,
        )

    async def _try_dispatch_veto_compaction(
        self,
        port: int,
        role_name: str,
        tokens: int,
    ) -> None:
        """Dispatch a maintenance-only compaction wakeup."""
        key = (port, role_name)
        now = _time_mod.monotonic()
        last = self._last_veto_compaction_ts.get(key)
        if last is not None and now - last < _VETO_COMPACTION_COOLDOWN_SECONDS:
            return
        synthetic = [
            {
                "type": "scratchpad_compaction_required",
                "id": f"scratchpad-veto:{port}:{role_name}:{int(now)}",
                "role": role_name,
                "tokens": tokens,
                "veto_tokens": self._scratchpad_thresholds[2],
            }
        ]
        logger.info(
            "Wakeup: dispatching scratchpad compaction to role=%s port=%d tokens=%d",
            role_name,
            port,
            tokens,
        )
        self._last_veto_compaction_ts[key] = now
        self._last_dispatch_ts[key] = now
        await self._invoke_and_wait(
            role_name=role_name,
            port=port,
            events=synthetic,
            scratchpad_status="veto_compact",
            wakeup_class=WakeupClass.maintenance,
        )

    async def _invoke_and_wait(
        self,
        *,
        role_name: str,
        port: int,
        events: list[dict[str, Any]],
        scratchpad_status: str,
        wakeup_class: WakeupClass,
    ) -> None:
        """Invoke the role, block the per-role loop until the subprocess exits."""
        fn = self._resolve_invoke_fn()
        extra_env = {
            "MINIONS_SCRATCHPAD_STATUS": scratchpad_status,
            "MINIONS_WAKEUP_CLASS": wakeup_class.value,
        }
        loop = asyncio.get_running_loop()

        def _call() -> Any:
            try:
                return fn(role_name, port, events, extra_env=extra_env, wait=True)
            except TypeError:
                # Older test doubles may not accept wait= / extra_env=.
                try:
                    return fn(role_name, port, events, extra_env=extra_env)
                except TypeError:
                    return fn(role_name, port, events)

        try:
            result = await loop.run_in_executor(None, _call)
        except Exception as exc:
            logger.error(
                "Wakeup: invoke failed role=%s port=%d: %s",
                role_name,
                port,
                exc,
                exc_info=True,
            )
            return
        if asyncio.iscoroutine(result):
            with contextlib.suppress(Exception):
                await result

    def _resolve_invoke_fn(self) -> InvokeFn:
        fn = self._invoke_fn
        if fn is not None:
            return fn
        from minions.lifecycle.role import invoke_role_ephemeral

        return invoke_role_ephemeral

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_cooled_down(self, key: tuple[int, str]) -> bool:
        if self._cooldown_seconds <= 0:
            return True
        last = self._last_dispatch_ts.get(key)
        if last is None:
            return True
        return (_time_mod.monotonic() - last) >= self._cooldown_seconds

    def _safe_poll(self, port: int, agent_id: str, timeout_secs: int) -> list[dict[str, Any]]:
        try:
            payload = poll_events(
                port,
                agent_id,
                timeout_secs=timeout_secs,
                http_timeout=timeout_secs + 10.0,
            )
        except Exception as exc:
            logger.debug("poll_events failed role=%s port=%d: %s", agent_id, port, exc)
            raise
        events = payload.get("events") or payload.get("messages") or []
        return [e for e in events if isinstance(e, dict)] if isinstance(events, list) else []

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
