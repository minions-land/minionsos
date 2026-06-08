"""Book helper functions - internal utilities for book operations.

Extracted from book.py to reduce file size and improve modularity.
Contains frontmatter parsing, index operations, contradiction detection, etc.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from minions.errors import BookError
from minions.paths import (
    project_shared_subdir,
    project_state_dir,
    project_workspace_root,
)
from minions.tools.book_utils import (
    atomic_write_text as _atomic_write_text,
)
from minions.tools.book_utils import (
    quoted as _quoted,
)

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_CLAIM_REF_RE = re.compile(r"\^\[([^\]]+)\]")

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
    }
)


def _book_root(port: int) -> Path:
    return project_shared_subdir(port, "book")


def _env_port() -> int:
    raw = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not raw:
        raise BookError("MINIONS_PROJECT_PORT not set")
    return int(raw)


def _resolve_port(port: int | None) -> int:
    if port is not None:
        return int(port)
    return _env_port()


def _resolve_source_path(port: int, src_path: str) -> tuple[Path, str]:
    from minions.paths import project_shared_workspace

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
        raise BookError(f"src_path must be under branches/main/: {src}") from exc

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


def _contradiction_slug(new_slug: str) -> str:
    return f"contradiction-{new_slug}"


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(text.lower()) if len(token) >= 3}


def _token_list(text: str) -> list[str]:
    """Ordered token list (with repeats) for term-frequency scoring."""
    return [token for token in _TOKEN_RE.findall(text.lower()) if len(token) >= 3]


def _oneline(text: str) -> str:
    """Condense text to a single line for compact display."""
    return " ".join(text.strip().split())


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML-ish frontmatter as a simple key:value dict."""
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    fm_block = text[4:end]
    result: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _strip_frontmatter(text: str) -> str:
    """Remove frontmatter block from page text, return body only."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end == -1:
        return text
    return text[end + 5 :].lstrip()


def _update_frontmatter_field(text: str, field: str, value: str) -> str:
    """Set/replace a frontmatter field: value line. Adds the field if absent."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
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
        return text
    return "\n".join(new_lines).rstrip() + "\n"


def _render_v2_frontmatter(
    *,
    page_kind: str,
    title: str,
    slug: str,
    source_file: str | None = None,
    source_role: str | None = None,
    date_ingested: str | None = None,
    reel_ref: str | None = None,
    status: str | None = None,
    motif_kind: str | None = None,
    evidence_for: list[str] | None = None,
    evidence_against: list[str] | None = None,
    supersedes: str | None = None,
    superseded_by: str | None = None,
    ratified_by: str | None = None,
    ratified_at: str | None = None,
    paper_role: str | None = None,
) -> str:
    """Central frontmatter builder for all Book page kinds (V2 schema)."""
    lines = ["---"]
    lines.append(f"type: {page_kind}")
    lines.append(f"title: {_quoted(title)}")
    lines.append(f"slug: {_quoted(slug)}")
    if source_file is not None:
        lines.append(f"source_file: {_quoted(source_file)}")
    if source_role is not None:
        lines.append(f"source_role: {_quoted(source_role)}")
    if date_ingested is not None:
        lines.append(f"date_ingested: {_quoted(date_ingested)}")
    lines.append(f"page_kind: {page_kind}")
    if page_kind == "source":
        lines.append("confidence: high")
    if reel_ref:
        lines.append(f"reel_ref: {_quoted(reel_ref)}")
    if status is not None:
        lines.append(f"status: {_quoted(status)}")
    if motif_kind is not None:
        lines.append(f"motif_kind: {_quoted(motif_kind)}")
    if evidence_for:
        lines.append(f"evidence_for: {json.dumps(evidence_for, ensure_ascii=False)}")
    if evidence_against:
        lines.append(f"evidence_against: {json.dumps(evidence_against, ensure_ascii=False)}")
    if supersedes is not None:
        lines.append(f"supersedes: {_quoted(supersedes)}")
    if superseded_by is not None:
        lines.append(f"superseded_by: {_quoted(superseded_by)}")
    if ratified_by is not None:
        lines.append(f"ratified_by: {_quoted(ratified_by)}")
    if ratified_at is not None:
        lines.append(f"ratified_at: {_quoted(ratified_at)}")
    if paper_role is not None:
        lines.append(f"paper_role: {_quoted(paper_role)}")
    lines.extend(["---", ""])
    return "\n".join(lines)


def _render_source_frontmatter(
    *,
    title: str,
    slug: str,
    source_file: str,
    source_role: str,
    date_ingested: str,
    reel_ref: str | None = None,
    status: str | None = None,
    motif_kind: str | None = None,
    evidence_for: list[str] | None = None,
    evidence_against: list[str] | None = None,
    supersedes: str | None = None,
    superseded_by: str | None = None,
    ratified_by: str | None = None,
    ratified_at: str | None = None,
    paper_role: str | None = None,
) -> str:
    """Thin wrapper around _render_v2_frontmatter for source pages."""
    return _render_v2_frontmatter(
        page_kind="source",
        title=title,
        slug=slug,
        source_file=source_file,
        source_role=source_role,
        date_ingested=date_ingested,
        reel_ref=reel_ref,
        status=status,
        motif_kind=motif_kind,
        evidence_for=evidence_for,
        evidence_against=evidence_against,
        supersedes=supersedes,
        superseded_by=superseded_by,
        ratified_by=ratified_by,
        ratified_at=ratified_at,
        paper_role=paper_role,
    )


def _inject_claim_refs(
    body: str,
    *,
    claim_refs: dict[str, str] | None = None,
    page_default_ref: str | None = None,
) -> str:
    """Inject reel_ref markers into substantive claim lines."""
    if not page_default_ref:
        return body
    if claim_refs is None:
        claim_refs = {}

    lines = body.splitlines()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or stripped.startswith("-")
            or stripped.startswith(">")
        ):
            out.append(line)
            continue
        if _CLAIM_REF_RE.search(line):
            out.append(line)
            continue

        ref = page_default_ref
        for prefix, override_ref in claim_refs.items():
            if stripped.startswith(prefix):
                ref = override_ref
                break

        out.append(f"{line} ^[{ref}]")

    return "\n".join(out)


def _parse_index_entries(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        if line.startswith("## Relations") or line.startswith("# Relations"):
            if current is not None:
                entries.append(current)
                current = None
            break
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


def _scan_book_edges(book_root: Path) -> list[dict[str, str]]:
    """Synthesize edges from on-disk Book pages."""
    contradictions_dir = book_root / "contradictions"
    if not contradictions_dir.is_dir():
        return []
    edges: list[dict[str, str]] = []
    for page in sorted(contradictions_dir.glob("*.md")):
        try:
            text = page.read_text(encoding="utf-8")
        except OSError:
            continue
        if not text.startswith("---\n"):
            continue
        end = text.find("\n---\n", 4)
        if end == -1:
            continue
        frontmatter = text[4:end]
        meta: dict[str, str] = {}
        for line in frontmatter.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
        new_source = meta.get("new_source", "")
        opposing_page = meta.get("opposing_page", "")
        status = meta.get("status", "")
        if not new_source or not opposing_page:
            continue
        opposing_slug = Path(opposing_page).stem
        if not opposing_slug or new_source == opposing_slug:
            continue
        if status and status.lower() in {"resolved", "refuted-resolved"}:
            continue
        edges.append(
            {
                "from": new_source,
                "to": opposing_slug,
                "relation": "contradicts",
                "evidence": f"book/contradictions/{page.name}",
            }
        )
    edges.sort(key=lambda e: (e["from"], e["to"], e["relation"]))
    return edges


__all__ = [
    "_book_root",
    "_contradiction_slug",
    "_env_port",
    "_inject_claim_refs",
    "_oneline",
    "_parse_frontmatter",
    "_parse_index_entries",
    "_read_first_lines",
    "_render_source_frontmatter",
    "_render_v2_frontmatter",
    "_resolve_port",
    "_resolve_source_path",
    "_scan_book_edges",
    "_stage_path",
    "_stage_text",
    "_strip_frontmatter",
    "_token_list",
    "_tokens",
    "_update_frontmatter_field",
]
