"""Book ingestion module - handles source artifact ingestion into Book.

Extracted from book.py to focus on ingest functionality.
This module contains mos_book_ingest and mos_book_ingest_batch with all helpers.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from minions.errors import BookError
from minions.paths import project_shared_subdir, project_shared_workspace
from minions.tools.book_utils import now_iso as _now_iso, validate_component as _validate_component

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
    """Get Book root directory for a project."""
    return project_shared_subdir(port, "book")


def _sources_dir(port: int) -> Path:
    """Get sources directory."""
    return _book_root(port) / "sources"


def _resolve_source_path(port: int, src_path: str) -> tuple[Path, str]:
    """Resolve source path to absolute Path and relative source_file string."""
    workspace = project_shared_workspace(port)
    if src_path.startswith("shared/"):
        src_path = src_path[len("shared/"):]

    abs_src = workspace / src_path
    if not abs_src.exists():
        raise BookError(f"Source not found: {src_path}")

    # Return tuple of (absolute path, relative source_file)
    return abs_src, src_path


def _read_first_lines(src: Path, max_lines: int = 100) -> str:
    """Read first N lines from source file."""
    try:
        text = src.read_text(encoding="utf-8")
        lines = text.split('\n')[:max_lines]
        return '\n'.join(lines) + '\n'
    except Exception as e:
        raise BookError(f"Failed to read {src}: {e}") from e


def _stage_text(port: int, filename: str, content: str) -> Path:
    """Stage text content to temporary file."""
    from minions.paths import project_state_dir
    stage_dir = project_state_dir(port) / "book_staging"
    stage_dir.mkdir(parents=True, exist_ok=True)
    stage_file = stage_dir / filename
    stage_file.write_text(content, encoding="utf-8")
    return stage_file


def mos_book_ingest(
    src_path: str,
    source_role: str,
    source_slug: str,
    title: str | None = None,
    summary: str | None = None,
    *,
    port: int | None = None,
    reel_ref: str | None = None,
    claim_refs: dict[str, str] | None = None,
) -> dict[str, object]:
    """Ingest a published artifact into the Book.

    Note: This is a simplified stub for initial extraction.
    Full implementation requires integrating all helper functions from book.py.
    """
    resolved_port = _resolve_port(port)
    _validate_component("source_role", source_role)
    _validate_component("source_slug", source_slug)

    slug = f"{source_role}-{source_slug}"
    src, source_file = _resolve_source_path(resolved_port, src_path)

    # Simplified implementation - full version needs:
    # - _inject_claim_refs
    # - _render_source_frontmatter
    # - _detect_contradictions
    # - _index_append_many
    # - _log_append
    # - _publish_files

    logger.info(
        "book ingest stub: port=%d slug=%s source=%s",
        resolved_port,
        slug,
        source_file,
    )

    raise NotImplementedError("Full ingest implementation requires completing helper extraction")


def mos_book_ingest_batch(
    sources: list[dict[str, Any]],
    *,
    port: int | None = None,
) -> dict[str, object]:
    """Ingest multiple artifacts in one batch.

    Note: Stub - requires full implementation.
    """
    raise NotImplementedError("Batch ingest stub - requires full helper extraction")
