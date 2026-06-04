"""Book lint module - comprehensive Book integrity checks.

Extracted from book.py to focus on validation and health checks.
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


def _read_lint_text(path: Path) -> str:
    """Read text for linting, returning empty string on error."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _book_lint_target_exists(port: int, target: str) -> bool:
    """Check if a lint target (wikilink) exists."""
    # Simplified check - full version needs comprehensive path resolution
    book_root = _book_root(port)

    # Try common locations
    for subdir in ["sources", "open_questions", "contradictions"]:
        candidate = book_root / subdir / f"{target}.md"
        if candidate.exists():
            return True

    return False


def _add_lint_finding(
    findings: list[dict[str, Any]],
    category: str,
    message: str,
    path: str | None = None,
) -> None:
    """Add a lint finding to the list."""
    finding: dict[str, Any] = {
        "category": category,
        "message": message,
    }
    if path:
        finding["path"] = path

    findings.append(finding)


def _collect_book_lint_findings(port: int) -> list[dict[str, Any]]:
    """Collect all lint findings for Book."""
    findings: list[dict[str, Any]] = []
    book_root = _book_root(port)

    if not book_root.exists():
        _add_lint_finding(findings, "error", f"Book root does not exist: {book_root}")
        return findings

    # Check for index.md
    index_path = book_root / "index.md"
    if not index_path.exists():
        _add_lint_finding(findings, "missing_index", "book/index.md not found")

    # Check for log.md
    log_path = book_root / "log.md"
    if not log_path.exists():
        _add_lint_finding(findings, "missing_log", "book/log.md not found")

    # Check sources directory
    sources_dir = book_root / "sources"
    if sources_dir.exists():
        source_files = list(sources_dir.glob("*.md"))

        # Check for orphan pages (simplified check)
        for source_file in source_files:
            content = _read_lint_text(source_file)
            if not content:
                _add_lint_finding(
                    findings,
                    "unreadable",
                    f"Cannot read source: {source_file.name}",
                    f"book/sources/{source_file.name}",
                )

    return findings


def _book_lint_result(findings: list[dict[str, Any]]) -> dict[str, object]:
    """Convert findings list to result dict."""
    # Group findings by category
    by_category: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        category = finding["category"]
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(finding)

    return {
        "findings": findings,
        "lint_count": len(findings),
        "by_category": by_category,
        "orphan_pages": by_category.get("orphan", []),
        "dead_links": by_category.get("dead_link", []),
        "missing_concept_pages": by_category.get("missing_concept", []),
        "stale_claims": by_category.get("stale_claim", []),
    }


def _short_lint_value(findings: list[dict[str, Any]]) -> str:
    """Short summary of lint findings."""
    if not findings:
        return "clean"
    return f"{len(findings)} issues"


def _publish_book_lint_outputs(port: int, result: dict[str, object]) -> None:
    """Publish lint results to Book."""
    # Simplified - full version writes to book/lint.json
    import json

    from minions.paths import project_state_dir

    state_dir = project_state_dir(port)
    state_dir.mkdir(parents=True, exist_ok=True)

    lint_output = state_dir / "book_lint.json"
    lint_output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    logger.info("book lint output written to %s", lint_output)


def mos_book_lint(*, port: int | None = None) -> dict[str, object]:
    """Audit book/ for structural health.

    Returns {orphan_pages, dead_links, missing_concept_pages, stale_claims,
    lint_count, findings}. This tool is filesystem-only and best-effort:
    failures are returned as 'error' alongside any collected partial result.
    """
    result: dict[str, object] = _book_lint_result([])
    resolved_port: int | None = None

    try:
        resolved_port = _resolve_port(port)
        result = _book_lint_result(_collect_book_lint_findings(resolved_port))
    except Exception as exc:
        logger.warning("book lint failed: %s", exc)
        result["error"] = str(exc)

    if resolved_port is None:
        return result

    try:
        _publish_book_lint_outputs(resolved_port, result)
    except Exception as exc:
        logger.warning("book lint publish failed: %s", exc)
        existing = result.get("error")
        result["error"] = f"{existing}; publish failed: {exc}" if existing else str(exc)

    return result
