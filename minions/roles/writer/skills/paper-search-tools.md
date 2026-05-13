---
slug: paper-search-tools
summary: Use MinionsOS paper-search MCP tools for focused scholarly lookup — search_arxiv / search_pubmed / search_biorxiv / search_medrxiv / search_google_scholar, plus read_* and download_*.
layer: logical
tools: search_arxiv, search_pubmed, search_biorxiv, search_medrxiv, search_google_scholar, read_arxiv_paper, read_pubmed_paper, read_biorxiv_paper, read_medrxiv_paper, download_arxiv, download_pubmed, download_biorxiv, download_medrxiv
version: 2
status: active
supersedes:
references: citation-audit, end-to-end-paper-workflow
provenance: human
---

# Skill — Paper Search Tools

Focused scholarly lookup via the `minionsos` MCP server's paper-search tools when available.

## When to invoke

- Writer needs method-family references, closest competitors, datasets, baselines, benchmark papers, or factual-claim citations.
- A citation gap flagged by `paper-literature-citation-builder` needs to be filled.
- Reviewer asks about prior-art coverage.

## Structure

Tool families from the `minionsos` MCP server:

- `search_arxiv`, `search_pubmed`, `search_biorxiv`, `search_medrxiv`, `search_google_scholar`.
- `read_arxiv_paper`, `read_pubmed_paper`, `read_biorxiv_paper`, `read_medrxiv_paper`.
- `download_arxiv`, `download_pubmed`, `download_biorxiv`, `download_medrxiv`.

Output directories: background / closest-related / dataset-benchmark / methodology / contrasting-work groups under `branches/writer/paper/references/` or `branches/writer/paper/notes/`. Per-paper metadata: title, authors, year, venue / source, URL or ID, DOI / arXiv ID when present, and the specific claim the paper supports.

Fallback: `WebSearch` / `WebFetch` when a dedicated tool is unavailable. Record the lookup source. Do not block the whole paper solely because one source is down.

## Procedure

1. **Search with a claim in mind.** Query for the method family, closest competitors, datasets, baselines, benchmarks, and factual claims needing citation support.
2. **Prefer reliable metadata.** Title, authors, year, venue / source, URL or ID, DOI / arXiv ID when present, specific supported claim.
3. **Separate paper classes.** Background, closest-related, dataset / benchmark, methodology, contrasting-work groups under `branches/writer/paper/references/` or `.../notes/`.
4. **Verify before citing.** Do not trust a search result title alone. Read the abstract or paper text when the citation supports a specific technical claim.
5. **Fallback gracefully.** If the dedicated search tool is unavailable, use `WebSearch` / `WebFetch` and record the lookup source.
6. **Never fabricate BibTeX.** Incomplete metadata → mark a citation gap instead of inventing authors, venue, DOI, or year.

## Pitfalls

- Citing from search-result snippets without reading the paper.
- Invented BibTeX when metadata is incomplete.
- Over-collecting references without mapping each to a specific claim.
- Trusting a single source; cross-reference arXiv with venue page on ambiguous cases.
