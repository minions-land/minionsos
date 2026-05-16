---
slug: allocate-resources
summary: Translate an accepted experiment request into queue-ready unit specs — decide unit boundaries, constraints, estimates, and SIGTERM checkpoint contract, then hand the spec to dispatch-runner. Never calls mos_exp_queue_submit.
layer: logical
tools: mos_exp_gpu_pool_set
version: 4
status: active
supersedes:
references: triage-request, dispatch-runner, track-run
provenance: human
---

# Skill — Allocate Resources

Turn an accepted request into a queue-ready plan. You decide units, constraints, estimates, resource policy, and the SIGTERM checkpoint contract. The Python scheduler later decides exact GPU placement; `dispatch-runner` performs the actual submission. This skill produces a spec, not a queue record.

## When to invoke

- Immediately after `triage-request` returns `accept` for a non-trivial request.
- When a sweep or multi-seed batch would otherwise be launched serially by reflex.
- When several small accepted requests could share a target efficiently.

## Structure

Output is a **plan**: a list of unit specs plus any resource-policy changes the plan needs. Each unit spec is `{command, target_id?, gpu_ids?, gpus_needed, min_free_mb?, reserve_mb?, expected_wallclock, input_paths, output_paths, needs_staging?}`. Artifact destinations are planned upfront under `artifacts/exp-{id}/` so `collect-report` can find them. The plan is consumed by `dispatch-runner`, which calls `mos_exp_queue_submit` and (if `needs_staging`) `mos_exp_put`.

## Procedure

1. **Size the work.** Per unit: command, `target_id` constraint, optional `gpu_ids`, `gpus_needed`, `min_free_mb`, `reserve_mb`, expected wallclock, input / output paths.
2. **Respect pins.** Honour explicit target / GPU constraints from the request.
3. **Adjust the GPU pool if policy changed.** If the user changed allowed GPUs, call `mos_exp_gpu_pool_set` now — the pool is the resource frame the queue runs against, and it must be correct before `dispatch-runner` submits. This is the only side effect this skill performs. Two modes:
   - **Drain** (`evict=False`, default): in-flight runs on removed GPUs keep going; only new placements are blocked. Use when the operator says "I'll need these cards, but only after current jobs finish."
   - **Evict** (`evict=True`): SIGTERM runs on removed GPUs and reset their units to `pending` so they re-launch on remaining allowed GPUs. Use when the operator says "I need these cards back NOW." Eviction does not burn the OOM retry budget. Requires the unit's command to honour SIGTERM (see step 4).
4. **Lock in the SIGTERM checkpoint contract.** Every command that holds non-trivial GPU state must trap SIGTERM, save the latest checkpoint, and exit cleanly. The evict path sends SIGTERM to the whole process group, so a trap on the inner shell or a Python `signal.SIGTERM` handler both work. A safe default for sweep scripts:
   - bash: `trap 'python3 save_checkpoint.py && exit 0' TERM` before the long-running command
   - python: register `signal.signal(signal.SIGTERM, lambda *_: save_and_exit())` early
   Without this contract, `evict` is destructive — the operator gets the cards back but loses the partial training.
5. **Flag input staging.** If a unit's data is not already on its target, mark `needs_staging: true` with the source / destination paths. Do not call `mos_exp_put` here — `dispatch-runner` will run it before submission.
6. **Record artifact slots.** Each unit has a planned destination under `artifacts/exp-{id}/` or an equivalent batch artifact directory.
7. **Hand off to dispatch-runner.** Emit the plan: unit list, pool changes (if any), staging flags, artifact slots, and a one-line note saying which units are SIGTERM-safe. Mark tool facts `[derived: allocate-resources plan @ <ts>]`. Do not call `mos_exp_queue_submit` — that is `dispatch-runner`'s job.

## Pitfalls

- Calling `mos_exp_queue_submit` inside this skill. Submission is `dispatch-runner`'s exclusive responsibility — calling it here causes double-submit when the chain runs end-to-end.
- Calling `mos_exp_put` here. Input staging is a side effect that belongs with submission, so it stays on `dispatch-runner`'s side of the boundary.
- Choosing `evict=True` for a command that does not trap SIGTERM. Eviction will then lose state — confirm the trap exists or downgrade to `evict=False` and tell the operator the cards will free up only after the current run completes.
- Planning serial launches because parallel feels risky — serial kills throughput and violates fire-and-poll.
- Manually assigning GPUs in the plan. The scheduler owns placement; you decide constraints, not placements.
- Submitting units without `reserve_mb` when you already know the approximate VRAM need.
- Padding VRAM estimates by 2×. Leave headroom, but not so much that GPUs sit half-empty.
- Treating `gpus_needed: 1` as "one run per target." It is per-GPU — a 4-GPU host absorbs 4 independent units.
