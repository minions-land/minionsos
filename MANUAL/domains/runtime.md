---
id: domain-runtime
kind: domain
domain: runtime
auth: ['*']
source: minions/tools/mcp/runtime_tools.py:1
since: stable
keywords: [mcp, wake, compact, reset, attach, kill, monitor, loop, gru]
related: [mos_await_events, mos_get_events, mos_unread_summary, mos_compact_context, mos_reset_context]
status: stable
---

# Domain: Runtime control

MCP topology and wake-loop control. The visible tool list is broad for cache
parity; server-side authz is the execution boundary.

## MCP layers

| Layer | Server | Role-facing meaning |
|---|---|---|
| OS | `minionsos` | `mos_*` tools for projects, memory, lifecycle, review, experiments, visual checks, and runtime |
| Network | `eacn3` | raw agent-network messages, tasks, bids, results, registry, and observability |
| Keepalive | `keepalive` | `wait_bg` / `keepalive_now` during long background work |
| Plugin | per Expert | workflow tools attached only to the spawned Expert instance |

## Event intake

## Top tools

```bash
lookup.py --id mos_await_events       # Expert/Ethics resident wake driver
lookup.py --id mos_unread_summary     # Gru project unread scan
lookup.py --id mos_get_events         # Gru one-project drain
lookup.py --id mos_compact_context    # tell harness to compact
lookup.py --id mos_reset_context      # mark for fresh boot next wake
```

| Caller | Use |
|---|---|
| Expert / Ethics | `mos_draft_view` then `mos_await_events` |
| Gru | `mos_unread_summary` then `mos_get_events({"port": ...})` |

## When to compact vs reset

| Condition | Use |
|---|---|
| token usage > ~70 % AND work continues | `mos_compact_context` |
| phase boundary, drift risk, fresh-start required | `mos_reset_context` (flush plan to Draft FIRST) |

## Pre-reset checklist

```python
# Before mos_reset_context, persist what next-me needs:
mos_draft_append(nodes=[{
  "type": "pending_plan",
  "text": "Resume P2 baselines — 3 of 7 done, drain queue then publish.",
  "metadata": {"for_role": "expert"},
}])
mos_reset_context(reason="P2 mid-progress checkpoint")
```

`mos_draft_view` on the next wake will surface that node.
