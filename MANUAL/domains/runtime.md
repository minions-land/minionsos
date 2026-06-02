---
id: domain-runtime
kind: domain
domain: runtime
auth: ['*']
source: minions/tools/mcp/runtime_tools.py:1
since: stable
keywords: [wake, compact, reset, attach, kill, monitor, loop]
related: [mos_await_events, mos_noter_wait, mos_compact_context, mos_reset_context]
status: stable
---

# Domain: Runtime control

Wake-loop control. Three real entry points, one escape hatch.

## Top tools

```bash
lookup.py --id mos_await_events       # EACN roles wake driver
lookup.py --id mos_noter_wait         # Noter only — timer-based
lookup.py --id mos_compact_context    # tell harness to compact
lookup.py --id mos_reset_context      # mark for fresh boot next wake
```

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
  "metadata": {"for_role": "coder"},
}])
mos_reset_context(reason="P2 mid-progress checkpoint")
```

`mos_draft_view` on the next wake will surface that node.
