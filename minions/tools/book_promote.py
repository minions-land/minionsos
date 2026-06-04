"""Book promotion module - verified content promotion and ratification.

Extracted from book.py to focus on content promotion workflow.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from minions.errors import BookError
from minions.paths import project_shared_subdir
from minions.tools.book_utils import (
    validate_component as _validate_component,
)

logger = logging.getLogger(__name__)


def _resolve_port(port: int | None) -> int:
    """Resolve port from parameter or environment."""
    if port is not None:
        return port
    raw = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not raw:
        raise BookError("MINIONS_PROJECT_PORT not set and port not provided")
    return int(raw)


def _book_root(port: int) -> Path:
    """Get Book root directory."""
    return project_shared_subdir(port, "book")


def mos_book_promote_verified(
    source_path: str,
    verdict: str,
    *,
    port: int | None = None,
) -> dict[str, object]:
    """Promote verified content from Draft to Book.

    Note: Simplified stub - full implementation requires:
    - Reading source page frontmatter
    - Creating promoted version
    - Updating status fields
    - Publishing through mos_publish_to_shared
    """
    resolved_port = _resolve_port(port)

    # Validate inputs
    if not source_path:
        raise BookError("source_path required")
    if not verdict:
        raise BookError("verdict required")

    logger.info(
        "book promote_verified stub: port=%d source=%s",
        resolved_port,
        source_path,
    )

    raise NotImplementedError("Full implementation requires integration with book.py helpers")


def mos_book_ratify(
    source_path: str,
    rationale: str,
    *,
    port: int | None = None,
) -> dict[str, object]:
    """Ethics ratification of a Book page.

    Marks page as ratified by Ethics with rationale.

    Note: Stub - requires full implementation with:
    - Frontmatter updates
    - Ratification metadata
    - Publishing workflow
    """
    resolved_port = _resolve_port(port)

    if not source_path:
        raise BookError("source_path required")
    if not rationale.strip():
        raise BookError("rationale required")

    _validate_component("source_path", source_path)

    logger.info(
        "book ratify stub: port=%d source=%s",
        resolved_port,
        source_path,
    )

    raise NotImplementedError("Full ratify implementation requires helper integration")
