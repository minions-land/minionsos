---
slug: dispatch-runner
summary: Submit allocate-resources's plan to the Python queue — stage inputs, call mos_exp_queue_submit once, persist the batch id, broadcast handoff, exit. The only place mos_exp_queue_submit is called.
layer: logical
tools: mos_exp_queue_submit, mos_exp_put
version: 3
status: active
supersedes:
references: allocate-resources, track-run
provenance: human
---

# Skill — Dispatch Runner

Submit once, persist the batch id, exit. The Python scheduler issues non-blocking `mos_exp_run` calls, records run handles, and keeps pending work flowing on later reconciles. This skill owns the queue-submit boundary: `allocate-resources` produces the plan, this skill turns the plan into queued runs.

## When to invoke

- After `allocate-resources` produces a plan (unit specs + staging flags + pool changes).
- On wake-up when a new request should be merged into the global queue.

## Structure

One call to `mos_exp_queue_submit` per plan. If any unit was flagged `needs_staging`, run `mos_exp_put` for that unit's input paths before submitting. After submitting, store `{batch_id, unit_ids}` in scratchpad or the requester-facing note so later wake-ups can call `mos_exp_queue_status`. Never follow with long `mos_exp_wait` — Python reconciles and tracks detached runs. Heavy per-unit execution prep (non-trivial scripting, data massage, config expansion) is delegated to a subagent whose whitelist is `mos_exp_*` only.

## Procedure

1. **Stage inputs.** For each unit the plan flagged `needs_staging: true`, run `mos_exp_put(target_id, src, dst)` before submission. Skip if already staged.
2. **Submit all units.** `mos_exp_queue_submit(units=[...])`; include `reserve_mb` / `min_free_mb` from the plan.
3. **Record the batch id.** Store `{batch_id, unit_ids}` in scratchpad or the requester-facing note so later wake-ups can call `mos_exp_queue_status`.
4. **Do not block.** Never follow queue submission with long `mos_exp_wait`; Python reconciles and tracks detached runs.
5. **Delegate heavy per-unit execution prep to a subagent** when a unit requires non-trivial scripting, data massage, or config expansion. Subagents have `mos_exp_*` only; they must not inherit `eacn3_*`.
6. **Broadcast a short EACN handoff** listing the batch id, currently launched units, and pending count so Noter / requester know jobs are alive: `{batch_id, submitted, launched_now, pending}` plus a pointer to status / report artifacts.

## Pitfalls

- Re-doing `allocate-resources`'s planning here. If the plan is wrong, return to `allocate-resources` rather than mutating units in-place at submit time.
- Reaching for `mos_exp_wait(timeout=3600)` out of habit. This is explicitly banned as a default primitive (§Fire-and-poll).
- Forgetting to persist `batch_id` before the ephemeral session exits — detached jobs survive, your memory does not.
- Starting a subagent that inherits `eacn3_*`. Subagents must not; the whitelist enforces this.
- Calling `mos_exp_gpu_pool_set` here to "fix" a pool issue. Pool policy belongs to `allocate-resources` (or to the user via `triage-request`); changing it at submit time hides the policy decision from the plan record.
