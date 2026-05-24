# 11 — Runtime control

> **L2 card.** Wake-loop control. Three real entry points (`mos_await_events`, `mos_noter_wait`, `mos_compact_context`) and one escape hatch (`mos_reset_context`).
> Top three: `mos_await_events` (chapter 02 covers it), `mos_compact_context`, `mos_reset_context`.

---

## mos_noter_wait (Noter only)

```python
args:
  timeout_s: int = 180          # default = noter_periodic_interval, ~3 min
returns: {
  woke_at: str,
  reason: "timer" | "fresh_events_in_journal" | "fresh_artifact_in_shared",
  since_iso: str,                # delta window start
}
```

Noter is **not on EACN**. It observes the project by polling `events/*.jsonl` and `branches/shared/`. After `since_iso` was added in v15.10, Noter wakes only get deltas, not full re-scans.

**Cold-start pattern (Noter):**
```text
1. mos_draft_summary
2. mos_book_hot_get
3. mos_book_lint           # cheap; surface orphans early
4. mos_noter_wait          # block until next delta
```

---

## mos_compact_context

Ask the harness to compact and resume.

```python
args:
  reason: str | None
  preserve: list[str] | None    # paths/sections to keep verbatim
returns: { compacted: bool, summary_path }
```

**When to call.**
- Token usage > ~70 % of session budget AND your work is not done.
- Long subagent or codex bundles dumped into context.

**Don't:**
- Don't compact mid-tool-chain. Finish the current chain first.
- Don't compact and immediately re-read everything you just lost — the summary is meant to be enough.

---

## mos_reset_context

Drop a marker so the next wake is a fresh boot of this role.

```python
args:
  reason: str
returns: { marker_path }
```

Files a marker into `state/.reset_markers/<role>.json`. The watchdog respawns the role on next tick with a clean session. Your in-flight work survives via Draft + handoffs — make sure those are flushed first.

**Pattern: ending a long, drift-prone session**
```python
# 1. Flush plan for next-me
mos_draft_append(nodes=[{
  "type": "pending_plan",
  "text": "Resume P2 baselines — 3 of 7 done, drain queue then publish.",
  "metadata": { "for_role": "coder" },
}])
# 2. Reset
mos_reset_context(reason="P2 mid-progress checkpoint")
```

---

## mos_start_monitor (Gru)

Starts the Gru background monitor loop (backend health probes, role watchdog, queue reconcile). You almost never call this manually; `gru` launcher does it.

---

## Wake-loop reference (every EACN role except Noter)

```text
loop:
  events = mos_await_events()           # blocks until something
  if events.idle_check:
      mos_draft_summary()               # think; refresh state; maybe refresh hot.md
      continue
  for ev in events.events:
      handle(ev)                        # may dispatch subagent, run experiment, publish
  # token check
  if context_load > 0.7:
      mos_compact_context(reason="post-batch")
```

## Wake-loop reference (Noter)

```text
loop:
  delta = mos_noter_wait(timeout_s=180)
  if delta.reason == "timer":
      maybe_lint, maybe_promote_verified
  else:
      ingest new artifacts; update hot; commit draft; resolve contradictions
```
