---
slug: feature-implementation
summary: Translate an accepted feature task into a small, integrated implementation that matches the existing codebase; prefer local patterns over new abstractions.
layer: logical
tools:
version: 2
status: active
supersedes:
references: coding-methodology, bounded-repair-loop
provenance: human
---

# Skill — Feature Implementation

A bounded feature implementation after requirements and ownership are clear.

## When to invoke

- Gru or another role has completed feature intake and assigned implementation to Coder.
- A user request requires adding behavior rather than only debugging or review.
- A change that needs coordinated implementation — "coordinated" means it touches more than one Coder-owned module, or requires a handoff to another role (Writer, Experimenter, Reviewer, Ethics, Expert, Gru).

If requirements are still ambiguous, do not start; ask through EACN first.

## Structure

Smallest viable implementation in Coder-owned paths. Five phases: read the task, explore precedent, choose architecture, implement, verify, simplify, hand off. Adding an abstraction is justified only when it removes real duplication, protects a contract, or matches an existing pattern.

## Procedure

1. **Read the task and acceptance criteria.** If problem, owner, output path, or success condition is unclear, ask through EACN before implementation.
2. **Explore the nearest precedent.** Read similar commands, lifecycle helpers, tests, UI components, or role skills before designing anything new.
3. **Choose the smallest viable architecture.** Add an abstraction only if it removes real duplication, protects a contract, or matches an existing pattern.
4. **Implement in owned paths.** Edits scoped to Coder-owned workspace or system-maintenance paths explicitly assigned by Gru or the author.
5. **Add focused verification.** Unit tests for Python behavior, smoke tests for orchestration, or a build for dashboard changes. Heavy experiments stay out of Coder.
6. **Run `simplify-changes`.** After the feature works, refine changed code for clarity without altering behavior.
7. **Handoff with evidence.** Report what changed, commands run, and any unresolved follow-up.

## Pitfalls

- Starting implementation while requirements are still ambiguous.
- Designing from scratch when an existing module already establishes the shape.
- Expanding scope into scientific decisions, experiment execution, or Writer / Reviewer artifacts.
- Shipping working code that is too tangled to maintain.
