---
slug: collect-report
summary: Turn a completed run's raw outputs into a staged result bundle and publish it under branches/shared/exp/exp-<id>/ — request, execution facts, metrics, artifacts, failures.
layer: logical
tools: mos_exp_get, mos_publish_to_shared
version: 2
status: active
supersedes:
references: track-run, archive-execution
provenance: human
---

# Skill — Collect Report

Assemble the operational record of one run so Expert, Noter, Writer, and future Experimenter invocations can consume it without re-reading logs.

## When to invoke

- As soon as `mos_exp_status` reports a terminal state (completed / failed / killed) for a tracked run.
- Before dispatching any follow-up experiment that depends on this run's outputs.

## Structure

Stage the bundle under `branches/experimenter/exp/exp-<id>/`, then publish completed files to `branches/shared/exp/exp-<id>/` via `mos_publish_to_shared`. The bundle contains: `report.md`, pulled log excerpts, metrics files, and `remote_paths.txt` for anything left on the target. `report.md` follows the format fixed by `SYSTEM.md`: request, execution plan, run status, wallclock, GPU usage, metrics, artifact list, failures, reproducibility note, pending issues, suggested next actions. Operational facts go in the body; light interpretation is permitted but flagged and left to Expert for final judgment.

## Procedure

1. **Fetch results.** `mos_exp_get` for files ≤ 500 MB (metrics CSVs, small checkpoints, log excerpts). Larger outputs stay on the remote target — record their remote path. Never pull > 500 MB locally.
2. **Populate the staged bundle directory.** `branches/experimenter/exp/exp-<id>/` contains `report.md`, pulled log excerpts, metrics files, `remote_paths.txt`.
3. **Write `report.md`.** Format per `SYSTEM.md`: request, execution plan, run status, wallclock, GPU usage, metrics, artifact list, failures, reproducibility note, pending issues, suggested next actions.
4. **Separate fact from interpretation.** Operational facts (status, timing, metrics as emitted) in the body. Light interpretation (e.g. "loss plateau suggests LR too low") permitted but flagged and left to Expert.
5. **Publish completed files.** Use `mos_publish_to_shared` for each finished bundle file, with destinations under `exp/exp-<id>/`.
6. **Announce on EACN.** One-line reply pointing to `branches/shared/exp/exp-<id>/report.md` plus a terse summary (status + headline metric). Do not paste the whole report.
7. **Close the run's tracking entry.** Mark the `run_id` as `collected` in your per-invocation tracking note so `track-run` stops polling it. All metric claims in `report.md` are marked `[derived: run_id=<id> metrics.csv@<ts>]`.

## Pitfalls

- Over-interpreting the science. Report, do not adjudicate — that is Expert's job.
- Hiding failed runs because they are embarrassing. Failures that teach something must be preserved.
- Dumping raw logs as the "report." The report exists precisely so readers do not need the raw logs.
