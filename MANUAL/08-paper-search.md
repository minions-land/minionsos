# 08 — Paper search

> **L2 card.** Writer-primary surface. Other roles may search on demand.
> Top three: `mos_search_papers_federated` (broad), `mos_search_arxiv` (focused), `mos_read_arxiv_paper` (full text).
> All search tools are READ-only and external. The downloaders persist PDFs into the project's paper cache.

---

## Federated search

### mos_search_papers_federated

```python
args:
  query: str
  sources: list[str] | None        # default: ["arxiv","pubmed","biorxiv","medrxiv","scholar","semantic"]
  max_per_source: int = 5
  since_year: int | None
returns: {
  results: [ { source, id, title, authors, year, abstract, url } ],
  source_errors: { source: error_msg },
}
```

Use this first when you don't know which venue covers your topic. Always inspect `source_errors` — partial failures are common.

---

## Per-source search

| Tool | Source |
|---|---|
| `mos_search_arxiv(query, max_results=10, category=None)` | arXiv |
| `mos_search_pubmed(query, max_results=10, since_year=None)` | PubMed |
| `mos_search_biorxiv(query, max_results=10)` | bioRxiv |
| `mos_search_medrxiv(query, max_results=10)` | medRxiv |
| `mos_search_google_scholar(query, max_results=10)` | Scholar (rate-limited) |
| `mos_search_semantic(query, max_results=10)` | Semantic Scholar |

All return `{ results: [{ id, title, authors, year, abstract, url }] }`.

---

## Download + read

| Tool | What |
|---|---|
| `mos_download_arxiv(arxiv_id)` | persist PDF to project cache; returns local path |
| `mos_read_arxiv_paper(arxiv_id_or_path)` | extract text, return as string |
| `mos_resolve_arxiv_ids(titles_or_dois)` | bulk-lookup arXiv IDs |

The same shape exists for PubMed (`mos_download_pubmed` + `mos_read_pubmed_paper`), bioRxiv, medRxiv.

---

## Patterns

### Writer pulling related work for a Section 2

```python
hits = mos_search_papers_federated(query="grokking critical norm", since_year=2022)
for hit in hits["results"][:8]:
    if hit["source"] == "arxiv":
        path = mos_download_arxiv(hit["id"])
        body = mos_read_arxiv_paper(path)
        # cite + summarise; ingest your own summary as a Book page
```

### Coder verifying a baseline

```python
# 1. find Notsawo's predictor paper
hits = mos_search_arxiv(query="grokking spectral oscillation Notsawo")
# 2. read the method
text = mos_read_arxiv_paper(hits["results"][0]["id"])
# 3. extract the algorithm; record as a Draft node
mos_draft_append(nodes=[{ "type": "method", "text": "Notsawo predictor recipe", ... }])
```

---

## Pitfalls

- **Scholar is rate-limited.** Bursts of `mos_search_google_scholar` calls fail. Stagger or fall back to `mos_search_semantic`.
- **arXiv ID format matters.** `2306.01234` and `arxiv:2306.01234` and `arXiv:2306.01234v2` are different inputs to different tools. `mos_resolve_arxiv_ids` normalises.
- **PDF text extraction is lossy.** Equations and figure captions may be mangled. For tight formula work, fetch the source `.tar.gz` and read `.tex`.
- **Don't ingest a paper's full text into the Book.** Ingest your own summary, link out to the PDF in the project paper cache.
