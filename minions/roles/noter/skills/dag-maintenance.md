# DAG Maintenance

Operational guidelines for maintaining the Exploration DAG — learned from testing at scale (500+ nodes, 6 topics, 4 research phases).

## Core move

Keep the DAG structurally healthy so all roles can query it effectively. A well-maintained DAG has high edge density, meaningful communities, and no orphans.

## Procedure

1. **Query with full visibility.** Always use `mos_dag_query(limit=10000)` when doing maintenance. The default limit of 50 truncates the graph and causes incomplete maintenance.

2. **Connect dead ends to hypotheses first.** This is the highest-value edge type. For every `dead_end` node, ensure it has a `contradicts` edge to the hypothesis it refutes. This prevents other roles from re-exploring failed paths.

3. **Build same-topic chains.** Within each topic, consecutive discoveries should be linked:
   - experiment → result: `supports` (strength 0.8-0.9)
   - hypothesis → experiment: `tests` (strength 0.85-0.95)
   - result → decision: `derived_from` (strength 0.7-0.8)
   - dead_end → hypothesis: `contradicts` (strength 0.4-0.6)

4. **Bridge topics through decisions.** Decision nodes that were influenced by findings from other topics should have `related_to` edges connecting them. These cross-topic edges are what make community detection and paper-path extraction work.

5. **Target edge density >1.0 edges/node.** Below this threshold, community detection degrades into "one community per node" which is useless. Check with `mos_dag_summary()` — if `total_edges / total_nodes < 1.0`, prioritize adding edges.

6. **Use `mos_dag_communities()` to verify structure.** Healthy signs: 5-15 communities for a 500-node graph, largest community <30% of total nodes, multiple cross-community edges. Unhealthy: >50 communities (too sparse) or 1 community (everything collapsed).

7. **Use `mos_dag_god_nodes()` to spot fragility.** If one node has score >30 (degree >15), the graph is too centralized. Consider whether sub-hypotheses should be split out to distribute connectivity.

## When to invoke

- During micro-dream (after role exits): quick edge-density check, connect any new orphan nodes.
- During full-dream (daily): full audit — run all 7 steps above.
- When `mos_dag_summary()` shows edge density dropping below 1.0.

## Pitfalls

- Using default `limit=50` for maintenance queries — you will only see 10% of the graph.
- Adding edges without checking if they already exist — creates duplicates.
- Over-connecting: not every pair of nodes needs an edge. Only add edges that represent a real relationship (tests, supports, contradicts, derived_from, related_to).
- Resolving contradictions yourself — flag them and escalate to Expert. Your job is structure, not scientific judgment.

## Output habit

After maintenance: report edge density, community count, orphan count, and any contradictions flagged. `[derived: mos_dag_query + mos_dag_communities output]`
