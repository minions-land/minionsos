# Skill — Archive Execution

Preserve reusable operational knowledge — templates, scheduling lessons, failure patterns — beyond a single run.

## Core move

When a run matures (succeeds in a way worth repeating, or fails in a way worth remembering), distill the reusable part into a short artifact future Experimenter invocations can actually find and apply.

## Procedure

1. **Decide what is reusable.** A one-off flaky run is not reusable knowledge; a reproducible recipe is, and so is a failure mode that will recur. Err toward terse capture of recurring patterns.
2. **Pick the archive location.** Reusable templates and lessons live under `artifacts/exp-templates/` or a clearly named note under `branches/experimenter/experiments/notes/`. Per-run bundles stay in `artifacts/exp-{id}/`; don't move them.
3. **Write the entry tight.** Template: trigger (when this applies), recipe (scripts / env / gpus_needed / expected wallclock), pitfalls, pointers to the best reference `exp-{id}`.
4. **Capture failure cases too.** A short failure note (symptom, root cause, fix or workaround, `exp-{id}` of the canonical occurrence) prevents the team from re-paying the debugging cost.
5. **Link from `report.md`.** In the originating report, add a pointer to the archived template so the connection is bidirectional.
6. **Announce once on EACN** so Noter can pick it up for the project log. Do not re-announce every time the template is reused.

## When to invoke

- After a run succeeds in a way that will clearly be repeated (sweeps, seed replays, ablation families).
- After a circuit-broken failure (3 consecutive same-script failures) once the root cause is known.
- On idle time, when prior runs reveal a pattern that was never captured.

## Pitfalls

- Archiving everything. Most runs should not produce a template; the signal is in selectivity.
- Turning archives into a second paper. Keep entries operational, not narrative.
- Silently rewriting an old archived template. Version or date-tag updates so reproducibility is preserved.

## Output habit

A short markdown file under `artifacts/exp-templates/` or `branches/experimenter/experiments/notes/`, with bidirectional pointer to the canonical `exp-{id}`. EACN announcement is one line.
