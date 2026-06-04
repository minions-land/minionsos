"""Book (L2) durable product memory for MinionsOS projects.

The Draft is L1: fast, mutable coordination state for what roles are
testing, deciding, or handing off right now. The Book is L2: durable
product memory compiled from shared artefacts after they land.

Phase 2 implements the minimum writable surface under
``branches/shared/book/``. Ethics is the only writer: other roles publish raw
artefacts to their own shared subdirs, then Ethics ingest-compiles them into
book pages using the shared publish lock and commit machinery.

The full design follows the W1/W2/W3/W4/W5 mnemonic from the dev log:
W1 ingest-time compilation, W2 contradiction callouts, W3 ``hot.md`` as a
rolling wake-up cache, W4 lint, and W5 schema co-evolution. This phase ships
W1's file surface plus simple read tools only. Phase 5 adds W2 lexical
contradiction callouts. There are no LLM calls in the Book layer.

Book pages live beside the raw L1 artefacts in the shared worktree so
git history remains auditable. Writes are staged outside ``branches/shared``
and published through ``mos_publish_to_shared(role="ethics", ...)``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from pydantic import Field

from minions.config import slugify
from minions.errors import BookError
from minions.paths import (
    project_shared_draft_json,
    project_shared_subdir,
    project_shared_workspace,
    project_state_dir,
    project_workspace_root,
)
from minions.tools._returns import DictLikeBaseModel
from minions.tools.book_utils import (
    atomic_write_text as _atomic_write_text,
    now_iso as _now_iso,
    quoted as _quoted,
    validate_component as _validate_component,
)
from minions.tools.publish import mos_publish_files_to_shared, mos_publish_to_shared

# Import public API functions from modularized files
from minions.tools.book_audit import mos_book_audit_walk, mos_book_resolve_contradiction  # noqa: F401
from minions.tools.book_contradiction import (
    _detect_contradictions,
    _detect_contradictions_with_overlay,
)
from minions.tools.book_crystallize import (  # noqa: F401
    mos_book_crystallize_session,
    mos_book_save_synthesis,
)
from minions.tools.book_ingest import mos_book_ingest, mos_book_ingest_batch  # noqa: F401
from minions.tools.book_promote import mos_book_promote_verified, mos_book_ratify  # noqa: F401
from minions.tools.book_helpers import (
    _book_root,
    _contradiction_slug,
    _env_port,
    _inject_claim_refs,
    _oneline,
    _parse_frontmatter,
    _parse_index_entries,
    _read_first_lines,
    _render_source_frontmatter,
    _render_v2_frontmatter,
    _resolve_port,
    _resolve_source_path,
    _scan_book_edges,
    _stage_path,
    _stage_text,
    _strip_frontmatter,
    _token_list,
    _tokens,
    _update_frontmatter_field,
)
from minions.tools.book_index import (
    _index_append,
    _index_append_many,
    _log_append,
    _log_append_many,
)
from minions.tools.book_lint import mos_book_lint  # noqa: F401
from minions.tools.book_query import BookQueryResult, mos_book_query  # noqa: F401
from minions.tools.book_special import mos_book_dead_end, mos_book_open_question  # noqa: F401

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_NEGATION_MARKERS = frozenset(
    {
        "cannot",
        "fail",
        "failed",
        "fails",
        "false",
        "never",
        "no",
        "none",
        "not",
        "refute",
        "refuted",
        "refutes",
        "unsupported",
        "without",
    }
)
_COMMON_SHARED_TERMS = frozenset(
    {
        "about",
        "across",
        "after",
        "again",
        "among",
        "around",
        "because",
        "before",
        "behind",
        "being",
        "below",
        "between",
        "beyond",
        "could",
        "during",
        "first",
        "frontmatter",
        "index",
        "instead",
        "other",
        "page",
        "pages",
        "shared",
        "should",
        "since",
        "source",
        "sources",
        "their",
        "there",
        "these",
        "those",
        "through",
        "title",
        "toward",
        "under",
        "until",
        "versus",
        "where",
        "which",
        "while",
        "within",
        "would",
    }
)
# P2 subject-gate (2026-05-29 audit): the lexical detector fired on 71% false
# positives because a single shared >=5-char token + asymmetric nearby
# negation was enough. Most FPs rode on provenance/scaffolding nouns (role
# names, GPU/harness words, dates) or on stock idioms ("load-bearing"). These
# sets gate the shared term to plausible *claim subjects* only.
# NOTE: this set still includes the retired-role stamps ("coder", "noter",
# "writer") on purpose — they appear in provenance bylines of existing Book
# pages on disk, and gating them out is required for backward-compat with that
# historical data. Do not remove.
_PROVENANCE_SHARED_TERMS = frozenset(
    {
        "artifact",
        "bench",
        "coder",
        "commit",
        "cuda",
        "ethics",
        "expert",
        "gru",
        "harness",
        "kernel",
        "noter",
        "phase",
        "profiler",
        "reel",
        "report",
        "scaffolding",
        "session",
        "torch",
        "wrapper",
        "writer",
    }
)
# Stock phrases whose negation marker is idiomatic, not an assertion about the
# shared term. If either excerpt contains one, the pair is not a contradiction.
_CONTRADICTION_IDIOMS = (
    "load-bearing",
    "load bearing",
    "no blocking flags",
    "not applicable",
    "not_refuted",
    "not refuted",
)
_MIN_CONTRADICTION_SENTENCE_CHARS = 40
_MIN_SHARED_TERM_CHARS = 5
_NEGATION_LOOKBACK_TOKENS = 4
_MAX_CONTRADICTIONS = 5
_MAX_LINT_FINDINGS = 100
_STALE_CLAIM_SECONDS = 72 * 60 * 60


# ---------------------------------------------------------------------------
# Typed return shapes
# ---------------------------------------------------------------------------


class BookQueryResult(DictLikeBaseModel):
    """Result shape for ``mos_book_query``.

    ``matches`` is the ordered match list. Each entry always carries
    ``slug``/``title``/``page_kind``/``book_path``/``score``, plus
    ``paper_role``/``motif_kind``/``ratified_by`` read from the page
    frontmatter (empty string when absent). ``status`` is included when
    the caller passes ``include_status=True`` (default), and ``relations``
    is included when ``include_relations=True`` (default). ``total`` is
    the pre-``max_pages``-slice count of matches; ``queried`` echoes the
    raw query string.
    """

    matches: list[dict[str, Any]] = Field(
        description="Ranked Book index matches (sliced to max_pages)."
    )
    total: int = Field(description="Total match count before max_pages slice.")
    queried: str = Field(description="The raw query text the caller passed in.")


# ============================================================================
# SECTION 2: Core Helper Functions (lines ~180-700)
# ============================================================================
# - Path resolution (_book_root, _sources_dir, etc.)
# - Port/environment helpers (_env_port, _resolve_port)
# - Utility functions (_now_iso, _atomic_write_text, _quoted, _validate_component)
# - Frontmatter parsing and rendering
# - File I/O helpers
# ============================================================================
# Helper functions now imported from book_helpers, book_index, book_contradiction
# ============================================================================



# _render_v2_frontmatter, _render_source_frontmatter, _contradiction_slug,
# _resolve_port, _resolve_source_path, _stage_path, _stage_text, _read_first_lines
# now imported from book_helpers


def _validate_component(label: str, value: str) -> None:
    if not value or not _SAFE_COMPONENT_RE.fullmatch(value):
        raise BookError(
            f"{label} must be a safe path component "
            "(letters, numbers, dot, underscore, hyphen; no slashes)."
        )


# _resolve_port, _resolve_source_path already imported from book_helpers

# _stage_path, _stage_text, _read_first_lines, _inject_claim_refs
# already imported from book_helpers

_CLAIM_REF_RE = re.compile(r"\^\[([^\]]+)\]")
# _strip_frontmatter, _oneline already imported from book_helpers

def _is_structural_line(sentence: str) -> bool:
    """True for non-claim lines: headings, tables, provenance bylines, dates.

    P2 gate (2026-05-29 audit): these lines are not declarative claims, so a
    shared token between two of them is never a real contradiction. Filtering
    them out removed the bulk of the detector's 71% false-positive rate.
    """
    s = sentence.strip()
    if not s:
        return True
    if s[0] in "#|>":  # markdown heading, table row, residual blockquote
        return True
    # Provenance byline: "**Coder · 2026-05-28 · cuda:1 ..." — a middot or a
    # leading bold-role stamp marks metadata, not an assertion. The role list
    # below intentionally includes retired-role stamps (coder/noter/writer) for
    # backward-compat with bylines in existing Book pages on disk.
    if "·" in s[:40]:
        return True
    lowered = s.lower()
    return lowered.startswith(("**coder", "**noter", "**expert", "**ethics", "**writer", "**gru"))


# Contradiction detection functions moved to book_contradiction.py
# _strip_frontmatter, _oneline already imported from book_helpers


def _source_role_unmarked_ratio(book_root: Path, source_role: str) -> float | None:
    """Best-effort estimate of a role's unmarked-claim ratio from its Book pages.

    Reads the role's existing source pages, counts non-empty body lines, and
    counts how many carry an [evidence:|speculation|derived:] marker. Returns
    the unmarked ratio in [0, 1], or None when there is too little data.

    This is a *curator signal*, not an Ethics verdict: it is purely descriptive.
    Ethics still does its own statistical audit on the live EACN stream; this
    just gives Ethics a starting point when adjudicating a contradiction.
    """
    sources = book_root / "sources"
    if not sources.exists():
        return None
    role_pages = [p for p in sources.glob("*.md") if p.name.startswith(f"{source_role}-")]
    if not role_pages:
        return None
    total = 0
    marked = 0
    marker_re = re.compile(r"\[(evidence|speculation|derived)[:\]]")
    for page in role_pages:
        try:
            text = page.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
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


def _opposing_page_age_days(book_root: Path, opposing_page: str) -> float | None:
    """Read frontmatter date_ingested on the opposing source page; return age in days."""
    rel = opposing_page.removeprefix("book/")
    page = book_root / rel
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
    """Extract source_role from an opposing page path like book/sources/expert-foo.md."""
    name = opposing_page.rsplit("/", 1)[-1]
    stem = name.removesuffix(".md")
    if "-" in stem:
        return stem.split("-", 1)[0]
    return ""


def _draft_signals_for_terms(port: int, terms: list[str]) -> dict[str, Any]:
    """Best-effort lookup of Draft nodes whose text matches any shared term.

    Returns aggregated counts (no node bodies) so the contradiction page stays
    short. Terms are lowercased; matching is substring-based against node text.
    """
    try:
        from minions.tools.draft import _load_decay, _load_draft
    except ImportError:
        return {}
    try:
        draft = _load_draft(port)
    except (OSError, RuntimeError):
        return {}
    nodes = draft.get("nodes", []) or []
    edges = draft.get("edges", []) or []
    decay = _load_decay(port)
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


def _render_signals_block(
    port: int,
    contradictions: list[dict[str, object]],
    new_source_role: str,
    book_root: Path,
) -> str:
    """Build the Statistical signals section of a contradiction page.

    Pure observation; no verdict. Ethics consumes this as the evidence-list
    starting point when writing its adjudication. Each contradiction
    candidate gets one row; values that can't be computed render as '-'.
    """
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


# _parse_index_entries, _scan_book_edges already imported from book_helpers

def _render_relations_block(edges: list[dict[str, str]]) -> str:
    """Render the ``## Relations`` section appended to ``index.md``."""
    if not edges:
        return ""
    lines = ["", "## Relations", ""]
    lines.append(f"_Auto-derived from on-disk contradiction pages. Count: {len(edges)}._")
    lines.append("")
    for edge in edges:
        lines.append(
            f"- `{edge['from']}` --[{edge['relation']}]--> `{edge['to']}`  "
            f"(evidence: `{edge['evidence']}`)"
        )
    return "\n".join(lines)


def _render_index(entries: list[dict[str, str]], *, book_root: Path | None = None) -> str:
    """Render ``index.md``.

    When *book_root* is provided we scan ``contradictions/`` to synthesize
    a ``## Relations`` block at the bottom of the file (Issue: Book has
    nodes but no edges). Edges are re-derived per render so the index is
    always consistent with on-disk pages — see :func:`_scan_book_edges`.
    """
    lines = ["# Book Index", ""]
    for entry in entries:
        title = entry.get("title", entry["slug"])
        page_type = entry.get("type", entry.get("page_kind", "source"))
        page_kind = entry.get("page_kind", page_type)
        lines.extend(
            [
                f"## {title}",
                f"slug: {entry['slug']}",
                f"type: {page_type}",
                f"page_kind: {page_kind}",
                f"book_path: {entry['book_path']}",
                "",
            ]
        )
    out = "\n".join(lines).rstrip()
    if book_root is not None:
        relations = _render_relations_block(_scan_book_edges(book_root))
        if relations:
            out = out + "\n" + relations
    return out + "\n"


def _book_path_for_page_kind(page_kind: str, slug: str) -> str:
    if page_kind == "source":
        return f"book/sources/{slug}.md"
    if page_kind == "contradiction":
        return f"book/contradictions/{slug}.md"
    if page_kind == "query":
        return f"book/queries/{slug}.md"
    if page_kind == "open_question":
        return f"book/open_questions/{slug}.md"
    raise BookError(f"unsupported book page_kind: {page_kind!r}")


def _index_entry(slug: str, title: str, page_kind: str) -> dict[str, str]:
    return {
        "slug": slug,
        "title": title,
        "type": page_kind,
        "page_kind": page_kind,
        "book_path": _book_path_for_page_kind(page_kind, slug),
    }


def _index_append_many(
    port: int,
    entries_to_append: list[tuple[str, str, str]],
) -> Path:
    if not entries_to_append:
        raise BookError("at least one book index entry is required")
    index_path = _book_root(port) / "index.md"
    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    entries = _parse_index_entries(existing)
    next_entries = [
        _index_entry(slug, title, page_kind) for slug, title, page_kind in entries_to_append
    ]
    replacements = {entry["slug"]: entry for entry in next_entries}

    replaced: set[str] = set()
    merged: list[dict[str, str]] = []
    for entry in entries:
        slug = entry.get("slug", "")
        if slug in replacements:
            merged.append(replacements[slug])
            replaced.add(slug)
        else:
            merged.append(entry)
    for entry in next_entries:
        if entry["slug"] not in replaced:
            merged.append(entry)

    return _stage_text(
        port,
        f"book-index-{next_entries[0]['slug']}.md",
        _render_index(merged, book_root=_book_root(port)),
    )


def _index_append(port: int, slug: str, title: str, page_kind: str) -> Path:
    return _index_append_many(port, [(slug, title, page_kind)])


def _log_append(port: int, op: str, slug: str, **fields: Any) -> Path:
    log_path = _book_root(port) / "log.md"
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    entry = {"timestamp": _now_iso(), "op": op, "slug": slug, **fields}
    text = existing + json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
    return _stage_text(port, f"book-log-{slug}.md", text)


def _log_append_many(port: int, entries: list[dict[str, Any]]) -> Path:
    """Append multiple log entries and stage a single ``log.md`` file.

    Used by :func:`mos_book_ingest_batch` so a whole batch lands as one
    commit. Each entry must include ``op`` and ``slug``.
    """
    if not entries:
        raise BookError("at least one book log entry is required")
    log_path = _book_root(port) / "log.md"
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    now = _now_iso()
    rendered = existing
    for fields in entries:
        record = {"timestamp": now, **fields}
        rendered += json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    first_slug = entries[0].get("slug", "batch")
    return _stage_text(port, f"book-log-{first_slug}-batch.md", rendered)


def _log_append_many(port: int, entries: list[dict[str, Any]]) -> Path:
    """Append multiple log entries and stage a single ``log.md`` file.

    Used by :func:`mos_book_ingest_batch` so a whole batch lands as one
    commit. Each entry must include ``op`` and ``slug``.
    """
    if not entries:
        raise BookError("at least one book log entry is required")
    log_path = _book_root(port) / "log.md"
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    now = _now_iso()
    rendered = existing
    for fields in entries:
        record = {"timestamp": now, **fields}
        rendered += json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    first_slug = entries[0].get("slug", "batch")
    return _stage_text(port, f"book-log-{first_slug}-batch.md", rendered)


def _publish_file(
    port: int,
    abs_src: Path,
    rel_dst_under_book: str,
    message: str,
) -> dict[str, object]:
    rel_dst = Path(rel_dst_under_book)
    if rel_dst.is_absolute() or any(part == ".." for part in rel_dst.parts):
        raise BookError(f"book destination may not escape book/: {rel_dst_under_book!r}")
    # mos_publish_to_shared returns a PublishToSharedResult (DictLikeBaseModel),
    # which is read-compatible with dict[str, object] via __getitem__/get; the
    # cast keeps the existing book.py contract while preserving the typed model
    # at the publish layer.
    return cast(
        "dict[str, object]",
        mos_publish_to_shared(
            role="ethics",
            src_path=str(abs_src.resolve()),
            dst_subpath=f"book/{rel_dst.as_posix()}",
            commit_message=message,
            port=port,
        ),
    )


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


def _book_rel_path(book_root: Path, path: Path) -> str:
    try:
        return f"book/{path.relative_to(book_root).as_posix()}"
    except ValueError:
        return path.as_posix()


def _read_lint_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("book lint could not read %s: %s", path, exc)
        return ""


def _parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key:
            fields[key] = value.strip().strip("\"'")
    return fields


def _normalise_wikilink_slug(raw: str) -> str:
    return raw.split("|", 1)[0].split("#", 1)[0].strip().lower()


def _book_markdown_files(book_root: Path) -> list[Path]:
    if not book_root.exists():
        return []
    return sorted(path for path in book_root.rglob("*.md") if path.is_file())


def _wikilinks_by_page(pages: list[Path]) -> dict[Path, list[str]]:
    links: dict[Path, list[str]] = {}
    for page in pages:
        page_links = [
            slug
            for slug in (
                _normalise_wikilink_slug(raw) for raw in _WIKILINK_RE.findall(_read_lint_text(page))
            )
            if slug
        ]
        links[page] = page_links
    return links


def _book_lint_target_exists(book_root: Path, slug: str) -> bool:
    return (
        (book_root / "sources" / f"{slug}.md").exists()
        or (book_root / "contradictions" / f"contradiction-{slug}.md").exists()
        or (book_root / "contradictions" / f"{slug}.md").exists()
    )


def _add_lint_finding(
    findings: list[dict[str, object]],
    *,
    check: str,
    slug: str,
    detail: str,
    book_path: str,
    severity: str,
) -> None:
    if len(findings) >= _MAX_LINT_FINDINGS:
        return
    findings.append(
        {
            "check": check,
            "slug": slug,
            "detail": detail,
            "book_path": book_path,
            "severity": severity,
        }
    )


def _collect_book_lint_findings(port: int) -> list[dict[str, object]]:
    book_root = _book_root(port)
    pages = _book_markdown_files(book_root)
    links_by_page = _wikilinks_by_page(pages)
    findings: list[dict[str, object]] = []

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
                detail=(
                    f"Title token appears {count} times in book/index.md without a source page."
                ),
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
            detail=(
                f"Unresolved contradiction is {int(age_seconds // 3600)}h old (older than 72h)."
            ),
            book_path=_book_rel_path(book_root, page),
            severity="warning",
        )

    return findings


def _book_lint_result(findings: list[dict[str, object]]) -> dict[str, object]:
    counts = Counter(str(finding.get("check", "")) for finding in findings)
    return {
        "orphan_pages": counts["ORPHAN_PAGE"],
        "dead_links": counts["DEAD_LINK"],
        "missing_concept_pages": counts["MISSING_CONCEPT_PAGE"],
        "stale_claims": counts["STALE_CLAIM"],
        "lint_count": len(findings),
        "findings": findings,
    }


def _short_lint_value(value: object, *, limit: int = 160) -> str:
    text = _oneline(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _publish_book_lint_outputs(port: int, result: dict[str, object]) -> None:
    book_root = _book_root(port)
    log_path = book_root / "log.md"
    existing_log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    if existing_log and not existing_log.endswith("\n"):
        existing_log += "\n"
    log_fields = {
        "timestamp": _now_iso(),
        "op": "lint",
        "orphan_pages": result.get("orphan_pages", 0),
        "dead_links": result.get("dead_links", 0),
        "missing_concept_pages": result.get("missing_concept_pages", 0),
        "stale_claims": result.get("stale_claims", 0),
        "lint_count": result.get("lint_count", 0),
    }
    if result.get("error"):
        log_fields["error"] = _short_lint_value(result["error"])

    log_stage = _stage_text(
        port,
        "book-log-lint.md",
        existing_log + json.dumps(log_fields, ensure_ascii=False, sort_keys=True) + "\n",
    )

    message = "ethics: book lint"
    _publish_files(port, [(log_stage, "log.md")], message)


def _load_dag_for_match(port: int) -> dict[str, object]:
    path = project_shared_draft_json(port)
    if not path.exists():
        return {"nodes": [], "edges": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning(
            "book contradiction Draft edge lookup skipped: invalid Draft JSON at %s",
            path,
        )
        return {"nodes": [], "edges": []}
    if not isinstance(data, dict):
        return {"nodes": [], "edges": []}
    return data


def _normalise_match_text(text: object) -> str:
    return " ".join(str(text).lower().split())


def _find_dag_node_id(draft: dict[str, object], excerpt: object) -> str | None:
    needle = _normalise_match_text(excerpt)
    if not needle:
        return None
    nodes = draft.get("nodes", [])
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


def _emit_contradiction_dag_edges(port: int, contradictions: list[dict[str, object]]) -> int:
    if not contradictions:
        return 0

    draft = _load_dag_for_match(port)
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


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(text.lower()) if len(token) >= 3}


def _token_list(text: str) -> list[str]:
    """Ordered token list (with repeats) for term-frequency scoring."""
    return [token for token in _TOKEN_RE.findall(text.lower()) if len(token) >= 3]


def _is_contradiction_entry(entry: dict[str, str]) -> bool:
    """True if an index entry points at a tool-derived contradiction page.

    Contradiction pages are W2 callouts, not knowledge. They were polluting
    ~58% of ``mos_book_query`` result slots on live projects (the detector's
    lexical pass is high-recall / low-precision), so they are excluded from
    knowledge retrieval by default and reached instead through the
    ``relations`` edges on their source pages.
    """
    kind = (entry.get("page_kind") or entry.get("type") or "").strip().strip("`")
    if kind == "contradiction":
        return True
    slug = (entry.get("slug") or "").strip().strip("`")
    book_path = (entry.get("book_path") or "").strip().strip("`")
    return slug.startswith("contradiction-") or "/contradictions/" in book_path


def _read_page_body_tokens(book_root: Path, book_path: str) -> list[str]:
    """Tokenize a Book page body (frontmatter stripped) for BM25 scoring."""
    abs_path = book_root.parent.parent.parent / "branches" / "shared" / book_path
    if not abs_path.exists():
        rel = book_path[len("book/") :] if book_path.startswith("book/") else book_path
        abs_path = book_root / rel
    if not abs_path.exists():
        return []
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    return _token_list(_strip_frontmatter(text))


def _bm25_scores(
    query_tokens: set[str],
    docs: dict[str, list[str]],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> dict[str, float]:
    """Okapi BM25 over a small in-memory corpus. Pure function, no LLM.

    ``docs`` maps page slug -> body token list. Returns slug -> score for
    pages with a positive score only. This is the body-aware retrieval layer
    that lifted content-query recall from 0/17 to 16/17 on the live CODA
    project audit (2026-05-29) versus the prior title+filename-only match.
    """
    n_docs = len(docs)
    if not query_tokens or n_docs == 0:
        return {}
    df: Counter[str] = Counter()
    for tokens in docs.values():
        for term in set(tokens):
            if term in query_tokens:
                df[term] += 1
    total_len = sum(len(tokens) for tokens in docs.values())
    avgdl = (total_len / n_docs) if n_docs else 0.0
    scores: dict[str, float] = {}
    for slug, tokens in docs.items():
        if not tokens:
            continue
        tf = Counter(tokens)
        dl = len(tokens)
        score = 0.0
        for term in query_tokens:
            term_freq = tf.get(term, 0)
            if term_freq == 0:
                continue
            doc_freq = df.get(term, 0)
            idf = math.log(1 + (n_docs - doc_freq + 0.5) / (doc_freq + 0.5))
            denom = term_freq + k1 * (1 - b + b * (dl / avgdl if avgdl else 0.0))
            score += idf * (term_freq * (k1 + 1)) / denom if denom else 0.0
        if score > 0:
            scores[slug] = score
    return scores


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


# ============================================================================
# SECTION 4: Public API - Promote Functions (lines ~1970-2280)
# ============================================================================
# - mos_book_promote_verified: Promote verified content to Book
# - mos_book_ratify: Ethics ratification of Book pages
# ============================================================================

def _update_frontmatter_field(text: str, field: str, value: str) -> str:
    """Set/replace a frontmatter ``field: value`` line. Adds the field if absent.

    Used by :func:`mos_book_resolve_contradiction` to flip ``status:``.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        # No frontmatter — synthesize one
        return f"---\n{field}: {_quoted(value)}\n---\n\n{text}"

    new_lines: list[str] = ["---"]
    in_frontmatter = True
    found = False
    end_idx = -1
    for idx, line in enumerate(lines[1:], start=1):
        if in_frontmatter and line.strip() == "---":
            in_frontmatter = False
            end_idx = idx
            if not found:
                new_lines.append(f"{field}: {_quoted(value)}")
            new_lines.append(line)
            new_lines.extend(lines[idx + 1 :])
            break
        if in_frontmatter and line.startswith(f"{field}:"):
            new_lines.append(f"{field}: {_quoted(value)}")
            found = True
        else:
            new_lines.append(line)
    if end_idx == -1:
        # Malformed frontmatter — fallback: leave text untouched
        return text
    return "\n".join(new_lines).rstrip() + "\n"


# ============================================================================
# SECTION 8: Public API - Lint & Validation (lines ~3050-3099)
# ============================================================================
# - mos_book_lint: Comprehensive Book integrity checks (imported from book_lint)
# ============================================================================


# Hot-cache tools (mos_book_hot_update / mos_book_hot_get) were removed in the
# V23-era Memory simplification: the hot.md rolling wake-cache layer was retired.
# Cold-start orientation now comes directly from `mos_draft_view()` (orientation
# header + newest nodes), so a hand-maintained ~500-word Book summary is moot.


__all__ = [
    "BookError",
    "mos_book_audit_walk",
    "mos_book_crystallize_session",
    "mos_book_dead_end",
    "mos_book_ingest",
    "mos_book_ingest_batch",
    "mos_book_lint",
    "mos_book_open_question",
    "mos_book_promote_verified",
    "mos_book_query",
    "mos_book_ratify",
    "mos_book_resolve_contradiction",
    "mos_book_save_synthesis",
]
