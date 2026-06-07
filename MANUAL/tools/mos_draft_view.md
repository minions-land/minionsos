---
id: mos_draft_view
kind: tool
domain: memory
auth: [gru, expert, ethics]
source: minions/tools/mcp/memory_tools.py:85
since: stable
keywords: [draft, view, query, orient, wake, graph]
related: [mos_draft_append, mos_draft_annotate, mos_draft_path]
status: stable
---

# mos_draft_view

**One line:** Unified read over the team Draft graph: orientation header + filtered node/edge slice. The single role-facing memory lens.

## Signature
```py
mos_draft_view(
  query: str | None = None,        # free-text match over node text
  by_role: str | None = None,      # filter to one author role
  by_status: str | None = None,    # support_status: verified / refuted / pending ...
  by_type: str | None = None,      # node type: hypothesis / plan / pending_plan / evidence / result / insight / method
  related_to: str | None = None,   # node_id — return its neighbourhood (edges + adjacent nodes)
  sort: str | None = None,         # "recent" (default) / "confidence"
  limit: int | None = None,        # cap on returned nodes
) -> {
  orientation: {                   # always present — the header
    total_nodes, total_edges,
    pending_plans: [ ... ],        # 🔑 todos left by previous selves
    counts_by_type: { ... },
    counts_by_status: { ... },
  },
  nodes: [ { node_id, type, text, author_role, support_status, ts } ],
  edges: [ { from_id, to_id, relation } ],
}
```

## Behaviour
Reads `branches/main/draft/draft.json`. The `orientation` header is always
returned; the `nodes`/`edges` slice reflects whatever filters you passed. This
single lens provides both orientation and filtered Draft reads.

## Cold-start orient
A no-arg call is the cold-start orientation — call it first on every wake:
```py
mos_draft_view()          # ← first call after wake; read `orientation.pending_plans`
mos_await_events()        # then: what's new
```
Pass filters when you need to drill into a region of the graph, e.g.
`mos_draft_view(by_status="verified", by_type="result")` or
`mos_draft_view(related_to="n_42")`.

## Don't
- Don't call this every cycle — once per wake to orient is enough.
- Don't ignore `orientation.pending_plans`. It's the only memory of what you
  were doing before the last context reset.
