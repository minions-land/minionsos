---
slug: coding-review
summary: Phase 2 of coding methodology — implement the plan, then self-review the diff on five axes before declaring done.
layer: logical
version: 1
status: active
provenance: human
---

# Coding Review (Phase 2)

Implement the plan, then self-review the diff before declaring it done.

## When to use

- Code is written (by you or a subagent) and needs verification before committing.
- You want to catch behavior, boundary, and coverage issues before they reach Reviewer.

## Skip when

- Trivial change where the gate alone is sufficient verification.
- User explicitly said "just implement, I'll review."

## Procedure

1. **Implement** per the plan. One step at a time; verify each step's criterion before moving to the next.

2. **Self-review the diff.** Five axes, in priority order:
   - **Behavior correctness**: logic errors, state corruption, broken edge cases, missing error propagation.
   - **Boundary fit**: did you stay inside your write scope? Did you bypass EACN for role communication? Did you touch generated state unnecessarily?
   - **Configuration and persistence**: migration behavior, default values, project isolation.
   - **Test coverage**: changed behavior has a fast local test or a clear reason why not.
   - **Style**: only when it affects maintainability or contracts.

3. **Fix** any high-confidence issues found. Defer low-confidence concerns rather than churning.

## Output

Implementation complete + self-review notes (issues found and fixed, or "clean").

## Gate

```bash
ruff check <changed_paths> && ruff format --check <changed_paths> && ty check <package> && pytest tests/unit/ -q
```

All four must pass. If any fails, fix before advancing.
