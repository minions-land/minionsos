---
slug: type-design-review
summary: Evaluate whether new or changed data types express the invariants they need to protect; review structured data as a contract, not just a container.
layer: logical
tools:
version: 2
status: active
supersedes:
references: static-type-check
provenance: human
---

# Skill — Type Design Review

A good type makes invalid states hard to create and easy to detect at project boundaries.

## When to invoke

- Adding or changing lifecycle project entries, role metadata, EACN payloads, config models, dashboard API types, or experiment request shapes.
- Before merging any new Pydantic model, dataclass, or TypedDict into a shared lifecycle or state module.
- A bug comes from invalid combinations of fields.
- A feature introduces a new state machine or persisted schema.

## Structure

Each reviewed type gets a short verdict: `strong` (invariants enforced by the type itself), `adequate` (enforced by constructor or validator), `convention-only` (enforced only by reader vigilance), or `unsafe` (invariants not enforced anywhere). Serialization compatibility matters as much as in-memory shape — persisted JSON/YAML and API payloads must keep backward compatibility or supply a migration path.

## Procedure

1. **Identify the type boundary.** New or changed dataclasses, Pydantic models, enums, TypedDicts, payload dictionaries, frontend shared types.
2. **Name the invariants.** For each type, state what must always be true: required fields, mutually exclusive fields, path scope, token secrecy, status transitions, timestamps, role ownership.
3. **Check enforcement.** Type, constructor, parser, validation function, tests, or only convention.
4. **Check serialization.** Persisted JSON/YAML and API payloads maintain backward compatibility or provide a migration path.
5. **Simplify if possible.** Remove types that only rename `dict` without clarifying invariants. Split types only when consumers need different guarantees.
6. **Patch high-value fixes.** Add enums, validators, helper constructors, or focused tests when they prevent real bugs.
7. **Report** each reviewed type with a verdict (`strong` / `adequate` / `convention-only` / `unsafe`) plus any fixes or migration risks.

## Pitfalls

- Designing types for theoretical elegance instead of actual callers.
- Breaking old state files without migration.
- Encoding secrets or tokens into debug-friendly string representations.
- Hiding uncertain fields behind `Any`.
