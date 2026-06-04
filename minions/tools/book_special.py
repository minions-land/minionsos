"""Special Book functions: open questions, dead ends, and ratification.

Complete implementation extracted from book.py.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from minions.config import slugify
from minions.errors import BookError
from minions.paths import project_shared_subdir
from minions.tools.book_utils import now_iso as _now_iso
from minions.tools.book_utils import quoted as _quoted
from minions.tools.book_utils import validate_component as _validate_component


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


def _sources_dir(port: int) -> Path:
    """Get sources directory."""
    return _book_root(port) / "sources"


def mos_book_open_question(
    question: str,
    *,
    related_pages: list[str] | None = None,
    slug: str | None = None,
    port: int | None = None,
) -> dict[str, object]:
    """Record an open research question as a durable Book page.

    Creates book/open_questions/<slug>.md with status: open_question.
    """
    resolved_port = _resolve_port(port)
    if not question.strip():
        raise BookError("question must be non-empty")

    if slug is None:
        slug = slugify(question)[:60] or f"oq-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    _validate_component("slug", slug)

    date_created = _now_iso()
    related_pages = related_pages or []

    fm_lines = [
        "---",
        "type: open_question",
        f"slug: {_quoted(slug)}",
        f"question: {_quoted(question.strip())}",
        f"date_created: {_quoted(date_created)}",
        "page_kind: open_question",
        "status: open_question",
        f"related_pages: {json.dumps(related_pages, ensure_ascii=False)}",
        "---",
        "",
        f"# Open Question: {question.strip()}",
        "",
        "**Status**: open — awaiting investigation.",
        "",
        "## Context",
        "",
        question.strip(),
        "",
    ]

    if related_pages:
        fm_lines.extend([
            "## Related Pages",
            "",
        ])
        for page in related_pages:
            fm_lines.append(f"- [[{page}]]")
        fm_lines.append("")

    page_content = "\n".join(fm_lines)

    # Write to book/open_questions/
    open_questions_dir = _book_root(resolved_port) / "open_questions"
    open_questions_dir.mkdir(parents=True, exist_ok=True)
    page_path = open_questions_dir / f"{slug}.md"
    page_path.write_text(page_content, encoding="utf-8")

    # Publish via mos_publish_to_shared
    from minions.tools.publish import mos_publish_to_shared

    publish_result = mos_publish_to_shared(
        role="ethics",
        src_path=str(page_path),
        dst_subpath=f"book/open_questions/{slug}.md",
        commit_message=f"ethics: open question {slug}",
        port=resolved_port,
    )

    return {
        "slug": slug,
        "book_path": f"book/open_questions/{slug}.md",
        "publish_result": publish_result,
    }


def mos_book_dead_end(
    claim: str,
    refutation_evidence: str,
    *,
    slug: str | None = None,
    port: int | None = None,
) -> dict[str, object]:
    """Record a refuted claim as a permanent dead-end Book page.

    Creates book/sources/dead-end-<slug>.md with status: refuted.
    REFUTED PAGES MUST NEVER BE DELETED.
    """
    resolved_port = _resolve_port(port)
    if not claim.strip():
        raise BookError("claim must be non-empty")
    if not refutation_evidence.strip():
        raise BookError("refutation_evidence must be non-empty")

    raw_slug = slug or slugify(claim)[:50] or f"de-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    full_slug = f"dead-end-{raw_slug}"
    _validate_component("slug", full_slug)

    date_created = _now_iso()

    fm_lines = [
        "---",
        "page_kind: source",
        f"title: {_quoted(f'Dead end: {claim.strip()[:80]}')}",
        f"slug: {_quoted(full_slug)}",
        f"date_ingested: {_quoted(date_created)}",
        "status: refuted",
        "---",
        "",
        f"# Dead End: {claim.strip()}",
        "",
        "**Status**: refuted — do not re-attempt without new evidence.",
        "",
        "## Claim",
        "",
        claim.strip(),
        "",
        "## Refutation Evidence",
        "",
        refutation_evidence.strip(),
        "",
    ]

    page_content = "\n".join(fm_lines)

    # Write to book/sources/
    sources_dir = _sources_dir(resolved_port)
    sources_dir.mkdir(parents=True, exist_ok=True)
    page_path = sources_dir / f"{full_slug}.md"
    page_path.write_text(page_content, encoding="utf-8")

    # Publish
    from minions.tools.publish import mos_publish_to_shared

    publish_result = mos_publish_to_shared(
        role="ethics",
        src_path=str(page_path),
        dst_subpath=f"book/sources/{full_slug}.md",
        commit_message=f"ethics: dead end {full_slug}",
        port=resolved_port,
    )

    return {
        "slug": full_slug,
        "book_path": f"book/sources/{full_slug}.md",
        "publish_result": publish_result,
    }
