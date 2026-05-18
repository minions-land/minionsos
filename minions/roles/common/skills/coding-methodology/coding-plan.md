---
slug: coding-plan
summary: Phase 1 of coding methodology — decide how to write the code before writing it. Karpathy discipline applied to planning.
layer: logical
version: 1
status: active
provenance: human
---

# Coding Plan (Phase 1)

Decide how to write the code before writing it.

## When to use

- The change is non-trivial and you haven't decided on an approach yet.
- The request has multiple reasonable interpretations.
- You're about to touch shared state, public APIs, or lifecycle code.

## Skip when

- Spec is concrete: file path + acceptance criteria already stated.
- Single-line fix with no ambiguity.

## Procedure

1. **Read the territory first.** Before stating any assumption, read the file you'll touch — its exports, callers, shared utilities. If you don't understand why nearby code is structured the way it is, that is the first thing to resolve. The depth is proportional to the change: a one-line patch reads the function; a cross-module change reads the immediate callers and any shared helper module.

2. **Surface assumptions.** State them explicitly. Uncertain → ask. Multiple interpretations → present them; do not pick silently.

3. **Choose the simplest approach.** No features beyond what was asked. No abstractions for single-use code. No "flexibility" not requested. No error handling for impossible scenarios.

4. **Scope surgical changes.** Touch only what you must. Do not "improve" adjacent code. Match existing style. Every changed line traces to the request. If the codebase has two contradicting patterns for the thing you're about to write, pick the one that is more recent or has more callers, follow it, and flag the other as a separate cleanup item.

5. **Define verifiable success.** Transform the task into a concrete check:
   - "Add validation" → "write tests for invalid inputs, then make them pass."
   - "Fix the bug" → "write a test that reproduces it, then make it pass."
   - "Refactor X" → "ensure tests pass before and after."

## Output

A 3–6 line plan with per-step verification criteria.

## Gate

Plan exists, no ambiguity remains, success criteria are concrete. Then run:

```bash
ruff check <changed_paths> && ruff format --check <changed_paths> && ty check <package> && pytest tests/unit/ -q
```
