---
slug: feature-intake
summary: Open when the author requests a feature, repair, dashboard change, or role capability — convert it into bounded role-owned briefs with observable acceptance criteria, then delegate via EACN direct messages so the owning Role posts its own task.
layer: logical
tools: eacn3_send_message
version: 2
status: active
supersedes:
references: project-automation-audit, role-skill-design, eacn3-mcp
provenance: human
---

# Skill — Feature Intake

Gru owns intake and coordination. Experts own implementation, experiments, and paper drafting; Ethics owns evidence and claim audits; Gru invokes `mos_review_run` for formal submission review. Intake is not implementation. Gru never posts EACN tasks — it sends direct briefs and the owning Role creates its own task.

## When to invoke

- The author asks for a feature, repair, dashboard change, or role capability.
- A project is blocked because multiple roles need coordinated work.
- A large request needs decomposition before any role starts editing.

## Structure

Six steps, ending with an EACN-visible intake note: outcome, owner roles, acceptance criteria, briefs issued, unresolved assumptions. Acceptance criteria prefer observable checks (command output, file path, EACN artifact, dashboard behavior, paper section, review verdict) over prose. Questions to the author are reserved for genuinely undecidable points.

## Procedure

1. **Restate the requested outcome.** Problem, target project, user value, visible success condition in one paragraph.
2. **Identify ownership.** Assign implementation, experiments, writing, review, and audit to appropriate roles. Do not centralize ordinary work in Gru.
3. **Find blockers early.** Ask the author only for missing information that cannot be inferred safely and would change the route or acceptance criteria.
4. **Set acceptance criteria.** Observable checks: command output, file path, EACN artifact, dashboard behavior, paper section, review verdict.
5. **Send a bounded brief** to each owning Role via `eacn3_send_message` — scope, allowed paths, expected output, deadline / budget if any, handoff format. The Role posts its own EACN task to track the work; Gru does not post tasks.
6. **Track without micromanaging.** Nudge only on stalls, blockers, high-signal failures, or cross-project relay needs.

## Pitfalls

- Asking which language / framework to use when the repo is already Python with a clear stack — broad preference questions waste author time when the codebase already implies the answer.
- Letting an Expert start before the success condition is observable.
- Assigning scientific judgment to Gru when Expert should decide.
- Turning intake into implementation.
- Trying to post the bounded task yourself with `eacn3_create_task` — server-side denied; send a direct brief and let the Role create the task.
