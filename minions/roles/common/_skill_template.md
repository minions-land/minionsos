---
slug: <kebab-case-slug-matching-this-filename>
summary: <one-line capability statement, ≤200 chars; the [Skills] block shows only this>
layer: <scheduling | structural | logical | composite>
tools:
version: 1
status: active
supersedes:
references:
provenance: human
---

# Skill — <Human-Readable Name>

<Optional second line elaborating the summary. Omit if the summary is enough.>

## When to invoke

<Scheduling layer. State the triggers, preconditions, and the shape of the input the Role is holding when this skill applies. If the Role is not in this situation, stop here — do not load the rest of the file.>

## Structure

<Structural layer. What phases does this skill unfold into, what order, which other skills does it compose with? A small list or a short scene graph is enough. Reference peer skills by slug; add them to `references:` above.>

## Procedure

<Logical layer. Concrete tool calls, signatures, resources touched, side effects. Prefer a numbered sequence. Name MCP tools in backticks. State any parameters that must be passed explicitly and any that can be inferred.>

## Pitfalls

<Logical layer, failure surface. Forbidden moves, common mistakes, recoverable vs. unrecoverable failures. Keep each bullet a single sentence where possible.>
