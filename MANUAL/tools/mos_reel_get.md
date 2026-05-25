---
id: mos_reel_get
kind: tool
domain: memory
auth: [gru, coder, ethics, writer, expert]
source: minions/tools/mcp/reel_tools.py:22
since: stable
keywords: [reel, raw, transcript, subagent, audit, codex, agent]
related: [mos_reel_window, pitfall-subagent-boilerplate]
status: stable
---

# mos_reel_get

**One line:** Drill into the raw transcript of a specific subagent / Codex call.

## Signature
```py
mos_reel_get(ref: str) -> {
  transcript_path: str,
  task_id: str,
  invoked_at: str,
  tool_name: str,             # "Agent" | "Task" | "mcp__codex-subagent__codex"
  prompt: str,
  output: str,                # full verbatim output
  events: [ ... ],            # sub-tool calls inside the subagent
}
```

`ref` shape: `"<role>/<session_id>/<task_id>"`. Copy it from
`metadata.reel_ref` on any Draft node or Book page.

## Permission boundary
- Each role can read its own reel.
- Gru can read any role's reel (cross-role audit).
- Noter cannot read reel at all.

## Use case
project_37596 / Ethics dispatched a subagent to verdict 18 contradictions.
The output stamped boilerplate "needs-experiment" verdicts. Ethics ran
`mos_reel_get(ref=...)` to confirm the subagent only read 2 of 18 inputs
before deciding. Verdicts rejected, redone inline.

## See also
- domain-memory
- mos_reel_window
- pitfall-subagent-boilerplate
