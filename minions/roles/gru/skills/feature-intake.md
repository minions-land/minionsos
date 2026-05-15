---
slug: feature-intake
summary: Open when the author requests a feature, repair, dashboard change, or role capability — convert it into bounded role-owned tasks with observable acceptance criteria, then delegate via EACN.
layer: logical
tools: eacn3_create_task
version: 2
status: active
supersedes:
references: project-automation-audit, role-skill-design, eacn3-mcp
provenance: human
---

# Skill — Feature Intake

Gru owns intake and coordination; Coder, Writer, Experimenter, and Reviewer own execution. Intake is not implementation.

## When to invoke

- The author asks for a feature, repair, dashboard change, or role capability.
- A project is blocked because multiple roles need coordinated work.
- A large request needs decomposition before any role starts editing.

## Structure

Six steps, ending with an EACN-visible intake note: outcome, owner roles, acceptance criteria, tasks issued, unresolved assumptions. Acceptance criteria prefer observable checks (command output, file path, EACN artifact, dashboard behavior, paper section, review verdict) over prose. Questions to the author are reserved for genuinely undecidable points.

## Procedure

1. **Restate the requested outcome.** Problem, target project, user value, visible success condition in one paragraph.
2. **Identify ownership.** Assign implementation, experiments, writing, review, and audit to appropriate roles. Do not centralize ordinary work in Gru.
3. **Find blockers early.** Ask the author only for missing information that cannot be inferred safely and would change the route or acceptance criteria.
4. **Set acceptance criteria.** Observable checks: command output, file path, EACN artifact, dashboard behavior, paper section, review verdict.
5. **Publish bounded tasks** via EACN — each role gets a scoped task with allowed paths, expected output, deadline / budget if any, and handoff format.
6. **Track without micromanaging.** Nudge only on stalls, blockers, high-signal failures, or cross-project relay needs.

## Pitfalls

- Asking which language / framework to use when the repo is already Python with a clear stack — broad preference questions waste author time when the codebase already implies the answer.
- Letting Coder start before the success condition is observable.
- Assigning scientific judgment to Gru when Expert should decide.
- Turning intake into implementation.
