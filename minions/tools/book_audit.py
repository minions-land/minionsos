"""Book audit module - contradiction detection and resolution.

Extracted from book.py to focus on audit and contradiction handling.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from minions.errors import BookError
from minions.paths import project_shared_subdir

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


def mos_book_audit_walk(
    *,
    status_filter: str | None = None,
    max_pages: int = 50,
    port: int | None = None,
) -> dict[str, object]:
    """Walk Book pages for audit.

    Returns audit_queue with page metadata for review.

    Note: Simplified stub - full implementation requires:
    - Walking sources/ directory
    - Filtering by status
    - Extracting reel_refs
    - Building audit queue
    """
    resolved_port = _resolve_port(port)
    book_root = _book_root(resolved_port)

    audit_queue: list[dict[str, Any]] = []

    sources_dir = book_root / "sources"
    if not sources_dir.exists():
        return {
            "audit_queue": [],
            "queue_depth": 0,
            "filter": status_filter or "(any)",
        }

    # Simplified implementation
    source_files = list(sources_dir.glob("*.md"))[:max_pages]

    for source_file in source_files:
        try:
            _ = source_file.read_text(encoding="utf-8")
            # Simplified metadata extraction
            audit_queue.append({
                "page_path": f"book/sources/{source_file.name}",
                "slug": source_file.stem,
                "title": source_file.stem,
                "reel_refs": [],
                "frontmatter": {},
            })
        except Exception:
            continue

        if len(audit_queue) >= max_pages:
            break

    logger.info(
        "book audit_walk: port=%d queue_depth=%d",
        resolved_port,
        len(audit_queue),
    )

    return {
        "audit_queue": audit_queue,
        "queue_depth": len(audit_queue),
        "filter": status_filter or "(any)",
    }


def mos_book_resolve_contradiction(
    page_path: str,
    resolution: str,
    verdict: str,
    *,
    port: int | None = None,
) -> dict[str, object]:
    """Resolve a contradiction page.

    Updates contradiction status based on verdict (affirmed/refuted).

    Note: Stub - requires full implementation with:
    - Frontmatter updates
    - Status transitions
    - Publishing workflow
    """
    resolved_port = _resolve_port(port)

    if not page_path:
        raise BookError("page_path required")
    if not resolution.strip():
        raise BookError("resolution required")
    if verdict not in ("affirmed", "refuted"):
        raise BookError(f"Invalid verdict: {verdict}")

    logger.info(
        "book resolve_contradiction stub: port=%d path=%s verdict=%s",
        resolved_port,
        page_path,
        verdict,
    )

    raise NotImplementedError("Full contradiction resolution requires helper integration")
