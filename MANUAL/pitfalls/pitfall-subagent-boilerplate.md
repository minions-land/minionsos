---
id: pitfall-subagent-boilerplate
kind: pitfall
domain: memory
auth: ['*']
source: minions/review/SYSTEM.md:1
since: stable
keywords: [subagent, boilerplate, lazy, verdict, review, contradiction, codex, agent]
related: [mos_reel_get, mos_reel_window, mos_book_resolve_contradiction]
status: stable
---

# pitfall: subagent verdicts are boilerplate, not real

**Symptom:**
```
The subagent did boilerplate work — every "needs-experiment" verdict has a
one-line generic rationale "Substantive disagreement requires further
investigation" with a contradictory action ("Close as resolved.")
```

A subagent dispatched to verdict 18 contradictions returned 18 generic
rationales that contradicted their own actions.

## Cause

Spawning `Agent` / `mcp__codex-subagent__codex` and accepting the verdict
without inspecting the trace. Lazy subagents stamp boilerplate over
non-trivial decisions.

## Recipe

Before accepting a verdict touching > 3 items:

```python
# 1. Pull the subagent's reel
trace = mos_reel_get(ref="<role>/<session_id>/<task_id>")
# 2. Tail it for "did it actually read each item?"
window = mos_reel_window(ref=..., span=10)
# 3. Look for: did it grep / read each input? Or did it pattern-match titles only?
```

Generic rationales like "Substantive disagreement requires further
investigation" are red flags. So is "Close as resolved" paired with
"needs-experiment" verdict in the same record.

## Discipline

- Don't ask one subagent to verdict 18 contradictions in one call.
  Chunk to 5-at-a-time, OR do the long-tail inline.
- Subagent tasks must always carry the artifact path, not just a summary.
- Review the reel before signing off bulk verdicts.
