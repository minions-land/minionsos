# Workspace Structure

Guide for organizing workspace writes so the main branch stays coherent and extractable into a paper.

## Core move

Every file you write to the workspace should be findable by its DAG node. The DAG is the index; the workspace holds the full content. Connect them through evidence_tag references.

## Structure convention

```
workspace/
  logic/                    ← claims and reasoning (What & Why)
    claims.md               ← claim IDs, one per line, with DAG node refs
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

This is a recommendation, not a rigid schema. Adapt to your project's needs. The principle is: a new agent joining the project should be able to navigate from DAG node → workspace file without guessing.

## Procedure

1. **When writing a result:** create `experiments/E-xxx/results.md` and set the DAG node's `evidence_tag` to point there.
2. **When recording a dead end:** create `dead_ends/DEAD-xxx.md` with the full story (not just the one-liner in the DAG).
3. **When making a decision:** create `logic/decisions/D-xxx.md` explaining the rationale, alternatives considered, and what evidence drove the choice.
4. **When verifying a citation:** add to `evidence/citations/` and update the DAG node's `evidence_tag`.
5. **Provenance tag:** at the top of each file, note who wrote it and how:
   ```
   <!-- provenance: expert-1, ai-executed, 2026-05-16 -->
   ```

## When to invoke

- Before writing any file to the workspace — check if it fits the structure.
- During cognitive-checkpoint — ensure new DAG nodes have corresponding workspace files.
- Skip for scratch work that won't survive the session (use your branch freely for drafts).

## Pitfalls

- Writing results without linking to DAG nodes — creates orphan files nobody can find.
- Putting everything in one giant file — breaks progressive disclosure (agents load what they need).
- Skipping dead_ends/ — future agents will re-explore the same failures.
- Over-structuring drafts — this convention is for DURABLE outputs on main branch, not for your working branch.

## Relationship to DAG

```
DAG node (index, one-liner)  ←→  Workspace file (full content)
     H-003: "entropy correlates"  →  logic/hypotheses/H-003.md (full reasoning)
     E-005: "ablation on BERT"    →  experiments/E-005/results.md (data, plots)
     DEAD-002: "random pruning"   →  dead_ends/DEAD-002.md (what went wrong)
```

The DAG is what you query. The workspace is what you read when you need depth.

## Output habit

When creating a workspace file: `[workspace: {path}] linked to DAG node {id}`.
