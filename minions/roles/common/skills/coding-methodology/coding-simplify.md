---
slug: coding-simplify
summary: Phase 3 of coding methodology — focused cleanup on code that already works, without altering behavior or contracts.
layer: logical
version: 1
status: active
provenance: human
---

# Coding Simplify (Phase 3)

Focused cleanup on code that already works. Never alter behavior or contracts.

## When to use

- Code works and was accepted; now you want it cleaner.
- User explicitly asks for a cleanup pass.
- Phase 2 left working but verbose code.

## Skip when

- User said "don't clean up" or "ship as-is."
- The diff is ≤5 lines — cleanup overhead exceeds value.
- You're tempted to "improve" code you didn't touch this session.

## Procedure

1. **Scope:** only the files you touched in Phase 2 (or the files the user pointed at). Do not wander.

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

6. **Re-run the Phase 2 baseline.** The specific tests, fixtures, and commands you used to verify behavior before cleanup are the comparison point — not just any green smoke run.

## Output

Simplified code + confirmation that all Phase 2 checks still pass.

## Gate

```bash
ruff check <changed_paths> && ruff format --check <changed_paths> && ty check <package> && pytest tests/unit/ -q
```

Every check that passed at the end of Phase 2 must still pass. If any breaks, the simplification changed behavior — revert that part.
