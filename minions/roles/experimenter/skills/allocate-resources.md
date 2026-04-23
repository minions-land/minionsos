# Skill — Allocate Resources

Translate an accepted experiment request into a concrete resource plan that respects the fill-GPU policy.

## Core move

Decide **where** each launchable unit of work will run and **when** each queued unit can start, so `dispatch-runner` can fire everything launchable in parallel without re-deciding anything.

## Procedure

1. **Refresh visibility.** Call `query_gpus` on every configured target so your free-VRAM picture is < 1 minute old.
2. **Size the work.** Per unit: VRAM floor, CPU/RAM estimate, expected wallclock, input/output data paths, output artifact destination under `artifacts/exp-{id}/`.
3. **Assign to targets.** Prefer `target=auto` unless the request pins a `target_id`. Respect `gpus_needed: N` (default 1). Pack multiple small jobs per target when VRAM permits — fill-GPU is mandatory (see root §6, `SYSTEM.md` Fire-and-poll).
4. **Order the queue.** Units that fit now go in the `launch_now` list. Units waiting on VRAM or on an upstream `run_id` go in `queued` with an explicit gate.
5. **Pre-stage inputs.** If data needs to land on a target first, schedule an `exp_put` or remote download step before the first `exp_run`.
6. **Record `exp-{id}` slots.** Each unit gets a deterministic `artifacts/exp-{id}/` directory reserved for its bundle so later collection is trivial.

## When to invoke

- Immediately after `triage-request` returns `accept` for a non-trivial request.
- When a sweep or multi-seed batch would otherwise be launched serially by reflex.
- When several small accepted requests could share a target efficiently.

## Pitfalls

- Planning serial launches because planning parallel launches feels risky — serial kills throughput and violates fire-and-poll.
- Relying on stale GPU state. Re-poll if the plan takes longer than ~1 minute to produce.
- Padding VRAM estimates by 2×. Leave headroom, but not so much that GPUs sit half-empty.

## Output habit

Emit a plan record (kept in-message or written under `artifacts/exp-{id}/plan.md`): `launch_now` list, `queued` list with gates, target assignments, expected wallclocks, artifact destinations. Mark VRAM / availability facts `[derived: query_gpus @ <ts>]` per root §9.
