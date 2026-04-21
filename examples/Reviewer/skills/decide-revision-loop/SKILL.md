---
name: decide-revision-loop
description: "Decide whether another revision/review cycle is required"
---

# /decide-revision-loop — Decide Next Review Step

Decide whether the authors must revise and return for another review cycle.

## Goal

Enforce the rule that revision continues unless the work has clearly reached Accept or Strong Accept quality.

## Decision logic

- if major evidence-backed weaknesses remain, require revision
- if claims still exceed support, require revision
- if code-validity or originality risk remains unresolved, require revision
- if the work clearly reaches Accept or Strong Accept, switch to camera-ready-only changes

## Output

Return a review-step decision:
- round id
- verdict state
- whether revision is required
- why
- whether another full round is needed