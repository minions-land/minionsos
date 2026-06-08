"""Paper search/read/download tools — thin dispatch over paper_search."""

from __future__ import annotations

from minions.tools import paper_search as _paper_search
from minions.tools.mcp import mcp
from minions.tools.mcp._common import (
    ArxivIdsArgs,
    PaperFederatedArgs,
    PaperIdArgs,
    PaperSearchArgs,
    _require_tool_allowed,
)


@mcp.tool()
def mos_search_arxiv(args: PaperSearchArgs) -> list[dict]:
    """Search arXiv papers through the project-local MinionsOS MCP server."""
    _require_tool_allowed("mos_search_arxiv")
    return _paper_search.search_arxiv(args.query, args.max_results)


@mcp.tool()
def mos_search_pubmed(args: PaperSearchArgs) -> list[dict]:
    """Search PubMed papers through the project-local MinionsOS MCP server."""
    _require_tool_allowed("mos_search_pubmed")
    return _paper_search.search_pubmed(args.query, args.max_results)


@mcp.tool()
def mos_search_biorxiv(args: PaperSearchArgs) -> list[dict]:
    """Search bioRxiv-indexed preprints through Europe PMC."""
    _require_tool_allowed("mos_search_biorxiv")
    return _paper_search.search_biorxiv(args.query, args.max_results)


@mcp.tool()
def mos_search_medrxiv(args: PaperSearchArgs) -> list[dict]:
    """Search medRxiv-indexed preprints through Europe PMC."""
    _require_tool_allowed("mos_search_medrxiv")
    return _paper_search.search_medrxiv(args.query, args.max_results)


@mcp.tool()
def mos_search_google_scholar(args: PaperSearchArgs) -> list[dict]:
    """Scholar-like broad search using Semantic Scholar metadata."""
    _require_tool_allowed("mos_search_google_scholar")
    return _paper_search.search_google_scholar(args.query, args.max_results)


@mcp.tool()
def mos_search_semantic(args: PaperSearchArgs) -> list[dict]:
    """Search Semantic Scholar metadata."""
    _require_tool_allowed("mos_search_semantic")
    return _paper_search.search_semantic(args.query, args.max_results)


@mcp.tool()
def mos_search_papers_federated(args: PaperFederatedArgs) -> list[dict]:
    """Run a federated search across multiple academic sources, deduplicating by DOI/title."""
    _require_tool_allowed("mos_search_papers_federated")
    return _paper_search.search_papers_federated(
        args.query, sources=args.sources, max_results=args.max_results
    )


@mcp.tool()
def mos_resolve_arxiv_ids(args: ArxivIdsArgs) -> list[dict]:
    """Batch-resolve arXiv ids to canonical paper dicts (Web → ID → paper, step 2)."""
    _require_tool_allowed("mos_resolve_arxiv_ids")
    return _paper_search.resolve_arxiv_ids(args.ids)


@mcp.tool()
def mos_read_arxiv_paper(args: PaperIdArgs) -> str:
    """Read arXiv metadata and abstract text for a paper id."""
    _require_tool_allowed("mos_read_arxiv_paper")
    return _paper_search.read_arxiv_paper(args.paper_id, args.save_path)


@mcp.tool()
def mos_read_pubmed_paper(args: PaperIdArgs) -> str:
    """Read PubMed metadata and abstract text for a PMID."""
    _require_tool_allowed("mos_read_pubmed_paper")
    return _paper_search.read_pubmed_paper(args.paper_id, args.save_path)


@mcp.tool()
def mos_read_biorxiv_paper(args: PaperIdArgs) -> str:
    """Read bioRxiv metadata pointers for a DOI-like paper id."""
    _require_tool_allowed("mos_read_biorxiv_paper")
    return _paper_search.read_biorxiv_paper(args.paper_id, args.save_path)


@mcp.tool()
def mos_read_medrxiv_paper(args: PaperIdArgs) -> str:
    """Read medRxiv metadata pointers for a DOI-like paper id."""
    _require_tool_allowed("mos_read_medrxiv_paper")
    return _paper_search.read_medrxiv_paper(args.paper_id, args.save_path)


@mcp.tool()
def mos_download_arxiv(args: PaperIdArgs) -> str:
    """Download an arXiv PDF to a relative workspace path."""
    _require_tool_allowed("mos_download_arxiv")
    return _paper_search.download_arxiv(args.paper_id, args.save_path)


@mcp.tool()
def mos_download_pubmed(args: PaperIdArgs) -> str:
    """Save PubMed metadata and abstract text to a relative workspace path."""
    _require_tool_allowed("mos_download_pubmed")
    return _paper_search.download_pubmed(args.paper_id, args.save_path)


@mcp.tool()
def mos_download_biorxiv(args: PaperIdArgs) -> str:
    """Download a bioRxiv PDF to a relative workspace path."""
    _require_tool_allowed("mos_download_biorxiv")
    return _paper_search.download_biorxiv(args.paper_id, args.save_path)


@mcp.tool()
def mos_download_medrxiv(args: PaperIdArgs) -> str:
    """Download a medRxiv PDF to a relative workspace path."""
    _require_tool_allowed("mos_download_medrxiv")
    return _paper_search.download_medrxiv(args.paper_id, args.save_path)
