---
slug: cognitive-checkpoint
summary: Persist cognitive state to the Exploration DAG before calling mos_reset_context or when finishing a line of investigation.
layer: logical
tools: mos_dag_append, mos_dag_annotate, mos_reset_context
version: 3
status: active
supersedes:
references: think-then-act
provenance: human+agent
---

# Skill — Cognitive Checkpoint

Persist discoveries and pending plans to the Exploration DAG so your future self (post-reset) can pick up without re-deriving context.

## When to invoke

- Before calling `mos_reset_context()` (mandatory — reset without checkpoint = data loss).
- When finishing a coherent line of investigation.
- When think-then-act determines the next events require a direction change.

## Procedure

1. **Persist completed work.** For each discovery not yet in the DAG, call `mos_dag_append` with the appropriate type and a self-contained one-line description.
2. **Update node statuses.** For any node whose status changed during this session, call `mos_dag_annotate` with evidence references.
3. **Record dead ends.** Append with type `dead_end` and the abandonment reason.
4. **Persist pending plans.** If you have planned next steps that you have not yet executed, append them as `unverified` nodes (hypothesis, experiment, or question) so your post-reset self knows what to do next. Add edges connecting them to the current work.
5. **Add edges.** Connect all new nodes to existing ones with appropriate relations.
6. **Call `mos_reset_context()`** with a reason describing why you are resetting.

## Pitfalls

- Calling `mos_reset_context()` without checkpointing first — your future self starts blind.
- Persisting intermediate reasoning as nodes — only persist conclusions and plans.
- Forgetting pending plans — your post-reset self will not know what was next.
- Writing vague node text — each node must be self-contained and interpretable without surrounding context.

## Output habit

`[checkpoint: {node_ids persisted}, pending: {planned_node_ids}] → mos_reset_context({reason})`
