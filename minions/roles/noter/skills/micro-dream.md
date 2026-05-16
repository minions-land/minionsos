# Micro-Dream

Lightweight DAG maintenance — merge journal entries, verify consistency, refresh the pre-computed summary.

## Core move

Reconcile `exploration/journal.jsonl` with the live DAG so the summary stays current for all roles to query.

## Procedure

1. Call `mos_dag_summary()` to get current graph statistics.
2. Call `mos_dag_query()` with no filters to check for inconsistencies:
   - Nodes referenced in edges but missing from the node list.
   - Contradiction pairs: nodes connected by `contradicts` where both are `verified` or `tentative`.
3. If contradictions found: send an EACN advisory message to the relevant Expert(s) noting the conflict. Do not resolve it yourself.
4. Write an updated `exploration/summary.md` containing:
   - Total nodes/edges, counts by `support_status`.
   - Active frontier (nodes with status `tentative` or `unverified` that have recent activity).
   - Flagged contradictions (if any).
   - Dead end count (so roles can query before re-exploring).

## When to invoke

- After receiving a role-exit or time-trigger event via `mos_await_events`.
- Lightweight enough to run on every Noter wake as a preamble before other work.

## Pitfalls

- Never resolve contradictions — that is Expert's job. Only flag them.
- Do not rewrite `journal.jsonl`; it is append-only and immutable.
- Keep the summary under 120 lines so it stays useful as quick context.
- Mark all summary claims as `[derived: exploration/dag.json]`.

## Output habit

`exploration/summary.md` refreshed. No EACN messages unless a contradiction is found.
