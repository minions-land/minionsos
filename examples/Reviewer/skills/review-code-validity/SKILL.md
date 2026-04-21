---
name: review-code-validity
description: "Review clean submission code for validity risks such as leakage, bugs, or evaluation loopholes"
---

# /review-code-validity — Review Code Validity

Review the clean submission-ready code for validity risks.

## Goal

Detect cases where apparent gains may be fake or unreliable because of implementation or evaluation problems.

## Check

- data leakage
- script bugs
- evaluation flaws
- benchmark loopholes
- implementation mismatches with the paper description
- suspicious shortcuts that could create false gains

## Evidence rule

Tie criticism to concrete code locations, pipeline behavior, or evaluation findings whenever possible.

## Output

Return a focused code-validity review:
- weaknesses
- questions
- detected risks
- evidence list
- required revisions