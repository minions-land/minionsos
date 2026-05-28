from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SummarizationEvent:
    session_id: str
    at_pct: float
    tokens_at_event: int
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            object.__setattr__(self, "timestamp", datetime.now(tz=UTC).isoformat())


class SpendSink:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._events: list[SummarizationEvent] = []

    def record_summarization(self, event: SummarizationEvent) -> None:
        self._events.append(event)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.__dict__) + "\n")
        except OSError as exc:
            logger.debug("spend sink write failed: %s", exc)

    def summarization_events(self) -> list[SummarizationEvent]:
        return list(self._events)
