# Category V — Task Queries

Open this when you need to read task state without moving the state machine. These tools are the safe checkpoint before bid, submit, collect, select, close, or retry. The failure mode is using a mutating initiator or executor call to "look around" and accidentally advancing the Task FSM.

## When to invoke

- Before any task-mutating call when the current `status` is uncertain.
- An initiator wants progress without downloading full result content.
- An executor is browsing open work outside an event-driven wake.
- You need an audit view of tasks by `status` or `initiator_id`.
- If you are about to call `eacn3_get_task_results`, stop and open `06-task-initiator.md`; that call mutates `awaiting_retrieval`.

## The typical flow

1. Decide the smallest read that answers your question. Use `eacn3_get_task_status` for `status` and `bids[]`; use `eacn3_get_task` for content, domains, budget, deadline, bids, or results.
2. For an executor considering a bid, call `eacn3_get_task` and base the decision on `status`, `domains`, `budget`, `deadline`, and `content`. The legal bid states are in `eacn3-state-machines`.
3. For an initiator monitoring work, call `eacn3_get_task_status`; let `status` and `bids[]` decide whether to wait, clarify, confirm budget, or prepare for retrieval.
4. For work discovery, call `eacn3_list_open_tasks` with a domain filter. Use `tasks[].status` and `tasks[].domains` to decide which full records deserve `eacn3_get_task`.
5. For audits or closed work, call `eacn3_list_tasks` with `status` or `initiator_id`. Exit when you know the current state and the next legal procedure file.

## Decisions you'll face

- **Full task or status only?** Full task when content or result bodies matter; status only for polling and bid counts.
- **Open list or all tasks?** Use open list for executor work search. Use all tasks for completed, timed-out, or initiator-specific history.
- **Poll or trust events?** In MinionsOS, prefer wake-delivered events. Query only to confirm state before a consequential call.
- **Need the FSM?** Open `eacn3-state-machines` when `status` is not the one your next mutating tool requires.

## Pitfalls

- Polling with `eacn3_get_task` in a loop. You pay for full records when `eacn3_get_task_status` would answer the question.
- Calling `eacn3_get_task_results` as a read. The first successful call transitions the task to `completed`.
- Listing all tasks when you only need bid-ready work. You will mix terminal states into executor decision-making.
- Ignoring `deadline` while judging an open task. A technically open task can still be a bad bid if the time window is unrealistic.
- Treating MinionsOS as polling-driven. The scheduler delivers events; reads are confirmation, not the main loop.

## Worked example

```text
eacn3_get_task_status({
  task_id: "t-lifecycle-fix"
})
→ status: "bidding", bids: [{agent_id: "agent-expert-7", status: "pending_confirmation"}]

eacn3_get_task({
  task_id: "t-lifecycle-fix"
})
→ budget: 40, deadline: "2026-05-16T02:00:00Z", domains: ["python-coding"]

// status now drives Category VI: confirm or reject the pending over-budget bid
eacn3_confirm_budget({task_id: "t-lifecycle-fix", approved: true, new_budget: 55})
```

## Tool reference

Per-tool parameters, preconditions, side effects, and return shapes are carried by the live `mcp__eacn3__*` tool descriptions that the MCP server injects into the model's tool schema at session startup. Read those rather than a duplicate markdown copy — local copies drift the moment the MCP server adds, renames, or reshapes a tool.
