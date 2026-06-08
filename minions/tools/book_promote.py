"""Book promotion module - verified content promotion and ratification.

Extracted from book.py to focus on content promotion workflow.
Contains mos_book_promote_verified and mos_book_ratify.
"""

from __future__ import annotations

import contextlib
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minions.errors import BookError
from minions.paths import project_shared_subdir
from minions.tools.book_helpers import (
    _book_root,
    _resolve_port,
    _stage_text,
    _update_frontmatter_field,
)
from minions.tools.book_index import _log_append
from minions.tools.book_utils import (
    now_iso as _now_iso,
)
from minions.tools.book_utils import (
    validate_component as _validate_component,
)

logger = logging.getLogger(__name__)


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


def _node_cited_in_book(book_root: Path, node_id: str) -> bool:
    """True if any book page already cites this Draft node id."""
    sources = book_root / "sources"
    if not sources.exists():
        return False
    needle = f"draft_node_id: {node_id}"
    needle_alt = f"[{node_id}]"
    for page in sources.glob("*.md"):
        try:
            text = page.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle in text or needle_alt in text:
            return True
    return False


def check_book_ratify_authz(caller_role: str | None = None) -> None:
    """Raise BookError unless *caller_role* is Ethics."""
    role = (
        caller_role if caller_role is not None else os.environ.get("MINIONS_ROLE_NAME", "")
    ).strip()
    if role != "ethics":
        raise BookError(f"mos_book_ratify is Ethics-only; got ratifier_role={role!r}")


def mos_book_promote_verified(
    *,
    min_age_days: float = 7.0,
    min_supporting_edges: int = 2,
    max_promotions: int = 5,
    port: int | None = None,
) -> dict[str, object]:
    """Promote verified Draft insights to durable Book pages.

    Knowledge promotion (Book consolidation tier): when a Draft
    node of type ∈ {insight, method, result} reaches support_status=verified,
    has at least ``min_supporting_edges`` ``supports`` edges, has been stable
    for ``min_age_days`` days, and isn't already cited by any Book page,
    Ethics promotes it by creating a verbatim Book source page.

    Strict verbatim contract — Ethics never restates. The page body is the
    node's exact ``text``, plus a Draft ID reference and the citation
    list of supporting edges. This keeps Ethics inside its "records only,
    makes no new claims" boundary while still moving knowledge from L1
    (process memory) to L2 (product memory).

    Whitelisted to Ethics only. Idempotent — re-running won't duplicate
    pages because the citation check filters out already-promoted nodes.
    """
    resolved_port = _resolve_port(port)
    from minions.tools.draft import _load_decay, _load_draft, _parse_iso

    draft = _load_draft(resolved_port)
    nodes = draft.get("nodes", []) or []
    edges = draft.get("edges", []) or []
    decay = _load_decay(resolved_port)
    book_root = _book_root(resolved_port)
    now = datetime.now(UTC)

    # Dead-ends are first-class citizens
    eligible_types = {"insight", "method", "result", "dead_end"}
    candidates: list[dict[str, Any]] = []
    for node in nodes:
        if node.get("type") not in eligible_types:
            continue
        if node.get("support_status") != "verified":
            continue
        node_id = str(node.get("id", "") or "")
        if not node_id:
            continue
        created = _parse_iso(str(node.get("created_at", "") or ""))
        age_days = 0.0 if created is None else (now - created).total_seconds() / 86400.0
        if age_days < min_age_days:
            continue
        supporting = [
            edge
            for edge in edges
            if edge.get("relation") == "supports"
            and (edge.get("from_id") == node_id or edge.get("to_id") == node_id)
        ]
        if len(supporting) < min_supporting_edges:
            continue
        if _node_cited_in_book(book_root, node_id):
            continue
        decay_entry = decay.get(node_id, {}) if isinstance(decay, dict) else {}
        candidates.append(
            {
                "node": node,
                "supporting": supporting,
                "age_days": age_days,
                "effective_confidence": (
                    decay_entry.get("effective_confidence")
                    if isinstance(decay_entry, dict)
                    else None
                ),
            }
        )

    candidates.sort(
        key=lambda c: float(
            c["effective_confidence"]
            if c["effective_confidence"] is not None
            else c["node"].get("confidence", 0.0)
        ),
        reverse=True,
    )
    promoted: list[dict[str, str]] = []
    for candidate in candidates[: max(0, int(max_promotions))]:
        node: dict[str, Any] = candidate["node"]
        node_id = str(node.get("id", ""))
        node_type = str(node.get("type", ""))
        node_text = str(node.get("text", "")).strip()
        author_role = str(node.get("author_role", "") or "unknown")
        evidence_tag = str(node.get("evidence_tag", "") or "")
        supporting: list[dict[str, Any]] = candidate["supporting"]

        # Verbatim summary body
        cite_lines = ["", "## Citations (Draft supports edges)", ""]
        for edge in supporting:
            other = edge.get("to_id") if edge.get("from_id") == node_id else edge.get("from_id")
            cite_lines.append(
                f"- `[{other}]` ({edge.get('relation', 'supports')}, "
                f"strength={edge.get('strength', 1.0)}, by {edge.get('author_role', '')})"
            )
        body_lines = [
            f"# {node_type.capitalize()} {node_id}",
            "",
            f"**Draft node**: `[{node_id}]`",
            f"**Author role**: {author_role}",
            f"**Promoted at**: {_now_iso()}",
        ]
        if evidence_tag:
            body_lines.append(f"**Evidence tag**: {evidence_tag}")
        if candidate["effective_confidence"] is not None:
            body_lines.append(
                f"**Effective confidence at promotion**: {candidate['effective_confidence']}"
            )
        body_lines.extend(["", "## Verbatim claim", "", node_text, *cite_lines, ""])
        body = "\n".join(body_lines)

        promotion_temp_dir = project_shared_subdir(resolved_port, "ethics") / ".promotions"
        promotion_temp_dir.mkdir(parents=True, exist_ok=True)
        slug_id = node_id.replace("-", "").lower()
        temp_path = promotion_temp_dir / f"promoted-{slug_id}.md"
        temp_path.write_text(body, encoding="utf-8")
        try:
            from minions.tools.book_ingest import mos_book_ingest

            ingest_result = mos_book_ingest(
                src_path=str(temp_path),
                source_role="ethics",
                source_slug=f"promoted-{slug_id}",
                title=f"Promoted {node_type}: {node_id}",
                port=resolved_port,
            )
        finally:
            with contextlib.suppress(OSError):
                temp_path.unlink(missing_ok=True)
        # Mark promoted page as pending Ethics ratification
        promoted_path_rel = str(ingest_result.get("book_path", ""))
        if promoted_path_rel.startswith("book/"):
            promoted_abs = _book_root(resolved_port) / promoted_path_rel[len("book/") :]
            if promoted_abs.exists():
                _pt = promoted_abs.read_text(encoding="utf-8")
                _pt = _update_frontmatter_field(_pt, "ratified_by", "pending_ethics")
                promoted_abs.write_text(_pt, encoding="utf-8")
        promoted.append(
            {
                "node_id": node_id,
                "type": node_type,
                "book_path": str(ingest_result.get("book_path", "")),
                "supporting_edges": str(len(supporting)),
            }
        )

    return {
        "promoted": promoted,
        "promoted_count": len(promoted),
        "candidates_total": len(candidates),
    }


def mos_book_ratify(
    slug: str,
    evidence_review: str,
    ratifier_role: str,
    *,
    port: int | None = None,
) -> dict[str, object]:
    """Ethics ratifies a promoted Book page.

    Sets ``ratified_by: ethics``, ``ratified_at: <iso>``, and appends a
    ``## Ratification`` section verbatim. Only Ethics may call this
    (``ratifier_role`` must equal ``"ethics"``).

    Args:
        slug: The slug of the source page to ratify (under book/sources/).
        evidence_review: The Ethics evidence review text to append verbatim.
        ratifier_role: Must be ``"ethics"``.
        port: Project port.

    Returns:
        ``{"slug", "book_path", "publish_result"}``.
    """
    resolved_port = _resolve_port(port)
    check_book_ratify_authz(ratifier_role)
    if not slug.strip():
        raise BookError("slug must be non-empty")
    if not evidence_review.strip():
        raise BookError("evidence_review must be non-empty")

    _validate_component("slug", slug)
    book_root = _book_root(resolved_port)
    page_path = book_root / "sources" / f"{slug}.md"
    if not page_path.exists():
        raise BookError(f"book source page not found: book/sources/{slug}.md")

    text = page_path.read_text(encoding="utf-8")
    now = _now_iso()
    text = _update_frontmatter_field(text, "ratified_by", "ethics")
    text = _update_frontmatter_field(text, "ratified_at", now)
    if not text.endswith("\n"):
        text += "\n"
    text += f"\n## Ratification\n\n*Ratified by Ethics on {now}*\n\n{evidence_review.strip()}\n"

    stage = _stage_text(resolved_port, f"book-ratify-{slug}.md", text)
    log_stage = _log_append(resolved_port, "ratify", slug, ratifier_role=ratifier_role)
    message = f"ethics: ethics ratify {slug}"
    publish_result = _publish_files(
        resolved_port,
        [
            (stage, f"sources/{slug}.md"),
            (log_stage, "log.md"),
        ],
        message,
    )
    logger.info("book ratify: port=%d slug=%s", resolved_port, slug)
    return {
        "slug": slug,
        "book_path": f"book/sources/{slug}.md",
        "ratified_at": now,
        "publish_result": publish_result,
    }
