---
slug: think-then-act
summary: Think then act — toolkit of four cognitive postures for structured planning. Use any combination of unstated-premises audit, first-principles derivation, dialectical synthesis, and goal-setting before dispatching execution.
layer: logical
tools: eacn3_send_message, codex
version: 5
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

## After the postures: dispatch (never self-execute)

**Hard rule: once Think-then-Act is invoked, the main agent becomes a pure
dispatcher. It does NOT implement, edit files, run commands, or produce
artifacts itself — not even for single-step tasks.** All execution goes
through a subagent. This is non-negotiable regardless of task simplicity.

Why: the value of Think-then-Act is context separation. The thinking
context stays clean for coordination; the doing context is disposable.
If the main agent both thinks and does, context bloats and the thinking
degrades on subsequent tasks.

When you have enough clarity (from however many postures you used):

- **Write a plan**: Use Superpowers `writing-plans` if available, or write a markdown checklist.
- **Persist the plan if ≥2 steps** (see "Plan persistence" below). Single-step work skips persistence — still dispatch.
- **Dispatch ALL execution** via one of (in priority order):
  1. `delegate-heavy-task` (Codex subagent) — preferred for implementation work.
  2. `subagent-driven-development` — when multiple independent tasks can parallelize.
  3. Host-native `Task` tool or `Agent` tool — fallback when Codex is unavailable.
- **Pass goals verbatim**: Copy your Goal-Setting threshold (specific numbers, not "a good report") into the dispatch as its acceptance criterion. No placeholders — "TBD", "reasonable", "appropriate" are plan failures. If you ran Goal-Setting, the final dispatch's acceptance must be the same threshold, not a softer paraphrase.
- **After dispatch returns**: review the result, verify acceptance criteria are met, report completion. If criteria are NOT met, re-dispatch with corrective instructions — do not fix it yourself.

## Plan persistence (≥2 steps)

Multi-step plans must survive context resets. Write them to durable disk so a
future wake — yours or a respawned process under the same role — can resume
without re-deriving them. **This is distinct from the DAG `pending_plan` flag**
(used by `cognitive-checkpoint` for deferred single events). An execution plan
is your own multi-step roadmap; a `pending_plan` DAG node is a deferred event.
They coexist.

**Where**: `project_{port}/branches/<role>/plans/<role>-<slug>.md` (active) →
`project_{port}/branches/<role>/plans/archive/` (when status flips to `done` or
`abandoned`).

**Resume protocol** (handled by `roles/SYSTEM.md` lifecycle, but you must obey
it from think-then-act too): before designing a new plan at wake, list
`branches/<your-role>/plans/<your-role>-*.md` and resume the oldest active one's next
pending step. Only enter the postures when no active plan applies to the
current event batch.

**Update protocol**: after each step's dispatch returns, atomically rewrite
the plan file — flip that step's `Status` to `done` and fill `Evidence`
(commit SHA, artifact path, EACN event id). When all steps `done`, set
frontmatter `status: done` and `git mv` to `archive/`. If the work is
superseded or wrong direction, set `status: abandoned` with a one-line
`abandoned-reason` and archive.

### Template

```markdown
---
plan-id: <role>-<slug>-YYYY-MM-DD
owner: <role>
parent-eacn-task: <task-id or null>
status: active   # active | done | abandoned
---

## Postures used
- <posture>: <one-line takeaway>

## Steps

| # | What | Goal (sensor / threshold) | Dispatch | Status | Evidence |
|---|------|---------------------------|----------|--------|----------|
| 1 | ... | ... | inline / Task / codex / EACN | pending | — |
| 2 | ... | ... | ... | pending | — |

## Notes
<free-form: open questions, branch points, things to revisit>
```

*Worked example.* You woke to "add /healthz endpoint + test". Two steps minimum
(endpoint, test). Write `branches/coder/plans/coder-healthz-2026-05-17.md` with both
steps and their goals. Dispatch step 1 via Task subagent. When it returns, flip
step 1 to `done`, fill Evidence with the commit SHA, write back. Dispatch step
2. If `mos_reset_context` fires between steps for any reason, the next process
sees the active plan in `branches/coder/plans/`, picks up at step 2, no re-thinking
needed.

## Hard constraints

1. **Autonomous-only, evidence-first**: You cannot reach a human terminal. Messaging another role and exiting is a LAST resort — first try `codex` (read-only) or a `Task` subagent on the codebase, git history, EACN logs, and artifacts. Most "I need to ask X" questions are answerable from the repo. Architectural questions ("should we change Y?") almost always have more signal in the code than in the proposer's head. Only message another role when (a) the answer is a fact about that role's intent or external state that cannot be inferred from artifacts, AND (b) the role is reachable this wake. Never pause for human input.

   *Worked example.* A peer asks "should we replace static X with dynamic X?" Tempting move: EACN-message them asking what problem they're solving. Wrong, if they are offline — that loops the wake into nothing. Right move: dispatch `codex` on the relevant code path, role configs, and recent EACN logs to surface concrete friction (or its absence), then make a defensible recommendation from that evidence. The proposer's intent is rarely the bottleneck; the codebase has the answer.
2. **Time-aware**: The postures are thinking tools, not rituals. 2–8 minutes total, not hours.
3. **Evidence-marked**: Tag outputs per the Evidence-first EACN convention.
