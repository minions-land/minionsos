---
id: mos_book_query
kind: tool
domain: memory
auth: [gru, coder, ethics, writer, expert, noter]
source: minions/tools/mcp/memory_tools.py:194
since: stable
keywords: [book, query, search, page, knowledge, durable]
related: [mos_book_ingest, mos_book_save_synthesis, mos_draft_view]
status: stable
---

# mos_book_query

**One line:** Search durable Book pages by topic. Pages live at `branches/shared/book/sources/`.

## Signature
```py
mos_book_query(
  query: str,                  # natural-language; matched against title + content
  max_results: int = 10,
  filter_role: str | None,
) -> { pages: [ { slug, title, snippet, role, reel_ref?, links_in, links_out } ] }
```

## When to call
- BEFORE `mos_book_ingest` — if a page already covers your topic, link via
  `mos_book_save_synthesis` instead of duplicating.
- During Writer narrative work — Book is the citation-shaped knowledge.
- During Ethics audits to validate claim provenance.

## See also
- domain-memory
- mos_book_ingest
- mos_book_save_synthesis
