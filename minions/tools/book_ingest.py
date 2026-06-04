"""Book ingest operations - ingesting sources into the Book layer.

Extracted from book.py as part of modularization effort.
Contains mos_book_ingest and mos_book_ingest_batch with all helpers.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, cast

from minions.errors import BookError
from minions.paths import project_shared_draft_json, project_shared_subdir
from minions.tools.book_contradiction import (
    _detect_contradictions,
    _detect_contradictions_with_overlay,
)
from minions.tools.book_helpers import (
    _book_root,
    _contradiction_slug,
    _inject_claim_refs,
    _oneline,
    _parse_frontmatter,
    _read_first_lines,
    _render_source_frontmatter,
    _resolve_port,
    _resolve_source_path,
    _stage_text,
)
from minions.tools.book_index import (
    _index_append_many,
    _log_append,
    _log_append_many,
)
from minions.tools.book_utils import now_iso as _now_iso, quoted as _quoted, validate_component as _validate_component
from minions.tools.publish import mos_publish_files_to_shared

logger = logging.getLogger(__name__)


def _publish_files(
    port: int,
    files: list[tuple[Path, str]],
    message: str,
) -> dict[str, object]:
    """Publish multiple book/ files in a single commit.

    Each entry is ``(abs_src, rel_dst_under_book)``. Routes through
    :func:`mos_publish_files_to_shared` so all writes land as one commit on
    the shared branch (see GitHub Issue #13).
    """
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


def _emit_contradiction_dag_edges(port: int, contradictions: list[dict[str, object]]) -> int:
    """Emit Draft edges for detected contradictions."""
    if not contradictions:
        return 0

    path = project_shared_draft_json(port)
    if not path.exists():
        draft: dict[str, object] = {"nodes": [], "edges": []}
    else:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning(
                "book contradiction Draft edge lookup skipped: invalid Draft JSON at %s",
                path,
            )
            return 0
        if not isinstance(data, dict):
            draft = {"nodes": [], "edges": []}
        else:
            draft = data

    raw_edges = draft.get("edges", [])
    if not isinstance(raw_edges, list):
        raw_edges = []
    existing_edges: set[tuple[object, object, object]] = set()
    for edge in raw_edges:
        if isinstance(edge, dict):
            edge_dict = cast(dict[str, object], edge)
            existing_edges.add(
                (
                    edge_dict.get("from_id"),
                    edge_dict.get("to_id"),
                    edge_dict.get("relation"),
                )
            )

    def _normalise_match_text(text: object) -> str:
        return " ".join(str(text).lower().split())

    def _find_dag_node_id(draft_data: dict[str, object], excerpt: object) -> str | None:
        needle = _normalise_match_text(excerpt)
        if not needle:
            return None
        nodes = draft_data.get("nodes", [])
        if not isinstance(nodes, list):
            return None
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_dict = cast(dict[str, object], node)
            node_id = node_dict.get("id", "")
            node_text = _normalise_match_text(node_dict.get("text", ""))
            if (
                isinstance(node_id, str)
                and node_id
                and node_text
                and (needle in node_text or node_text in needle)
            ):
                return node_id
        return None

    edges: list[dict[str, object]] = []
    queued: set[tuple[str, str, str]] = set()
    for contradiction in contradictions:
        excerpts = contradiction.get("excerpts", {})
        if not isinstance(excerpts, dict):
            continue
        excerpts_dict = cast(dict[str, object], excerpts)
        new_node_id = _find_dag_node_id(draft, excerpts_dict.get("new", ""))
        opposing_node_id = _find_dag_node_id(draft, excerpts_dict.get("opposing", ""))
        if not new_node_id or not opposing_node_id or new_node_id == opposing_node_id:
            continue
        edge_key = (new_node_id, opposing_node_id, "contradicts")
        if edge_key in existing_edges or edge_key in queued:
            continue
        queued.add(edge_key)
        edges.append(
            {
                "from_id": new_node_id,
                "to_id": opposing_node_id,
                "relation": "contradicts",
                "strength": 0.5,
                "author_role": "ethics",
            }
        )

    if not edges:
        return 0

    from minions.tools import draft

    old_port = os.environ.get("MINIONS_PROJECT_PORT")
    os.environ["MINIONS_PROJECT_PORT"] = str(port)
    try:
        result = draft.mos_draft_append(edges=edges)
    except Exception:
        logger.exception("book contradiction Draft edge emission failed")
        return 0
    finally:
        if old_port is None:
            os.environ.pop("MINIONS_PROJECT_PORT", None)
        else:
            os.environ["MINIONS_PROJECT_PORT"] = old_port
    return int(result.get("created_edge_count", 0))


def _render_signals_block(
    port: int,
    contradictions: list[dict[str, object]],
    new_source_role: str,
    book_root: Path,
) -> str:
    """Build the Statistical signals section of a contradiction page."""
    from collections import Counter
    from datetime import UTC, datetime

    def _source_role_unmarked_ratio(book_root_p: Path, source_role: str) -> float | None:
        sources = book_root_p / "sources"
        if not sources.exists():
            return None
        role_pages = [p for p in sources.glob("*.md") if p.name.startswith(f"{source_role}-")]
        if not role_pages:
            return None
        total = 0
        marked = 0
        import re
        marker_re = re.compile(r"\[(evidence|speculation|derived)[:\]]")
        for page in role_pages:
            try:
                text = page.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            from minions.tools.book_helpers import _strip_frontmatter
            for line in _strip_frontmatter(text).splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                    continue
                total += 1
                if marker_re.search(stripped):
                    marked += 1
        if total < 5:
            return None
        return round(1.0 - marked / total, 3)

    def _opposing_page_age_days(book_root_p: Path, opposing_page: str) -> float | None:
        rel = opposing_page.removeprefix("book/")
        page = book_root_p / rel
        if not page.exists():
            return None
        try:
            text = page.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        fm = _parse_frontmatter(text)
        raw = fm.get("date_ingested", "").strip().strip('"').strip("'")
        if not raw:
            return None
        try:
            ingested = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return round((datetime.now(UTC) - ingested).total_seconds() / 86400.0, 2)

    def _opposing_source_role(opposing_page: str) -> str:
        name = opposing_page.rsplit("/", 1)[-1]
        stem = name.removesuffix(".md")
        if "-" in stem:
            return stem.split("-", 1)[0]
        return ""

    def _draft_signals_for_terms(port_n: int, terms: list[str]) -> dict[str, Any]:
        try:
            from minions.tools.draft import _load_decay, _load_draft
        except ImportError:
            return {}
        try:
            draft = _load_draft(port_n)
        except (OSError, RuntimeError):
            return {}
        nodes = draft.get("nodes", []) or []
        edges = draft.get("edges", []) or []
        decay = _load_decay(port_n)
        lowered_terms = [t.lower() for t in terms if t]
        if not lowered_terms:
            return {}
        matched_ids: list[str] = []
        for node in nodes:
            text = str(node.get("text", "")).lower()
            if any(term in text for term in lowered_terms):
                matched_ids.append(str(node.get("id", "")))
        if not matched_ids:
            return {"matched_node_count": 0}
        matched_set = set(matched_ids)
        supports = sum(
            1
            for edge in edges
            if edge.get("relation") == "supports"
            and (edge.get("from_id") in matched_set or edge.get("to_id") in matched_set)
        )
        contradicts = sum(
            1
            for edge in edges
            if edge.get("relation") == "contradicts"
            and (edge.get("from_id") in matched_set or edge.get("to_id") in matched_set)
        )
        eff_values = [
            float(decay[nid].get("effective_confidence", 0.0))
            for nid in matched_ids
            if isinstance(decay, dict)
            and isinstance(decay.get(nid), dict)
            and decay[nid].get("effective_confidence") is not None
        ]
        avg_eff = round(sum(eff_values) / len(eff_values), 3) if eff_values else None
        return {
            "matched_node_count": len(matched_ids),
            "supports_edges": supports,
            "contradicts_edges": contradicts,
            "avg_effective_confidence": avg_eff,
        }

    lines = [
        "## Statistical signals",
        "",
        "*Curator-assembled descriptive signals — no verdict. Ethics adjudicates.*",
        "",
        (
            "| # | opposing_page | new_role | opposing_role | opposing_age_d "
            "| new_role_unmarked | opposing_unmarked | draft_matches "
            "| supports | contradicts | avg_eff_conf |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    new_unmarked = _source_role_unmarked_ratio(book_root, new_source_role)

    def fmt(value: object) -> str:
        if value is None:
            return "-"
        return str(value)

    for idx, contradiction in enumerate(contradictions, start=1):
        opposing_page = str(contradiction.get("opposing_page", ""))
        opposing_role = _opposing_source_role(opposing_page)
        age = _opposing_page_age_days(book_root, opposing_page)
        opp_unmarked = (
            _source_role_unmarked_ratio(book_root, opposing_role) if opposing_role else None
        )
        shared_terms_raw = contradiction.get("shared_terms")
        terms: list[str] = (
            [str(t) for t in shared_terms_raw] if isinstance(shared_terms_raw, list) else []
        )
        sig = _draft_signals_for_terms(port, terms)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx),
                    f"`{opposing_page}`",
                    new_source_role,
                    opposing_role or "-",
                    fmt(age),
                    fmt(new_unmarked),
                    fmt(opp_unmarked),
                    fmt(sig.get("matched_node_count")),
                    fmt(sig.get("supports_edges")),
                    fmt(sig.get("contradicts_edges")),
                    fmt(sig.get("avg_effective_confidence")),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_contradiction_page(
    new_slug: str,
    contradictions: list[dict[str, object]],
    source_role: str,
    date: str,
    *,
    port: int | None = None,
) -> str:
    """Render a contradiction detection page."""
    page_slug = _contradiction_slug(new_slug)
    lines = [
        "---",
        "type: contradiction",
        f"slug: {_quoted(page_slug)}",
        f"new_source: {_quoted(new_slug)}",
        f"new_source_role: {_quoted(source_role)}",
        f"opposing_count: {len(contradictions)}",
        f"date_detected: {_quoted(date)}",
        "page_kind: contradiction",
        "status: unresolved",
        "---",
        "",
        f"# Contradiction: {new_slug}",
        "",
        f"New source: `book/sources/{new_slug}.md`",
        "",
    ]
    for idx, contradiction in enumerate(contradictions, start=1):
        excerpts_raw = contradiction.get("excerpts", {})
        excerpts: dict[str, object] = (
            cast(dict[str, object], excerpts_raw) if isinstance(excerpts_raw, dict) else {}
        )
        new_excerpt = _oneline(str(excerpts.get("new", "")))
        opposing_excerpt = _oneline(str(excerpts.get("opposing", "")))
        shared_terms_raw = contradiction.get("shared_terms", [])
        shared_terms: list[object] = (
            list(shared_terms_raw) if isinstance(shared_terms_raw, list) else []
        )
        terms = ", ".join(f"`{term}`" for term in shared_terms) if shared_terms else "(none)"
        lines.extend(
            [
                f"## Candidate {idx}",
                "",
                "> [!contradiction]",
                f"> Opposing page: `{contradiction.get('opposing_page', '')}`",
                f"> Shared terms: {terms}",
                ">",
                f"> New excerpt: {new_excerpt}",
                f"> Opposing excerpt: {opposing_excerpt}",
                "",
            ]
        )
    if port is not None and contradictions:
        lines.append(_render_signals_block(port, contradictions, source_role, _book_root(port)))
    return "\n".join(lines).rstrip() + "\n"


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
    """Ingest a published shared/<role>/ artifact into the Book.

    Reads ``src_path`` under ``branches/shared/``, stages a source page,
    idempotently merges ``book/index.md``, appends ``book/log.md``, and
    publishes the three files through ``mos_publish_to_shared`` as Ethics.

    Reel-ref propagation (for drill-down audit):
    - ``reel_ref`` becomes the page default: embedded in frontmatter, and
      appended as ``^[reel_ref]`` to every substantive claim line in the
      body. Auto-derived from MINIONS_ROLE_NAME + MINIONS_SESSION_ID if
      not explicitly provided.
    - ``claim_refs`` is an optional ``{sentence_prefix: reel_ref}`` map
      that overrides the page default for specific claims — useful when
      different sentences in one summary come from different subagent
      transcripts (different ``task_id`` under the same session).
    """
    resolved_port = _resolve_port(port)
    _validate_component("source_role", source_role)
    _validate_component("source_slug", source_slug)
    slug = f"{source_role}-{source_slug}"
    src, source_file = _resolve_source_path(resolved_port, src_path)
    resolved_title = (title or src.stem).strip() or src.stem
    date_ingested = _now_iso()
    raw_body = summary.strip() + "\n" if summary is not None else _read_first_lines(src)

    # Auto-derive reel_ref if not explicitly provided.
    if reel_ref is None:
        role = os.environ.get("MINIONS_ROLE_NAME", "").strip()
        session = os.environ.get("MINIONS_SESSION_ID", "").strip()
        if role and session:
            reel_ref = f"{role}/{session}"

    # Inject per-claim reel_ref markers (Slice A: claim-level provenance).
    body = _inject_claim_refs(
        raw_body,
        claim_refs=claim_refs,
        page_default_ref=reel_ref,
    )

    page = (
        _render_source_frontmatter(
            title=resolved_title,
            slug=slug,
            source_file=source_file,
            source_role=source_role,
            date_ingested=date_ingested,
            reel_ref=reel_ref,
        )
        + body
    )
    page_stage = _stage_text(resolved_port, f"book-source-{slug}.md", page)
    contradictions = _detect_contradictions(resolved_port, slug, body, source_role)
    contradiction_stage: Path | None = None
    contradiction_slug = _contradiction_slug(slug)
    if contradictions:
        contradiction_stage = _stage_text(
            resolved_port,
            f"book-contradiction-{slug}.md",
            _render_contradiction_page(
                slug, contradictions, source_role, date_ingested, port=resolved_port
            ),
        )
    index_entries = [(slug, resolved_title, "source")]
    if contradictions:
        index_entries.append((contradiction_slug, f"Contradiction: {slug}", "contradiction"))
    index_stage = _index_append_many(resolved_port, index_entries)
    log_stage = _log_append(
        resolved_port,
        "ingest",
        slug,
        source_file=source_file,
        source_role=source_role,
        title=resolved_title,
        contradiction_count=len(contradictions),
    )

    message = f"ethics: ingest {slug}"
    files: list[tuple[Path, str]] = [(page_stage, f"sources/{slug}.md")]
    if contradiction_stage is not None:
        files.append((contradiction_stage, f"contradictions/{contradiction_slug}.md"))
    files.extend([(index_stage, "index.md"), (log_stage, "log.md")])
    publish_results = [_publish_files(resolved_port, files, message)]
    dag_edges_created = _emit_contradiction_dag_edges(resolved_port, contradictions)

    logger.info(
        "book ingest: port=%d slug=%s source=%s publishes=%d contradictions=%d dag_edges=%d",
        resolved_port,
        slug,
        source_file,
        len(publish_results),
        len(contradictions),
        dag_edges_created,
    )
    return {
        "slug": slug,
        "book_path": f"book/sources/{slug}.md",
        "indexed": True,
        "logged": True,
        "contradictions": contradictions,
        "contradiction_count": len(contradictions),
        "contradiction_path": (
            f"book/contradictions/{contradiction_slug}.md" if contradictions else None
        ),
        "dag_edges_created": dag_edges_created,
        "publish_results": publish_results,
    }


def mos_book_ingest_batch(
    sources: list[dict[str, Any]],
    *,
    port: int | None = None,
) -> dict[str, object]:
    """Ingest multiple shared artifacts into the Book in one ordered batch.

    **Why batch:** single-source :func:`mos_book_ingest` is order-dependent —
    contradiction detection only sees pages already on disk when each source
    arrives. If three sources arrive in order A, B, C and B contradicts both
    A and C, the run-by-run result depends on whether C is ingested before
    or after B. Batch ingest fixes this: phase 1 stages all incoming sources
    in memory, phase 2 runs contradiction detection over the full set
    (existing pages + the entire incoming batch), then phase 3 publishes
    everything in a single commit.

    Each entry in ``sources`` is a dict with the same keys
    :func:`mos_book_ingest` accepts: ``src_path``, ``source_role``,
    ``source_slug``, optional ``title``, ``summary``, ``reel_ref``,
    ``claim_refs``.

    Returns:
        A dict with ``ingested`` (list of per-source result dicts) and
        ``total_contradictions`` (count across the batch).
    """
    resolved_port = _resolve_port(port)
    if not sources:
        return {"ingested": [], "total_contradictions": 0}

    # Phase 1 — stage all incoming sources in memory.
    staged: list[dict[str, Any]] = []
    for src_entry in sources:
        src_path = src_entry["src_path"]
        source_role = src_entry["source_role"]
        source_slug = src_entry["source_slug"]
        _validate_component("source_role", source_role)
        _validate_component("source_slug", source_slug)
        slug = f"{source_role}-{source_slug}"
        src, source_file = _resolve_source_path(resolved_port, src_path)
        title = src_entry.get("title")
        summary = src_entry.get("summary")
        reel_ref = src_entry.get("reel_ref")
        claim_refs = src_entry.get("claim_refs")
        resolved_title = (title or src.stem).strip() or src.stem
        date_ingested = _now_iso()
        raw_body = summary.strip() + "\n" if summary is not None else _read_first_lines(src)

        if reel_ref is None:
            role = os.environ.get("MINIONS_ROLE_NAME", "").strip()
            session = os.environ.get("MINIONS_SESSION_ID", "").strip()
            if role and session:
                reel_ref = f"{role}/{session}"

        body = _inject_claim_refs(
            raw_body,
            claim_refs=claim_refs,
            page_default_ref=reel_ref,
        )

        staged.append(
            {
                "slug": slug,
                "source_role": source_role,
                "source_file": source_file,
                "title": resolved_title,
                "date_ingested": date_ingested,
                "body": body,
                "reel_ref": reel_ref,
            }
        )

    # Phase 2 — contradiction detection over (existing pages + batch).
    detection_results: list[list[dict[str, Any]]] = []
    in_memory_overlay: dict[str, str] = {}

    for entry in staged:
        contradictions = _detect_contradictions_with_overlay(
            resolved_port,
            entry["slug"],
            entry["body"],
            entry["source_role"],
            overlay=in_memory_overlay,
        )
        detection_results.append(contradictions)
        in_memory_overlay[entry["slug"]] = entry["body"]

    # Phase 3 — publish everything in a SINGLE commit.
    ingested: list[dict[str, object]] = []
    total_contradictions = 0
    batch_index_entries: list[tuple[str, str, str]] = []
    batch_log_fields: list[dict[str, Any]] = []
    files: list[tuple[Path, str]] = []
    slugs_for_message: list[str] = []

    for entry, contradictions in zip(staged, detection_results, strict=True):
        slug = entry["slug"]
        slugs_for_message.append(slug)
        page = (
            _render_source_frontmatter(
                title=entry["title"],
                slug=slug,
                source_file=entry["source_file"],
                source_role=entry["source_role"],
                date_ingested=entry["date_ingested"],
                reel_ref=entry["reel_ref"],
            )
            + entry["body"]
        )
        page_stage = _stage_text(resolved_port, f"book-source-{slug}.md", page)
        files.append((page_stage, f"sources/{slug}.md"))

        contradiction_slug = _contradiction_slug(slug)
        if contradictions:
            contradiction_stage = _stage_text(
                resolved_port,
                f"book-contradiction-{slug}.md",
                _render_contradiction_page(
                    slug,
                    contradictions,
                    entry["source_role"],
                    entry["date_ingested"],
                    port=resolved_port,
                ),
            )
            files.append((contradiction_stage, f"contradictions/{contradiction_slug}.md"))

        batch_index_entries.append((slug, entry["title"], "source"))
        if contradictions:
            batch_index_entries.append(
                (contradiction_slug, f"Contradiction: {slug}", "contradiction")
            )
        batch_log_fields.append(
            {
                "op": "ingest",
                "slug": slug,
                "source_file": entry["source_file"],
                "source_role": entry["source_role"],
                "title": entry["title"],
                "contradiction_count": len(contradictions),
                "batch": True,
            }
        )
        dag_edges = _emit_contradiction_dag_edges(resolved_port, contradictions)
        total_contradictions += len(contradictions)

        ingested.append(
            {
                "slug": slug,
                "book_path": f"book/sources/{slug}.md",
                "contradictions": contradictions,
                "contradiction_count": len(contradictions),
                "contradiction_path": (
                    f"book/contradictions/{contradiction_slug}.md" if contradictions else None
                ),
                "dag_edges_created": dag_edges,
            }
        )

    # One combined index + log stage covering every source in the batch.
    index_stage = _index_append_many(resolved_port, batch_index_entries)
    log_stage = _log_append_many(resolved_port, batch_log_fields)
    files.append((index_stage, "index.md"))
    files.append((log_stage, "log.md"))

    summary_slug = slugs_for_message[0] if len(slugs_for_message) == 1 else "batch"
    message = f"ethics: ingest {summary_slug} (batch x{len(staged)})"
    publish_result = _publish_files(resolved_port, files, message)
    for ingest_entry in ingested:
        ingest_entry["publish_results"] = [publish_result]

    logger.info(
        "book ingest_batch: port=%d sources=%d total_contradictions=%d",
        resolved_port,
        len(staged),
        total_contradictions,
    )
    return {
        "ingested": ingested,
        "total_contradictions": total_contradictions,
    }
