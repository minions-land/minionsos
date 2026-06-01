"""mos_project_bridge MCP tool: cross-project message bridge via EACN3.

Cross-project communication is intentionally Gru-only. Gru sits in the same
host process across every active project; on each project's Local EACN it is
already registered as the ``gru`` agent. To bridge a message from project A
to project B, Gru therefore performs **two** EACN actions:

1. It receives a message addressed to its own ``gru`` agent on project A
   (typically via ``mos_get_events(port=A)``).
2. It calls ``mos_project_bridge(to_port=B, to_agent_id=..., content=...)``
   which posts a single ``POST /api/messages`` to project B's backend, with
   sender = B's real ``gru`` agent and a ``[Bridged from project-A]``
   attribution header in the message body.

The bridge is a structural boundary, not a transitional hack. Each project
is a closed scientific universe; cross-project signal is meant to be sparse
and supervisor-mediated, so funnelling it through Gru is exactly the
behavior we want.
"""

from __future__ import annotations

import logging
from typing import Literal

import httpx

from minions.errors import ProjectBridgeError

logger = logging.getLogger(__name__)

BridgeMode = Literal["auto", "quote", "paraphrase"]


def format_bridge_message(
    content: str,
    mode: BridgeMode,
    from_port: int,
    source_note: str | None = None,
) -> str:
    """Build the bridged message body with source attribution.

    Args:
        content: The raw message content.
        mode: ``"auto"``, ``"quote"``, or ``"paraphrase"``.
        from_port: Source project port (for attribution).
        source_note: Optional human-readable note about the bridge source.

    Returns:
        Formatted message string.

    Raises:
        ``ValueError`` if *mode* is not one of the three valid values.
    """
    valid_modes = ("auto", "quote", "paraphrase")
    if mode not in valid_modes:
        raise ValueError(f"Invalid bridge mode {mode!r}; must be one of {valid_modes}.")

    source_line = f"[Bridged from project-{from_port}"
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


def _gru_agent_id() -> str:
    """Return Gru's per-project agent_id from configuration.

    Gru registers under the same stable ID on every project (default
    ``"gru"``), so we do not need to discover it from the target backend.
    """
    try:
        from minions.config import load_gru_config

        return load_gru_config().gru_eacn_agent_id or "gru"
    except Exception:
        return "gru"


def _send_eacn_message(
    port: int,
    to_agent_id: str,
    from_agent_id: str,
    content: str,
) -> None:
    """POST a direct message to the EACN backend on *port* via ``POST /api/messages``."""
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
        raise ProjectBridgeError(
            f"EACN message to port {port} failed with HTTP {exc.response.status_code}: "
            f"{exc.response.text}"
        ) from exc
    except Exception as exc:
        raise ProjectBridgeError(f"EACN message to port {port} failed: {exc}") from exc


def project_bridge(
    from_port: int,
    to_port: int,
    to_agent_id: str,
    content: str,
    mode: BridgeMode = "auto",
    source_note: str | None = None,
) -> dict[str, bool]:
    """Bridge *content* from project *from_port* to *to_agent_id* on project *to_port*.

    The message is posted as a direct message on *to_port*'s EACN backend.
    Both sender and recipient are real, registered agents on that backend:
    sender is *to_port*'s ``gru`` (same host process, same identity), and
    recipient is *to_agent_id*. A ``[Bridged from project-<from_port>]``
    attribution header is prepended to the body for traceability.

    Args:
        from_port: Source project port (used only for the attribution header).
        to_port: Destination project port.
        to_agent_id: Target agent_id on the destination project (e.g.
            ``"expert"``, ``"ethics"``). Pass an explicit value rather than
            relying on a default — the destination project may have any
            registered agent.
        content: The message body to bridge.
        mode: ``"auto"`` (default), ``"quote"``, or ``"paraphrase"``.
        source_note: Optional human-readable note about the bridge source.

    Returns:
        ``{"ok": True}`` on success.

    Raises:
        ``ProjectBridgeError`` on delivery failure.
    """
    logger.info(
        "mos_project_bridge from_port=%d to_port=%d to_agent=%s mode=%s len=%d",
        from_port,
        to_port,
        to_agent_id,
        mode,
        len(content),
    )
    message = format_bridge_message(content, mode, from_port, source_note)
    gru_id = _gru_agent_id()
    _send_eacn_message(to_port, to_agent_id, gru_id, message)
    logger.debug("mos_project_bridge delivered to port %d agent %s.", to_port, to_agent_id)
    return {"ok": True}
