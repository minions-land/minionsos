---
slug: think-then-act
summary: Think then act — toolkit of four cognitive postures for structured planning. Use any combination of Socratic inquiry, first-principles derivation, dialectical synthesis, and goal-setting before dispatching execution.
layer: logical
tools: eacn3_send_message, codex
version: 3
status: active
references: socratic-inquiry, first-principles, dialectics, goal-setting
provenance: human+agent
---

# Skill — Think Then Act

Four thinking postures available for planning non-trivial work at wake-up.
You decide which to use, how many, and in what order. The default sequence
below is a recommendation for when you are unsure how to start — not a
mandatory pipeline.

## When to consider this skill

- Wake delivers events requiring multi-step coordinated work
- You are uncertain about the right approach
- The work crosses boundaries (files, roles, experiments)

Skip entirely for trivial single-step responses. Use one posture alone if
that is all the situation needs.

## The four postures (your toolkit)

| Posture | Skill file | Use when... |
|---|---|---|
| **Socratic** | `socratic-inquiry.md` | Task has unstated constraints or you are filling in blanks with "obviously" |
| **First-Principles** | `first-principles.md` | "Everyone does it this way" is the strongest argument, or you need to derive options from mechanisms |
| **Dialectics** | `dialectics.md` | Two approaches conflict, or you are about to commit to a confident claim |
| **Goal-Setting** | `goal-setting.md` | You are about to dispatch work and need to define what "done" looks like |

Each posture is an independent skill. Read its file when you decide to use it.

## Default recommendation (not mandatory)

For complex, ambiguous tasks where you genuinely do not know how to start:

1. **Socratic** — surface what is NOT said
2. **First-Principles** — derive options from constraints
3. **Dialectics** — model tensions between options
4. **Goal-Setting** — define acceptance metrics

Then write a plan and dispatch. But this is ONE way to use the toolkit.

## Other valid patterns

- **Just Goal-Setting**: Task is clear, you only need to define metrics before dispatch.
- **Socratic → Goal-Setting**: Premises are unclear but once clarified, the path is obvious.
- **First-Principles → Dialectics**: You need to derive options and pick between them, but premises are already explicit and metrics are trivial.
- **Socratic only**: You realize you cannot proceed and need to consult another role via EACN.
- **Skip all four**: The task is well-specified, the approach is obvious, and "test passes" is a sufficient goal. Just do it.

The agent decides. The skill does not decide for you.

## After the postures: plan and dispatch

When you have enough clarity (from however many postures you used):

- **Write a plan**: Use Superpowers `writing-plans` if available, or write an inline markdown checklist.
- **Dispatch**: Use `subagent-driven-development`, `delegate-heavy-task` (Codex), or host-native `Task`.
- **Pass goals**: Each dispatched task should carry its acceptance metric from Goal-Setting (if you ran it).

## Constraints that DO apply regardless

1. **Autonomous-only**: You cannot reach a human terminal. Humans cannot reach
   yours. If you are stuck, blocked, or need a second opinion during any
   posture, send a message on EACN3 to the relevant role (Expert, Coder,
   Experimenter, etc.) and either wait for a reply in this wake or exit and
   let MinionsOS re-wake you when the answer arrives. Never pause for human
   input — it will never come.
2. **Time-aware**: The postures are thinking tools, not rituals. 2-8 minutes total, not hours.
3. **Evidence-marked**: Tag outputs per the Evidence-first EACN convention.

## Fallback

If Superpowers plugin skills are unavailable:
- Write the plan inline as a markdown checklist with goals per task.
- Dispatch via `delegate-heavy-task` (Codex bridge) or host-native `Task` tool.
