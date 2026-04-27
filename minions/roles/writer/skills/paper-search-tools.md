# Skill — Paper Search Tools

Use MinionsOS paper-search MCP tools for focused scholarly lookup when they are available.

Writer may have these tools from the `minionsos` MCP server: `search_arxiv`, `search_pubmed`, `search_biorxiv`, `search_medrxiv`, `search_google_scholar`, plus matching `read_*_paper` and `download_*` tools.

1. **Search with a claim in mind.** Query for the method family, closest competitors, datasets, baselines, benchmark papers, and factual claims that need citation support.
2. **Prefer reliable metadata.** Capture title, authors, year, venue/source, URL or ID, DOI/arXiv ID when present, and the specific claim the paper supports.
3. **Separate paper classes.** Maintain background, closest-related, dataset/benchmark, methodology, and contrasting-work groups in `workspace/paper/references/` or `workspace/paper/notes/`.
4. **Verify before citing.** Do not trust a search result title alone. Read the abstract or paper text when the citation supports a specific technical claim.
5. **Fallback gracefully.** If the dedicated search tool is unavailable, use `WebSearch`/`WebFetch` and record the lookup source. Do not block the whole paper solely because one paper source is down.
6. **Never fabricate BibTeX.** If metadata is incomplete, mark a citation gap instead of inventing authors, venue, DOI, or year.
