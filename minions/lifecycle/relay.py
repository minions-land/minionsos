"""gru_relay: cross-project message relay via EACN3.

Gru is the only agent that may call this.  The relay builds a formatted
message with source attribution and posts it to the target project's EACN
backend via ``POST /api/messages``.

This module delegates to ``minions.tools.relay`` which contains the
canonical implementation against the real EACN3 API.
"""

from __future__ import annotations

from minions.tools.relay import (
    RelayMode,
    format_relay_message,
    gru_relay,
)

__all__ = ["RelayMode", "format_relay_message", "gru_relay"]
