---
slug: allocate-resources
summary: Translate an accepted experiment request into queue-ready unit specs — decide unit boundaries, constraints, and estimates, then hand the spec to dispatch-runner. Never calls exp_queue_submit.
layer: logical
tools: exp_gpu_pool_set
version: 3
status: active
supersedes:
references: triage-request, dispatch-runner, track-run
provenance: human
---

# Skill — Allocate Resources

Turn an accepted request into a queue-ready plan. You decide units, constraints, estimates, and resource policy. The Python scheduler later decides exact GPU placement; `dispatch-runner` performs the actual submission. This skill produces a spec, not a queue record.

## When to invoke

- Immediately after `triage-request` returns `accept` for a non-trivial request.
- When a sweep or multi-seed batch would otherwise be launched serially by reflex.
- When several small accepted requests could share a target efficiently.

## Structure

Output is a **plan**: a list of unit specs plus any resource-policy changes the plan needs. Each unit spec is `{command, target_id?, gpu_ids?, gpus_needed, min_free_mb?, reserve_mb?, expected_wallclock, input_paths, output_paths, needs_staging?}`. Artifact destinations are planned upfront under `artifacts/exp-{id}/` so `collect-report` can find them. The plan is consumed by `dispatch-runner`, which calls `exp_queue_submit` and (if `needs_staging`) `exp_put`.

## Procedure

1. **Size the work.** Per unit: command, `target_id` constraint, optional `gpu_ids`, `gpus_needed`, `min_free_mb`, `reserve_mb`, expected wallclock, input / output paths.
2. **Respect pins.** Honour explicit target / GPU constraints from the request.
3. **Adjust the GPU pool if policy changed.** If the user changed allowed GPUs, call `exp_gpu_pool_set` now — the pool is the resource frame the queue runs against, and it must be correct before `dispatch-runner` submits. This is the only side effect this skill performs.
4. **Flag input staging.** If a unit's data is not already on its target, mark `needs_staging: true` with the source / destination paths. Do not call `exp_put` here — `dispatch-runner` will run it before submission.
5. **Record artifact slots.** Each unit has a planned destination under `artifacts/exp-{id}/` or an equivalent batch artifact directory.
6. **Hand off to dispatch-runner.** Emit the plan: unit list, pool changes (if any), staging flags, artifact slots. Mark tool facts `[derived: allocate-resources plan @ <ts>]`. Do not call `exp_queue_submit` — that is `dispatch-runner`'s job.

## Pitfalls

- Calling `exp_queue_submit` inside this skill. Submission is `dispatch-runner`'s exclusive responsibility — calling it here causes double-submit when the chain runs end-to-end.
- Calling `exp_put` here. Input staging is a side effect that belongs with submission, so it stays on `dispatch-runner`'s side of the boundary.
- Planning serial launches because parallel feels risky — serial kills throughput and violates fire-and-poll.
- Manually assigning GPUs in the plan. The scheduler owns placement; you decide constraints, not placements.
- Submitting units without `reserve_mb` when you already know the approximate VRAM need.
- Padding VRAM estimates by 2×. Leave headroom, but not so much that GPUs sit half-empty.
- Treating `gpus_needed: 1` as "one run per target." It is per-GPU — a 4-GPU host absorbs 4 independent units.
