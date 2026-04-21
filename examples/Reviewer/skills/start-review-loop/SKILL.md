---
name: start-review-loop
description: "Start a multi-round review loop over a paper and its clean submission-ready code"
---

# /start-review-loop — Start Review Loop

Start a structured review loop for a target paper.

## Goal

Reviewer organizes repeated rounds of evidence-backed review. One round corresponds to one reviewer opinion composed from multiple narrow subspect checks.

## Include

- review target
- available inputs: PDF, clean code, supporting materials
- intended round count
- whether previous rounds already exist
- whether convergence suggests fewer later rounds

## Default policy

- run at least 3 rounds in normal cases
- commonly run 3 to 5 rounds total
- stop early only when later rounds become clearly redundant or strongly convergent

## Output

Return a review-loop plan:
- target
- planned round count
- input set
- expected subspects
- stopping rule