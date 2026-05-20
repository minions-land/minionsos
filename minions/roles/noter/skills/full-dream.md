---
slug: full-dream
summary: Deep Scratchpad consolidation — audit structural health, surface contradictions, escalate to Experts, generate comprehensive cognitive-graph status report.
layer: logical
tools: mos_scratchpad_query, mos_scratchpad_append, mos_scratchpad_annotate, eacn3_send_message, mos_publish_to_shared
version: 3
status: active
supersedes:
references: scratchpad-maintenance, micro-dream
provenance: human
---

# Skill — Full-Dream

Deep consolidation of the Scratchpad (L1). Audit structural health, surface contradictions, escalate unresolvable conflicts to Experts, and produce a comprehensive cognitive-graph status report.

## When to invoke

- Daily, triggered by a scheduled time-trigger event via `mos_await_events`.
- On-demand when Gru sends a direct EACN message requesting Scratchpad maintenance.

## Structure

Full audit producing two artifacts: `branches/shared/scratchpad/summary.md` (refreshed) and `branches/shared/notes/dream-{date}.md` (new), staged first under `branches/noter/` and published via `mos_publish_to_shared`. Contradictions are escalated to Experts via EACN. The audit classifies problem nodes into four categories: stale, contradictions, orphans, and missing-evidence.

## Procedure

1. **Load the complete graph.** Call `mos_scratchpad_query()` with no filters.
2. **Classify problem nodes:**
   - **Stale**: `unverified` for >3 days with no connected activity.
   - **Contradictions**: nodes linked by `contradicts` edges where both are `verified` or `tentative`.
   - **Orphans**: nodes with zero incoming and zero outgoing edges (exclude the root question).
   - **Missing evidence**: `verified` nodes without an `evidence_tag`.
3. **Annotate stale nodes.** Call `mos_scratchpad_annotate` to set status `blocked` with metadata `{"stale_reason": "no activity since {date}"}`.
4. **Escalate contradictions.** Call `mos_scratchpad_append` to create a new `question` node ("How to resolve contradiction between {X} and {Y}?"), then send an EACN message to the relevant Expert(s).
5. **Log orphans and missing-evidence nodes** in the report but take no mutating action.
6. **Write a staged `branches/noter/scratchpad-summary.md`** with full statistics: node/edge counts by type and status, stale count, contradiction count, orphan count, frontier nodes. Publish it to `branches/shared/scratchpad/summary.md`.
7. **Write a staged dream report** under `branches/noter/` and publish it to `branches/shared/notes/dream-{YYYY-MM-DD}.md`, summarizing actions taken and open issues.

## Pitfalls

- Resolving contradictions yourself — create the question node and escalate. Resolution is Expert's domain.
- Deleting or archiving nodes. Stale nodes get annotated, never removed.
- Exceeding the 120-line cap on `branches/shared/scratchpad/summary.md`.
- Unmarked claims — all written claims must carry `[derived: branches/shared/scratchpad/scratchpad.json]`.
