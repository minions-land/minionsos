---
id: mos_draft_summary
kind: tool
domain: memory
auth: [gru, coder, ethics, writer, expert, noter]
source: minions/tools/mcp/memory_tools.py:98
since: stable
keywords: [draft, summary, wake, pending, plan, hypotheses]
related: [mos_draft_query, mos_draft_append, mos_draft_annotate, mos_book_hot_get]
status: stable
---

# mos_draft_summary

**One line:** First call after every wake. Surfaces `pending_plan` nodes left by your previous self.

## Signature
```py
mos_draft_summary() -> {
  recent_nodes: [ { node_id, type, text, author_role, ts } ],
  pending_plan_for_me: [ ... ],          # 🔑 todos from past-me
  active_hypotheses: [ ... ],
  recently_verified: [ ... ],
  recently_refuted: [ ... ],
}
```

## Behaviour
Reads `branches/shared/draft/draft.json`. Filters `pending_plan_for_me` to your role.

## Cold-start order
```py
1. mos_draft_summary       # ← first
2. mos_book_hot_get        # what the team converged on
3. mos_await_events        # what's new
```

## Don't
- Don't call this every cycle — once per wake is enough.
- Don't ignore `pending_plan_for_me`. It's the only memory of what you were
  doing before the last context reset.
