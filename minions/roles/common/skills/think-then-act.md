---
slug: think-then-act
summary: Think then act — toolkit of five postures for structured planning before Workflow dispatch. Use any combination of unstated-premises audit, first-principles derivation, dialectical synthesis, goal-setting, and plan-persistence; then issue a single Workflow per common §4.
layer: logical
tools: Workflow, eacn3_send_message
version: 7
status: active
references: unstated-premises, first-principles, dialectical-synthesis, goal-setting, plan-persistence, think-in-parallel, evidence-driven-proposal, role-act-via-workflow, coding-methodology
provenance: human+agent
---

# Skill — Think Then Act

Five postures available for planning non-trivial work at wake-up.
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

## The five postures (your toolkit)

| Posture | Skill file | Use when | Skip when |
|---|---|---|---|
| **Unstated Premises** | `unstated-premises.md` | Task has unstated constraints, or filling blanks with "obviously" | Spec is concrete and every premise verifiable from artifacts |
| **First-Principles** | `first-principles.md` | "Everyone does it this way" is the strongest argument | Routine engineering choice (lib, optimizer) where convention is load-bearing |
| **Dialectical Synthesis** | `dialectical-synthesis.md` | Two approaches conflict, or about to publish a confident claim | No genuine opposing position — manufacturing one is worse |
| **Goal-Setting** | `goal-setting.md` | About to dispatch work, need acceptance criteria | One-line binary check ("test passes") is sufficient |
| **Plan Persistence** | `plan-persistence.md` | Multi-step work (≥2 steps) that must survive context resets | Single-step task where dispatch alone is sufficient |

Each posture is an independent skill. Read its file when you decide to use it.

## Default recommendation (not mandatory)

For complex, ambiguous tasks where you genuinely do not know how to start:

1. **Unstated Premises** — surface what is NOT said
2. **First-Principles** — derive options from constraints
3. **Dialectical Synthesis** — model tensions between options
4. **Goal-Setting** — write the 5-element feedback loop (sensor / metric / threshold / feedback period / stop rule); not a verdict or MVP recommendation
5. **Plan Persistence** — write the plan to disk so it survives resets

Then dispatch. But this is ONE way to use the toolkit.

## Common failure mode — Posture 4 collapses into engineering conclusions

Synthesis (Posture 3) tends to end with "so we should build X". That is the recommendation, not the goal. Posture 4 must produce a Goal block in the canonical format from `goal-setting.md` — sensor, metric, threshold, feedback period, stop rule — that the executor can use as a stopping condition. "Can we build it: yes", "MVP scope is Y", "approach Z is impossible" are inputs to synthesis, not goals. If your Posture-4 output reads like an executive summary, a yes/no verdict, or an "engineering conclusions" list, you skipped Posture 4 — open `goal-setting.md` and write the actual Goal block before dispatching.

## Other valid patterns

- **Just Goal-Setting**: Task is clear, you only need to define metrics before dispatch.
- **Unstated-Premises → Goal-Setting**: Premises are unclear but once clarified, the path is obvious.
- **First-Principles → Dialectical Synthesis**: You need to derive options and pick between them, but premises are already explicit and metrics are trivial.
- **Goal-Setting → Plan Persistence**: Task is clear but multi-step; persist the plan, then dispatch.
- **Unstated-Premises only**: You realize you cannot proceed and need to consult another role via EACN.
- **Skip all five**: The task is well-specified, the approach is obvious, and "test passes" is a sufficient goal. Just do it.
- **Goal-Setting → think-in-parallel**: Task is a hard single-point reasoning problem (math, algorithm, counter-intuitive logic); skip planning postures and go straight to parallel sampling.

The agent decides. The skill does not decide for you.

## After the postures: Workflow (never self-execute)

**Hard rule: once Think-then-Act is invoked, the main agent becomes a
pure dispatcher for implementation work. It does NOT implement, edit
files, produce artifacts, or run experiments itself — not even for
single-step tasks.** All implementation execution goes through the
**Workflow tool** per common SYSTEM.md §4 Plan → Workflow → Verify.
This is non-negotiable regardless of task simplicity.

**Carve-out for verification probes.** A ≤5-second read-only probe per
`evidence-driven-proposal.md` (e.g. `grep`, `head` of a config, `python
-c "import x; print(x.__version__)"`, single-test rerun) is **not**
implementation work — it is the publication gate, and routing it
through a Workflow would defeat the low-cost anchor value the probe is
for. Run those probes inline, mark the claim with `[evidence: …]`, and
keep dispatching the actual work.

Why: the value of Think-then-Act is context separation. The thinking
context stays clean for coordination; the doing context is disposable.
If the main agent both thinks and does, context bloats and the thinking
degrades on subsequent tasks.

When you have enough clarity (from however many postures you used):

- **Write a plan** as a markdown checklist or use a host-native
  planning tool if available.
- **Persist the plan if ≥2 steps** — read `plan-persistence.md`.
  Single-step work skips persistence — still dispatch via Workflow.
- **Dispatch ALL execution via Workflow** (canonical per common §4).
  Pick the shape that captures the dependency graph: `single agent`,
  `parallel`, `pipeline`, `phase` (e.g. `coding-methodology` Plan →
  Review → Simplify), or `fan-out + verifier`. See `role-act-via-
  workflow.md` for per-role recipe pointers.
- **For code-shaped artefacts** (multi-file refactor, plotting
  scripts, public-API edits, ≥ 2-file changes), open
  `coding-methodology` (Plan → Review → Simplify, smoke-test gated)
  inside the Workflow agent that does the editing.
- **If the Workflow's return is suspect** (broken logic, contradictory
  reasoning, two probes disagree): escalate via
  `Skill(think-in-parallel)` — do NOT accept or fix manually, and do
  NOT dispatch a fresh Workflow as a workaround.
- **Pass goals verbatim**: copy your Goal-Setting threshold (specific
  numbers, not "a good report") into the Workflow spec as its
  acceptance criterion. No placeholders — "TBD", "reasonable",
  "appropriate" are plan failures.
- **Long Workflows** (acceptance criterion plausibly > 60 s, any
  `phase`, any `parallel` of ≥ 3 agents) MUST run with
  `run_in_background=true`. Re-enter `mos_await_events` while polling
  via `mcp__keepalive__wait_bg`. EACN responsiveness takes precedence
  over Workflow latency.
- **Host fallback** (Workflow unreachable): follow the §4
  host-fallback ladder — Task subagent → Sonnet (only when
  harness-native tools are required as actions to satisfy the
  acceptance criterion) → inline. Inline writes follow the
  `reliable-file-io` Tier 0 recipe for CJK / LaTeX / multi-section
  content.
- **On Workflow return**: verify acceptance criteria, then run
  `evidence-driven-proposal.md` before publishing the finding. Flip
  step to `done` with the `[evidence: …]` / `[derived: …]` /
  `[speculation]` markers it produces.

## Hard constraints

1. **Autonomous-only, evidence-first**: You cannot reach a human terminal. Messaging another role and exiting is a LAST resort — first try a Workflow that reads the codebase, git history, EACN logs, and artifacts. Most "I need to ask X" questions are answerable from the repo. Only message another role when (a) the answer is a fact about that role's intent or external state that cannot be inferred from artifacts, AND (b) the role is reachable this wake. Never pause for human input.
2. **Time-aware**: The postures are thinking tools, not rituals. 2–8 minutes total, not hours.
3. **Evidence-marked**: Tag every load-bearing claim per `evidence-driven-proposal.md` — `[evidence: …]` (anchor probe with command + outcome) / `[derived: …]` (basis stated) / `[speculation]` (cannot probe or derive).
