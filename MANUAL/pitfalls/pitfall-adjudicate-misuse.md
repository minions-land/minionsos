---
id: pitfall-adjudicate-misuse
kind: pitfall
domain: deliverables
auth: [gru, ethics]
source: minions/tools/mcp/evaluator_tools.py:60
since: stable
keywords: [adjudicate, mid, run, closure, submission, answer, panel]
related: [mos_adjudicate, mos_submit, mos_book_resolve_contradiction, mos_signboard_evaluate]
status: stable
---

# pitfall: `mos_adjudicate` errored looking for `submissions/answer.json`

**Symptom (project_37596 / role-ethics):**
```
mos_adjudicate ... → "submissions/answer.json doesn't exist"
```
Ethics tried to use `mos_adjudicate` because Gru asked to "adjudicate"
pending events.

## Cause

`mos_adjudicate` is the **project-final answer adjudicator**. It expects:
- `branches/shared/submissions/answer.json` already populated (via `mos_submit`).
- Profile's `evaluation.adjudication.depth ∈ {single, panel}`.

The default `scientific-paper` profile has `depth: none` — `mos_adjudicate`
never fires during the run.

## Use the right tool for mid-project verdicts

| Need | Tool |
|---|---|
| Resolve a Book contradiction | `mos_book_resolve_contradiction` |
| Phase-transition consensus | `mos_signboard_evaluate` |
| Ethics audit verdict | publish to `branches/shared/ethics/` |
| Per-task EACN closure | `eacn3_select_result` + `eacn3_close_task` |

## When `mos_adjudicate` IS the right tool

- The project is a `hle-answer` / `mmlu` / `gpqa` profile, AND
- A previous `mos_submit(kind="answer", ...)` populated `submissions/answer.json`.
