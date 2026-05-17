---
slug: archive-execution
summary: Preserve reusable operational knowledge — templates, scheduling lessons, failure patterns — beyond a single run, in a form future Experimenter invocations can find and apply.
layer: logical
tools: mos_publish_to_shared
version: 2
status: active
supersedes:
references: collect-report
provenance: human
---

# Skill — Archive Execution

Distill the reusable part of a matured run — a reproducible recipe, a recurring failure pattern — into a short artifact future Experimenter invocations can find and apply.

## When to invoke

- After a run succeeds in a way that will clearly be repeated (sweeps, seed replays, ablation families).
- After a circuit-broken failure (3 consecutive same-script failures) once the root cause is known.
- When no runs are in flight and at least 2 prior runs share a pattern that was never captured.

## Structure

Reusable templates and lessons are staged under `branches/experimenter/exp/templates/` and published to `branches/shared/exp/templates/` via `mos_publish_to_shared`. Per-run bundles stay in `branches/shared/exp/exp-<id>/` and are not moved. Each archive entry is terse and operational: trigger (when this applies), recipe (scripts / env / `gpus_needed` / expected wallclock), pitfalls, pointers to the canonical reference `exp-{id}`. Failure notes follow the same shape: symptom, root cause, fix or workaround, canonical `exp-{id}`.

## Procedure

1. **Decide what is reusable.** A one-off flaky run is not reusable; a reproducible recipe is, and so is a recurring failure mode. Err toward terse capture of recurring patterns.
2. **Pick the archive location.** Draft at `branches/experimenter/exp/templates/<slug>.md`; publish to `branches/shared/exp/templates/<slug>.md`. Per-run bundles stay in `branches/shared/exp/exp-<id>/` — do not move them.
3. **Write the entry tight.** Trigger (when this applies), recipe (scripts / env / `gpus_needed` / expected wallclock), pitfalls, pointers to the best reference `exp-{id}`.
4. **Capture failure cases too.** Symptom, root cause, fix or workaround, `exp-{id}` of the canonical occurrence — prevents re-paying the debugging cost.
5. **Link from `report.md`.** Add a pointer in the originating report to the archived template so the connection is bidirectional.
6. **Announce once on EACN** so Noter can pick it up for the project log. Do not re-announce every time the template is reused.

## Pitfalls

- Archiving everything. Most runs should not produce a template; the signal is in selectivity.
- Turning archives into a second paper. Keep entries operational, not narrative.
- Silently rewriting an old archived template. Version or date-tag updates so reproducibility is preserved.
