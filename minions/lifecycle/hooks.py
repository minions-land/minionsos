"""Lifecycle event hook registry.

Hooks fire on lifecycle events (project created, role dispatched, etc.)
for logging, notifications, and state synchronization. Hook errors are
logged but never propagate to the caller.
"""

from __future__ import annotations

import enum
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class LifecycleEvent(enum.Enum):
    project_created = "project_created"
    project_closed = "project_closed"
    project_dormant = "project_dormant"
    project_revived = "project_revived"
    role_dispatched = "role_dispatched"
    role_completed = "role_completed"
    role_dismissed = "role_dismissed"
    review_completed = "review_completed"


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
