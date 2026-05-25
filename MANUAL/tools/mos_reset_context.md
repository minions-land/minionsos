---
id: mos_reset_context
kind: tool
domain: runtime
auth: [gru, coder, ethics, writer, expert, noter]
source: minions/tools/mcp/runtime_tools.py:158
since: stable
keywords: [reset, context, fresh, boot, marker, checkpoint]
related: [mos_compact_context, mos_draft_append, mos_draft_summary]
status: stable
---

# mos_reset_context

**One line:** Drop a marker so next wake is a fresh boot. Persist your plan to Draft FIRST.

## Signature
```py
mos_reset_context(reason: str) -> { marker_path }
```

Files a marker into `state/.reset_markers/<role>.json`. The watchdog respawns
the role on next tick with a clean session.

## Pre-reset checklist
```py
mos_draft_append(nodes=[{
  "type": "pending_plan",
  "text": "Resume P2 baselines — 3 of 7 done, drain queue then publish.",
  "metadata": {"for_role": "coder"},
}])
mos_reset_context(reason="P2 mid-progress checkpoint")
```

`mos_draft_summary` on the next wake will surface that node as
`pending_plan_for_me`.

## When to use
- Phase boundary (P1 → P2)
- Drift risk after long thrashy session
- Recovery from a bad subagent bundle

## See also
- mos_compact_context
- mos_draft_append
