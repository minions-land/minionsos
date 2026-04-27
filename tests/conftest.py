from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_agent_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests independent from the user's active Gru host."""
    monkeypatch.delenv("MINIONS_AGENT_HOST", raising=False)
