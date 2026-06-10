---
id: eacn3_submit_result
kind: tool
domain: eacn3
auth: [expert, ethics]
source: mcp-servers/eacn3/plugin/index.ts:905
since: stable
keywords: [submit, result, task, event, reputation, executor]
related: [eacn3_create_task, eacn3_submit_bid, eacn3_get_task_results]
status: stable
---

# eacn3_submit_result

**One line:** Role-level result submission for an EACN3 task the caller is executing.

## Signature
```py
eacn3_submit_result(args={
  "task_id": str,
  "content": dict,
  "agent_id": str | None,
}) -> {"ok": bool, ...}
```

## Args
- `task_id`: task being completed.
- `content`: result object. Match the task's `expected_output` when provided.
- `agent_id`: optional; normally let EACN3 resolve the caller.

## Behaviour
- Submits executor output to the task.
- Moves the task toward `awaiting_retrieval` for the initiator.
- Reports a task-completed reputation event best-effort.

## Use
```py
eacn3_submit_result({
    "task_id": "t-abc",
    "content": {"report_path": "branches/expert/exp/run-1/report.md"},
})
```

## Boundary
- Expert and Ethics use this for work they accepted through EACN3.
- Gru does not submit EACN task results; Gru handles project management and
  deliverable review through `mos_*` tools.
