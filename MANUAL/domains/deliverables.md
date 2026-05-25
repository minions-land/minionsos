---
id: domain-deliverables
kind: domain
domain: deliverables
auth: [gru]
source: minions/tools/mcp/evaluator_tools.py:25
since: stable
keywords: [submit, evaluate, adjudicate, review, deliverable, paper, answer]
related: [mos_submit, mos_evaluate, mos_adjudicate, mos_review_run, pitfall-adjudicate-misuse]
status: stable
---

# Domain: Deliverables (Gru only)

Other roles surface a deliverable to Gru by EACN message; Gru calls these tools.

## The 4 tools, what each does

| Tool | What | When |
|---|---|---|
| `mos_submit` | persist payload under `branches/shared/submissions/` | role hands off final |
| `mos_evaluate` | run profile-defined strategy → `{score, verdict}` | after submit |
| `mos_adjudicate` | pre-grader audit; depth ∈ {single, panel} | only when profile asks |
| `mos_review_run` | one peer-review round (Pass A/B/C) | scientific-paper profile |

## Strategies (set in `minions/profiles/<name>.yaml`)

| Strategy | What | Profile |
|---|---|---|
| `scientific_peer_review` | delegates to `mos_review_run` | scientific-paper |
| `answer_grader` | compares `submissions/answer.json` to `input/expected.json` | hle-answer |
| `test_runner` | runs project test suite | reserved (SWE-bench) |

## Pitfalls

- `mos_adjudicate` is for **final** answers. Calling it for mid-run task
  closure errors with "submissions/answer.json doesn't exist" — see
  `pitfall-adjudicate-misuse`. Use `mos_book_resolve_contradiction` or
  `mos_signboard_evaluate` for mid-project verdicts.

## Full surface

```bash
lookup.py --domain deliverables
```
