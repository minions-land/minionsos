"""Book crystallize module - session crystallization and synthesis.

Extracted from book.py to focus on crystallization workflow.
"""

from __future__ import annotations

import logging
import os

from minions.errors import BookError

logger = logging.getLogger(__name__)


def _resolve_port(port: int | None) -> int:
    """Resolve port from parameter or environment."""
    if port is not None:
        return port
    raw = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not raw:
        raise BookError("MINIONS_PROJECT_PORT not set and port not provided")
    return int(raw)


def mos_book_crystallize_session(
    role: str,
    session_id: str,
    *,
    port: int | None = None,
) -> dict[str, object]:
    """Crystallize a session into Book.

    Archives session outcomes as a durable Book page.

    Note: Stub - requires full implementation.
    """
    resolved_port = _resolve_port(port)

    if not role:
        raise BookError("role required")
    if not session_id:
        raise BookError("session_id required")

    logger.info(
        "book crystallize_session stub: port=%d role=%s session=%s",
        resolved_port,
        role,
        session_id,
    )

    raise NotImplementedError("Full crystallization requires helper integration")


def mos_book_save_synthesis(
    role: str,
    content: str,
    context_query: str,
    *,
    port: int | None = None,
) -> dict[str, object]:
    """Save synthesis result to Book.

    Creates a synthesis page with content and context.

    Note: Stub - requires full implementation.
    """
    resolved_port = _resolve_port(port)

    if not role:
        raise BookError("role required")
    if not content.strip():
        raise BookError("content required")

    logger.info(
        "book save_synthesis stub: port=%d role=%s",
        resolved_port,
        role,
    )

    raise NotImplementedError("Full synthesis saving requires helper integration")
