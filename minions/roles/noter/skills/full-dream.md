# Full-Dream

Deep consolidation of the Exploration DAG — audit structural health, surface contradictions, generate team status report.

## Core move

Audit the entire DAG for structural health, escalate unresolvable conflicts to Experts, and produce a comprehensive exploration status report.

## Procedure

1. Call `mos_dag_query()` with no filters to load the complete graph.
2. Classify problem nodes:
   - **Stale**: `unverified` for >3 days with no connected activity (no edges added/modified since creation).
   - **Contradictions**: nodes linked by `contradicts` edges where both are `verified` or `tentative`.
   - **Orphans**: nodes with zero incoming and zero outgoing edges (exclude the root question).
   - **Missing evidence**: `verified` nodes without an `evidence_tag`.
3. For stale nodes: call `mos_dag_annotate` to set status `blocked` with metadata `{"stale_reason": "no activity since {date}"}`.
4. For contradictions: call `mos_dag_append` to create a new `question` node — "How to resolve contradiction between {X} and {Y}?" — then send an EACN message to the relevant Expert(s) with `[derived: exploration/dag.json]`.
5. Log orphans and missing-evidence nodes in the report but take no mutating action.
6. Write `exploration/summary.md` with full statistics: node/edge counts by type and status, stale count, contradiction count, orphan count, frontier nodes.
7. Write a dream report to `artifacts/notes/dream-{YYYY-MM-DD}.md` summarizing actions taken and open issues.

## When to invoke

- Daily, triggered by a scheduled time-trigger event via `mos_await_events`.
- On-demand when Gru sends a direct EACN message requesting DAG maintenance.

## Pitfalls

- Do not resolve contradictions yourself — create the question node and escalate. Resolution is Expert's domain.
- Do not delete or archive nodes. Stale nodes get annotated, never removed.
- Respect the 120-line cap on `exploration/summary.md`.
- Mark all written claims: `[derived: exploration/dag.json]`.

## Output habit

Two artifacts per invocation: `exploration/summary.md` (refreshed), `artifacts/notes/dream-{date}.md` (new). EACN messages if contradictions are escalated.
