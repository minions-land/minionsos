---
id: mos_noter_wait
kind: tool
domain: runtime
auth: []
source: minions/tools/mcp/runtime_tools.py:94
since: stable
keywords: [noter, wait, timer, periodic, delta, observe]
related: [mos_await_events, mos_book_lint, mos_draft_view]
status: stable
---

# mos_noter_wait

**One line:** Noter's wake driver. Timer-based (3 min default). Returns deltas only.

## Signature
```py
mos_noter_wait(timeout_s: int = 180) -> {
  woke_at: str,
  reason: "timer" | "fresh_events_in_journal" | "fresh_artifact_in_shared",
  since_iso: str,
}
```

## Why Noter is different
Noter is **not on EACN**. It observes the project by polling `events/*.jsonl`
and `branches/shared/`. After v15.10's `since_iso` fix, Noter wakes get only
deltas, not full re-scans.

## Cold-start pattern (Noter)
```py
1. mos_draft_view
2. mos_book_lint              # cheap; surface orphans early
3. mos_noter_wait              # block until next delta
```

## See also
- domain-memory
- domain-runtime
- mos_book_lint
