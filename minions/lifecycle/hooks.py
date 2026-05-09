"""Lifecycle event hook registry.

Two layers of hooks share one registry:

- Lifecycle events fire on project / role state transitions for logging,
  notifications, and state synchronization.
- Wake events fire when MinionsOS observes a reason a Role should go online
  (direct message routed to it, EACN queue has pending events, phase change,
  human trigger). ``wake_signals`` registers default handlers that persist
  compact wake signals to the per-role inbox; callers then just fire the
  relevant event instead of calling the signal helpers directly.

Hook errors are logged but never propagate to the caller.
"""

from __future__ import annotations

import enum
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class LifecycleEvent(enum.Enum):
    # Lifecycle layer
    project_created = "project_created"
    project_closed = "project_closed"
    project_dormant = "project_dormant"
    project_revived = "project_revived"
    role_dispatched = "role_dispatched"
    role_completed = "role_completed"
    role_dismissed = "role_dismissed"
    review_completed = "review_completed"
    # Wake layer — MinionsOS wants this Role to go online and read EACN3.
    wake_direct_message = "wake_direct_message"
    wake_task_invitation = "wake_task_invitation"
    wake_eacn_queue_pending = "wake_eacn_queue_pending"
    wake_phase_change = "wake_phase_change"
    wake_human_trigger = "wake_human_trigger"


HookFn = Callable[[dict[str, Any]], None]


class HookRegistry:
    """Register and fire lifecycle hooks."""

    def __init__(self) -> None:
        self._hooks: dict[LifecycleEvent, list[HookFn]] = defaultdict(list)

    def register(self, event: LifecycleEvent, fn: HookFn) -> None:
        self._hooks[event].append(fn)

    def fire(self, event: LifecycleEvent, data: dict[str, Any]) -> None:
        for fn in self._hooks.get(event, []):
            try:
                fn(data)
            except Exception as exc:
                logger.warning(
                    "Hook error on %s: %s",
                    event.value,
                    exc,
                    exc_info=True,
                )


registry = HookRegistry()


def fire(event: LifecycleEvent, data: dict[str, Any]) -> None:
    """Fire an event on the shared module-level registry."""
    registry.fire(event, data)
