"""Book index operations - index.md and log.md management.

Extracted from book.py to reduce file size.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from minions.errors import BookError

logger = logging.getLogger(__name__)


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


def _render_relations_block(edges: list[dict[str, str]]) -> str:
    """Render the ## Relations section appended to index.md."""
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
    """Render index.md with optional relations block."""
    from minions.tools.book_helpers import _scan_book_edges

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


def _index_append_many(
    port: int,
    entries_to_append: list[tuple[str, str, str]],
) -> Path:
    from minions.tools.book_helpers import _book_root, _parse_index_entries, _stage_text

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
    from minions.tools.book_helpers import _book_root, _stage_text
    from minions.tools.book_utils import now_iso as _now_iso

    log_path = _book_root(port) / "log.md"
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    entry = {"timestamp": _now_iso(), "op": op, "slug": slug, **fields}
    text = existing + json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
    return _stage_text(port, f"book-log-{slug}.md", text)


def _log_append_many(port: int, entries: list[dict[str, Any]]) -> Path:
    """Append multiple log entries and stage a single log.md file."""
    from minions.tools.book_helpers import _book_root, _stage_text
    from minions.tools.book_utils import now_iso as _now_iso

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


__all__ = [
    "_book_path_for_page_kind",
    "_index_append",
    "_index_append_many",
    "_index_entry",
    "_log_append",
    "_log_append_many",
    "_render_index",
    "_render_relations_block",
]
