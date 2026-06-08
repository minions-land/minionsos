"""Book crystallize module - session crystallization and synthesis.

Extracted from book.py to focus on crystallization workflow.
Contains mos_book_crystallize_session and mos_book_save_synthesis.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from minions.config import slugify
from minions.errors import BookError
from minions.paths import project_shared_subdir, project_workspace_root
from minions.tools.book_helpers import (
    _inject_claim_refs,
    _resolve_port,
    _stage_text,
)
from minions.tools.book_index import _index_append_many, _log_append
from minions.tools.book_utils import now_iso as _now_iso
from minions.tools.book_utils import quoted as _quoted
from minions.tools.book_utils import validate_component as _validate_component

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


def _crystallize_session_window(
    port: int,
    role: str,
    window_minutes: int,
    max_chars: int,
) -> tuple[str, list[str]]:
    """Build a verbatim crystallization body for a role's recent session window."""
    from minions.tools.draft import _load_draft, _parse_iso

    draft = _load_draft(port)
    nodes = draft.get("nodes", []) or []
    cutoff = datetime.now(UTC) - timedelta(minutes=int(window_minutes))

    role_nodes = []
    for node in nodes:
        if str(node.get("author_role", "")) != role:
            continue
        created = _parse_iso(str(node.get("created_at", "") or ""))
        if created is None or created < cutoff:
            continue
        role_nodes.append(node)
    role_nodes.sort(key=lambda n: str(n.get("created_at", "")))

    cited_ids: list[str] = []
    lines = [
        f"# Session crystallization: {role}",
        "",
        f"**Window**: last {window_minutes} minutes",
        f"**Crystallized at**: {_now_iso()}",
        f"**Role**: {role}",
        "",
        (
            "Verbatim digest of one continuous reasoning interval, "
            "captured at a context-reset boundary so the closed "
            "thought-window survives across sessions."
        ),
        "",
        "## Draft nodes added in window",
        "",
    ]
    if not role_nodes:
        lines.append("*(no Draft nodes in this window)*")
    else:
        for node in role_nodes:
            node_id = str(node.get("id", ""))
            cited_ids.append(node_id)
            text = str(node.get("text", "")).strip().replace("\n", " ")
            lines.append(
                f"- `[{node_id}]` ({node.get('type', '')}, "
                f"{node.get('support_status', '')}, conf={node.get('confidence', '')}): {text}"
            )

    events_dir = project_workspace_root(port) / "events"
    eacn_lines: list[str] = []
    if events_dir.exists():
        from minions.tools.draft import _parse_iso as parse_iso_event

        for jsonl in sorted(events_dir.glob("*.jsonl")):
            try:
                with jsonl.open("r", encoding="utf-8") as f:
                    for raw in f:
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        ts = str(event.get("timestamp", "") or event.get("ts", ""))
                        ev_dt = parse_iso_event(ts)
                        if ev_dt is None or ev_dt < cutoff:
                            continue
                        sender = str(event.get("sender", "") or event.get("from", ""))
                        if sender != role:
                            continue
                        payload = event.get("payload", event)
                        text = str(payload.get("text") or payload.get("content") or "").replace(
                            "\n", " "
                        )
                        if not text:
                            continue
                        if len(text) > 400:
                            text = text[:400] + "…"
                        eacn_lines.append(f"- {ts} [{event.get('type', '')}] {text}")
            except OSError:
                continue

    lines.extend(["", "## EACN messages sent in window", ""])
    if not eacn_lines:
        lines.append("*(no EACN messages from this role in this window)*")
    else:
        lines.extend(eacn_lines[-50:])

    body = "\n".join(lines) + "\n"
    if len(body) > max_chars:
        body = body[: max_chars - 80] + "\n\n*(truncated to fit crystallization size budget)*\n"
    return body, cited_ids


def mos_book_crystallize_session(
    role: str,
    window_minutes: int = 60,
    *,
    max_chars: int = 24000,
    port: int | None = None,
) -> dict[str, object]:
    """Crystallize a role's session window into a verbatim Book page.

    A "session" is the closed reasoning interval between two context-reset
    boundaries. At reset/compact time the role's recent thinking would be
    lost — this captures it as durable product memory before that happens,
    by digesting:
      - Draft nodes the role added in the window (verbatim, with IDs),
      - EACN messages the role sent in the window (verbatim, truncated),
      - structured pointers only, no paraphrase.

    Whitelisted to Ethics only. Ethics audits the result through its normal
    Book + mock-review path; the verbatim contract makes that easy
    because the page never invents content beyond what's in the sources.
    """
    resolved_port = _resolve_port(port)
    _validate_component("role", role)
    body, cited = _crystallize_session_window(
        resolved_port, role, int(window_minutes), int(max_chars)
    )
    crystallization_dir = project_shared_subdir(resolved_port, "ethics") / ".crystallizations"
    crystallization_dir.mkdir(parents=True, exist_ok=True)
    ts_slug = re.sub(r"[^A-Za-z0-9]", "", _now_iso())
    temp_path = crystallization_dir / f"session-{role}-{ts_slug}.md"
    temp_path.write_text(body, encoding="utf-8")
    try:
        from minions.tools.book_ingest import mos_book_ingest

        ingest_result = mos_book_ingest(
            src_path=str(temp_path),
            source_role="ethics",
            source_slug=f"session-{role}-{ts_slug.lower()}",
            title=f"Session crystallization: {role} ({window_minutes}m)",
            port=resolved_port,
        )
    finally:
        with contextlib.suppress(OSError):
            temp_path.unlink(missing_ok=True)
    return {
        "role": role,
        "window_minutes": int(window_minutes),
        "book_path": ingest_result.get("book_path"),
        "cited_node_ids": cited,
        "char_count": len(body),
    }


def mos_book_save_synthesis(
    question: str,
    answer: str,
    sources: list[str] | None = None,
    *,
    slug: str | None = None,
    port: int | None = None,
    reel_ref: str | None = None,
) -> dict[str, object]:
    """Save a question→answer pair as a compounding Book page.

    **Compounding queries pattern**: when a role synthesizes
    an answer from multiple Book pages, calling this tool materializes
    that synthesis as a new ``book/queries/<slug>.md`` page. Future
    queries match the question text and surface the prior answer first,
    so knowledge compounds across sessions instead of being re-derived.

    Args:
        question: The query text the answer responds to.
        answer: The synthesized answer (free-form markdown).
        sources: Optional list of ``book/sources/<slug>.md`` paths the
            answer drew from. Surfaced in frontmatter for audit.
        slug: Optional explicit slug for the query page. Defaults to a
            slugified prefix of the question.
        port: Project port.
        reel_ref: Optional reel pointer. Defaults to the caller's session.

    Returns:
        ``{"slug", "book_path", "publish_result"}``.

    Notes on form-vs-content boundary:
        This tool writes the answer text verbatim — it does not analyze,
        rephrase, or judge the answer. The caller (a role) is responsible
        for the synthesis. Ethics is purely mechanical here: it owns the
        formal structure (frontmatter, index entry, log line) but never
        the substantive content.
    """
    resolved_port = _resolve_port(port)
    if not question.strip():
        raise BookError("question must be non-empty")
    if not answer.strip():
        raise BookError("answer must be non-empty")

    if slug is None:
        slug = slugify(question)[:60] or f"q-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    _validate_component("slug", slug)

    date_ingested = _now_iso()

    if reel_ref is None:
        role = os.environ.get("MINIONS_ROLE_NAME", "").strip()
        session = os.environ.get("MINIONS_SESSION_ID", "").strip()
        if role and session:
            reel_ref = f"{role}/{session}"

    sources = sources or []
    fm_lines = [
        "---",
        "type: query",
        f"slug: {_quoted(slug)}",
        f"question: {_quoted(question.strip())}",
        f"date_created: {_quoted(date_ingested)}",
        "page_kind: query",
        f"sources: {json.dumps(sources, ensure_ascii=False)}",
    ]
    if reel_ref:
        fm_lines.append(f"reel_ref: {_quoted(reel_ref)}")
    fm_lines.extend(["---", ""])

    body_with_refs = _inject_claim_refs(
        answer.strip() + "\n",
        claim_refs=None,
        page_default_ref=reel_ref,
    )

    page_text = "\n".join(fm_lines) + body_with_refs
    page_stage = _stage_text(resolved_port, f"book-query-{slug}.md", page_text)

    title = f"Q: {question.strip()[:80]}"
    index_stage = _index_append_many(resolved_port, [(slug, title, "query")])
    log_stage = _log_append(
        resolved_port,
        "save_synthesis",
        slug,
        question=question.strip()[:200],
        source_count=len(sources),
    )

    message = f"ethics: save synthesis {slug}"
    publish_results = [
        _publish_files(
            resolved_port,
            [
                (page_stage, f"queries/{slug}.md"),
                (index_stage, "index.md"),
                (log_stage, "log.md"),
            ],
            message,
        )
    ]

    logger.info(
        "book save_synthesis: port=%d slug=%s source_count=%d",
        resolved_port,
        slug,
        len(sources),
    )
    return {
        "slug": slug,
        "book_path": f"book/queries/{slug}.md",
        "publish_results": publish_results,
    }
