---
name: spawn-subspect-reviewers
description: "Open focused review subagents for narrow subspects within one review round"
---

# /spawn-subspect-reviewers — Open Narrow Reviewers

Open focused review subagents for one review round.

## Goal

One round should simulate one reviewer opinion. To do that, open multiple narrow review subagents, each responsible for one subspect only.

## Typical subspects

- novelty
- theory originality
- code validity
- experiment validity
- writing and clarity
- limitations and scope

## Specialized subspects

Add focused reviewers when useful for:
- plagiarism or originality risk
- code-level false gain risk such as leakage, script bugs, evaluation flaws, or benchmark loopholes

## Perturbation

You may apply mild attitude or bias variation to reduce convergence across rounds, but evidence remains mandatory.

## Output

Return a round setup record:
- round id
- opened subspects
- perturbation notes
- assigned reviewer focus