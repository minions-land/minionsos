# Batch: coder

## Per-skill grades

| slug | summary | trigger | procedure | pitfalls | structure | mean | verdict |
|---|---|---|---|---|---|---|---|
| bounded-repair-loop | 5 | 5 | 5 | 4 | 5 | 4.8 | KEEP |
| build-playground | 5 | 4 | 4 | 4 | 5 | 4.4 | KEEP |
| change-review | 5 | 4 | 5 | 4 | 5 | 4.6 | KEEP |
| feature-implementation | 5 | 4 | 4 | 4 | 5 | 4.4 | KEEP |
| karpathy-coding-guidelines | 4 | 3 | 5 | 4 | 4 | 4.0 | TUNE |
| silent-failure-audit | 5 | 4 | 5 | 5 | 5 | 4.8 | KEEP |
| simplify-changes | 5 | 4 | 5 | 4 | 5 | 4.6 | KEEP |
| static-type-check | 5 | 4 | 4 | 4 | 5 | 4.4 | KEEP |
| test-coverage-review | 5 | 4 | 5 | 4 | 5 | 4.6 | KEEP |
| type-design-review | 5 | 4 | 4 | 4 | 5 | 4.4 | KEEP |

---

## Per-skill notes

### bounded-repair-loop
- **Verdict:** KEEP
- **Strengths:** Best-in-batch trigger section — three concrete match conditions plus one explicit exclusion; procedure is fully executable with named gates.
- **Issues:**
  - Pitfall "Treating this as permission to keep editing indefinitely" is a restatement of the skill's own premise rather than a distinct failure mode. It adds no new information beyond what the bound-setting step already covers.
- **Recommended action:** Replace the first pitfall with a concrete failure pattern, e.g. "Resetting the iteration counter after a partial pass to avoid hitting the bound."

### build-playground
- **Verdict:** KEEP
- **Strengths:** Summary is precise and decision-enabling; structure section clearly names the three required surfaces (controls, live preview, copyable output).
- **Issues:**
  - Trigger condition "Static prose would leave too many visual degrees of freedom ambiguous" is vague — a fresh agent cannot reliably judge "too many degrees of freedom" without a concrete threshold or example.
  - Step 2 names a specific path (`branches/coder/playgrounds/<slug>.html`) but does not say what to do when that path does not exist in the project (no mkdir instruction, no fallback).
- **Recommended action:** Add one concrete example to the third trigger bullet; add a one-line fallback for the output path in step 2.

### change-review
- **Verdict:** KEEP
- **Strengths:** Five-axis priority ordering is clear and actionable; "findings carry file and line evidence" is a concrete output contract.
- **Issues:**
  - Trigger "Before returning an EACN result after non-trivial implementation" leaves "non-trivial" undefined — a fresh agent must guess the threshold.
  - Pitfall "Reporting speculative issues without file/line evidence" is good but duplicates the procedure's own step 6 ("Fix high-confidence issues immediately... Defer or report low-confidence concerns").
- **Recommended action:** Define "non-trivial" with a rough line-count or structural heuristic (e.g. ">10 lines changed or any shared lifecycle/state path touched").

### feature-implementation
- **Verdict:** KEEP
- **Strengths:** References chain (simplify-changes, change-review, bounded-repair-loop) makes the post-implementation workflow explicit; "smallest viable architecture" framing is concrete.
- **Issues:**
  - Trigger "A dashboard, CLI, lifecycle, state, role, or tool change needs coordinated implementation" is a near-exhaustive list that matches almost any Coder task — it does not help a fresh agent distinguish this skill from just doing the work.
  - Structure section says "Five phases: read the task, explore precedent, choose architecture, implement, verify, simplify, hand off" — that is seven items, not five.
- **Recommended action:** Fix the count mismatch in Structure; tighten the third trigger bullet to name what "coordinated" means (e.g. "touches more than one owned module or requires a handoff to another role").

### karpathy-coding-guidelines
- **Verdict:** TUNE
- **Strengths:** Procedure is the most detailed in the batch — each guideline has concrete sub-bullets and a self-test question.
- **Issues:**
  - Trigger "Open whenever Coder, Experimenter, or Gru is about to produce non-trivial code" is too broad to be a decision gate. A fresh agent cannot tell when NOT to open this skill, making it feel like a background rule rather than a situational skill.
  - The skill names itself after a person ("Karpathy") without explaining the provenance. A fresh agent reading this cold has no context for why the name matters or whether it implies a specific external reference to consult.
  - "Skip for trivial edits (single-line fixes, comment updates) where the discipline is overhead" — "trivial" is undefined and the parenthetical examples are too narrow to generalize from.
  - Structure section lists four guidelines but the H2 is `## Structure` rather than `## When to invoke` / `## Structure` split — the When to invoke content is embedded in the Structure section prose, breaking the four-section contract.
- **Recommended action:** Move the trigger paragraph into a proper `## When to invoke` section; replace "non-trivial code" with a concrete threshold (e.g. "any change touching shared state, public APIs, or more than one file"); drop or explain the Karpathy attribution.

### silent-failure-audit
- **Verdict:** KEEP
- **Strengths:** Three-class verdict schema (verified / patched / accepted fallback) is the clearest output contract in the batch — a fresh agent knows exactly what to produce. Pitfalls are all concrete anti-patterns with real consequences.
- **Issues:**
  - Trigger "A smoke test passes while logs show hidden errors" is good but assumes the agent has already run a smoke test — it does not say when to run this skill proactively before any test.
- **Recommended action:** Add a proactive trigger: "Before handing off any change that introduces new exception handling or subprocess calls, even if no test has been run yet."

### simplify-changes
- **Verdict:** KEEP
- **Strengths:** "If no cleanup is worthwhile, say so and move on" is a rare and valuable explicit exit condition. Contract-protection list (function signatures, CLI behavior, file formats, EACN message shapes, persisted state semantics) is specific and useful.
- **Issues:**
  - Trigger threshold "more than roughly 20 lines" is the only quantitative trigger in the batch — good — but "roughly" weakens it. A fresh agent may still hesitate at 18 lines.
  - Pitfall "Optimizing for fewer lines instead of clearer code" is a platitude without a concrete failure example.
- **Recommended action:** Drop "roughly" from the line-count trigger; replace the first pitfall with a concrete example (e.g. "collapsing a readable three-step conditional into a single nested ternary to reduce line count").

### static-type-check
- **Verdict:** KEEP
- **Strengths:** "Boundary conversions" framing correctly identifies where type mismatches actually occur; step 6 explicitly handles the tool-unavailable case.
- **Issues:**
  - Trigger "Prefer the project's configured type tool (e.g. Pyright)" appears in the Structure section, not the Procedure — a fresh agent may miss it when scanning for the tool name.
  - Step 2 says "If Pyright is configured, run the narrowest useful command first" but does not give the command. The project uses `uv run ty check minions` (from CLAUDE.md), not Pyright — this is a factual mismatch.
- **Recommended action:** Replace "Pyright" with `uv run ty check minions` (the actual configured tool per CLAUDE.md) in both Structure and Procedure step 2.

### test-coverage-review
- **Verdict:** KEEP
- **Strengths:** Priority gap ordering (lifecycle transitions → persisted state → role boundaries → EACN payloads → config defaults → CLI behavior → dashboard read-only) is the most actionable triage list in the batch.
- **Issues:**
  - Trigger "Before completing a feature, bug fix, or refactor with behavioral impact" — "behavioral impact" is undefined; almost any change has behavioral impact.
  - Step 5 mentions "fake Codex binaries for Codex" but does not name the pattern or path, unlike the Claude equivalent (`MINIONS_FAKE_CLAUDE=1`). A fresh agent cannot act on this without more context.
- **Recommended action:** Name or reference the fake Codex pattern in step 5; tighten the first trigger to "any change that alters a public function signature, state schema, or CLI output."

### type-design-review
- **Verdict:** KEEP
- **Strengths:** Four-verdict schema (strong / adequate / convention-only / unsafe) mirrors silent-failure-audit's classification approach and gives a fresh agent a concrete output shape. Serialization compatibility check is explicitly called out.
- **Issues:**
  - Trigger "A bug comes from invalid combinations of fields" requires the agent to already know a bug exists — it does not help with proactive invocation.
  - Step 5 "Remove types that only rename `dict` without clarifying invariants" is good advice but has no corresponding pitfall about over-splitting types, which is the symmetric failure.
- **Recommended action:** Add a proactive trigger (e.g. "Before merging any new Pydantic model, dataclass, or TypedDict into a shared lifecycle or state module"); add a pitfall for over-splitting ("Splitting one type into two when both consumers need the same guarantees, creating sync burden without safety gain").

---

## Batch-level observations

- **Uniformly strong summaries.** All 10 frontmatter `summary:` lines are decision-enabling at a glance. This is the best-performing dimension across the batch (9 scores of 5, one 4).

- **Consistent structure compliance.** All 10 files follow the four-section split cleanly, with one exception: `karpathy-coding-guidelines` folds its trigger content into the Structure section, breaking the contract.

- **Trigger vagueness is the systemic weakness.** Eight of ten files use "non-trivial" or an equivalently undefined threshold in their trigger section. The two that avoid this (`bounded-repair-loop` with its three named conditions, `simplify-changes` with its 20-line threshold) are noticeably easier to match against a real situation.

- **Output contracts vary in quality.** `silent-failure-audit` and `type-design-review` define explicit verdict schemas that tell a fresh agent exactly what to produce. `change-review` and `test-coverage-review` have strong report steps. `build-playground`, `feature-implementation`, and `karpathy-coding-guidelines` have weaker or implicit output shapes.

- **Tool name drift.** `static-type-check` references Pyright, but the project's actual configured tool is `uv run ty check minions` (per CLAUDE.md). This is the only factual error in the batch and should be fixed before the next role wake-up cycle.

- **Pitfall quality is uneven.** `silent-failure-audit` has the strongest pitfalls (all concrete, all consequential). Several others include at least one restatement of the skill's own premise rather than a distinct failure mode (`bounded-repair-loop`, `simplify-changes`).

- **Reference graph is well-formed.** The `references:` fields form a coherent dependency graph: `feature-implementation` → `simplify-changes` + `change-review` + `bounded-repair-loop`; `change-review` → `bounded-repair-loop` + `feature-implementation` + `simplify-changes`; `static-type-check` → `type-design-review` + `change-review`. No cycles, no orphans.

- **No redundancy requiring MERGE.** Despite the reference density, each skill has a distinct invocation context. `static-type-check` (run a tool, fix annotations) and `type-design-review` (evaluate invariant design) are complementary, not duplicative.

- **`karpathy-coding-guidelines` is the outlier.** It is the only skill that reads as a background behavioral standard rather than a situational procedure. Its trigger is effectively "always," which makes it a poor fit for the skill-selection model. Tuning the trigger and fixing the section structure would bring it in line with the rest of the batch.
