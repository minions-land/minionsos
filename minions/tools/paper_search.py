"""Project-local academic paper search facades over paper-search-mcp.

The heavy lifting (arXiv / PubMed / bioRxiv / medRxiv / Semantic Scholar
search; PDF downloads; multi-source federation) is delegated to the
``paper_search_mcp`` library, pinned via ``[tool.uv.sources]`` in
``pyproject.toml`` to a known-good commit on the project's ``main`` branch
(the PyPI release lags behind ``main`` by many months and ships a known-broken
arXiv relevance-sort default; we install from git for that reason).

This module wraps the library to:

1. Preserve the MinionsOS canonical dict schema (16 fields including ``extra``
   as ``dict`` and ``fetched_at`` as ISO timestamp) for the ``mos_*`` MCP tool
   surface.
2. Enforce workspace-relative paths through ``_relative_output_dir``; the
   library accepts a raw ``save_path`` string and we resolve it before
   passing.
3. Keep the public function names and signatures stable for callers.

The facade exposes ``search_semantic`` for Semantic Scholar metadata,
``search_google_scholar`` for scholar-like broad search backed by Semantic
Scholar, and ``search_papers_federated`` for multi-source federated search
returning a single deduplicated list.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from paper_search_mcp.academic_platforms.arxiv import ArxivSearcher
from paper_search_mcp.academic_platforms.biorxiv import BioRxivSearcher
from paper_search_mcp.academic_platforms.crossref import CrossRefSearcher
from paper_search_mcp.academic_platforms.europepmc import EuropePMCSearcher
from paper_search_mcp.academic_platforms.medrxiv import MedRxivSearcher
from paper_search_mcp.academic_platforms.openalex import OpenAlexSearcher
from paper_search_mcp.academic_platforms.pubmed import PubMedSearcher
from paper_search_mcp.academic_platforms.semantic import SemanticSearcher
from paper_search_mcp.paper import Paper

DEFAULT_TIMEOUT = 20.0
MAX_RESULTS = 50

# Source key → searcher class. Keys are stable identifiers callers can
# pass to ``search_papers_federated``; values are the paper-search-mcp
# connectors.
KNOWN_SOURCES: dict[str, type] = {
    "arxiv": ArxivSearcher,
    "pubmed": PubMedSearcher,
    "biorxiv": BioRxivSearcher,
    "medrxiv": MedRxivSearcher,
    "semantic": SemanticSearcher,
    "crossref": CrossRefSearcher,
    "openalex": OpenAlexSearcher,
    "europepmc": EuropePMCSearcher,
}

DEFAULT_FEDERATED_SOURCES: tuple[str, ...] = ("arxiv", "semantic")


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _limit(max_results: int) -> int:
    return max(1, min(int(max_results), MAX_RESULTS))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _workspace_root() -> Path:
    """Resolve the project workspace for role-host and interactive MCP sessions."""
    port = os.environ.get("MINIONS_PROJECT_PORT", "").strip()
    if port.isdigit():
        try:
            from minions.paths import project_workspace

            return project_workspace(int(port))
        except Exception:
            pass
    return Path.cwd()


def _relative_output_dir(save_path: str) -> Path:
    """Resolve a workspace-relative ``save_path`` to an absolute directory.

    Refuses absolute paths and any ``..`` components. Creates the directory
    if missing.
    """
    base = Path(save_path)
    if base.is_absolute():
        raise ValueError("save_path must be relative to the current project workspace.")
    if ".." in base.parts:
        raise ValueError("save_path must not contain '..'.")
    output_dir = _workspace_root() / base
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _relative_output_path(save_path: str, filename: str) -> Path:
    """Backwards-compatible single-file resolver used by tests + helpers."""
    return _relative_output_dir(save_path) / filename


def _safe_filename(value: str, suffix: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return f"{safe or 'paper'}{suffix}"


# ---------------------------------------------------------------------------
# Paper -> dict adapter
# ---------------------------------------------------------------------------


def _to_minions_dict(paper: Paper, source_override: str | None = None) -> dict[str, Any]:
    """Convert a paper-search-mcp ``Paper`` into the MinionsOS canonical dict.

    Preserve the MinionsOS paper-record shape:

    - ``extra`` is a ``dict`` (the upstream ``Paper.to_dict`` returns ``str(dict)``).
    - ``fetched_at`` is an ISO-8601 UTC timestamp added at conversion time.
    - ``published_date`` / ``updated_date`` are ISO strings (or empty).
    - List fields are joined into ``"; "``-separated strings.
    """
    pub = paper.published_date.isoformat() if paper.published_date else ""
    upd = paper.updated_date.isoformat() if paper.updated_date else ""
    return {
        "paper_id": paper.paper_id,
        "title": _clean_text(paper.title),
        "authors": "; ".join(paper.authors or []),
        "abstract": _clean_text(paper.abstract),
        "doi": paper.doi or "",
        "published_date": pub,
        "updated_date": upd,
        "pdf_url": paper.pdf_url or "",
        "url": paper.url or "",
        "source": source_override or paper.source,
        "categories": "; ".join(paper.categories or []),
        "keywords": "; ".join(paper.keywords or []),
        "citations": int(paper.citations or 0),
        "references": "; ".join(paper.references or []),
        "extra": dict(paper.extra) if paper.extra else {},
        "fetched_at": _now_iso(),
    }


def _search(
    searcher_cls: type,
    query: str,
    max_results: int,
    *,
    source_override: str | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Internal helper: instantiate a searcher, run it, convert results."""
    n = _limit(max_results)
    papers = searcher_cls().search(query, max_results=n, **kwargs)
    return [_to_minions_dict(p, source_override=source_override) for p in papers]


# ---------------------------------------------------------------------------
# Public search facades — existing public API, signatures unchanged.
# Internally upgraded from handwritten httpx code to paper-search-mcp.
# ---------------------------------------------------------------------------


def search_arxiv(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search arXiv (relevance-sorted by default via ArxivSearcher)."""
    return _search(ArxivSearcher, query, max_results)


def search_pubmed(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search PubMed via paper-search-mcp's PubMedSearcher."""
    return _search(PubMedSearcher, query, max_results)


def search_biorxiv(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search bioRxiv preprints via paper-search-mcp's BioRxivSearcher."""
    return _search(BioRxivSearcher, query, max_results)


def search_medrxiv(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search medRxiv preprints via paper-search-mcp's MedRxivSearcher."""
    return _search(MedRxivSearcher, query, max_results)


def search_google_scholar(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Scholar-like broad paper search via Semantic Scholar.

    The ``source`` field on returned papers is ``"semantic_scholar"`` to make
    the provider explicit.
    """
    return _search(SemanticSearcher, query, max_results, source_override="semantic_scholar")


# ---------------------------------------------------------------------------
# Search facades
# ---------------------------------------------------------------------------


def search_semantic(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search Semantic Scholar metadata."""
    return _search(SemanticSearcher, query, max_results, source_override="semantic_scholar")


def search_papers_federated(
    query: str,
    sources: list[str] | None = None,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """Run a federated search across multiple sources, returning a flat dedup list.

    Args:
        query: Search query.
        sources: List of source keys (subset of ``KNOWN_SOURCES``). Defaults to
            ``DEFAULT_FEDERATED_SOURCES`` (``arxiv``, ``semantic``).
            Crossref / OpenAlex / EuropePMC are valid keys but **not in the
            default set** because their text-search relevance is poor for
            very recent arXiv-only preprints (cf. the 2026-05-19 comparison
            study, Task 3): they tend to return string-similar but
            semantically unrelated work, polluting the federated dedup list.
            Pass them explicitly when querying for established / DOI-bearing
            literature.
            Unknown source keys are silently skipped.
        max_results: Per-source result count (clamped to ``1..MAX_RESULTS``).

    Returns:
        Deduplicated list of MinionsOS-canonical paper dicts. Dedup keys are
        normalised DOI and lowercased title; per-source failures do not block
        the overall call.
    """
    chosen = sources or list(DEFAULT_FEDERATED_SOURCES)
    out: list[dict[str, Any]] = []
    seen_doi: set[str] = set()
    seen_title: set[str] = set()
    for src in chosen:
        searcher_cls = KNOWN_SOURCES.get(src)
        if searcher_cls is None:
            continue
        try:
            papers = searcher_cls().search(query, max_results=_limit(max_results))
        except Exception:
            # Per-source failure should not block the federated call.
            continue
        for p in papers:
            d = _to_minions_dict(p)
            doi = (d.get("doi") or "").lower().strip()
            title = (d.get("title") or "").lower().strip()
            if doi and doi in seen_doi:
                continue
            if title and title in seen_title:
                continue
            if doi:
                seen_doi.add(doi)
            if title:
                seen_title.add(title)
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# Read facades — return a metadata + abstract block (NOT full PDF text).
# ---------------------------------------------------------------------------


def _arxiv_metadata_by_id(paper_id: str) -> dict[str, Any] | None:
    """Resolve a single arXiv paper by id via the public Atom API.

    The paper-search-mcp library prefixes user queries with ``all:``, which
    breaks the ``id:`` look-up syntax we used previously. arXiv supports a
    dedicated ``id_list=`` parameter for direct id resolution; we use that.
    """
    params = {"id_list": paper_id, "max_results": 1}
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        resp = client.get("https://export.arxiv.org/api/query", params=params)
        resp.raise_for_status()
    root = ET.fromstring(resp.text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entry = root.find("a:entry", ns)
    if entry is None:
        return None
    authors = [
        _clean_text(a.findtext("a:name", namespaces=ns) or "")
        for a in entry.findall("a:author", ns)
    ]
    pdf = ""
    for link in entry.findall("a:link", ns):
        if link.attrib.get("type") == "application/pdf":
            pdf = link.attrib.get("href", "")
            break
    return {
        "title": _clean_text(entry.findtext("a:title", namespaces=ns) or ""),
        "authors": "; ".join(a for a in authors if a),
        "published_date": _clean_text(entry.findtext("a:published", namespaces=ns) or ""),
        "url": _clean_text(entry.findtext("a:id", namespaces=ns) or ""),
        "pdf_url": pdf,
        "abstract": _clean_text(entry.findtext("a:summary", namespaces=ns) or ""),
    }


def read_arxiv_paper(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Return arXiv metadata and abstract text for a paper id."""
    meta = _arxiv_metadata_by_id(paper_id)
    if not meta:
        return ""
    return "\n".join(
        [
            f"Title: {meta['title']}",
            f"Authors: {meta['authors']}",
            f"Published: {meta['published_date']}",
            f"URL: {meta['url']}",
            f"PDF: {meta['pdf_url']}",
            "",
            "Abstract:",
            meta["abstract"],
        ]
    ).strip()


def resolve_arxiv_ids(ids: list[str]) -> list[dict[str, Any]]:
    """Batch-resolve arXiv ids to MinionsOS canonical paper dicts.

    Designed as the resolve step of a Web → ID → canonical workflow: an
    upstream call (e.g. ``WebSearch`` in the orchestrator's LLM context, or
    Google) returns URLs, the orchestrator extracts arXiv ids by regex on
    ``arxiv.org/abs/<id>``, and this tool returns one structured paper dict
    per id with all 16 canonical fields. Bypasses keyword search entirely
    by using arXiv's ``id_list=`` API parameter, so it does not suffer from
    the lexical-relevance limits that bite ``search_arxiv`` on broad
    domain queries (see Task 2 in the comparison study, 2026-05-19).

    Bad ids are silently skipped (arXiv returns no entry for them); the
    returned list may be shorter than ``ids``. Up to ``MAX_RESULTS`` ids
    per call.
    """
    cleaned = [i.strip() for i in ids if i and i.strip()][:MAX_RESULTS]
    if not cleaned:
        return []
    params = {"id_list": ",".join(cleaned), "max_results": len(cleaned)}
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        resp = client.get("https://export.arxiv.org/api/query", params=params)
        resp.raise_for_status()
    root = ET.fromstring(resp.text)
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    out: list[dict[str, Any]] = []
    for entry in root.findall("a:entry", ns):
        paper_url = _clean_text(entry.findtext("a:id", namespaces=ns) or "")
        paper_id = paper_url.rstrip("/").split("/")[-1]
        authors = [
            _clean_text(a.findtext("a:name", namespaces=ns) or "")
            for a in entry.findall("a:author", ns)
        ]
        pdf_url = ""
        for link in entry.findall("a:link", ns):
            if link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href", "")
                break
        doi = _clean_text(entry.findtext("arxiv:doi", namespaces=ns) or "")
        categories = [
            tag.attrib.get("term", "")
            for tag in entry.findall("a:category", ns)
            if tag.attrib.get("term")
        ]
        out.append(
            {
                "paper_id": paper_id,
                "title": _clean_text(entry.findtext("a:title", namespaces=ns) or ""),
                "authors": "; ".join(a for a in authors if a),
                "abstract": _clean_text(entry.findtext("a:summary", namespaces=ns) or ""),
                "doi": doi,
                "published_date": _clean_text(entry.findtext("a:published", namespaces=ns) or ""),
                "updated_date": _clean_text(entry.findtext("a:updated", namespaces=ns) or ""),
                "pdf_url": pdf_url,
                "url": paper_url,
                "source": "arxiv",
                "categories": "; ".join(categories),
                "keywords": "",
                "citations": 0,
                "references": "",
                "extra": {},
                "fetched_at": _now_iso(),
            }
        )
    return out


def _pubmed_efetch(paper_id: str) -> ET.Element:
    params = {"db": "pubmed", "id": paper_id, "retmode": "xml"}
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params=params,
        )
        resp.raise_for_status()
    return ET.fromstring(resp.text)


def read_pubmed_paper(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Fetch PubMed XML and return title, authors, and abstract metadata."""
    root = _pubmed_efetch(paper_id)
    title = _clean_text(root.findtext(".//ArticleTitle"))
    abstract_parts = [
        _clean_text("".join(node.itertext())) for node in root.findall(".//AbstractText")
    ]
    authors: list[str] = []
    for node in root.findall(".//Author"):
        last = _clean_text(node.findtext("LastName"))
        fore = _clean_text(node.findtext("ForeName"))
        name = _clean_text(f"{fore} {last}")
        if name:
            authors.append(name)
    return "\n".join(
        [
            f"PMID: {paper_id}",
            f"Title: {title}",
            f"Authors: {'; '.join(authors)}",
            f"URL: https://pubmed.ncbi.nlm.nih.gov/{paper_id}/",
            "",
            "Abstract:",
            "\n".join(part for part in abstract_parts if part),
        ]
    ).strip()


def _preprint_pdf_url(server: str, paper_id: str) -> str:
    return f"https://www.{server}.org/content/{paper_id}.full.pdf"


def read_biorxiv_paper(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Return a bioRxiv landing/PDF pointer for a DOI-like paper id."""
    return f"bioRxiv ID/DOI: {paper_id}\nPDF: {_preprint_pdf_url('biorxiv', paper_id)}"


def read_medrxiv_paper(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Return a medRxiv landing/PDF pointer for a DOI-like paper id."""
    return f"medRxiv ID/DOI: {paper_id}\nPDF: {_preprint_pdf_url('medrxiv', paper_id)}"


# ---------------------------------------------------------------------------
# Download facades — write to a workspace-relative path, return absolute file.
# Delegates the actual fetch to paper-search-mcp where supported.
# ---------------------------------------------------------------------------


def download_arxiv(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Download an arXiv PDF to a workspace-relative path via paper-search-mcp."""
    output_dir = _relative_output_dir(save_path)
    return ArxivSearcher().download_pdf(paper_id, str(output_dir))


def download_pubmed(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Save PubMed metadata + abstract as a relative ``.txt`` file.

    PubMed itself does not host downloadable PDFs for most articles, so this
    writes a metadata text file at the requested path.
    """
    output = _relative_output_path(save_path, _safe_filename(paper_id, ".txt"))
    output.write_text(read_pubmed_paper(paper_id, save_path), encoding="utf-8")
    return str(output)


def download_biorxiv(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Download a bioRxiv PDF by DOI-like paper id via paper-search-mcp."""
    output_dir = _relative_output_dir(save_path)
    return BioRxivSearcher().download_pdf(paper_id, str(output_dir))


def download_medrxiv(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Download a medRxiv PDF by DOI-like paper id via paper-search-mcp."""
    output_dir = _relative_output_dir(save_path)
    return MedRxivSearcher().download_pdf(paper_id, str(output_dir))
