---
slug: coding-methodology
summary: Three-phase coding pipeline — Plan → Review → Simplify — each gated by a fixed smoke test. Open before any change that touches shared state, public APIs, lifecycle, or ≥2 files, or adds any new public function or class.
layer: logical
tools:
version: 2
status: active
supersedes: coding-discipline, change-review, simplify-changes
references: bounded-repair-loop, feature-implementation, test-coverage-review
provenance: human
---

# Skill — Coding Methodology

Three sequential phases for writing code that works and stays clean. Each phase has an exit gate: the same fixed smoke test. Do not advance to the next phase until the gate passes.

## When to invoke

By default, run all three phases (Plan → Review → Simplify) for any non-trivial code change. The phases are the methodology — not optional checkpoints. Use the triggers below to decide whether the *whole methodology* applies; once it does, do all three phases unless the user explicitly limits scope.

- Run when: the change touches shared state, public APIs, lifecycle, or more than one file.
- Run when: the edit changes more than 20 lines in one module.
- Run when: you are about to dispatch a non-trivial subagent.
- Run when: you are tempted to "just refactor this quickly while I'm here."
- Run when: the request has multiple reasonable interpretations.

Skip for single-file, single-function edits with no caller impact: comment fixes, typo corrections, isolated one-line bug fixes.

**User intent wins.** If the user has explicitly asked you to stop at a specific stage (e.g. "just implement, don't clean up", "just review the diff, don't change anything"), respect that. Phase 3 is *available* whenever the threshold is met, but only run it when the implementation is accepted or cleanup was requested. Do not auto-launch cleanup the user did not ask for.

## Gate (same for all phases)

```bash
ruff check <changed_paths>
ruff format --check <changed_paths>
ty check <package>          # or mypy / pyright if the project uses those
pytest tests/unit/ -q       # the fast local suite
```

All four must pass. If any fails, fix before advancing. GPU-based or integration tests are out of scope for this gate — they belong to Experimenter.

**Fail loud, don't fail silent.** "Gate passes" means every command above ran end-to-end and reported green. A skipped test, a tool that wasn't installed, a command you didn't run, a check that timed out — none of these count as passing. If any check could not be run, name which one and why in the same message that reports the gate result. "Tests pass" while you only ran one of the four commands is wrong.

## Procedure

The three phases run in order. Each phase's exit gate is the smoke test above. Do not advance until it passes.

### Phase 1 — Plan (Karpathy Discipline)

Decide how to write the code before writing it.

1. **Read the territory first.** Before stating any assumption, read the file you'll touch (its exports, its callers, its shared utilities). If you don't understand why nearby code is structured the way it is, that is the first thing to ask. "Looks orthogonal" is the most expensive phrase in this codebase — duplicate helpers, conflicting state writers, and double-handled errors all start there. The depth is proportional to the change: a one-line patch reads the function; a cross-module change reads the immediate callers and any shared helper module.
2. **Surface assumptions.** State them explicitly. Uncertain → ask. Multiple interpretations → present them; do not pick silently.
3. **Choose the simplest approach.** No features beyond what was asked. No abstractions for single-use code. No "flexibility" not requested. No error handling for impossible scenarios.
4. **Scope surgical changes.** Touch only what you must. Do not "improve" adjacent code. Match existing style. Every changed line traces to the request. **If the codebase already has two contradicting patterns for the thing you're about to write** (two error-handling styles, two state-writer shapes, two test conventions), do not blend them. Pick the one that is more recent or has more callers, follow it, and flag the other as a separate cleanup item — averaging the two produces code that satisfies neither rule and confuses the next reader.
5. **Define verifiable success.** Transform the task into a concrete check:
   - "Add validation" → "write tests for invalid inputs, then make them pass."
   - "Fix the bug" → "write a test that reproduces it, then make it pass."
   - "Refactor X" → "ensure tests pass before and after."

Output: a 3-6 line plan with per-step verification criteria.

Gate: plan exists, no ambiguity remains, success criteria are concrete.

### Phase 2 — Code Review

Implement the plan, then self-review the diff before declaring it done.

1. **Implement** per the plan. One step at a time; verify each step's criterion before moving to the next.
2. **Self-review the diff.** Five axes, in priority order:
   - Behavior correctness: logic errors, state corruption, broken edge cases, missing error propagation.
   - Boundary fit: did you stay inside your write scope? Did you bypass EACN for role communication? Did you touch generated state unnecessarily?
   - Configuration and persistence: migration behavior, default values, project isolation.
   - Test coverage: changed behavior has a fast local test or a clear reason why not.
   - Style: only when it affects maintainability or contracts.
3. **Fix** any high-confidence issues found. Defer low-confidence concerns rather than churning.

Gate: `ruff check` + `ruff format --check` + `ty check` + `pytest tests/unit/` all pass.

### Phase 3 — Code Simplifier

Focused cleanup on code that already works. Never alter behavior or contracts.

1. **Scope:** only the files you touched in Phase 2. Do not wander.
2. **Read nearby patterns.** Match local naming, helper APIs, error handling, typing, and test style.
3. **Simplify:**
   - Remove duplication.
   - Flatten unnecessary nesting.
   - Clarify names.
   - Replace clever one-liners with readable code.
   - Delete stale comments that describe obvious code.
   - Consolidate related logic.
4. **Protect contracts.** Public function signatures, CLI behavior, file formats, EACN message shapes, persisted state semantics — unchanged unless the task explicitly requires it.
5. **Avoid over-simplification.** Do not create overly compact solutions that are hard to debug. Do not combine too many concerns into one function. Do not remove helpful abstractions. Choose clarity over brevity.
6. **Re-run the same checks that proved the code worked at the end of Phase 2.** The Phase-2 baseline (the specific tests, fixtures, and commands you used to verify behavior before cleanup) is the comparison point — not just any green smoke run. Cleanup that breaks a Phase-2 check changed behavior.

Gate: every check that passed at the end of Phase 2 still passes. If any breaks, the simplification changed behavior — revert that part.

## Pitfalls

- Skipping Phase 1 because the task feels obvious — the obvious-looking ones are where assumptions hide.
- Adding code in a file you have not read this session. Reading 200 lines before a 5-line change is not overhead; not reading them is the overhead, paid later.
- Declaring Phase 2 done without running the gate. "It looks right" is not a gate pass.
- Reporting "tests pass" or "gate green" when one of the four commands was skipped, errored at startup, or never ran. Silent skip is worse than visible failure.
- Phase 3 changing behavior under the banner of "cleanup." The gate catches this, but only if you run it.
- Treating the three phases as ritual. They are judgment heuristics applied in order, not a checklist to rush through.
- Removing pre-existing dead code during Phase 3. The skill says: leave it unless asked.
- (Experimenter) Dispatching a subagent without including the gate commands in the subagent prompt. Subagents must verify their own slice.
