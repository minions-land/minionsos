---
slug: code-validity-review
summary: Deep-trace zoom of the experiments / reproducibility aspects — open when aspect-review must walk code paths to decide whether implementation invalidates a paper claim. Delegate the actual code trace to Codex; keep validity judgment here.
layer: logical
tools: codex
version: 4
status: active
supersedes:
references: aspect-review, simulate-reviewer-instance
provenance: human
---

# Skill — Code Validity Review

The deep-trace zoom of `aspect-review`'s `experiments` and `reproducibility` aspects. Most of the time, those aspects produce findings from the submission package alone — claims, tables, configs, logs. This skill opens only when the aspect's evidence trail requires walking actual code paths (script → config → data loader → metric → output) to decide whether an implementation detail invalidates a claim.

The question is not whether the code is elegant. It is whether implementation details could invalidate experiments, metrics, baselines, or claims.

## Relationship to aspect-review

This skill is not a third reviewer aspect. It is the *callable mode* an `experiments` or `reproducibility` aspect subagent escalates to when surface-level reading cannot resolve a validity question.

Decision rule:

- **Use `aspect-review` directly** with the `experiments` or `reproducibility` aspect when the submission package, configs, and reported metrics are enough to surface findings. This is the default path.
- **Open `code-validity-review`** when an aspect finding requires walking code paths to confirm or reject. Examples: a metric whose definition is only resolvable by reading the script; a baseline whose true configuration is only in code; a leakage suspicion that needs a data-loader trace.

Output of `code-validity-review` lands inside the same aspect note (an `experiments` or `reproducibility` aspect-note) — it is a deeper evidence layer, not a separate artifact.

## Codex delegation (default mode)

Code-trace is the canonical Codex use case for review work. **Default to delegating the trace to Codex** rather than reading the submitted code line-by-line yourself:

- `codex.run_codex_worker` — full-access subagent that can read the entire submitted code tree, follow imports, grep for patterns, and return a structured trace. Use this when the validity question touches more than one file.
- `codex.ask_codex` — read-only analysis when a single file or short snippet suffices.

Hand Codex: the paper claim being audited, the validity-risk checklist below, the file paths it may read, and a request for a structured finding (claim → code evidence → risk severity → minimum fix). Codex returns evidence; you decide whether the evidence invalidates the claim and write the aspect-note.

Read the code yourself only when (a) Codex returns ambiguous evidence and a human (you) reading two or three specific lines resolves it, or (b) the trace is so short that delegating is overhead.

## When to invoke

- An `experiments` or `reproducibility` aspect-review surfaced a question that cannot be resolved from the submission package alone, and the parent reviewer instance asks for a code-trace.
- The orchestrator is asked directly for a code-trace zoom outside the orchestrated round flow.

If none of those triggers apply, use `aspect-review` with `experiments` or `reproducibility` instead.

## Structure

Every finding is bound to a specific claim, cites a concrete code path / line / config / log / artifact / missing-provenance item, and states the minimum revision or experiment needed to resolve the risk. Style and maintainability are out of scope unless they create a realistic validity risk. The review session is read-only on `branches/**` and writes only under `artifacts/reviews/round-<n>/`.

Validity-risk checklist: data leakage, train / test mixups, hardcoded results, benchmark shortcuts, stale baselines, seed contamination, cherry-picking, metric mismatch, unreported filtering.

## Procedure

1. **Bind code to claims.** Identify the paper claim, experiment report, table, or figure the code supports.
2. **Delegate the trace to Codex.** Hand `codex.run_codex_worker` the claim, the validity-risk checklist, and the submitted code paths. Ask for a structured trace: script → config → data loader → metric → output, with file:line evidence at each step.
3. **Check validity risks** per the checklist above against Codex's returned evidence.
4. **Check reproducibility hooks.** Seeds, configs, commit SHAs, dataset versions, command lines recorded well enough for the claim — Codex can sweep these in one pass.
5. **Separate bugs from style.** Ignore style and maintainability unless they create a realistic validity risk.
6. **Write evidence-backed findings** in the current aspect note with severity, claim affected, evidence pointer (file:line from Codex), and the minimum revision or experiment needed to resolve.

## Pitfalls

- Performing general code review instead of scientific validity review.
- Inferring a bug from unfamiliar style without tracing execution.
- Reading historical review context during a fresh Pass A review.
- Suggesting fixes in any role's branch (e.g. `branches/coder/`, `branches/writer/`); the review session is read-only on `branches/` and writes only under `artifacts/reviews/`.
- Skipping Codex and doing the trace by hand when Codex would do it in one shot.
- Letting Codex *judge* whether a finding invalidates the claim. Codex returns the trace; the validity verdict stays in this skill.

