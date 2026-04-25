"""gru_relay MCP tool: cross-project message relay via EACN3 POST /messages.

Gru is the only agent that may call this.  The relay builds a formatted
message with source attribution and posts it to the target project's EACN
backend via the real ``POST /api/messages`` endpoint.
"""

from __future__ import annotations

import logging
from typing import Literal

import httpx

from minions.errors import RelayError

logger = logging.getLogger(__name__)

RelayMode = Literal["auto", "quote", "paraphrase"]


def format_relay_message(
    content: str,
    mode: RelayMode,
    from_port: int,
    source_note: str | None = None,
) -> str:
    """Build the relay message body with source attribution.

    Args:
        content: The raw message content.
        mode: ``"auto"``, ``"quote"``, or ``"paraphrase"``.
        from_port: Source project port (for attribution).
        source_note: Optional human-readable note about the relay source.

    Returns:
        Formatted message string.

    Raises:
        ``ValueError`` if *mode* is not one of the three valid values.
    """
    valid_modes = ("auto", "quote", "paraphrase")
    if mode not in valid_modes:
        raise ValueError(f"Invalid relay mode {mode!r}; must be one of {valid_modes}.")

    source_line = f"[Relayed from project-{from_port}"
    if source_note:
        source_line += f" — {source_note}"
    source_line += "]"

    if mode == "quote":
        body = f"{source_line}\n\n> {content.replace(chr(10), chr(10) + '> ')}"
    elif mode == "paraphrase":
        body = f"{source_line}\n\n{content}"
    else:
        # auto: quote for short messages, paraphrase for long ones.
        if len(content) <= 500:
            body = f"{source_line}\n\n> {content.replace(chr(10), chr(10) + '> ')}"
        else:
            body = f"{source_line}\n\n{content}"

    return body


def _post_message(port: int, to_agent_id: str, from_agent_id: str, content: str) -> None:
    """POST a direct message to the EACN backend on *port* via ``POST /api/messages``.

    Uses the three-layer MessageAddress schema:
    ``{"to": {"agent_id": ...}, "from": {"agent_id": ...}, "content": ...}``
    """
    url = f"http://127.0.0.1:{port}/api/messages"
    payload = {
        "to": {"agent_id": to_agent_id, "server_id": "", "network_id": ""},
        "from": {"agent_id": from_agent_id, "server_id": "", "network_id": ""},
        "content": content,
    }
    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RelayError(
            f"EACN message to port {port} failed with HTTP {exc.response.status_code}: "
            f"{exc.response.text}"
        ) from exc
    except Exception as exc:
        raise RelayError(f"EACN message to port {port} failed: {exc}") from exc


def _get_gru_agent_id(port: int) -> str | None:
    """Look up the Gru agent ID on the target backend via discovery.

    Returns the agent_id whose ``name`` is exactly ``"gru"`` or whose
    ``agent_id`` matches the configured ``gru_eacn_agent_id``. This avoids
    matching stale relay-origin agents like ``"gru-relay-<port>"`` that a
    prior run may have left in the registry.
    """
    try:
        from minions.config import load_gru_config

        configured_id = load_gru_config().gru_eacn_agent_id
    except Exception:
        configured_id = "gru"
    try:
        resp = httpx.get(
            f"http://127.0.0.1:{port}/api/discovery/agents",
            params={"domain": "coordination"},
            timeout=3.0,
        )
        if resp.status_code == 200:
            agents = resp.json()
            for a in agents:
                if a.get("name") == "gru" or a.get("agent_id") == configured_id:
                    return a.get("agent_id")
    except Exception:
        pass
    return None


def gru_relay(
    from_port: int,
    to_port: int,
    content: str,
    mode: RelayMode = "auto",
    source_note: str | None = None,
) -> dict[str, bool]:
    """Relay *content* from project *from_port* to project *to_port*.

    Builds a formatted message with source attribution and delivers it to
    the target project's EACN backend via ``POST /api/messages``.

    The message is addressed to the Gru agent on the target project.  If
    Gru's agent_id cannot be resolved via discovery, a fallback agent_id
    of ``"gru"`` is used (EACN will queue it for polling).

    Args:
        from_port: Source project port (for attribution).
        to_port: Destination project port.
        content: The message content to relay.
        mode: ``"auto"`` (default), ``"quote"``, or ``"paraphrase"``.
        source_note: Optional human-readable note about the relay source.

    Returns:
        ``{"ok": True}`` on success.

    Raises:
        ``RelayError`` on delivery failure.
    """
    logger.info(
        "gru_relay from_port=%d to_port=%d mode=%s len=%d",
        from_port,
        to_port,
        mode,
        len(content),
    )
    message = format_relay_message(content, mode, from_port, source_note)

    # Resolve the Gru agent ID on the target backend; fall back to "gru".
    to_agent_id = _get_gru_agent_id(to_port) or "gru"
    from_agent_id = f"gru-relay-{from_port}"

    _post_message(to_port, to_agent_id, from_agent_id, message)
    logger.debug("gru_relay delivered to port %d agent %s.", to_port, to_agent_id)
    return {"ok": True}
