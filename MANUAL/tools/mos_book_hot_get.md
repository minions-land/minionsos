---
id: mos_book_hot_get
kind: tool
domain: memory
auth: [gru, coder, ethics, writer, expert, noter]
source: minions/tools/mcp/memory_tools.py:277
since: stable
keywords: [book, hot, cache, wake, summary, rolling]
related: [mos_book_query, mos_book_hot_update, mos_draft_summary]
status: stable
---

# mos_book_hot_get

**One line:** Read the Book hot cache — rolling ~500-word summary auto-injected at wake.

## Signature
```py
mos_book_hot_get() -> {
  hot_md: str,                            # the rolling cache
  recent_ingests: [ { slug, title, role } ],
  recently_verified: [ ... ],
  unresolved_contradictions: int,
  active_hypotheses: int,
}
```

## When to call
- Right after `mos_draft_summary` on every wake (cold-start order).
- Mid-cycle when you want a refresher.

## Updating the hot cache
Only Noter writes — via `mos_book_hot_update`. Don't try to update from
another role; it's whitelisted.

## See also
- domain-memory
- mos_book_hot_update
