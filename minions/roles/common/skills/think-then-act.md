---
slug: think-then-act
summary: Think then act — toolkit of four cognitive postures for structured planning. Use any combination of unstated-premises audit, first-principles derivation, dialectical synthesis, and goal-setting before dispatching execution.
layer: logical
tools: eacn3_send_message, codex
version: 4
status: active
references: unstated-premises, first-principles, dialectical-synthesis, goal-setting
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

**Skip entirely** when the spec is concrete (file path + acceptance already
stated) or the task is trivial single-step. Don't audit premises the spec
already pins — that is ceremony, not thinking. Use one posture alone if
that is all the situation needs.

## The four postures (your toolkit)

| Posture | Skill file | Use when | Skip when |
|---|---|---|---|
| **Unstated Premises** | `unstated-premises.md` | Task has unstated constraints, or filling blanks with "obviously" | Spec is concrete and every premise verifiable from artifacts |
| **First-Principles** | `first-principles.md` | "Everyone does it this way" is the strongest argument | Routine engineering choice (lib, optimizer) where convention is load-bearing |
| **Dialectical Synthesis** | `dialectical-synthesis.md` | Two approaches conflict, or about to publish a confident claim | No genuine opposing position — manufacturing one is worse |
| **Goal-Setting** | `goal-setting.md` | About to dispatch work, need acceptance criteria | One-line binary check ("test passes") is sufficient |

Each posture is an independent skill. Read its file when you decide to use it.

## Default recommendation (not mandatory)

For complex, ambiguous tasks where you genuinely do not know how to start:

1. **Unstated Premises** — surface what is NOT said
2. **First-Principles** — derive options from constraints
3. **Dialectical Synthesis** — model tensions between options
4. **Goal-Setting** — define acceptance metrics

Then write a plan and dispatch. But this is ONE way to use the toolkit.

## Other valid patterns

- **Just Goal-Setting**: Task is clear, you only need to define metrics before dispatch.
- **Unstated-Premises → Goal-Setting**: Premises are unclear but once clarified, the path is obvious.
- **First-Principles → Dialectical Synthesis**: You need to derive options and pick between them, but premises are already explicit and metrics are trivial.
- **Unstated-Premises only**: You realize you cannot proceed and need to consult another role via EACN.
- **Skip all four**: The task is well-specified, the approach is obvious, and "test passes" is a sufficient goal. Just do it.

The agent decides. The skill does not decide for you.

## After the postures: plan and dispatch

When you have enough clarity (from however many postures you used):

- **Write a plan**: Use Superpowers `writing-plans` if available, or write an inline markdown checklist.
- **Dispatch**: Use `subagent-driven-development`, `delegate-heavy-task` (Codex), or host-native `Task`. If Superpowers plugin skills are unavailable, write the plan inline and dispatch via `delegate-heavy-task` or `Task`.
- **Pass goals verbatim**: Copy your Goal-Setting threshold (specific numbers, not "a good report") into the dispatch as its acceptance criterion. No placeholders — "TBD", "reasonable", "appropriate" are plan failures. If you ran Goal-Setting, the final dispatch's acceptance must be the same threshold, not a softer paraphrase.

## Hard constraints

1. **Autonomous-only, evidence-first**: You cannot reach a human terminal. Messaging another role and exiting is a LAST resort — first try `codex` (read-only) or a `Task` subagent on the codebase, git history, EACN logs, and artifacts. Most "I need to ask X" questions are answerable from the repo. Architectural questions ("should we change Y?") almost always have more signal in the code than in the proposer's head. Only message another role when (a) the answer is a fact about that role's intent or external state that cannot be inferred from artifacts, AND (b) the role is reachable this wake. Never pause for human input.

   *Worked example.* A peer asks "should we replace static X with dynamic X?" Tempting move: EACN-message them asking what problem they're solving. Wrong, if they are offline — that loops the wake into nothing. Right move: dispatch `codex` on the relevant code path, role configs, and recent EACN logs to surface concrete friction (or its absence), then make a defensible recommendation from that evidence. The proposer's intent is rarely the bottleneck; the codebase has the answer.
2. **Time-aware**: The postures are thinking tools, not rituals. 2–8 minutes total, not hours.
3. **Evidence-marked**: Tag outputs per the Evidence-first EACN convention.
