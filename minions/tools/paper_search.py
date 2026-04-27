"""Project-local academic paper search helpers for the MinionsOS MCP server."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

DEFAULT_TIMEOUT = 20.0
MAX_RESULTS = 50


def _limit(max_results: int) -> int:
    return max(1, min(int(max_results), MAX_RESULTS))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _paper(
    *,
    paper_id: str,
    title: str,
    authors: list[str] | None = None,
    abstract: str = "",
    source: str,
    url: str = "",
    pdf_url: str = "",
    published_date: str = "",
    updated_date: str = "",
    doi: str = "",
    categories: list[str] | None = None,
    citations: int = 0,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "paper_id": paper_id,
        "title": _clean_text(title),
        "authors": "; ".join(authors or []),
        "abstract": _clean_text(abstract),
        "doi": doi,
        "published_date": published_date,
        "updated_date": updated_date,
        "pdf_url": pdf_url,
        "url": url,
        "source": source,
        "categories": "; ".join(categories or []),
        "keywords": "",
        "citations": citations,
        "references": "",
        "extra": extra or {},
        "fetched_at": _now_iso(),
    }


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


def _relative_output_path(save_path: str, filename: str) -> Path:
    base = Path(save_path)
    if base.is_absolute():
        raise ValueError("save_path must be relative to the current project workspace.")
    if ".." in base.parts:
        raise ValueError("save_path must not contain '..'.")
    output_dir = _workspace_root() / base
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / filename


def _safe_filename(value: str, suffix: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return f"{safe or 'paper'}{suffix}"


def search_arxiv(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search arXiv via its public Atom API."""
    params = {
        "search_query": query,
        "max_results": _limit(max_results),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        resp = client.get("https://export.arxiv.org/api/query", params=params)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    out: list[dict[str, Any]] = []
    for entry in root.findall("a:entry", ns):
        paper_url = _clean_text(entry.findtext("a:id", namespaces=ns))
        paper_id = paper_url.rstrip("/").split("/")[-1]
        authors = [
            _clean_text(author.findtext("a:name", namespaces=ns))
            for author in entry.findall("a:author", ns)
        ]
        pdf_url = ""
        for link in entry.findall("a:link", ns):
            if link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href", "")
                break
        doi = _clean_text(entry.findtext("arxiv:doi", namespaces=ns))
        out.append(
            _paper(
                paper_id=paper_id,
                title=entry.findtext("a:title", namespaces=ns) or "",
                authors=[a for a in authors if a],
                abstract=entry.findtext("a:summary", namespaces=ns) or "",
                source="arxiv",
                url=paper_url,
                pdf_url=pdf_url,
                published_date=_clean_text(entry.findtext("a:published", namespaces=ns)),
                updated_date=_clean_text(entry.findtext("a:updated", namespaces=ns)),
                doi=doi,
                categories=[
                    tag.attrib.get("term", "")
                    for tag in entry.findall("a:category", ns)
                    if tag.attrib.get("term")
                ],
            )
        )
    return out


def read_arxiv_paper(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Return arXiv metadata and abstract text for a paper id."""
    results = search_arxiv(f"id:{paper_id}", max_results=1)
    if not results:
        return ""
    paper = results[0]
    lines = [
        f"Title: {paper['title']}",
        f"Authors: {paper['authors']}",
        f"Published: {paper['published_date']}",
        f"URL: {paper['url']}",
        f"PDF: {paper['pdf_url']}",
        "",
        "Abstract:",
        paper["abstract"],
    ]
    return "\n".join(lines).strip()


def download_arxiv(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Download an arXiv PDF to a relative path under the current workspace."""
    output = _relative_output_path(save_path, _safe_filename(paper_id, ".pdf"))
    url = f"https://arxiv.org/pdf/{quote(paper_id, safe='')}.pdf"
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
    output.write_bytes(resp.content)
    return str(output)


def _pubmed_ids(query: str, max_results: int) -> list[str]:
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": _limit(max_results),
    }
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params=params,
        )
        resp.raise_for_status()
    data = resp.json()
    return [str(item) for item in data.get("esearchresult", {}).get("idlist", [])]


def search_pubmed(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search PubMed via NCBI E-utilities."""
    ids = _pubmed_ids(query, max_results)
    if not ids:
        return []
    params = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params=params,
        )
        resp.raise_for_status()
    data = resp.json().get("result", {})
    out: list[dict[str, Any]] = []
    for pmid in ids:
        item = data.get(pmid, {})
        authors = [a.get("name", "") for a in item.get("authors", []) if isinstance(a, dict)]
        doi = ""
        for article_id in item.get("articleids", []):
            if article_id.get("idtype") == "doi":
                doi = article_id.get("value", "")
                break
        out.append(
            _paper(
                paper_id=pmid,
                title=item.get("title", ""),
                authors=[a for a in authors if a],
                source="pubmed",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                published_date=item.get("pubdate", ""),
                doi=doi,
                extra={
                    "journal": item.get("fulljournalname", ""),
                    "source": item.get("source", ""),
                },
            )
        )
    return out


def read_pubmed_paper(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Fetch PubMed XML and return title, abstract, and citation metadata."""
    params = {"db": "pubmed", "id": paper_id, "retmode": "xml"}
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params=params,
        )
        resp.raise_for_status()
    root = ET.fromstring(resp.text)
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


def download_pubmed(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Save PubMed readable metadata and abstract text to a relative text file."""
    output = _relative_output_path(save_path, _safe_filename(paper_id, ".txt"))
    output.write_text(read_pubmed_paper(paper_id, save_path), encoding="utf-8")
    return str(output)


def _search_europe_pmc(query: str, source_name: str, max_results: int) -> list[dict[str, Any]]:
    journal = "bioRxiv" if source_name == "biorxiv" else "medRxiv"
    params = {
        "query": f'({query}) AND JOURNAL:"{journal}"',
        "format": "json",
        "pageSize": _limit(max_results),
    }
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params=params,
        )
        resp.raise_for_status()
    results = resp.json().get("resultList", {}).get("result", [])
    out: list[dict[str, Any]] = []
    for item in results:
        doi = item.get("doi", "")
        full_text_urls = item.get("fullTextUrlList", {}).get("fullTextUrl", [{}])
        out.append(
            _paper(
                paper_id=doi or item.get("id", ""),
                title=item.get("title", ""),
                authors=[_clean_text(item.get("authorString", ""))],
                abstract=item.get("abstractText", ""),
                source=source_name,
                url=item.get("doiUrl", "") or full_text_urls[0].get("url", ""),
                published_date=item.get("firstPublicationDate", "") or item.get("pubYear", ""),
                doi=doi,
                extra={
                    "journal": item.get("journalTitle", ""),
                    "pmcid": item.get("pmcid", ""),
                },
            )
        )
    return out


def search_biorxiv(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search bioRxiv-indexed preprints via Europe PMC."""
    return _search_europe_pmc(query, "biorxiv", max_results)


def search_medrxiv(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search medRxiv-indexed preprints via Europe PMC."""
    return _search_europe_pmc(query, "medrxiv", max_results)


def _preprint_pdf_url(server: str, paper_id: str) -> str:
    return f"https://www.{server}.org/content/{paper_id}.full.pdf"


def read_biorxiv_paper(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Return a bioRxiv landing/PDF pointer for a DOI-like paper id."""
    return f"bioRxiv ID/DOI: {paper_id}\nPDF: {_preprint_pdf_url('biorxiv', paper_id)}"


def read_medrxiv_paper(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Return a medRxiv landing/PDF pointer for a DOI-like paper id."""
    return f"medRxiv ID/DOI: {paper_id}\nPDF: {_preprint_pdf_url('medrxiv', paper_id)}"


def download_biorxiv(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Download a bioRxiv PDF by DOI-like paper id."""
    return _download_preprint_pdf("biorxiv", paper_id, save_path)


def download_medrxiv(paper_id: str, save_path: str = "paper/references/downloads") -> str:
    """Download a medRxiv PDF by DOI-like paper id."""
    return _download_preprint_pdf("medrxiv", paper_id, save_path)


def _download_preprint_pdf(server: str, paper_id: str, save_path: str) -> str:
    output = _relative_output_path(save_path, _safe_filename(paper_id, ".pdf"))
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(_preprint_pdf_url(server, paper_id))
        resp.raise_for_status()
    output.write_bytes(resp.content)
    return str(output)


def search_google_scholar(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Scholar-like broad paper search via the Semantic Scholar public API.

    Google Scholar has no official public API. This keeps the imported
    ``search_google_scholar`` name for compatibility but returns Semantic
    Scholar metadata with ``source="semantic_scholar"``.
    """
    params = {
        "query": query,
        "limit": _limit(max_results),
        "fields": (
            "title,abstract,authors,year,url,venue,externalIds,citationCount,"
            "publicationDate,openAccessPdf"
        ),
    }
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params=params,
        )
        resp.raise_for_status()
    out: list[dict[str, Any]] = []
    for item in resp.json().get("data", []):
        external_ids = item.get("externalIds") or {}
        pdf = item.get("openAccessPdf") or {}
        out.append(
            _paper(
                paper_id=item.get("paperId", ""),
                title=item.get("title", ""),
                authors=[a.get("name", "") for a in item.get("authors", []) if isinstance(a, dict)],
                abstract=item.get("abstract") or "",
                source="semantic_scholar",
                url=item.get("url", ""),
                pdf_url=pdf.get("url", "") if isinstance(pdf, dict) else "",
                published_date=item.get("publicationDate") or str(item.get("year") or ""),
                doi=external_ids.get("DOI", ""),
                citations=int(item.get("citationCount") or 0),
                extra={"venue": item.get("venue", ""), "external_ids": external_ids},
            )
        )
    return out
