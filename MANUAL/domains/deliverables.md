---
id: domain-deliverables
kind: domain
domain: deliverables
auth: [gru]
source: minions/tools/mcp/evaluator_tools.py:25
since: stable
keywords: [submit, evaluate, adjudicate, review, deliverable, paper, answer]
related: [mos_submit, mos_evaluate, mos_review_run]
status: stable
---

# Domain: Deliverables (Gru only)

Other roles surface a deliverable to Gru by EACN message; Gru calls these tools.

## The 3 tools, what each does

| Tool | What | When |
|---|---|---|
| `mos_submit` | persist payload under `branches/shared/submissions/` | role hands off final |
| `mos_evaluate` | run profile-defined strategy → `{score, verdict}` | after submit |
| `mos_review_run` | one peer-review round (Pass A/B/C) | scientific-paper profile |

## Strategies (set in `minions/profiles/<name>.yaml`)

| Strategy | What | Profile |
|---|---|---|
| `scientific_peer_review` | delegates to `mos_review_run` | scientific-paper |

## Full surface

```bash
lookup.py --domain deliverables
```
