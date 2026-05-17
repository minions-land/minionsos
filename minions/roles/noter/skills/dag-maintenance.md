---
slug: dag-maintenance
summary: Keep the Exploration DAG structurally healthy — connect dead ends to hypotheses, build same-topic chains, bridge topics through decisions, target edge density >1.0 edges/node.
layer: logical
tools: mos_dag_query, mos_dag_append, mos_dag_annotate, mos_dag_summary
version: 2
status: active
supersedes:
references: full-dream, micro-dream
provenance: human
---

# Skill — DAG Maintenance

A well-maintained DAG has high edge density, meaningful communities, and no orphans. This skill keeps the graph structurally healthy so all roles can query it effectively.

## When to invoke

- During micro-dream (after role exits): quick edge-density check, connect any new orphan nodes.
- During full-dream (daily): full audit — run all steps below.
- When `mos_dag_summary()` shows edge density dropping below 1.0.

## Structure

Seven maintenance operations, ordered from highest-value (dead-end connections) to diagnostic (community and fragility checks). The principle: edges carry meaning, orphans waste future tokens, and over-centralization creates fragility.

## Procedure

1. **Query with full visibility.** Always use `mos_dag_query(limit=10000)` for maintenance. The default limit of 50 truncates the graph and causes incomplete maintenance.

2. **Connect dead ends to hypotheses.** Highest-value edge type. For every `dead_end` node, ensure it has a `contradicts` edge to the hypothesis it refutes. This prevents other roles from re-exploring failed paths.

3. **Build same-topic chains.** Within each topic, link consecutive discoveries:
   - experiment → result: `supports` (strength 0.8–0.9)
   - hypothesis → experiment: `tests` (strength 0.85–0.95)
   - result → decision: `derived_from` (strength 0.7–0.8)
   - dead_end → hypothesis: `contradicts` (strength 0.4–0.6)

4. **Bridge topics through decisions.** Decision nodes influenced by findings from other topics get `related_to` edges. These cross-topic edges enable community detection and paper-path extraction.

5. **Target edge density >1.0 edges/node.** Below this threshold, community detection degrades. Check with `mos_dag_summary()`.

6. **Verify structure with `mos_dag_communities()`.** Healthy: 5–15 communities for a 500-node graph, largest <30% of total, multiple cross-community edges. Unhealthy: >50 (too sparse) or 1 (collapsed).

7. **Spot fragility with `mos_dag_god_nodes()`.** Score >30 (degree >15) means the graph is too centralized. Split sub-hypotheses to distribute connectivity.

## Pitfalls

- Using default `limit=50` for maintenance queries — you see only 10% of the graph.
- Adding edges without checking existence — creates duplicates.
- Over-connecting: only add edges representing real relationships.
- Resolving contradictions yourself — flag and escalate to Expert. Your job is structure, not scientific judgment.
