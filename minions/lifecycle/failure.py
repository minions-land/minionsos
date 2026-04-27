"""MCP/tool failure classification, retry, and logging."""

from __future__ import annotations

import enum
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ToolFailureKind(enum.Enum):
    transient = "transient"
    permanent = "permanent"
    auth = "auth"
    timeout = "timeout"


_TRANSIENT_TYPES = (ConnectionError, ConnectionRefusedError, OSError)
_TIMEOUT_TYPES = (TimeoutError,)
_AUTH_TYPES = (PermissionError,)


@dataclass
class ToolFailure:
    kind: ToolFailureKind
    tool_name: str
    message: str
    timestamp: float = field(default_factory=time.monotonic)
    retryable: bool = False


def classify_failure(tool_name: str, exc: BaseException) -> ToolFailure:
    """Map an exception to a classified ``ToolFailure``."""
    if isinstance(exc, _TIMEOUT_TYPES):
        return ToolFailure(
            kind=ToolFailureKind.timeout,
            tool_name=tool_name,
            message=str(exc),
            retryable=True,
        )
    if isinstance(exc, _AUTH_TYPES):
        return ToolFailure(
            kind=ToolFailureKind.auth,
            tool_name=tool_name,
            message=str(exc),
            retryable=False,
        )
    if isinstance(exc, _TRANSIENT_TYPES):
        return ToolFailure(
            kind=ToolFailureKind.transient,
            tool_name=tool_name,
            message=str(exc),
            retryable=True,
        )
    return ToolFailure(
        kind=ToolFailureKind.permanent,
        tool_name=tool_name,
        message=str(exc),
        retryable=False,
    )


def with_retry(
    fn: Callable[[], T],
    max_retries: int = 3,
    delay: float = 1.0,
) -> T:
    """Call *fn* with retries on transient/timeout failures."""
    last_exc: BaseException | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except (*_TRANSIENT_TYPES, *_TIMEOUT_TYPES) as exc:
            last_exc = exc
            logger.debug("with_retry attempt %d failed: %s", attempt + 1, exc)
            if attempt < max_retries - 1 and delay > 0:
                time.sleep(delay)
        except Exception:
            raise
    raise last_exc  # type: ignore[misc]


class FailureLog:
    """Bounded in-memory log of tool failures."""

    def __init__(self, max_entries: int = 100) -> None:
        self._entries: deque[ToolFailure] = deque(maxlen=max_entries)

    def record(self, failure: ToolFailure) -> None:
        self._entries.append(failure)
        logger.warning(
            "Tool failure: tool=%s kind=%s msg=%s",
            failure.tool_name,
            failure.kind.value,
            failure.message,
        )

    def recent(self, n: int | None = None) -> list[ToolFailure]:
        entries = list(self._entries)
        if n is not None:
            return entries[-n:]
        return entries

    def summary(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        for f in self._entries:
            by_kind[f.kind.value] = by_kind.get(f.kind.value, 0) + 1
        return {"total": len(self._entries), "by_kind": by_kind}
