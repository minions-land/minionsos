# Skill — Allocate Resources

Translate an accepted experiment request into queue units for the Python fluid-GPU scheduler.

## Core move

Decide the unit boundaries, constraints, and resource estimates, then hand them to `exp_queue_submit`. Python decides the exact GPU placement and later queue migration.

## Procedure

1. **Size the work.** Per unit: command, `target_id` constraint, optional `gpu_ids`, `gpus_needed`, `min_free_mb`, `reserve_mb`, expected wallclock, input/output paths.
2. **Respect pins.** Honour explicit target/GPU constraints from the request. If the user changes allowed GPUs, call `exp_gpu_pool_set` before submitting or reconciling.
3. **Submit, don't hand-pack.** Call `exp_queue_submit` with all units. Batches are labels; new requests merge into the project-global pending pool automatically.
4. **Let Python migrate pending work.** Do not bind queued units to a specific GPU in scratchpad. If any allowed GPU frees up, `exp_queue_reconcile` can place the next pending unit there.
5. **Pre-stage inputs.** If data needs to land on a target first, schedule an `exp_put` or remote download step before queue submission.
6. **Record artifact slots.** Each unit should have a planned destination under `artifacts/exp-{id}/` or an equivalent batch artifact directory so later collection is trivial.

## When to invoke

- Immediately after `triage-request` returns `accept` for a non-trivial request.
- When a sweep or multi-seed batch would otherwise be launched serially by reflex.
- When several small accepted requests could share a target efficiently.

## Pitfalls

- Planning serial launches because planning parallel launches feels risky — serial kills throughput and violates fire-and-poll.
- Manually assigning GPUs after queue submission. The scheduler owns placement.
- Submitting units without `reserve_mb` when you already know the approximate VRAM need.
- Padding VRAM estimates by 2×. Leave headroom, but not so much that GPUs sit half-empty.
- Treating `gpus_needed: 1` as "one run per target." Per-GPU, not per-target — a 4-GPU host should be able to absorb 4 independent units.

## Output habit

Emit a queue record: batch id, unit ids, constraints, reserve estimates, and artifact destinations. Mark tool facts `[derived: exp_queue_submit @ <ts>]` per root §9.
