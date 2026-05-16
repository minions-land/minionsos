---
slug: paper-literature-search
summary: Focused literature search for paper writing — claim-first queries via the MinionsOS paper-search MCP tools (arxiv / pubmed / biorxiv / medrxiv / scholar), with verify-before-cite discipline.
layer: logical
tools: mos_search_arxiv, mos_search_pubmed, mos_search_biorxiv, mos_search_medrxiv, mos_search_google_scholar, mos_read_arxiv_paper, mos_read_pubmed_paper, mos_read_biorxiv_paper, mos_read_medrxiv_paper, mos_download_arxiv, mos_download_pubmed, mos_download_biorxiv, mos_download_medrxiv
version: 3
status: active
supersedes: paper-search-tools
references: citation-audit, end-to-end-paper-workflow
provenance: human
---

# Skill — Paper Literature Search

This skill does two things on purpose: it names the **MCP tools** to use for scholarly lookup, and it sets the **search discipline** (claim-first queries, paper-class grouping, no-fabrication rule) that turns those tool calls into citable evidence. Both halves are needed — the tool list without discipline produces snippet-grade citations, and the discipline without the tool list produces guesswork.

## When to invoke

- Writer needs method-family references, closest competitors, datasets, baselines, benchmark papers, or factual-claim citations.
- A citation gap flagged by `paper-literature-citation-builder` needs to be filled.
- Reviewer asks about prior-art coverage.

## Structure — tool reference

Tool families from the `minionsos` MCP server. Use the dedicated tool first; fall back to general web search only if it is unavailable.

- **Search.** `mos_search_arxiv`, `mos_search_pubmed`, `mos_search_biorxiv`, `mos_search_medrxiv`, `mos_search_google_scholar`.
- **Read.** `mos_read_arxiv_paper`, `mos_read_pubmed_paper`, `mos_read_biorxiv_paper`, `mos_read_medrxiv_paper`.
- **Download.** `mos_download_arxiv`, `mos_download_pubmed`, `mos_download_biorxiv`, `mos_download_medrxiv`.
- **Fallback.** `WebSearch` / `WebFetch` when a dedicated tool is unavailable. Record the lookup source. Do not block the whole paper because one source is down.

Output paths: background / closest-related / dataset-benchmark / methodology / contrasting-work groups under `branches/writer/paper/references/` or `branches/writer/paper/notes/`. Per-paper metadata: title, authors, year, venue / source, URL or ID, DOI / arXiv ID when present, and the specific claim the paper supports.

## Procedure — search discipline

1. **Search with a claim in mind.** Before opening a search tool, write down the specific claim or method-family you are looking for. Query for the method family, closest competitors, datasets, baselines, benchmarks, and factual claims needing citation support. A query without a target claim produces snippet citations that fail `citation-audit`'s context check.
2. **Prefer reliable metadata.** Capture title, authors, year, venue / source, URL or ID, DOI / arXiv ID when present, and the specific supported claim. Skipping any of these now means a `MISSING`-or-`DRIFT` verdict later.
3. **Separate paper classes at intake time.** File results into background / closest-related / dataset-benchmark / methodology / contrasting-work groups under `branches/writer/paper/references/` or `.../notes/`. Mixing classes turns the related-work section into a list rather than an argument.
4. **Verify before citing.** Do not trust a search-result title alone. Read the abstract or paper text when the citation supports a specific technical claim — that is the layer `citation-audit` will later check as `WRONG_CONTEXT`.
5. **Fallback gracefully.** If the dedicated search tool is unavailable, use `WebSearch` / `WebFetch` and record the lookup source so the audit trail is honest.
6. **Never fabricate BibTeX.** Incomplete metadata → mark a citation gap and ask through EACN, not invent authors, venue, DOI, or year.

## Pitfalls

- Citing from search-result snippets without reading the paper.
- Invented BibTeX when metadata is incomplete.
- Over-collecting references without mapping each to a specific claim.
- Trusting a single source; cross-reference arXiv with venue page on ambiguous cases.
- Treating this skill as tool-only and skipping the discipline section — that produces the failure modes `citation-audit` exists to catch.
