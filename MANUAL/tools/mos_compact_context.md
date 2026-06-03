---
id: mos_compact_context
kind: tool
domain: runtime
auth: [gru, expert, ethics]
source: minions/tools/mcp/runtime_tools.py:186
since: stable
keywords: [compact, context, token, summary, resume, harness]
related: [mos_reset_context, mos_await_events]
status: stable
---

# mos_compact_context

**One line:** Ask the harness to compact and resume.

## Signature
```py
mos_compact_context(
  reason: str | None,
  preserve: list[str] | None,    # paths/sections to keep verbatim
) -> { compacted: bool, summary_path }
```

## When to call
- Token usage > ~70 % of session budget AND your work is not done.
- After a long subagent / codex bundle dumped into context.

## Don't
- Don't compact mid-tool-chain. Finish the current chain first.
- Don't compact and immediately re-read everything — the summary is meant to suffice.

## vs `mos_reset_context`
- `_compact` keeps state, summarises history.
- `_reset` drops a marker; next wake is a clean boot. Persist your plan to
  Draft FIRST.
