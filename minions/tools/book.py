"""Book (L2) durable product memory for MinionsOS projects.

The Draft is L1: fast, mutable coordination state for what roles are
testing, deciding, or handing off right now. The Book is L2: durable
product memory compiled from shared artefacts after they land.

Phase 2 implements the minimum writable surface under
``branches/shared/book/``. Noter is the only writer: other roles publish raw
artefacts to their own shared subdirs, then Noter ingest-compiles them into
book pages using the shared publish lock and commit machinery.

The full design follows the W1/W2/W3/W4/W5 mnemonic from the dev log:
W1 ingest-time compilation, W2 contradiction callouts, W3 ``hot.md`` as a
rolling wake-up cache, W4 lint, and W5 schema co-evolution. This phase ships
W1's file surface plus simple read tools only. Phase 5 adds W2 lexical
contradiction callouts. There are no LLM calls in the Book layer.

Book pages live beside the raw L1 artefacts in the shared worktree so
git history remains auditable. Writes are staged outside ``branches/shared``
and published through ``mos_publish_to_shared(role="noter", ...)``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from minions.paths import (
    project_shared_draft_json,
    project_shared_subdir,
    project_shared_workspace,
    project_state_dir,
    project_workspace_root,
)
from minions.tools.publish import mos_publish_to_shared

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_LINT_SUMMARY_START = "<!-- lint-summary-start -->"
_LINT_SUMMARY_END = "<!-- lint-summary-end -->"
_LINT_SUMMARY_BLOCK_RE = re.compile(
    rf"{re.escape(_LINT_SUMMARY_START)}.*?{re.escape(_LINT_SUMMARY_END)}",
    re.DOTALL,
)
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
        "after",
        "again",
        "because",
        "before",
        "being",
        "could",
        "first",
        "frontmatter",
        "index",
        "other",
        "page",
        "pages",
        "shared",
        "should",
        "source",
        "sources",
        "there",
        "these",
        "those",
        "through",
        "title",
        "under",
        "where",
        "which",
        "while",
        "would",
    }
)
_MIN_CONTRADICTION_SENTENCE_CHARS = 40
_MIN_SHARED_TERM_CHARS = 5
_NEGATION_LOOKBACK_TOKENS = 4
_MAX_CONTRADICTIONS = 5
_MAX_LINT_FINDINGS = 100
_MAX_HOT_BYTES = 4096
_STALE_CLAIM_SECONDS = 72 * 60 * 60


class BookError(Exception):
    """Raised when a book operation violates Phase 2 policy."""


def _book_root(port: int) -> Path:
    return project_shared_subdir(port, "book")


def _env_port() -> int:
    raw = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not raw:
        raise RuntimeError("MINIONS_PROJECT_PORT not set")
    return int(raw)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _render_source_frontmatter(
    *,
    title: str,
    slug: str,
    source_file: str,
    source_role: str,
    date_ingested: str,
) -> str:
    return "\n".join(
        [
            "---",
            "type: source",
            f"title: {_quoted(title)}",
            f"slug: {_quoted(slug)}",
            f"source_file: {_quoted(source_file)}",
            f"source_role: {_quoted(source_role)}",
            f"date_ingested: {_quoted(date_ingested)}",
            "page_kind: source",
            "confidence: high",
            "---",
            "",
        ]
    )


def _contradiction_slug(new_slug: str) -> str:
    return f"contradiction-{new_slug}"


def _validate_component(label: str, value: str) -> None:
    if not value or not _SAFE_COMPONENT_RE.fullmatch(value):
        raise BookError(
            f"{label} must be a safe path component "
            "(letters, numbers, dot, underscore, hyphen; no slashes)."
        )


def _resolve_port(port: int | None) -> int:
    if port is not None:
        return int(port)
    return _env_port()


def _resolve_source_path(port: int, src_path: str) -> tuple[Path, str]:
    workspace_root = project_workspace_root(port).resolve()
    shared_root = project_shared_workspace(port).resolve()
    raw = Path(src_path).expanduser()

    candidates: list[Path]
    if raw.is_absolute():
        candidates = [raw]
    else:
        candidates = [Path.cwd() / raw, workspace_root / raw, shared_root / raw]

    src: Path | None = None
    for candidate in candidates:
        if candidate.exists():
            src = candidate.resolve()
            break
    if src is None:
        raise BookError(f"src_path does not exist: {src_path!r}")
    if not src.is_file():
        raise BookError(f"src_path is not a file: {src}")

    try:
        src.relative_to(shared_root)
    except ValueError as exc:
        raise BookError(f"src_path must be under branches/shared/: {src}") from exc

    try:
        source_file = src.relative_to(workspace_root).as_posix()
    except ValueError as exc:
        raise BookError(f"src_path must be under project workspace root: {src}") from exc
    return src, source_file


def _stage_path(port: int, name: str) -> Path:
    return project_state_dir(port) / "book-staging" / name


def _stage_text(port: int, name: str, text: str) -> Path:
    path = _stage_path(port, name)
    _atomic_write_text(path, text)
    return path


def _read_first_lines(path: Path, *, limit: int = 200) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[:limit]).rstrip() + "\n"


def _strip_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[idx + 1 :])
    return text


def _sentence_candidates(text: str) -> list[str]:
    body = _strip_frontmatter(text)
    body = re.sub(r"^>+\s?", "", body, flags=re.MULTILINE)
    sentences: list[str] = []
    for chunk in _SENTENCE_SPLIT_RE.split(body):
        sentence = " ".join(chunk.strip().split())
        if len(sentence) >= _MIN_CONTRADICTION_SENTENCE_CHARS:
            sentences.append(sentence)
    return sentences


def _tokens_for_sentence(sentence: str) -> list[str]:
    normalized = sentence.lower().replace("can't", "cannot").replace("won't", "not")
    normalized = re.sub(r"n't\b", " not", normalized)
    return _TOKEN_RE.findall(normalized)


def _shared_claim_terms(left_tokens: list[str], right_tokens: list[str]) -> list[str]:
    right_terms = {
        token
        for token in right_tokens
        if len(token) >= _MIN_SHARED_TERM_CHARS
        and token not in _NEGATION_MARKERS
        and token not in _COMMON_SHARED_TERMS
    }
    seen: set[str] = set()
    terms: list[str] = []
    for token in left_tokens:
        if (
            token in right_terms
            and token not in seen
            and token not in _NEGATION_MARKERS
            and token not in _COMMON_SHARED_TERMS
        ):
            seen.add(token)
            terms.append(token)
    return terms


def _negated_terms(tokens: list[str], terms: set[str]) -> set[str]:
    negated: set[str] = set()
    for idx, token in enumerate(tokens):
        if token not in terms:
            continue
        start = max(0, idx - _NEGATION_LOOKBACK_TOKENS)
        if any(marker in _NEGATION_MARKERS for marker in tokens[start:idx]):
            negated.add(token)
    return negated


def _opposed_shared_terms(new_sentence: str, existing_sentence: str) -> list[str]:
    new_tokens = _tokens_for_sentence(new_sentence)
    existing_tokens = _tokens_for_sentence(existing_sentence)
    shared_terms = _shared_claim_terms(new_tokens, existing_tokens)
    if not shared_terms:
        return []

    shared_set = set(shared_terms)
    new_negated = _negated_terms(new_tokens, shared_set)
    existing_negated = _negated_terms(existing_tokens, shared_set)
    return [term for term in shared_terms if (term in new_negated) != (term in existing_negated)]


def _detect_contradictions(
    port: int,
    slug: str,
    body: str,
    source_role: str,
) -> list[dict[str, object]]:
    """Find lexical contradictions between a new source body and existing book sources."""
    source_dir = _book_root(port) / "sources"
    if not source_dir.exists():
        return []

    new_sentences = _sentence_candidates(body)
    if not new_sentences:
        return []

    contradictions: list[dict[str, object]] = []
    for page in sorted(source_dir.glob("*.md")):
        if page.name == f"{slug}.md":
            continue
        existing_sentences = _sentence_candidates(
            page.read_text(encoding="utf-8", errors="replace")
        )
        if not existing_sentences:
            continue
        for new_sentence in new_sentences:
            for existing_sentence in existing_sentences:
                shared_terms = _opposed_shared_terms(new_sentence, existing_sentence)
                if not shared_terms:
                    continue
                contradictions.append(
                    {
                        "opposing_page": f"book/sources/{page.name}",
                        "excerpts": {
                            "new": new_sentence,
                            "opposing": existing_sentence,
                        },
                        "shared_terms": shared_terms[:8],
                        "new_source": slug,
                        "new_source_role": source_role,
                    }
                )
                if len(contradictions) >= _MAX_CONTRADICTIONS:
                    return contradictions
                break
            if len(contradictions) >= _MAX_CONTRADICTIONS:
                return contradictions
    return contradictions


def _oneline(value: object) -> str:
    return " ".join(str(value).strip().split())


def _source_role_unmarked_ratio(book_root: Path, source_role: str) -> float | None:
    """Best-effort estimate of a role's unmarked-claim ratio from its Book pages.

    Reads the role's existing source pages, counts non-empty body lines, and
    counts how many carry an [evidence:|speculation|derived:] marker. Returns
    the unmarked ratio in [0, 1], or None when there is too little data.

    This is a *Noter signal*, not an Ethics verdict: it is purely descriptive.
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
    """Extract source_role from an opposing page path like book/sources/coder-foo.md."""
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
        "*Noter-assembled descriptive signals — no verdict. Ethics adjudicates.*",
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
        terms = list(contradiction.get("shared_terms", []) or [])
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
        excerpts = contradiction.get("excerpts", {})
        if not isinstance(excerpts, dict):
            excerpts = {}
        new_excerpt = _oneline(excerpts.get("new", ""))
        opposing_excerpt = _oneline(excerpts.get("opposing", ""))
        shared_terms = contradiction.get("shared_terms", [])
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


def _parse_index_entries(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                entries.append(current)
            current = {"title": line[3:].strip()}
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"slug", "type", "page_kind", "book_path"}:
            current[key] = value.strip().strip("`")
    if current is not None:
        entries.append(current)
    return [entry for entry in entries if entry.get("slug") and entry.get("book_path")]


def _render_index(entries: list[dict[str, str]]) -> str:
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
    return "\n".join(lines).rstrip() + "\n"


def _book_path_for_page_kind(page_kind: str, slug: str) -> str:
    if page_kind == "source":
        return f"book/sources/{slug}.md"
    if page_kind == "contradiction":
        return f"book/contradictions/{slug}.md"
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

    return _stage_text(port, f"book-index-{next_entries[0]['slug']}.md", _render_index(merged))


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


def _publish_file(
    port: int,
    abs_src: Path,
    rel_dst_under_book: str,
    message: str,
) -> dict[str, object]:
    rel_dst = Path(rel_dst_under_book)
    if rel_dst.is_absolute() or any(part == ".." for part in rel_dst.parts):
        raise BookError(f"book destination may not escape book/: {rel_dst_under_book!r}")
    return mos_publish_to_shared(
        role="noter",
        src_path=str(abs_src.resolve()),
        dst_subpath=f"book/{rel_dst.as_posix()}",
        commit_message=message,
        port=port,
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


def _render_lint_hot_block(result: dict[str, object]) -> str:
    lines = [
        _LINT_SUMMARY_START,
        "## Book Lint",
        f"updated: {_now_iso()}",
        f"lint_count: {result.get('lint_count', 0)}",
        f"orphan_pages: {result.get('orphan_pages', 0)}",
        f"dead_links: {result.get('dead_links', 0)}",
        f"missing_concept_pages: {result.get('missing_concept_pages', 0)}",
        f"stale_claims: {result.get('stale_claims', 0)}",
    ]
    error = result.get("error")
    if error:
        lines.append(f"error: {_short_lint_value(error)}")

    findings = result.get("findings", [])
    if isinstance(findings, list) and findings:
        lines.extend(["", "Top findings:"])
        for finding in findings[:10]:
            if not isinstance(finding, dict):
                continue
            severity = _short_lint_value(finding.get("severity", "info"), limit=24)
            check = _short_lint_value(finding.get("check", ""), limit=40)
            slug = _short_lint_value(finding.get("slug", ""), limit=80)
            book_path = _short_lint_value(finding.get("book_path", ""), limit=120)
            detail = _short_lint_value(finding.get("detail", ""), limit=140)
            lines.append(f"- {severity} {check}: `{slug}` at `{book_path}` - {detail}")
    else:
        lines.extend(["", "No lint findings."])

    lines.append(_LINT_SUMMARY_END)
    return "\n".join(lines).rstrip() + "\n"


def _cap_hot_text(text: str, required_block: str) -> str:
    if len(text.encode("utf-8")) <= _MAX_HOT_BYTES:
        return text if text.endswith("\n") else text + "\n"

    lines = text.splitlines()
    while lines:
        candidate = "\n".join(lines).rstrip() + "\n"
        if len(candidate.encode("utf-8")) <= _MAX_HOT_BYTES:
            if _LINT_SUMMARY_START in candidate and _LINT_SUMMARY_END in candidate:
                return candidate
            break
        lines.pop(0)
    return required_block


def _replace_lint_hot_block(existing: str, block: str) -> str:
    block = block.rstrip() + "\n"
    if _LINT_SUMMARY_BLOCK_RE.search(existing):
        updated = _LINT_SUMMARY_BLOCK_RE.sub(block.rstrip(), existing, count=1)
        updated = updated.rstrip() + "\n"
    else:
        prefix = existing.rstrip()
        updated = f"{prefix}\n\n{block}" if prefix else block
    return _cap_hot_text(updated, block)


def _read_existing_lint_hot_block(port: int) -> str:
    hot_path = _book_root(port) / "hot.md"
    existing = hot_path.read_text(encoding="utf-8") if hot_path.exists() else ""
    match = _LINT_SUMMARY_BLOCK_RE.search(existing)
    if match:
        return match.group(0).rstrip() + "\n"
    return "\n".join(
        [
            _LINT_SUMMARY_START,
            "## Book Lint",
            "No lint summary available.",
            _LINT_SUMMARY_END,
            "",
        ]
    )


def _hot_ingest_value(ingest: dict[str, str], *keys: str, default: str) -> str:
    for key in keys:
        value = _oneline(ingest.get(key, ""))
        if value:
            return value
    return default


def _render_hot_update_text(
    *,
    recent_ingests: list[dict[str, str]],
    active_hypotheses: int,
    recently_verified: list[str],
    recently_refuted: list[str],
    unresolved_contradictions: int,
    lint_block: str,
) -> str:
    lines = ["# Book Hot Cache", "", "## Recent activity", ""]
    if recent_ingests:
        for ingest in recent_ingests:
            title = _hot_ingest_value(ingest, "title", "source_slug", "slug", default="Untitled")
            role = _hot_ingest_value(ingest, "role", "source_role", default="unknown")
            takeaway = _hot_ingest_value(
                ingest,
                "one-line",
                "one_line",
                "takeaway",
                "summary",
                default="No takeaway recorded.",
            )
            lines.append(f"- **{title}** ({role}): {takeaway}")
    else:
        lines.append("No ingests recorded this cycle.")

    lines.extend(
        [
            "",
            "## Research state",
            "",
            f"Active hypotheses: {max(0, active_hypotheses)}",
            f"Verified this cycle: {len(recently_verified)}",
        ]
    )
    lines.extend(f"- {_oneline(item)}" for item in recently_verified if _oneline(item))
    lines.append(f"Refuted this cycle: {len(recently_refuted)}")
    lines.extend(f"- {_oneline(item)}" for item in recently_refuted if _oneline(item))
    lines.extend(
        [
            "",
            "## Open contradictions",
            "",
            f"{max(0, unresolved_contradictions)} unresolved - Ethics reviewing.",
            "",
            lint_block.rstrip(),
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _render_capped_hot_update(
    *,
    recent_ingests: list[dict[str, str]],
    active_hypotheses: int,
    recently_verified: list[str],
    recently_refuted: list[str],
    unresolved_contradictions: int,
    lint_block: str,
) -> str:
    ingests = list(recent_ingests[-5:])
    text = _render_hot_update_text(
        recent_ingests=ingests,
        active_hypotheses=active_hypotheses,
        recently_verified=recently_verified,
        recently_refuted=recently_refuted,
        unresolved_contradictions=unresolved_contradictions,
        lint_block=lint_block,
    )
    while len(text.encode("utf-8")) > _MAX_HOT_BYTES and ingests:
        ingests.pop(0)
        text = _render_hot_update_text(
            recent_ingests=ingests,
            active_hypotheses=active_hypotheses,
            recently_verified=recently_verified,
            recently_refuted=recently_refuted,
            unresolved_contradictions=unresolved_contradictions,
            lint_block=lint_block,
        )
    if len(text.encode("utf-8")) <= _MAX_HOT_BYTES:
        return text

    suffix = "\n" + lint_block.rstrip() + "\n"
    budget = max(0, _MAX_HOT_BYTES - len(suffix.encode("utf-8")) - 4)
    encoded = text.replace(suffix.lstrip(), "").encode("utf-8")[:budget]
    prefix = encoded.decode("utf-8", errors="ignore").rstrip()
    return f"{prefix}\n...\n{lint_block.rstrip()}\n"


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

    hot_path = book_root / "hot.md"
    existing_hot = hot_path.read_text(encoding="utf-8") if hot_path.exists() else ""
    hot_stage = _stage_text(
        port,
        "book-hot-lint.md",
        _replace_lint_hot_block(existing_hot, _render_lint_hot_block(result)),
    )

    message = "noter: book lint"
    _publish_file(port, log_stage, "log.md", message)
    _publish_file(port, hot_stage, "hot.md", message)


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
        node_id = node.get("id", "")
        node_text = _normalise_match_text(node.get("text", ""))
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
    existing_edges = {
        (
            edge.get("from_id"),
            edge.get("to_id"),
            edge.get("relation"),
        )
        for edge in raw_edges
        if isinstance(edge, dict)
    }
    edges: list[dict[str, object]] = []
    queued: set[tuple[str, str, str]] = set()
    for contradiction in contradictions:
        excerpts = contradiction.get("excerpts", {})
        if not isinstance(excerpts, dict):
            continue
        new_node_id = _find_dag_node_id(draft, excerpts.get("new", ""))
        opposing_node_id = _find_dag_node_id(draft, excerpts.get("opposing", ""))
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
                "author_role": "noter",
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


def mos_book_ingest(
    src_path: str,
    source_role: str,
    source_slug: str,
    title: str | None = None,
    summary: str | None = None,
    *,
    port: int | None = None,
) -> dict[str, object]:
    """Ingest a published shared/<role>/ artifact into the Book.

    Reads ``src_path`` under ``branches/shared/``, stages a source page,
    idempotently merges ``book/index.md``, appends ``book/log.md``, and
    publishes the three files through ``mos_publish_to_shared`` as Noter.
    """
    resolved_port = _resolve_port(port)
    _validate_component("source_role", source_role)
    _validate_component("source_slug", source_slug)
    slug = f"{source_role}-{source_slug}"
    src, source_file = _resolve_source_path(resolved_port, src_path)
    resolved_title = (title or src.stem).strip() or src.stem
    date_ingested = _now_iso()
    body = summary.strip() + "\n" if summary is not None else _read_first_lines(src)

    page = (
        _render_source_frontmatter(
            title=resolved_title,
            slug=slug,
            source_file=source_file,
            source_role=source_role,
            date_ingested=date_ingested,
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

    message = f"noter: ingest {slug}"
    publish_results = [_publish_file(resolved_port, page_stage, f"sources/{slug}.md", message)]
    if contradiction_stage is not None:
        publish_results.append(
            _publish_file(
                resolved_port,
                contradiction_stage,
                f"contradictions/{contradiction_slug}.md",
                message,
            )
        )
    publish_results.extend(
        [
            _publish_file(resolved_port, index_stage, "index.md", message),
            _publish_file(resolved_port, log_stage, "log.md", message),
        ]
    )
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


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(text.lower()) if len(token) >= 3}


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


def mos_book_promote_verified(
    *,
    min_age_days: float = 7.0,
    min_supporting_edges: int = 2,
    max_promotions: int = 5,
    port: int | None = None,
) -> dict[str, object]:
    """Promote verified Draft insights to durable Book pages.

    Knowledge promotion (LLM Wiki V2 consolidation tier): when a Draft
    node of type ∈ {insight, method, result} reaches support_status=verified,
    has at least ``min_supporting_edges`` ``supports`` edges, has been stable
    for ``min_age_days`` days, and isn't already cited by any Book page,
    Noter promotes it by creating a verbatim Book source page.

    Strict verbatim contract — Noter never restates. The page body is the
    node's exact ``text``, plus a Draft ID reference and the citation
    list of supporting edges. This keeps Noter inside its "records only,
    makes no new claims" boundary while still moving knowledge from L1
    (process memory) to L2 (product memory).

    Whitelisted to Noter only. Idempotent — re-running won't duplicate
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

    # Dead-ends are first-class citizens (per ARA's "preserve rejected
    # alternatives" principle) — they are negative knowledge that prevents
    # other projects from re-running the same failed experiment.
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

        # Verbatim summary body — Noter is not paraphrasing. Includes the
        # exact node text, the Draft pointer, and the citation list of
        # supporting edges. This is the L1→L2 promotion contract.
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

        promotion_temp_dir = project_shared_subdir(resolved_port, "noter") / ".promotions"
        promotion_temp_dir.mkdir(parents=True, exist_ok=True)
        slug_id = node_id.replace("-", "").lower()
        temp_path = promotion_temp_dir / f"promoted-{slug_id}.md"
        temp_path.write_text(body, encoding="utf-8")
        try:
            ingest_result = mos_book_ingest(
                src_path=str(temp_path),
                source_role="noter",
                source_slug=f"promoted-{slug_id}",
                title=f"Promoted {node_type}: {node_id}",
                port=resolved_port,
            )
        finally:
            with contextlib.suppress(OSError):
                temp_path.unlink(missing_ok=True)
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


def _crystallize_session_window(
    port: int,
    role: str,
    window_minutes: int,
    max_chars: int,
) -> tuple[str, list[str]]:
    """Build a verbatim crystallization body for a role's recent session window.

    Returns (body_markdown, cited_node_ids). The body is:
      - the role's recent Draft nodes verbatim,
      - the role's recent EACN messages verbatim (truncated per-message),
      - structured pointers (no paraphrase).
    """
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
        for jsonl in sorted(events_dir.glob("*.jsonl")):
            try:
                with jsonl.open("r", encoding="utf-8") as f:
                    for raw in f:
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        ts = str(event.get("timestamp", "") or event.get("ts", ""))
                        ev_dt = _parse_iso(ts)
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

    Whitelisted to Noter only. Ethics audits the result through its normal
    Book + mock-review path; the verbatim contract makes that easy
    because the page never invents content beyond what's in the sources.
    """
    resolved_port = _resolve_port(port)
    _validate_component("role", role)
    body, cited = _crystallize_session_window(
        resolved_port, role, int(window_minutes), int(max_chars)
    )
    crystallization_dir = project_shared_subdir(resolved_port, "noter") / ".crystallizations"
    crystallization_dir.mkdir(parents=True, exist_ok=True)
    ts_slug = re.sub(r"[^A-Za-z0-9]", "", _now_iso())
    temp_path = crystallization_dir / f"session-{role}-{ts_slug}.md"
    temp_path.write_text(body, encoding="utf-8")
    try:
        ingest_result = mos_book_ingest(
            src_path=str(temp_path),
            source_role="noter",
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


def mos_book_query(
    text: str,
    max_pages: int = 5,
    *,
    port: int | None = None,
) -> dict[str, object]:
    """Keyword-only search over book/index.md headers + page filenames."""
    resolved_port = _resolve_port(port)
    query_tokens = _tokens(text)
    index_path = _book_root(resolved_port) / "index.md"
    if not query_tokens or not index_path.exists():
        return {"matches": [], "total": 0, "queried": text}

    entries = _parse_index_entries(index_path.read_text(encoding="utf-8"))
    scored: list[dict[str, object]] = []
    for entry in entries:
        haystack = f"{entry.get('title', '')} {Path(entry.get('book_path', '')).name}"
        score = len(query_tokens & _tokens(haystack))
        if score <= 0:
            continue
        scored.append(
            {
                "slug": entry["slug"],
                "title": entry.get("title", entry["slug"]),
                "page_kind": entry.get("page_kind", entry.get("type", "")),
                "book_path": entry["book_path"],
                "score": score,
            }
        )

    scored.sort(key=lambda item: (-int(item["score"]), str(item["title"]), str(item["slug"])))
    total = len(scored)
    limit = max(0, int(max_pages))
    return {"matches": scored[:limit], "total": total, "queried": text}


def mos_book_lint(*, port: int | None = None) -> dict[str, object]:
    """Audit ``book/`` for structural health.

    Returns ``{orphan_pages, dead_links, missing_concept_pages, stale_claims,
    lint_count, findings}``. This tool is filesystem-only and best-effort:
    failures are returned as ``error`` alongside any collected partial result.
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


def mos_book_hot_update(
    recent_ingests: list[dict[str, str]] | None = None,
    active_hypotheses: int = 0,
    recently_verified: list[str] | None = None,
    recently_refuted: list[str] | None = None,
    unresolved_contradictions: int = 0,
    *,
    port: int | None = None,
) -> dict[str, object]:
    """Generate and publish book/hot.md rolling cache.

    Called by Noter on each periodic wake. Composes a ~500-word summary
    from the provided data and publishes it via mos_publish_to_shared.
    """
    resolved_port = _resolve_port(port)
    lint_block = _read_existing_lint_hot_block(resolved_port)
    hot_text = _render_capped_hot_update(
        recent_ingests=recent_ingests or [],
        active_hypotheses=active_hypotheses,
        recently_verified=recently_verified or [],
        recently_refuted=recently_refuted or [],
        unresolved_contradictions=unresolved_contradictions,
        lint_block=lint_block,
    )
    stage = _stage_text(resolved_port, "book-hot-update.md", hot_text)
    _publish_file(resolved_port, stage, "hot.md", "noter: book hot update")
    return {
        "updated": True,
        "bytes": len(hot_text.encode("utf-8")),
        "sections": [
            "Recent activity",
            "Research state",
            "Open contradictions",
            "Book Lint",
        ],
    }


def mos_book_hot_get(*, port: int | None = None) -> dict[str, object]:
    """Return current book/hot.md contents, or empty content if absent."""
    resolved_port = _resolve_port(port)
    path = _book_root(resolved_port) / "hot.md"
    if not path.exists():
        return {"content": "", "exists": False, "bytes": 0}
    content = path.read_text(encoding="utf-8")
    return {
        "content": content,
        "exists": True,
        "bytes": len(content.encode("utf-8")),
    }


__all__ = [
    "BookError",
    "mos_book_hot_get",
    "mos_book_hot_update",
    "mos_book_ingest",
    "mos_book_lint",
    "mos_book_query",
]
