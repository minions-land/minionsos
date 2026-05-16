# Pre-action Check

Before starting any paper drafting or structuring work, verify that required preconditions are satisfied.

## Core question

Do the artifacts necessary for a meaningful paper currently exist in the project?

## Procedure

1. Before planning or drafting, check the project workspace for the following required artifacts.
2. For each item, confirm it exists as a concrete artifact (file, result, or documented evidence) — not as a plan or intention.
3. If ANY required item is missing → do not start writing. Send an EACN message to the relevant role asking for status, then return to waiting.
4. If all required items exist → proceed with paper planning and drafting.

## Required preconditions (all must be satisfied)

- [ ] Main experiment: quantitative results exist in experiment artifacts
- [ ] Ablation study: at least one ablation with results
- [ ] Case visualization: qualitative examples or visual analysis exist
- [ ] Motivation: research motivation is documented with literature support
- [ ] Mathematical proof or formal derivation (if the contribution is algorithmic/theoretical)

## Optional (incorporate if available, do not block on these)

- [ ] Hyperparameter sensitivity experiment
- [ ] SOTA baseline comparison beyond the main experiment
- [ ] Additional datasets or cross-domain validation

## When to invoke

Every time you consider starting paper work — whether triggered by an event, a message, or your own judgment. This check is non-negotiable and precedes all drafting activity.

## Output habit

If preconditions are not met, your only output should be:
1. A brief status note identifying what is missing
2. An EACN message to the responsible role requesting the missing artifact
3. Return to `mos_await_events`

Do not produce outlines, drafts, or structural plans when preconditions are unmet. Planning without evidence leads to premature commitment that wastes tokens and pollutes memory.
