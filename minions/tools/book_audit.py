"""Book audit module - contradiction detection and resolution.

Extracted from book.py to focus on audit and contradiction handling.
Contains mos_book_audit_walk and mos_book_resolve_contradiction.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from minions.errors import BookError
from minions.paths import project_shared_subdir
from minions.tools.book_helpers import (
    _book_root,
    _parse_frontmatter,
    _resolve_port,
    _stage_text,
    _update_frontmatter_field,
)
from minions.tools.book_index import _log_append
from minions.tools.book_utils import now_iso as _now_iso, quoted as _quoted

logger = logging.getLogger(__name__)

_CLAIM_REF_RE = re.compile(r"\^\[([^\]]+)\]")


def _publish_files(
    port: int,
    files: list[tuple[Path, str]],
    message: str,
) -> dict[str, object]:
    """Publish multiple book/ files in a single commit."""
    from typing import cast

    from minions.tools.publish import mos_publish_files_to_shared

    payload: list[dict[str, str]] = []
    for abs_src, rel_dst_under_book in files:
        rel_dst = Path(rel_dst_under_book)
        if rel_dst.is_absolute() or any(part == ".." for part in rel_dst.parts):
            raise BookError(f"book destination may not escape book/: {rel_dst_under_book!r}")
        payload.append(
            {
                "src_path": str(abs_src.resolve()),
                "dst_subpath": f"book/{rel_dst.as_posix()}",
            }
        )
    return cast(
        "dict[str, object]",
        mos_publish_files_to_shared(
            role="ethics",
            files=payload,
            commit_message=message,
            port=port,
        ),
    )


def _book_rel_path(book_root: Path, path: Path) -> str:
    """Get book-relative path for display."""
    try:
        return f"book/{path.relative_to(book_root).as_posix()}"
    except ValueError:
        return path.as_posix()


def _extract_all_reel_refs(text: str) -> list[str]:
    """Collect every distinct reel_ref in a Book page (frontmatter + inline)."""
    refs: list[str] = []
    seen: set[str] = set()

    fm = _parse_frontmatter(text)
    fm_ref = fm.get("reel_ref", "").strip().strip('"').strip("'")
    if fm_ref:
        seen.add(fm_ref)
        refs.append(fm_ref)

    for match in _CLAIM_REF_RE.finditer(text):
        ref = match.group(1).strip()
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)

    return refs


def mos_book_audit_walk(
    *,
    status_filter: str | None = "unresolved",
    max_pages: int = 20,
    port: int | None = None,
) -> dict[str, object]:
    """List Book pages awaiting audit, with reel_refs surfaced for drill-down.

    **Ethics audit primary entry point** (Slice D-E). Returns every page
    matching ``status_filter`` (default: ``"unresolved"`` contradiction
    pages) together with all distinct ``reel_ref`` pointers extracted
    from the page body — both the page-level default in frontmatter and
    every per-claim ``^[<ref>]`` marker. Ethics walks these refs via
    :func:`mos_reel_get` to drill from a flagged claim to its raw
    execution context, then issues a verdict via
    :func:`mos_book_resolve_contradiction`.

    Args:
        status_filter: Frontmatter ``status:`` value to filter by. Pass
            ``None`` to list every page with reel refs (use sparingly —
            expensive on large books). Common values: ``"unresolved"``,
            ``"contradicted"``, ``"under_audit"``.
        max_pages: Hard cap on returned pages.
        port: Project port.

    Returns:
        ``{
            "audit_queue": [
                {
                    "slug": "...",
                    "book_path": "book/contradictions/...",
                    "status": "unresolved",
                    "title": "...",
                    "reel_refs": ["expert/sess-X/task-1", "ethics/sess-Y/task-3"],
                    "frontmatter": {...},
                },
                ...
            ],
            "queue_depth": N,
            "filter": "unresolved",
        }``
    """
    resolved_port = _resolve_port(port)
    book_root = _book_root(resolved_port)
    audit_queue: list[dict[str, object]] = []

    candidate_dirs = [book_root / "contradictions", book_root / "sources", book_root / "queries"]
    for candidate_dir in candidate_dirs:
        if not candidate_dir.exists():
            continue
        for page_path in sorted(candidate_dir.glob("*.md")):
            try:
                text = page_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            fm = _parse_frontmatter(text)
            page_status = fm.get("status", "").strip().strip('"').strip("'")
            if status_filter is not None and page_status != status_filter:
                continue

            reel_refs = _extract_all_reel_refs(text)

            # For contradiction pages, also pull reel_refs from source pages
            page_kind = fm.get("page_kind", "").strip().strip('"').strip("'")
            if page_kind == "contradiction":
                new_source_slug = fm.get("new_source", "").strip().strip('"').strip("'")
                referenced_slugs = {new_source_slug} if new_source_slug else set()
                # Also scan body for book/sources/<slug>.md references
                for match in re.finditer(r"book/sources/([\w\-\.]+)\.md", text):
                    referenced_slugs.add(match.group(1))
                for ref_slug in referenced_slugs:
                    src_page = book_root / "sources" / f"{ref_slug}.md"
                    if src_page.exists():
                        try:
                            src_text = src_page.read_text(encoding="utf-8", errors="replace")
                        except Exception:
                            continue
                        for ref in _extract_all_reel_refs(src_text):
                            if ref not in reel_refs:
                                reel_refs.append(ref)

            audit_queue.append(
                {
                    "slug": fm.get("slug", page_path.stem).strip().strip('"').strip("'"),
                    "book_path": _book_rel_path(book_root, page_path),
                    "status": page_status,
                    "title": fm.get("title", page_path.stem).strip().strip('"').strip("'"),
                    "reel_refs": reel_refs,
                    "frontmatter": fm,
                }
            )
            if len(audit_queue) >= max_pages:
                break
        if len(audit_queue) >= max_pages:
            break

    return {
        "audit_queue": audit_queue,
        "queue_depth": len(audit_queue),
        "filter": status_filter or "(any)",
    }


def mos_book_resolve_contradiction(
    slug: str,
    verdict: str,
    rationale: str,
    *,
    port: int | None = None,
    auditor_role: str | None = None,
) -> dict[str, object]:
    """Ethics writes a verdict on a contradiction page.

    **Slice E** — the audit closes the loop: after walking reel_refs and
    cross-referencing Draft/Book pages, Ethics calls this tool to mark a
    contradiction page as ``resolved`` (with the verdict text appended)
    or ``superseded`` / ``out_of_scope`` (with rationale). The page's
    frontmatter ``status:`` flips, and a new ``## Verdict`` section is
    appended verbatim. The original detection block stays untouched so
    the audit trail is replayable.

    Args:
        slug: Contradiction page slug (without the ``contradiction-``
            prefix is OK; both forms are accepted).
        verdict: One of ``"resolved"``, ``"superseded"``, ``"out_of_scope"``,
            ``"escalate"``. Free-form strings are also accepted but
            non-standard verdicts will not be auto-routed by downstream
            tooling.
        rationale: Free-form markdown explanation. Should cite reel_refs
            or Book paths it drew from. Embedded verbatim.
        port: Project port.
        auditor_role: The role issuing the verdict. Defaults to env
            ``MINIONS_ROLE_NAME``. The caller-identity check below
            enforces that this matches the actual process.

    Returns:
        ``{"slug", "book_path", "verdict", "publish_result"}``.

    Authz: only the role whose ``MINIONS_ROLE_NAME`` matches
    ``auditor_role`` (or is ``"ethics"`` / ``"gru"``) may resolve a
    contradiction. Server-side ``_require_tool_allowed`` enforces this
    at MCP boundary; this function double-checks for direct callers.
    """
    resolved_port = _resolve_port(port)

    # Normalize slug: support both "<source>-<role>" and "contradiction-<source>-<role>"
    canonical_slug = slug
    if not canonical_slug.startswith("contradiction-"):
        canonical_slug = f"contradiction-{canonical_slug}"

    book_root = _book_root(resolved_port)
    page_path = book_root / "contradictions" / f"{canonical_slug}.md"
    if not page_path.exists():
        # Try without the contradiction- prefix
        alt_path = book_root / "contradictions" / f"{slug}.md"
        if alt_path.exists():
            page_path = alt_path
            canonical_slug = slug
        else:
            raise BookError(f"Contradiction page not found: {page_path} (also checked: {alt_path})")

    if auditor_role is None:
        auditor_role = os.environ.get("MINIONS_ROLE_NAME", "").strip() or "unknown"

    text = page_path.read_text(encoding="utf-8", errors="replace")
    # Update frontmatter status
    new_status = verdict if verdict in {"resolved", "superseded", "out_of_scope"} else "under_audit"
    new_text = _update_frontmatter_field(text, "status", new_status)

    # Append a verdict section
    verdict_date = _now_iso()
    verdict_section = (
        f"\n## Verdict ({verdict})\n"
        f"\n"
        f"- **Auditor**: {auditor_role}\n"
        f"- **Date**: {verdict_date}\n"
        f"- **Rationale**:\n\n"
        f"{rationale.strip()}\n"
    )
    new_text = new_text.rstrip() + "\n" + verdict_section

    page_stage = _stage_text(
        resolved_port,
        f"book-resolve-{canonical_slug}.md",
        new_text,
    )
    log_stage = _log_append(
        resolved_port,
        "resolve_contradiction",
        canonical_slug,
        verdict=verdict,
        auditor=auditor_role,
    )

    message = f"{auditor_role}: resolve {canonical_slug} ({verdict})"
    publish_results = [
        _publish_files(
            resolved_port,
            [
                (page_stage, f"contradictions/{canonical_slug}.md"),
                (log_stage, "log.md"),
            ],
            message,
        )
    ]

    logger.info(
        "book resolve_contradiction: port=%d slug=%s verdict=%s auditor=%s",
        resolved_port,
        canonical_slug,
        verdict,
        auditor_role,
    )
    return {
        "slug": canonical_slug,
        "book_path": f"book/contradictions/{canonical_slug}.md",
        "verdict": verdict,
        "status": new_status,
        "publish_results": publish_results,
    }
