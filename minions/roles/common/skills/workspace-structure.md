---
slug: workspace-structure
summary: Guide for organizing workspace writes so the main branch stays coherent and extractable into a paper. Scratchpad is the index; workspace holds the full content.
layer: structural
tools: mos_scratchpad_append, mos_scratchpad_annotate
version: 2
status: active
supersedes:
references: cognitive-checkpoint
provenance: human
---

# Skill — Workspace Structure

Every durable shared file should be findable by its Scratchpad node. The Scratchpad is the index; role branches and the shared worktree hold the full content. Connect them through `evidence_tag` references. A new agent joining the project should be able to navigate from Scratchpad node → workspace file without guessing.

## When to invoke

- Before writing any durable file to the workspace — check if it fits the structure.
- During cognitive-checkpoint — ensure new Scratchpad nodes have corresponding workspace files.
- Skip for scratch work that won't survive the session (use your branch freely for drafts).

## Structure

```
branches/shared/
  logic/                    ← claims and reasoning (What & Why)
    claims.md               ← claim IDs, one per line, with Scratchpad node refs
    hypotheses/             ← one file per active hypothesis (H-xxx.md)
    decisions/              ← one file per major decision (D-xxx.md)
  experiments/              ← experiment designs and results (How)
    E-xxx/                  ← one directory per experiment
      design.md             ← what we're testing, method, expected outcome
      config.yaml           ← hyperparameters, seeds, environment
      results.md            ← findings, with figures/tables inline or referenced
  evidence/                 ← raw proof (receipts)
    tables/                 ← CSV, JSON data files
    figures/                ← plots, diagrams
    citations/              ← verified BibTeX, verification notes
  dead_ends/                ← preserved failures (one file per DEAD-xxx)
    DEAD-xxx.md             ← what was tried, why it failed, what we learned
```

This is a recommendation, not a rigid schema. Adapt to your project's needs. The principle is navigability from Scratchpad to content.

The Scratchpad and workspace relate as index to content:

```
Scratchpad node (index, one-liner)  ←→  Workspace file (full content)
     H-003: "entropy correlates"  →  logic/hypotheses/H-003.md
     E-005: "ablation on BERT"    →  experiments/E-005/results.md
     DEAD-002: "random pruning"   →  dead_ends/DEAD-002.md
```

## Procedure

1. **When writing a result:** create `experiments/E-xxx/results.md` and set the Scratchpad node's `evidence_tag` to point there.
2. **When recording a dead end:** create `dead_ends/DEAD-xxx.md` with the full story (not just the one-liner in the Scratchpad).
3. **When making a decision:** create `logic/decisions/D-xxx.md` explaining the rationale, alternatives considered, and what evidence drove the choice.
4. **When verifying a citation:** add to `evidence/citations/` and update the Scratchpad node's `evidence_tag`.
5. **Provenance tag** at the top of each file: `<!-- provenance: expert-1, ai-executed, 2026-05-16 -->`.

This structure applies to durable shared outputs published through the role's allowed shared subdirs. It does not constrain how you think, what you write on your role branch, what types of Scratchpad nodes you create, or whether you follow this structure for intermediate work. Structure is for communication (so others can find your work), not for cognition. If a discovery doesn't fit any category, write it anyway — the worst outcome is a discovery not recorded at all.

## Pitfalls

- Writing results without linking to Scratchpad nodes — creates orphan files nobody can find.
- Putting everything in one giant file — breaks progressive disclosure.
- Skipping dead_ends/ — future agents will re-explore the same failures.
- Over-structuring drafts — this convention is for durable outputs, not working-branch scratch.
