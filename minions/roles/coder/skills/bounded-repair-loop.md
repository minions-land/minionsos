# Skill — Bounded Repair Loop

Iterate on a failing local check in a controlled loop with a fixed stop condition.

## Core move

Use a short diagnose-fix-verify loop when a concrete command fails and the fix is
within Coder's local scope. This is the MinionsOS-safe version of an autonomous
repair loop: bounded, observable, and never open-ended.

## Procedure

1. **Name the failing check.** Record the exact command, failure summary, and the
   file or behavior it is meant to validate.
2. **Set a bound before editing.** Default to 3 iterations for focused failures
   and 5 only when the failure is deterministic and cheap. Do not run unbounded
   loops.
3. **Diagnose before each edit.** Read the relevant traceback, log, or assertion.
   Identify the most likely root cause before touching code.
4. **Apply one coherent fix per iteration.** Keep each edit small enough that the
   next failure can still be attributed to a specific change.
5. **Rerun the same check.** If it passes, optionally run one adjacent fast check
   for confidence. If it fails differently, start the next iteration from the new
   evidence.
6. **Stop cleanly.** Stop on pass, bound exhaustion, unclear ownership, missing
   dependency, or when the next step would require heavy experiments.

## When to invoke

- A unit test, smoke test, type check, or small CLI sanity check fails
  deterministically.
- A role request asks Coder to "make this pass" and provides a concrete command.
- A previous implementation handoff included a local verification failure.

## Pitfalls

- Treating this as permission to keep editing indefinitely.
- Changing unrelated code to make a test pass.
- Running GPU jobs, large data pipelines, or experiment sweeps; those belong to
  Experimenter.
- Hiding a failure by loosening assertions, swallowing errors, or deleting
  verification.

## Output habit

Report the command, iteration count, final status, changed paths, and the final
failure if unresolved. If blocked, send an EACN note with the smallest missing
input needed to continue.
