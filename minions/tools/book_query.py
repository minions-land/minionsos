"""Book query module - BM25 search implementation.

Extracted from book.py to focus on search functionality.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import Field

from minions.tools._returns import DictLikeBaseModel

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class BookQueryResult(DictLikeBaseModel):
    """Result shape for mos_book_query."""

    matches: list[dict[str, Any]] = Field(
        description="Ranked Book index matches (sliced to max_pages)."
    )
    total: int = Field(description="Total match count before max_pages slice.")
    queried: str = Field(description="The raw query text the caller passed in.")


def tokenize_for_bm25(text: str) -> list[str]:
    """Tokenize text for BM25 scoring (ordered list with repeats)."""
    return [token for token in _TOKEN_RE.findall(text.lower()) if len(token) >= 3]


def compute_bm25_scores(
    query_tokens: set[str],
    documents: dict[str, list[str]],
    k1: float = 1.5,
    b: float = 0.75,
) -> dict[str, float]:
    """Compute BM25 scores for documents against query tokens."""
    n_docs = len(documents)
    if not n_docs or not query_tokens:
        return {}
    df: Counter[str] = Counter()
    for tokens in documents.values():
        for term in set(tokens):
            if term in query_tokens:
                df[term] += 1
    total_len = sum(len(tokens) for tokens in documents.values())
    avgdl = (total_len / n_docs) if n_docs else 0.0
    scores: dict[str, float] = {}
    for slug, tokens in documents.items():
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


def _is_contradiction_entry(entry: dict[str, str]) -> bool:
    """True if entry is a contradiction page (slug starts with 'contradiction-')."""
    return entry.get("slug", "").startswith("contradiction-")


def _read_page_body_tokens(book_root: Path, book_path: str) -> list[str]:
    """Read and tokenize the body of a Book page for BM25 scoring."""
    from minions.tools.book_helpers import _strip_frontmatter

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
    body = _strip_frontmatter(text)
    return tokenize_for_bm25(body)


def _read_page_frontmatter(book_root: Path, book_path: str) -> dict[str, str]:
    """Return parsed frontmatter dict for a Book page, or empty dict on failure."""
    from minions.tools.book_helpers import _parse_frontmatter

    abs_path = book_root.parent.parent.parent / "branches" / "shared" / book_path
    if not abs_path.exists():
        rel = book_path[len("book/") :] if book_path.startswith("book/") else book_path
        abs_path = book_root / rel
    if not abs_path.exists():
        return {}
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    return _parse_frontmatter(text)


def mos_book_query(
    text: str,
    max_pages: int = 5,
    *,
    port: int | None = None,
    include_status: bool = True,
    include_relations: bool = True,
    include_contradictions: bool = False,
    status_filter: str | None = None,
    paper_role_filter: str | None = None,
) -> BookQueryResult:
    """Body-aware keyword search over Book pages (title + filename + body)."""
    from minions.tools.book_helpers import (
        _book_root,
        _parse_index_entries,
        _resolve_port,
        _scan_book_edges,
        _tokens,
    )

    resolved_port = _resolve_port(port)
    query_tokens = _tokens(text)
    book_root = _book_root(resolved_port)
    index_path = book_root / "index.md"
    if not query_tokens or not index_path.exists():
        return BookQueryResult(matches=[], total=0, queried=text)

    entries = _parse_index_entries(index_path.read_text(encoding="utf-8"))
    if not include_contradictions:
        entries = [e for e in entries if not _is_contradiction_entry(e)]
    edges_by_from: dict[str, list[dict[str, str]]] = {}
    if include_relations:
        for edge in _scan_book_edges(book_root):
            edges_by_from.setdefault(edge["from"], []).append(
                {
                    "to": edge["to"],
                    "relation": edge["relation"],
                    "evidence": edge["evidence"],
                }
            )

    body_tokens_by_slug: dict[str, list[str]] = {
        entry["slug"]: _read_page_body_tokens(book_root, entry["book_path"]) for entry in entries
    }
    bm25_by_slug = compute_bm25_scores(query_tokens, body_tokens_by_slug)

    scored: list[dict[str, object]] = []
    for entry in entries:
        haystack = f"{entry.get('title', '')} {Path(entry.get('book_path', '')).name}"
        title_score = len(query_tokens & _tokens(haystack))
        body_score = bm25_by_slug.get(entry["slug"], 0.0)
        score: float = title_score + round(body_score, 4)
        if score <= 0:
            continue
        page_fm = _read_page_frontmatter(book_root, entry["book_path"])
        page_status = page_fm.get("status", "").strip().strip('"').strip("'")
        page_paper_role = page_fm.get("paper_role", "").strip().strip('"').strip("'")
        page_motif_kind = page_fm.get("motif_kind", "").strip().strip('"').strip("'")
        page_ratified_by = page_fm.get("ratified_by", "").strip().strip('"').strip("'")
        if status_filter is not None and page_status != status_filter:
            continue
        if paper_role_filter is not None and page_paper_role != paper_role_filter:
            continue
        emitted_score: float | int = title_score if body_score == 0 else score
        match: dict[str, object] = {
            "slug": entry["slug"],
            "title": entry.get("title", entry["slug"]),
            "page_kind": entry.get("page_kind", entry.get("type", "")),
            "book_path": entry["book_path"],
            "score": emitted_score,
        }
        if include_status:
            match["status"] = page_status
        match["paper_role"] = page_paper_role
        match["motif_kind"] = page_motif_kind
        match["ratified_by"] = page_ratified_by
        if include_relations:
            match["relations"] = edges_by_from.get(entry["slug"], [])
        scored.append(match)

    scored.sort(key=lambda item: (-float(item["score"]), str(item["title"]), str(item["slug"])))
    total = len(scored)
    limit = max(0, int(max_pages))
    return BookQueryResult(matches=scored[:limit], total=total, queried=text)


__all__ = [
    "BookQueryResult",
    "compute_bm25_scores",
    "mos_book_query",
    "tokenize_for_bm25",
]
