# Skill — Simplify Changes

Refine recently modified code for clarity, reuse, and maintainability while
preserving behavior.

## Core move

Improve the shape of code that already works. This skill is not a redesign pass;
it is a focused cleanup after non-trivial edits.

## Procedure

1. **Identify the touched surface.** Use the current task, recent diff, and test
   failures to limit scope. Do not wander into unrelated modules.
2. **Read nearby patterns.** Match local naming, helper APIs, error handling,
   typing, and test style before inventing new structure.
3. **Look for real simplifications.** Remove duplication, flatten unnecessary
   nesting, clarify names, replace clever one-liners, and delete stale comments.
4. **Protect contracts.** Keep public function signatures, CLI behavior, file
   formats, EACN message shapes, and persisted state semantics unchanged unless
   the task explicitly requires a contract change.
5. **Patch narrowly.** Prefer small edits that make the next reader's job easier.
   Avoid broad refactors, formatting churn, or speculative abstractions.
6. **Re-run relevant fast checks.** Use the same tests or commands that proved
   the code worked before cleanup when available.

## When to invoke

- After Coder changes more than roughly 20 lines.
- After feature implementation passes its first verification.
- When a fix works but leaves duplicated, deeply nested, or hard-to-read code.

## Pitfalls

- Optimizing for fewer lines instead of clearer code.
- Changing behavior while "just cleaning up."
- Refactoring shared lifecycle or state contracts without tests.
- Cleaning generated output, logs, or unrelated user changes.

## Output habit

State what was simplified, why behavior is preserved, and which fast checks were
run. If no cleanup is worthwhile, say that and move on.
