---
slug: dispatch-runner
summary: Submit allocate-resources's plan to the Python queue — optionally dry-run with mos_exp_queue_plan, stage inputs, call mos_exp_queue_submit once, reflect on placement, persist the batch id, broadcast handoff, exit. The only place mos_exp_queue_submit is called.
layer: logical
tools: mos_exp_queue_submit, mos_exp_queue_plan, mos_exp_put
version: 4
status: active
supersedes:
references: allocate-resources, track-run
provenance: human
---

# Skill — Dispatch Runner

Submit once, reflect once, persist the batch id, exit. The Python scheduler issues non-blocking `mos_exp_run` calls, records run handles, and keeps pending work flowing on later reconciles. This skill owns the queue-submit boundary: `allocate-resources` produces the plan, this skill turns the plan into queued runs and double-checks the resulting placement.

## When to invoke

- After `allocate-resources` produces a plan (unit specs + staging flags + pool changes).
- When a new request arrives that should be merged into the global queue.

## Structure

Optional pre-check via `mos_exp_queue_plan` for non-trivial sweeps; one call to `mos_exp_queue_submit` per plan; one reflection pass on the returned `placement` summary. If any unit was flagged `needs_staging`, run `mos_exp_put` for that unit's input paths before submitting. After submitting, record `{batch_id, unit_ids}` via `mos_dag_append` or the requester-facing note so later wake-ups can call `mos_exp_queue_status`. Never follow with long `mos_exp_wait` — Python reconciles and tracks detached runs. Heavy per-unit execution prep is delegated to a subagent whose whitelist is `mos_exp_*` only.

## Procedure

1. **(Optional) Dry-run the placement.** For sweeps of ≥4 units or for any plan you're unsure will spread, call `mos_exp_queue_plan(units=[...])` first. It returns per-unit `(target, gpu_ids, reserve_mb)` or a `blocked` reason against the live GPU snapshot, with no DB writes. If the dry-run shows pile-ups or unexpected blocks, return to `allocate-resources` to adjust constraints rather than submitting blindly.
2. **Stage inputs.** For each unit the plan flagged `needs_staging: true`, run `mos_exp_put(target_id, src, dst)` before submission. Skip if already staged.
3. **Submit all units.** `mos_exp_queue_submit(units=[...])`; include `reserve_mb` / `min_free_mb` from the plan.
4. **Reflect on placement.** Read the `reconcile.placement` block in the response: `by_gpu` (current physical distribution), `blocked_reasons` (`no_capacity` / `target_pin` / `explicit_gpu`), and `skew_warning`. If `skew_warning` is non-empty, do not silently move on — return to `allocate-resources` for a constraint adjustment (e.g. tighter `gpus_needed`, explicit `target_id` spread, smaller `reserve_mb` if over-padded). If `blocked_reasons.target_pin` or `explicit_gpu` are non-zero and unexpected, surface that to the requester via EACN.
5. **Record the batch id.** Persist `{batch_id, unit_ids}` plus the placement summary via `mos_dag_append` or the requester-facing note so later wake-ups can call `mos_exp_queue_status`.
6. **Do not block.** Never follow queue submission with long `mos_exp_wait`; Python reconciles and tracks detached runs.
7. **Delegate heavy per-unit execution prep to a subagent** when a unit requires non-trivial scripting, data massage, or config expansion. Subagents have `mos_exp_*` only; they must not inherit `eacn3_*`.
8. **Broadcast a short EACN handoff** listing the batch id, currently launched units, pending count, and any non-empty placement signals so Noter / requester know jobs are alive: `{batch_id, submitted, launched_now, pending, skew_warning?, blocked_reasons?}` plus a pointer to status / report artifacts.

## Pitfalls

- Re-doing `allocate-resources`'s planning here. If the plan is wrong, return to `allocate-resources` rather than mutating units in-place at submit time.
- Ignoring a non-empty `skew_warning`. The Python scheduler's spread-first tie-break is best-effort; a non-empty warning means it is fighting your unit shape and a constraint change is needed upstream.
- Reaching for `mos_exp_wait(timeout=3600)` out of habit. This is explicitly banned as a default primitive (§Fire-and-poll).
- Forgetting to persist `batch_id` before the ephemeral session exits — detached jobs survive, your memory does not.
- Starting a subagent that inherits `eacn3_*`. Subagents must not; the whitelist enforces this.
- Calling `mos_exp_gpu_pool_set` here to "fix" a pool issue. Pool policy belongs to `allocate-resources` (or to the user via `triage-request`); changing it at submit time hides the policy decision from the plan record.
- Treating `mos_exp_queue_plan` as a substitute for submission. It is a dry-run only — nothing is queued until step 3.
