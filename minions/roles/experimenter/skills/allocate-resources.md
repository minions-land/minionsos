---
slug: allocate-resources
summary: Translate an accepted experiment request into queue units for the Python fluid-GPU scheduler; decide unit boundaries, constraints, and resource estimates, then hand them to exp_queue_submit.
layer: logical
tools: exp_queue_submit, exp_queue_reconcile, exp_gpu_pool_set, exp_put
version: 2
status: active
supersedes:
references: triage-request, dispatch-runner, track-run
provenance: human
---

# Skill — Allocate Resources

Turn an accepted request into queue units. Python decides exact GPU placement and later queue migration — you decide the units, constraints, and estimates.

## When to invoke

- Immediately after `triage-request` returns `accept` for a non-trivial request.
- When a sweep or multi-seed batch would otherwise be launched serially by reflex.
- When several small accepted requests could share a target efficiently.

## Structure

Each unit is `{command, target_id?, gpu_ids?, gpus_needed, min_free_mb?, reserve_mb?, expected_wallclock, input_paths, output_paths}`. Artifact destinations are planned upfront under `artifacts/exp-{id}/` so collection is trivial. Input staging (e.g. `exp_put`) happens before queue submission if data is not already on the target.

## Procedure

1. **Size the work.** Per unit: command, `target_id` constraint, optional `gpu_ids`, `gpus_needed`, `min_free_mb`, `reserve_mb`, expected wallclock, input / output paths.
2. **Respect pins.** Honour explicit target / GPU constraints from the request. If the user changes allowed GPUs, call `exp_gpu_pool_set` before submitting or reconciling.
3. **Submit, don't hand-pack.** Call `exp_queue_submit` with all units. Batches are labels; new requests merge into the project-global pending pool automatically.
4. **Let Python migrate pending work.** Do not bind queued units to a specific GPU in scratchpad. If any allowed GPU frees up, `exp_queue_reconcile` can place the next pending unit there.
5. **Pre-stage inputs.** If data needs to land on a target first, schedule an `exp_put` or remote download step before queue submission.
6. **Record artifact slots.** Each unit has a planned destination under `artifacts/exp-{id}/` or an equivalent batch artifact directory.
7. **Emit a queue record.** Batch id, unit ids, constraints, reserve estimates, artifact destinations. Mark tool facts `[derived: exp_queue_submit @ <ts>]`.

## Pitfalls

- Planning serial launches because parallel feels risky — serial kills throughput and violates fire-and-poll.
- Manually assigning GPUs after queue submission. The scheduler owns placement.
- Submitting units without `reserve_mb` when you already know the approximate VRAM need.
- Padding VRAM estimates by 2×. Leave headroom, but not so much that GPUs sit half-empty.
- Treating `gpus_needed: 1` as "one run per target." It is per-GPU — a 4-GPU host absorbs 4 independent units.
