# Skill — Feature Implementation

Implement a bounded feature after requirements and ownership are clear.

## Core move

Translate an accepted feature task into a small, integrated implementation that
matches the existing codebase. Prefer local patterns over new abstractions.

## Procedure

1. **Read the task and acceptance criteria.** If the problem, owner, output path,
   or success condition is unclear, ask through EACN before implementation.
2. **Explore the nearest precedent.** Read similar commands, lifecycle helpers,
   tests, UI components, or role skills before designing anything new.
3. **Choose the smallest viable architecture.** Add an abstraction only if it
   removes real duplication, protects a contract, or matches an existing pattern.
4. **Implement in owned paths.** Keep edits scoped to Coder-owned workspace or
   system-maintenance paths explicitly assigned by Gru or the author.
5. **Add focused verification.** Unit tests for Python behavior, smoke tests for
   orchestration, or a build for dashboard changes. Keep heavy experiments out of
   Coder.
6. **Run `simplify-changes`.** After the feature works, refine the changed code
   for clarity without altering behavior.
7. **Handoff with evidence.** Report what changed, commands run, and any
   unresolved follow-up.

## When to invoke

- Gru or another role has completed feature intake and assigned implementation
  to Coder.
- A user request requires adding behavior rather than only debugging or review.
- A dashboard, CLI, lifecycle, state, role, or tool change needs coordinated
  implementation.

## Pitfalls

- Starting implementation while requirements are still ambiguous.
- Designing from scratch when an existing module already establishes the shape.
- Expanding scope into scientific decisions, experiment execution, or Writer /
  Reviewer artifacts.
- Shipping working code that is too tangled to maintain.

## Output habit

Return changed paths, verification commands and results, any behavior not
covered by tests, and EACN follow-up needed from other roles.
