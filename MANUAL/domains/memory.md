---
id: domain-memory
kind: domain
domain: memory
auth: ['*']
source: minions/tools/mcp/memory_tools.py:1
since: stable
keywords: [draft, book, shelf, reel, memory, hot, hypothesis]
related: [mos_draft_summary, mos_book_query, mos_book_hot_get, mos_reel_get]
status: stable
---

# Domain: Memory (Draft / Book / Shelf / Reel)

Four layers, top-down:

| Layer | What | Who writes | File |
|---|---|---|---|
| **L0 Reel** | raw verbatim subagent traces | hook (auto) | `branches/<role>/reel/<sess>/...` |
| **L1 Draft** | process graph: hypotheses, plans, evidence, support edges | every EACN role | `branches/shared/draft/draft.json` |
| **L2 Book** | durable compiled knowledge, citation-shaped | Noter only | `branches/shared/book/sources/*.md` |
| **L3 Shelf** | structural graph index | `mos_shelf_register` | `branches/shared/shelf/shelf.json` |

## Top tools

```bash
lookup.py --id mos_draft_summary       # FIRST call after wake
lookup.py --id mos_draft_append        # record a hypothesis / result
lookup.py --id mos_draft_annotate      # mark verified / refuted
lookup.py --id mos_book_query          # find a Book page
lookup.py --id mos_book_hot_get        # the rolling cache
lookup.py --id mos_reel_get            # drill into a subagent trace
```

## Rules

- `mos_draft_summary` BEFORE `mos_await_events`. The summary surfaces
  `pending_plan` nodes left by your previous self before context reset.
- Draft `text` field: one sentence. Long content goes in `metadata` or a Book ingest.
- Use `evidence_tag: "[evidence: <path|sha|event_id>]"` on every result node.
- Book pages with no inbound `[[wikilink]]` keep flagging `ORPHAN_PAGE`.
  Either link via `mos_book_save_synthesis` or accept the lint warning.
- `mos_book_promote_verified` only picks Draft nodes (insight / method / result)
  with `support_status=verified` AND ≥ 2 `supports` edges AND age ≥ 7 days.

## Project_37596 lessons

- Subagents producing 18 contradiction verdicts in one shot wrote boilerplate
  rationales. Always `mos_reel_get(ref)` before accepting bulk verdicts.
  See `pitfall-subagent-boilerplate`.
- `mos_book_hot_update` schema is deferred. Run `ToolSearch(query="select:mos_book_hot_update")` once per session.

## Full surface

```bash
lookup.py --domain memory
```
