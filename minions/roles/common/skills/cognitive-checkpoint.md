---
slug: cognitive-checkpoint
summary: Persist cognitive state to the Draft before mos_compact_context (preferred) or mos_reset_context — including any unrelated events you received but deliberately did not execute, marked pending_plan, so the post-handoff agent picks them up before calling mos_await_events.
layer: logical
tools: mos_draft_append, mos_draft_annotate, mos_compact_context, mos_reset_context
version: 8
status: active
supersedes:
references: think-then-act
provenance: human+agent
---

# Skill — Cognitive Checkpoint

Both `mos_compact_context` and `mos_reset_context` discard your conversation history. Compact compresses it inside the same live process (cache stays warm); reset kills the tmux session and the Gru watchdog respawns a cold `claude`. In both cases the only bridge across the gap is the Draft. Anything not persisted is lost — including events already dequeued from EACN that will not be redelivered.

## Two distinct "plan" concepts — do not confuse them

This skill uses **`metadata.pending_plan = true`** on Draft nodes — a flag for *deferred single events* that the next fresh process must execute before it calls `mos_await_events`. Each pending_plan node is one EACN event you received but did not run.

This is **not** the same thing as `branches/<role>/plans/<role>-<slug>.md` produced by [[think-then-act]] — those are *your own multi-step execution plans* (markdown documents with frontmatter, step tables, and Goal-Setting thresholds). Execution plans persist across resets unchanged; only their per-step `Status` updates as steps complete. They do not carry the `pending_plan` flag, do not live in the Draft, and are not affected by `mos_reset_context`.

Both coexist. After respawn the role drains Draft `pending_plan` nodes (this skill), and separately resumes any active execution plan in `branches/<role>/plans/` (handled by think-then-act + `roles/SYSTEM.md` lifecycle).

## When to invoke

- Before every `mos_compact_context()` or `mos_reset_context()` call — mandatory.
- When think-then-act has split the incoming batch into relevant + unrelated, and the unrelated set is non-empty.
- When finishing a coherent line of investigation and the next thing in queue is a new direction.

## Compact vs Reset — choose after checkpointing

After persisting state (steps 1-5 below), choose the exit:

- **`mos_compact_context(reason, pending_plans)`** — PREFERRED. Process stays
  alive, prompt cache stays warm. Use when context is large but healthy.
  After calling, STOP immediately. You wake in compressed context.
- **`mos_reset_context(reason)`** — HARD RESET. Kills the process. Use only
  when behavior has drifted or SYSTEM.md changed externally. Costs ~50k
  uncached tokens on cold start.

## Pointer-only handoff (compact path)

The PreCompact hook (`minions/hooks/pre_compact_science.py`) tells the compact
model to produce a *pointer-shaped* summary that cites IDs and paths only:

- **L1 — Draft**: cite node IDs (H-001, E-002, R-003, DEAD-004, …) — never paste node text.
- **L2 — Book**: cite paths (`book/sources/<role>-<slug>.md`) — never paste page bodies.
- **L3 — Shelf**: cite community labels or node IDs (`n42_xxx`, `p<port>_xxx`) — never paste graph dumps.
- **EACN events**: cite event IDs / sender@timestamp — never paste message bodies.
- **Experiment artefacts**: cite `exp/exp-<id>/report.md` — never paste report content.

The post-compact agent re-fetches detail in one MCP call (`mos_book_query` /
`mos_draft_view`). That is
strictly cheaper than carrying detail across every subsequent turn until the
next compact.

This skill's job is to make sure the IDs the compact summary will cite
**already exist on disk** before `/compact` fires. Steps 1-5 below do that.

## Structure

The checkpoint persists two categories: completed work (discoveries, status changes, dead ends) and deferred work (events received but not executed). The deferred category uses `metadata.pending_plan = true` as the hand-off channel:

- **This process**: receives events, executes the related ones, persists the unrelated ones with `pending_plan = true`, hands off (compact or reset).
- **Post-handoff agent**: starts in a clean context (compressed-after-compact or cold-after-reset), calls `mos_draft_summary`, sees pending plans, executes them, THEN calls `mos_await_events` for genuinely new work.

If you skip the pending_plan persistence step, the unrelated events are lost forever — EACN does not redeliver.

## Procedure

1. **Persist completed work.** For each discovery not yet in the Draft, call `mos_draft_append` with the right type and a self-contained one-line description. Include `evidence_tag` pointing to the receipt / artifact / commit.
2. **Update node statuses.** For any node whose support_status changed during this session, call `mos_draft_annotate` with new evidence.
3. **Record dead ends.** Append with `type=dead_end` and the abandonment reason — losing these causes redundant re-exploration after reset.
4. **Persist unrelated-but-dequeued events as pending plans — critical.** For each event you received this cycle but deliberately did not execute (because it was unrelated to your context), append a node with **`metadata.pending_plan = true`**. The node text must capture enough of the event for a post-handoff agent to act on it without re-reading the original event (which is gone). Include sender, ask, and any deadline/budget. Same flag applies to planned-but-not-yet-executed next steps from your own work.
5. **Add edges.** Connect new nodes to existing ones with appropriate relations (`supports`, `refutes`, `depends_on`, `derived_from`). Orphans are hard to interpret post-handoff.
6. **Hand off — prefer compact.**
   - Default: call `mos_compact_context(reason=..., pending_plans=[...])`. Process stays alive, prompt cache stays warm. STOP immediately after the call — no more tool calls or text. The compacted agent wakes up and should call `mos_await_events()` first thing.
   - Fallback only when compact cannot recover (drifted role contract, externally-edited SYSTEM.md): call `mos_reset_context(reason=...)`. The tool kills your tmux session immediately; you almost never see its return value. Cold start costs ~$0.14 per respawn.

## Pending-plan node — shape

For an unrelated event handed off to the next process:

```python
mos_draft_append(nodes=[{
    "type": "question",            # or experiment / hypothesis — match event intent
    "text": "Writer requests Coder refactor data-loader for arbitrary tokenizers (HF vs SP). Originating event from writer@2026-05-17T14:02Z.",
    "support_status": "unverified",
    "metadata": {"pending_plan": True, "source": "eacn_event"},
}])
```

For your own planned-but-not-yet-executed next step:

```python
mos_draft_append(nodes=[{
    "type": "experiment",
    "text": "Sweep learning rate {1e-4, 5e-4, 1e-3} for the 12B variant",
    "support_status": "unverified",
    "metadata": {"pending_plan": True},
}])
```

Always add an edge anchoring the pending plan to its parent context (hypothesis, decision, or originating event) so it is not floating.

## Pitfalls

- **Handing off without persisting unrelated events.** Those events were dequeued from EACN — they will not be redelivered. The post-handoff agent will never know they existed.
- **Trying to execute unrelated events before handing off.** That defeats the purpose: the whole reason you are handing off is to avoid burning tokens in the wrong context. Persist them and let a clean context do them.
- **Forgetting `metadata.pending_plan = true`.** Without the flag, the node is buried; `mos_draft_summary` will not surface it; the post-handoff agent will not know to execute it before calling `mos_await_events`.
- **Vague node text.** Each pending_plan node must be interpretable by an agent who has zero context — they will not have the original event in their history. Include sender, request, and any deadline.
- **Reaching for reset when compact would do.** Reset costs ~$0.14 in cold-start tokens; compact is free in cache terms. Only escalate to reset when compact alone cannot recover.
- **Handing off mid-execution.** If a relevant event's work is half-done, finish it or roll back; don't hand off with workspace in an inconsistent state.

## Output habit

Default (preferred):

`[checkpoint: persisted={node_ids}, pending_plan={pending_node_ids}] → mos_compact_context({reason})`

Fallback (only when compact cannot recover):

`[checkpoint: persisted={node_ids}, pending_plan={pending_node_ids}] → mos_reset_context({reason})`
