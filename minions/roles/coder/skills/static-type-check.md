---
slug: static-type-check
summary: Use Python type information to catch contract drift before runtime — coherent public types, honest None handling, structured state/config in sync.
layer: logical
tools:
version: 2
status: active
supersedes:
references: type-design-review, coding-methodology
provenance: human
---

# Skill — Static Type Check

Catch contract drift in changed Python code before runtime hits it.

## When to invoke

- Code changes lifecycle state, config models, role registration, EACN payloads, CLI return values, or public helpers.
- A bug smells like a shape mismatch, missing key, or unexpected `None`.
- Before handing off a shared Python API change.

## Structure

Local type surface, not whole-repo annotation churn. Prefer the project's configured type tool — MinionsOS uses `uv run ty check minions` per `CLAUDE.md`; fall back to manual inspection plus existing tests when the tool is unavailable. Boundary conversions — JSON/YAML loading, environment variables, subprocess output, HTTP responses, EACN payloads, optional fields — are where mismatches actually live.

## Procedure

1. **Find the local type surface.** Changed public functions, dataclasses, Pydantic models, TypedDicts, config objects, and serialized state dictionaries.
2. **Prefer configured tools.** Run `uv run ty check minions` (the project's configured tool per `CLAUDE.md`) against the narrowest useful scope first. Otherwise inspect manually and use existing tests.
3. **Check boundary conversions.** JSON/YAML loading, environment variables, subprocess output, HTTP responses, EACN payloads, optional fields.
4. **Tighten only useful annotations.** Add or fix annotations where they protect a caller contract. Avoid churn in private throwaway code.
5. **Resolve real mismatches.** Fix incorrect defaults, unsafe casts, forgotten `None` handling, and schema drift instead of suppressing diagnostics.
6. **Document remaining tool gaps.** If `ty` is unavailable or too noisy on a path, report the specific limitation and what was checked manually.
7. **Report** the type-check command if run, key diagnostics fixed, any left open, and the behavior test that still guards the contract.

## Pitfalls

- Treating type checks as a substitute for behavior tests.
- Adding broad `Any` or ignore comments just to quiet diagnostics.
- Installing new tooling during a role task without explicit authorization.
- Ignoring persisted state compatibility when changing model fields.
