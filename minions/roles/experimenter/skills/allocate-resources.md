# Skill — Allocate Resources

Translate an accepted experiment request into a concrete resource plan that respects the fill-GPU policy.

## Core move

Decide **where** each launchable unit of work will run and **when** each queued unit can start, so `dispatch-runner` can fire everything launchable in parallel without re-deciding anything.

## Procedure

1. **Refresh visibility.** Call `query_gpus` on every configured target so your free-VRAM picture is < 1 minute old. Cross-reference with `exp_list` to know which GPUs already host a MinionsOS run (vs. foreign processes).
2. **Size the work.** Per unit: VRAM floor, CPU/RAM estimate, expected wallclock, input/output data paths, output artifact destination under `artifacts/exp-{id}/`.
3. **Assign with spread-first ordering (mandatory).** For each pending unit, pick its `(target_id, gpu_id)` by this ranked rule, applied over the **union of all configured targets** (local + ssh alike — the fleet is one pool):
   0. **Place multi-GPU units (`gpus_needed ≥ 2`) first**, as contiguous N-GPU reservations on a single target. Otherwise the spread below fragments the fleet and leaves no room for them.
   1. Prefer a GPU that is a **fresh slot** = no MinionsOS run per `exp_list` **AND** `free_mb ≥ unit_vram_floor + headroom`. A GPU with low `free_mb` because a *foreign* process occupies it is **not** fresh.
   2. Among fresh slots, prefer the one with the **largest `free_mb`**.
   3. Tiebreaker: **data locality** — prefer the target where inputs already live (avoids `exp_put`).
   4. Only when every eligible GPU in the fleet already has ≥1 MinionsOS run, stack a second run onto an already-busy GPU. Keep ≥10–15% VRAM headroom and cap MinionsOS runs per GPU at ~3.
   This is the **fill-GPU-spread-first policy** from `SYSTEM.md` §Scheduling. Piling N units onto GPU 0 while GPUs 1..k idle is a scheduling bug, even if GPU 0's VRAM nominally fits them all.
4. **Respect pins.** Honour explicit `target_id` / `gpu_id` / `gpus_needed: N` from the request; spread-first applies within the remaining free choices.
5. **Order the queue.** Units that fit now go in `launch_now` with explicit `(target_id, gpu_id)` assignments. Units that cannot land without violating rule 3 go in `queued` with an explicit gate (VRAM drain / upstream `run_id`).
6. **Pre-stage inputs.** If data needs to land on a target first, schedule an `exp_put` or remote download step before the first `exp_run`.
7. **Record `exp-{id}` slots.** Each unit gets a deterministic `artifacts/exp-{id}/` directory reserved for its bundle so later collection is trivial.

## When to invoke

- Immediately after `triage-request` returns `accept` for a non-trivial request.
- When a sweep or multi-seed batch would otherwise be launched serially by reflex.
- When several small accepted requests could share a target efficiently.

## Pitfalls

- Planning serial launches because planning parallel launches feels risky — serial kills throughput and violates fire-and-poll.
- **Stacking all units onto the first GPU that fits them.** Spread-first is the rule: empty GPUs must get a run before any GPU gets a second run.
- Relying on stale GPU state. Re-poll if the plan takes longer than ~1 minute to produce.
- Padding VRAM estimates by 2×. Leave headroom, but not so much that GPUs sit half-empty.
- Treating `gpus_needed: 1` as "one run per target." Per-GPU, not per-target — a 4-GPU host should be able to absorb 4 independent units.

## Output habit

Emit a plan record (kept in-message or written under `artifacts/exp-{id}/plan.md`): `launch_now` list, `queued` list with gates, target assignments, expected wallclocks, artifact destinations. Mark VRAM / availability facts `[derived: query_gpus @ <ts>]` per root §9.
