---
slug: plan-persistence
summary: Persist multi-step execution plans to disk so they survive context resets and conversation compaction. Use when work has ≥2 steps that span dispatches.
layer: logical
version: 1
status: active
provenance: human+agent
---

# Plan Persistence

Write multi-step plans to durable disk so a future wake can resume without re-deriving them.

## When to use

- Work has ≥2 steps that will be dispatched separately.
- Context handoffs (`mos_compact_context` or `mos_reset_context`) are likely between steps.
- You want the post-handoff agent under the same role to pick up where you left off.

## Skip when

- Single-step task where dispatch alone is sufficient.
- The plan is trivial enough to fit in one dispatch prompt.

## Key distinction

This is distinct from the DAG `pending_plan` flag (used by `cognitive-checkpoint` for deferred single events). An execution plan is your own multi-step roadmap; a `pending_plan` DAG node is a deferred event. They coexist.

## Where to write

```
project_{port}/branches/<role>/plans/<role>-<slug>.md   (active)
project_{port}/branches/<role>/plans/archive/           (done or abandoned)
```

## Resume protocol

Before designing a new plan at wake, list `branches/<your-role>/plans/<your-role>-*.md` and resume the oldest active one's next pending step. Only enter the thinking postures when no active plan applies to the current event batch.

## Update protocol

After each step's dispatch returns, atomically rewrite the plan file:
- Flip that step's `Status` to `done`.
- Fill `Evidence` (commit SHA, artifact path, EACN event id).
- When all steps `done`, set frontmatter `status: done` and `git mv` to `archive/`.
- If superseded or wrong direction, set `status: abandoned` with a one-line `abandoned-reason` and archive.

## Template

```markdown
---
plan-id: <role>-<slug>-YYYY-MM-DD
owner: <role>
parent-eacn-task: <task-id or null>
status: active   # active | done | abandoned
---

## Postures used
- <posture>: <one-line takeaway>

## Steps

| # | What | Goal (sensor / threshold) | Dispatch | Status | Evidence |
|---|------|---------------------------|----------|--------|----------|
| 1 | ... | ... | Task / codex / EACN | pending | — |
| 2 | ... | ... | ... | pending | — |

## Notes
<free-form: open questions, branch points, things to revisit>
```

## Worked example

You woke to "add /healthz endpoint + test". Two steps minimum (endpoint, test). Write `branches/coder/plans/coder-healthz-2026-05-17.md` with both steps and their goals. Dispatch step 1 via Task subagent. When it returns, flip step 1 to `done`, fill Evidence with the commit SHA, write back. Dispatch step 2. If a context handoff (`mos_compact_context` or `mos_reset_context`) fires between steps, the post-handoff agent sees the active plan, picks up at step 2 — no re-thinking needed.
