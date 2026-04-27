# Skill — Static Type Check

Use Python type information to catch contract drift before runtime.

## Core move

Check that changed Python code has coherent public types, handles `None`
honestly, and keeps structured state/config fields in sync.

## Procedure

1. **Find the local type surface.** Identify changed public functions,
   dataclasses, Pydantic models, TypedDicts, config objects, and serialized state
   dictionaries.
2. **Prefer configured tools.** If the project has Pyright, run the narrowest
   useful command first. Otherwise inspect types manually and use existing tests.
3. **Check boundary conversions.** Pay special attention to JSON/YAML loading,
   environment variables, subprocess output, HTTP responses, EACN payloads, and
   optional fields.
4. **Tighten only useful annotations.** Add or fix annotations where they protect
   a caller contract. Avoid annotation churn in private throwaway code.
5. **Resolve real mismatches.** Fix incorrect defaults, unsafe casts, forgotten
   `None` handling, and schema drift instead of suppressing diagnostics.
6. **Document remaining tool gaps.** If Pyright is unavailable or too noisy,
   report the specific limitation and what was checked manually.

## When to invoke

- Code changes lifecycle state, config models, role registration, EACN payloads,
  CLI return values, or public helpers.
- A bug smells like a shape mismatch, missing key, or unexpected `None`.
- Before handing off a shared Python API change.

## Pitfalls

- Treating type checks as a substitute for behavior tests.
- Adding broad `Any` or ignore comments just to quiet diagnostics.
- Installing new tooling during a role task without explicit authorization.
- Ignoring persisted state compatibility when changing model fields.

## Output habit

Report the type-check command if run, key diagnostics fixed, any diagnostics
left open, and the behavior test that still guards the contract.
