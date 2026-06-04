"""Book lint functionality - structural health checks.

Extracted from book.py to focus on lint/validation features.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minions.tools.book_helpers import (
    _book_root,
    _parse_frontmatter,
    _resolve_port,
)

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STALE_CLAIM_SECONDS = 72 * 60 * 60  # 72 hours


def _book_rel_path(book_root: Path, path: Path) -> str:
    """Return relative path from book root."""
    try:
        return str(path.relative_to(book_root.parent))
    except ValueError:
        return str(path)


def _read_lint_text(path: Path) -> str:
    """Read file for lint checking."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _normalise_wikilink_slug(raw: str) -> str:
    """Normalize wikilink slug."""
    return raw.strip().lower()


def _book_markdown_files(book_root: Path) -> list[Path]:
    """Return all markdown files in book root."""
    if not book_root.exists():
        return []
    return list(book_root.rglob("*.md"))


def _wikilinks_by_page(pages: list[Path]) -> dict[Path, list[str]]:
    """Extract wikilinks from each page."""
    links_by_page: dict[Path, list[str]] = {}
    for page in pages:
        text = _read_lint_text(page)
        # Simple regex for [[slug]] style wikilinks
        matches = re.findall(r'\[\[([^\]]+)\]\]', text)
        links_by_page[page] = [_normalise_wikilink_slug(m) for m in matches]
    return links_by_page


def _book_lint_target_exists(book_root: Path, slug: str) -> bool:
    """Check if target exists for slug."""
    # Check sources
    source = book_root / "sources" / f"{slug}.md"
    if source.exists():
        return True
    # Check contradictions
    contradiction = book_root / "contradictions" / f"contradiction-{slug}.md"
    if contradiction.exists():
        return True
    return False


def _add_lint_finding(
    findings: list[dict[str, Any]],
    *,
    check: str,
    slug: str,
    detail: str,
    book_path: str | None = None,
    severity: str = "info",
) -> None:
    """Add a lint finding to the list."""
    finding: dict[str, Any] = {
        "check": check,
        "slug": slug,
        "detail": detail,
        "severity": severity,
    }
    if book_path:
        finding["book_path"] = book_path

    findings.append(finding)


def _collect_book_lint_findings(port: int) -> list[dict[str, Any]]:
    """Collect all lint findings for Book."""
    book_root = _book_root(port)
    pages = _book_markdown_files(book_root)
    links_by_page = _wikilinks_by_page(pages)
    findings: list[dict[str, Any]] = []

    source_dir = book_root / "sources"
    source_pages = sorted(source_dir.glob("*.md")) if source_dir.exists() else []
    sources_by_slug = {path.stem.lower(): path for path in source_pages}
    inbound_source_slugs: set[str] = set()
    for page, slugs in links_by_page.items():
        for slug in slugs:
            source_page = sources_by_slug.get(slug)
            if source_page is not None and page != source_page:
                inbound_source_slugs.add(slug)

    for slug, source_page in sorted(sources_by_slug.items()):
        if slug in inbound_source_slugs:
            continue
        _add_lint_finding(
            findings,
            check="ORPHAN_PAGE",
            slug=slug,
            detail="No inbound wikilink from another book page.",
            book_path=_book_rel_path(book_root, source_page),
            severity="info",
        )

    seen_dead_links: set[tuple[str, Path]] = set()
    for page, slugs in links_by_page.items():
        for slug in sorted(set(slugs)):
            if _book_lint_target_exists(book_root, slug):
                continue
            key = (slug, page)
            if key in seen_dead_links:
                continue
            seen_dead_links.add(key)
            _add_lint_finding(
                findings,
                check="DEAD_LINK",
                slug=slug,
                detail="No source or contradiction page exists for this wikilink slug.",
                book_path=_book_rel_path(book_root, page),
                severity="error",
            )

    index_path = book_root / "index.md"
    if index_path.exists():
        title_tokens: Counter[str] = Counter()
        for line in _read_lint_text(index_path).splitlines():
            if line.startswith("## "):
                title_tokens.update(_TOKEN_RE.findall(line[3:].lower()))
        for slug, count in sorted(title_tokens.items()):
            if count < 3 or (book_root / "sources" / f"{slug}.md").exists():
                continue
            _add_lint_finding(
                findings,
                check="MISSING_CONCEPT_PAGE",
                slug=slug,
                detail=f"Title token appears {count} times in book/index.md without a source page.",
                book_path="book/index.md",
                severity="info",
            )

    contradiction_dir = book_root / "contradictions"
    now_ts = datetime.now(UTC).timestamp()
    contradiction_pages = (
        sorted(contradiction_dir.glob("contradiction-*.md")) if contradiction_dir.exists() else []
    )
    for page in contradiction_pages:
        frontmatter = _parse_frontmatter(_read_lint_text(page))
        if frontmatter.get("status", "").lower() != "unresolved":
            continue
        try:
            age_seconds = now_ts - page.stat().st_mtime
        except OSError as exc:
            logger.warning("book lint could not stat %s: %s", page, exc)
            continue
        if age_seconds <= _STALE_CLAIM_SECONDS:
            continue
        _add_lint_finding(
            findings,
            check="STALE_CLAIM",
            slug=page.stem,
            detail=f"Unresolved contradiction is {int(age_seconds // 3600)}h old (older than 72h).",
            book_path=_book_rel_path(book_root, page),
            severity="warning",
        )

    return findings


def _book_lint_result(findings: list[dict[str, Any]]) -> dict[str, object]:
    """Convert findings list to result dict."""
    from collections import Counter

    # Count findings by check type
    counts = Counter(str(finding.get("check", "")) for finding in findings)

    return {
        "orphan_pages": counts["ORPHAN_PAGE"],
        "dead_links": counts["DEAD_LINK"],
        "missing_concept_pages": counts["MISSING_CONCEPT_PAGE"],
        "stale_claims": counts["STALE_CLAIM"],
        "lint_count": len(findings),
        "findings": findings,
    }


def _publish_book_lint_outputs(port: int, result: dict[str, object]) -> None:
    """Publish lint results to Book."""
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
        if existing:
            result["error"] = f"{existing}; publish: {exc}"
        else:
            result["error"] = f"publish: {exc}"

    return result


__all__ = ["mos_book_lint"]
