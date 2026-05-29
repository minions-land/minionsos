---
slug: full-dream
summary: Deep Draft consolidation — audit structural health, surface contradictions via Draft annotation + Book open-questions (Noter is fully off-EACN), generate comprehensive cognitive-graph status report. Dispatched as a single Workflow with parallel motif-scan / dead-end-connect / communities-and-god-nodes phases plus a verifier.
layer: logical
tools: mos_draft_query, mos_draft_append, mos_draft_annotate, mos_book_open_question, mos_publish_to_shared, Workflow
version: 4
status: active
supersedes:
references: draft-maintenance, micro-dream, role-act-via-workflow
provenance: human
---

# Skill — Full-Dream

Deep consolidation of the Draft (L1). Audit structural health, surface
contradictions via Draft annotation + Book open-questions, and produce
a comprehensive cognitive-graph status report. Noter is fully
off-EACN — contradictions surface as durable artefacts that Ethics
adjudicates, never as direct DMs.

## When to invoke

- Periodic Noter wake when Draft has accumulated ≥ 10 new nodes since
  last full-dream pass.
- Detected status-flap (a node oscillating between `verified` and
  `tentative` over recent wakes).
- Triggered by an explicit Gru request via project state.

## Structure

Single-Workflow phase shape: `parallel(motif-scan |
dead-end-connect | communities-and-god-nodes) → verifier-agent →
one mos_draft_append batch`. The Workflow returns a size-bounded
structured summary; the main Noter session writes the final
artefacts (`branches/shared/draft/summary.md` refreshed,
`branches/shared/notes/dream-{date}.md` new) via
`mos_publish_to_shared`. Long full-dream Workflows MUST run with
`run_in_background=true` per common §4.

The audit classifies problem nodes into four categories: stale,
contradictions, orphans, and missing-evidence.

## Procedure

1. **Find stale, contradiction, orphan, and missing-evidence nodes.**
   Use `mos_draft_query` to list all nodes; for each compute:
   - **Stale**: nodes with `support_status="tentative"` and no
     activity (no new edges or annotations) for >24h project time.
   - **Contradictions**: pairs of nodes connected by a
     `contradicts` edge where both have `support_status="verified"`
     or `tentative`.
   - **Orphans**: nodes with no incoming or outgoing edges.
   - **Missing evidence**: `verified` nodes without an
     `evidence_tag`.
2. **Annotate stale nodes.** Call `mos_draft_annotate` to set status
   `blocked` with metadata `{"stale_reason": "no activity since
   {date}"}`.
3. **Surface contradictions to Ethics via durable artefacts**, never
   via DM. For each contradicting pair:
   - Call `mos_draft_append` to create a new `question` node ("How
     to resolve contradiction between {X} and {Y}?"), with edges
     pointing at both source nodes.
   - Call `mos_book_open_question` so Ethics picks it up via the
     Book contradiction surface (§Eth5).
4. **Log orphans and missing-evidence nodes** in the report but take
   no mutating action.
5. **Write a staged `branches/noter/draft-summary.md`** with full
   statistics: node/edge counts by type and status, stale count,
   contradiction count, orphan count, frontier nodes. Publish it to
   `branches/shared/draft/summary.md`.

## Pitfalls

- Resolving contradictions yourself — create the question node and
  let Ethics adjudicate. Resolution is not Noter's domain.
- Sending an EACN advisory DM. Noter is off-EACN; contradictions
  surface via Draft + Book open-question only.
- Deleting or archiving nodes. Stale nodes get annotated, never
  removed.
- Exceeding the 120-line cap on
  `branches/shared/draft/summary.md`.
- Forgetting the §10.1 scratchpad fragment in the Workflow spec —
  the PreToolUse hook will block path-shaped writes inside the
  agent.
- Unmarked claims — all written claims must carry
  `[derived: branches/shared/draft/draft.json]`.

