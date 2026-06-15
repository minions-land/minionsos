---
slug: bounded-repair-loop
summary: Iterate on a failing local check in a controlled diagnose-fix-verify loop with a fixed iteration bound; the MinionsOS-safe form of an autonomous repair loop.
layer: logical
tools:
version: 3
status: active
supersedes:
references: feature-implementation
provenance: human
---

# Skill — Bounded Repair Loop

The MinionsOS-safe form of an autonomous repair loop: bounded, observable, never open-ended.

## When to invoke

- A unit test, smoke test, type check, or small CLI sanity check fails deterministically.
- A role request asks Expert to "make this pass" with a concrete command.
- A previous implementation handoff included a local verification failure.

If the failure requires GPU jobs, large data pipelines, or experiment sweeps, do not run this loop — submit those to the experiment queue instead (see `run-experiments` skill).

## Structure

A short diagnose-fix-verify loop with three hard gates: a named failing command, an iteration bound set before any edit, and a clean stop condition. Every iteration produces evidence (the rerun output) that feeds the next iteration's diagnosis.

## Procedure

1. **Name the failing check.** Record the exact command, failure summary, and the file or behavior it is meant to validate.
2. **Set a bound before editing.** Default to 3 iterations for focused failures and 5 only when the failure is deterministic and cheap. Do not run unbounded loops.
3. **Diagnose before each edit.** Read the relevant traceback, log, or assertion. Identify the most likely root cause before touching code.
4. **Apply one coherent fix per iteration.** Keep each edit small enough that the next failure can still be attributed to a specific change. For code edits, apply SYSTEM.md §4 Stage 1 code quality gate (ruff check, ty check, pytest).
5. **Rerun the same check.** If it passes, optionally run one adjacent fast check for confidence. If it fails differently, start the next iteration from the new evidence.
6. **Stop cleanly.** Stop on pass, bound exhaustion, unclear ownership, missing dependency, or when the next step would require heavy experiments.
7. **Report.** Command, iteration count, final status, changed paths, final failure if unresolved. If blocked, send an EACN note with the smallest missing input needed to continue.

## Pitfalls

- Resetting the iteration counter after a partial pass to "give it one more try" — the bound exists precisely to prevent this drift; if 3 attempts did not pass, the next attempt almost certainly will not either.
- Changing unrelated code to make a test pass.
- Running GPU jobs, large data pipelines, or experiment sweeps inline; submit those to the experiment queue.
- Hiding a failure by loosening assertions, swallowing errors, or deleting verification.
