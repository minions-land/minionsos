# Skill — Collect Report

Turn a completed run's raw outputs into a structured result bundle under `artifacts/exp-{id}/`.

## Core move

Assemble the operational record of one run — request, execution facts, metrics, artifacts, failures — into `artifacts/exp-{id}/report.md` so Expert, Noter, Writer, and future Experimenter invocations can consume it without re-reading logs.

## Procedure

1. **Fetch results.** Use `exp_get` for files ≤ 500 MB (metrics CSVs, small checkpoints, log excerpts). Leave larger outputs on the remote target and record their remote path — never pull > 500 MB locally (`SYSTEM.md`).
2. **Populate the bundle directory.** `artifacts/exp-{id}/` should contain: `report.md`, pulled log excerpts, metrics files, and a `remote_paths.txt` for anything left on the target.
3. **Write `report.md`** with the format fixed by `SYSTEM.md`: request, execution plan, run status, wallclock, GPU usage, metrics, artifact list, failures, reproducibility note, pending issues, suggested next actions.
4. **Separate fact from interpretation.** Operational facts (status, timing, metrics as emitted) go in the report body. Light interpretation (e.g. "loss plateau suggests LR too low") is permitted but must be flagged and left to Expert for final judgment.
5. **Announce on EACN.** One-line reply pointing to `artifacts/exp-{id}/report.md` plus a terse summary (status + headline metric). Do not paste the whole report into EACN.
6. **Close the run's tracking entry.** Mark the `run_id` as `collected` in your per-invocation tracking note so `track-run` stops polling it.

## When to invoke

- As soon as `exp_status` reports a terminal state (completed / failed / killed) for a tracked run.
- Before dispatching any follow-up experiment that depends on this run's outputs.

## Pitfalls

- Over-interpreting the science. Report, don't adjudicate — that's Expert's job.
- Hiding failed runs because they are embarrassing. Failures that teach something must be preserved.
- Dumping raw logs as the "report." The report exists precisely so readers do not need the raw logs.

## Output habit

`artifacts/exp-{id}/report.md` is authoritative; all metric claims in it are marked `[derived: run_id=<id> metrics.csv@<ts>]` per root §9. EACN reply is one line: status, headline metric, and the report path.
