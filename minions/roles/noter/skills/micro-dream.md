---
slug: micro-dream
summary: Lightweight Draft maintenance — verify consistency, flag contradictions via Draft annotation + Book open-questions (Noter is fully off-EACN), refresh the pre-computed summary. Runs on every Noter wake as a preamble. Single-agent Workflow.
layer: logical
tools: mos_draft_query, mos_draft_summary, mos_draft_annotate, mos_book_open_question, mos_publish_to_shared, Workflow
version: 4
status: active
supersedes:
references: draft-maintenance, full-dream, role-act-via-workflow
provenance: human
---

# Skill — Micro-Dream

Lightweight Draft reconciliation that keeps the summary current for
all roles to query. Runs as a preamble on every Noter wake before
other work. Noter is fully off-EACN — contradictions surface as
durable artefacts that Ethics adjudicates, never as direct DMs.

## When to invoke

- On every Noter wake before other duty steps.
- After receiving a role-exit event in the wake delta.

## Structure

Single-agent Workflow producing a refreshed
`branches/shared/draft/summary.md`, staged first under
`branches/noter/` and published via `mos_publish_to_shared`. No heavy
mutations — only flags contradictions and refreshes statistics. Full
structural repair belongs to `full-dream`.

## Procedure

1. **Get current statistics.** Call `mos_draft_summary()`.
2. **Check for inconsistencies.** Call `mos_draft_query()` with no
   filters:
   - Nodes referenced in edges but missing from the node list.
   - Contradiction pairs: nodes connected by `contradicts` where both
     are `verified` or `tentative`.
3. **Flag contradictions via durable artefacts** (no DM). For each
   flagged pair, call `mos_book_open_question` so Ethics picks it up
   via the Book contradiction surface (§Eth5). Do not resolve.
4. **Write updated staged summary under `branches/noter/` and publish
   it to `branches/shared/draft/summary.md`:**
   - Total nodes/edges, counts by `support_status`.
   - Active frontier (nodes with status `tentative` or `unverified`
     that have recent activity).
   - Flagged contradictions (if any).
   - Dead end count (so roles can query before re-exploring).

## Pitfalls

- Resolving contradictions — that is Ethics' adjudication scope.
  Only flag them via Book open-questions.
- Sending an EACN advisory DM. Noter is off-EACN; contradictions
  surface via Draft + Book open-question only.
- Rewriting `journal.jsonl` — it is append-only and immutable.
- Exceeding 120 lines in the summary — keep it useful as quick
  context.
- Unmarked claims — all summary claims must carry
  `[derived: branches/shared/draft/draft.json]`.

