# Skill — Execution Guide

A disciplined, minimal, goal-driven stance for any hands-on experiment work — whether you do it yourself or dispatch it to a subagent.

## Core move

Before writing or running anything, state the assumptions, pick the minimum viable approach, and define verifiable per-step success criteria. Then execute surgically; do not expand scope.

## Procedure

1. **Think before coding.** Name your assumptions. If the request has multiple reasonable interpretations, surface them on EACN instead of silently picking one. If something is unclear, stop and ask rather than guess.
2. **Simplicity first.** Use the minimum code, config, and operational work needed for the assigned slice. No speculative features, no abstractions for one-off work, no extra configurability unless requested.
3. **Surgical changes.** Touch only what the slice requires. Do not refactor unrelated nearby code; do not "improve" adjacent scripts. Match local style; clean up only the orphans your own change created.
4. **Goal-driven steps.** Write a short plan where every step pairs with a concrete verification: `1. step → verify: check`. "Make it work" is too weak; replace with a pass/fail signal (metric threshold, file existence, exit code, log pattern).
5. **Respect the Experimenter/sub-agent split.** If you are the Experimenter main, dispatch non-trivial implementation to a subagent (root §7) with a tight slice and an artifact destination under `artifacts/exp-{id}/`. If you are the subagent, stay inside your assigned slice — do not reshape the scientific scope or take over scheduling decisions.
6. **Escalate clearly.** Blockers → EACN upward with the exact failing step and the verification that didn't pass. No silent retries that hide real problems.

## When to invoke

- Before any non-trivial `exp_run` batch or subagent dispatch.
- When a request is ambiguous enough that the first honest step is "name the ambiguity."
- When tempted to "just refactor this quickly while I'm here."

## Pitfalls

- Confusing progress with motion: code written ≠ assumptions verified.
- Treating the plan as a formality. Weak verifications produce confidently-wrong results.
- Silently expanding scope because the neighbouring code is ugly.

## Output habit

Hand back (to EACN or the dispatching agent): assumptions stated, steps taken with per-step verification results, artifacts produced with paths, blockers. Mark any claim derived from a specific log or metric `[derived: <source>]` per root §9.
