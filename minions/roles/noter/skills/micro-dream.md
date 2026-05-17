---
slug: micro-dream
summary: Lightweight DAG maintenance — verify consistency, flag contradictions, refresh the pre-computed summary. Runs on every Noter wake as a preamble.
layer: logical
tools: mos_dag_query, mos_dag_summary, eacn3_send_message, mos_publish_to_shared
version: 2
status: active
supersedes:
references: dag-maintenance, full-dream
provenance: human
---

# Skill — Micro-Dream

Lightweight DAG reconciliation that keeps the summary current for all roles to query. Runs as a preamble on every Noter wake before other work.

## When to invoke

- After receiving a role-exit or time-trigger event via `mos_await_events`.
- Lightweight enough to run on every Noter wake before other work.

## Structure

Quick consistency check producing a refreshed `branches/shared/exploration/summary.md`, staged first under `branches/noter/` and published via `mos_publish_to_shared`. No heavy mutations — only flags contradictions and refreshes statistics. Full structural repair belongs to `full-dream`.

## Procedure

1. **Get current statistics.** Call `mos_dag_summary()`.
2. **Check for inconsistencies.** Call `mos_dag_query()` with no filters:
   - Nodes referenced in edges but missing from the node list.
   - Contradiction pairs: nodes connected by `contradicts` where both are `verified` or `tentative`.
3. **Flag contradictions.** If found, send an EACN advisory message to the relevant Expert(s). Do not resolve.
4. **Write updated staged summary under `branches/noter/` and publish it to `branches/shared/exploration/summary.md`:**
   - Total nodes/edges, counts by `support_status`.
   - Active frontier (nodes with status `tentative` or `unverified` that have recent activity).
   - Flagged contradictions (if any).
   - Dead end count (so roles can query before re-exploring).

## Pitfalls

- Resolving contradictions — that is Expert's job. Only flag them.
- Rewriting `journal.jsonl` — it is append-only and immutable.
- Exceeding 120 lines in the summary — keep it useful as quick context.
- Unmarked claims — all summary claims must carry `[derived: branches/shared/exploration/dag.json]`.
