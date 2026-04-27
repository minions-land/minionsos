# Skill — Type Design Review

Evaluate whether new or changed data types express the invariants they need to
protect.

## Core move

Review structured data as a contract, not just a container. A good type makes
invalid states hard to create and easy to detect at project boundaries.

## Procedure

1. **Identify the type boundary.** Locate new or changed dataclasses, Pydantic
   models, enums, TypedDicts, payload dictionaries, and frontend shared types.
2. **Name the invariants.** For each type, state what must always be true:
   required fields, mutually exclusive fields, path scope, token secrecy, status
   transitions, timestamps, or role ownership.
3. **Check enforcement.** Determine whether invariants are enforced by the type,
   constructor, parser, validation function, tests, or only by convention.
4. **Check serialization.** Verify persisted JSON/YAML and API payloads maintain
   backward compatibility or provide a migration path.
5. **Simplify if possible.** Remove types that only rename `dict` without
   clarifying invariants. Split types only when consumers need different
   guarantees.
6. **Patch high-value fixes.** Add enums, validators, helper constructors, or
   focused tests when they prevent real bugs.

## When to invoke

- Adding or changing lifecycle project entries, role metadata, EACN payloads,
  config models, dashboard API types, or experiment request shapes.
- A bug comes from invalid combinations of fields.
- A feature introduces a new state machine or persisted schema.

## Pitfalls

- Designing types for theoretical elegance instead of actual callers.
- Breaking old state files without migration.
- Encoding secrets or tokens into debug-friendly string representations.
- Hiding uncertain fields behind `Any`.

## Output habit

Report each reviewed type with a short verdict: `strong`, `adequate`,
`convention-only`, or `unsafe`, plus any fixes or migration risks.
