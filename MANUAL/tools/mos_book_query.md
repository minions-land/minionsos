---
id: mos_book_query
kind: tool
domain: memory
auth: [gru, coder, ethics, writer, expert, noter]
source: minions/tools/mcp/memory_tools.py:194
since: stable
keywords: [book, query, search, page, knowledge, durable]
related: [mos_book_hot_get, mos_book_ingest, mos_book_save_synthesis, mos_shelf_query]
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

## vs `mos_book_hot_get`
- `_hot_get` returns the rolling ~500-word cache, auto-injected at wake.
- `_query` runs a real search against the full Book corpus.

## vs `mos_shelf_query`
- `mos_book_query` text-matches pages.
- `mos_shelf_query` walks the typed graph (claim ↔ source ↔ method).

## See also
- domain-memory
- mos_book_hot_get
- mos_book_ingest
