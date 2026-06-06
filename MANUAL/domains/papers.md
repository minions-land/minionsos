---
id: domain-papers
kind: domain
domain: papers
auth: [expert]
source: minions/tools/mcp/paper_tools.py:1
since: stable
keywords: [paper, search, arxiv, pubmed, biorxiv, scholar, semantic, citation]
related: [mos_search_papers_federated, mos_search_arxiv]
status: stable
---

# Domain: Paper search

Expert-primary. Other roles search on demand.

## Top tools

```bash
lookup.py --id mos_search_papers_federated   # broad — fan-out across all sources
lookup.py --id mos_search_arxiv              # focused
lookup.py --id mos_read_arxiv_paper          # full text from id-or-path
```

Per-source: `mos_search_{arxiv,pubmed,biorxiv,medrxiv,google_scholar,semantic}`.
Read paths: `mos_download_<source>` then `mos_read_<source>_paper`.

## Pitfalls

- Scholar is rate-limited — bursts fail. Stagger or use `mos_search_semantic`.
- arXiv ID forms differ across tools. Use `mos_resolve_arxiv_ids` to normalise.
- PDF text extraction is lossy on equations + figure captions. Fetch `.tar.gz`
  source for tight formula work.
- Don't ingest a paper's full text into the Book — ingest your own summary
  with the PDF cached in the project paper store.
