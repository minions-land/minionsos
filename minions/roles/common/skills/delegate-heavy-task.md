---
slug: delegate-heavy-task
summary: Delegate complex coding tasks to Codex GPT-5.5 via codex-bridge MCP; falls back to Claude subagent if Codex unavailable.
layer: logical
tools: codex
version: 3
status: active
supersedes:
references:
provenance: human
---

# Skill — Delegate Heavy Task

Route high-intensity coding work to Codex GPT-5.5 (via codex-bridge MCP). Fall back to a Claude subagent when Codex is unavailable.

## When to invoke

- Complex debugging that requires reading many files and iterating on fixes
- Cross-file refactoring or architecture changes
- Test failure diagnosis and repair
- Deep code review requiring a second opinion
- Implementation tasks that benefit from autonomous iteration (write → test → fix loop)

## Procedure

1. Call the `codex` MCP tool with `task` and `cwd`. Do not override model, reasoning_effort, or sandbox unless the user explicitly asks.

2. If `codex` returns `CODEX_UNAVAILABLE` or `CODEX_ERROR`, fall back to Agent tool with `model=sonnet`.

3. Review the result before accepting changes.

## Parameters (only use when needed)

- `sandbox: "read-only"` — for analysis in non-git directories
- `skip_git_check: true` — when cwd is not a git repo
- `add_dirs: [...]` — extra directories Codex can access
- `timeout_seconds: N` — extend for large tasks

## Pitfalls

- Always provide an absolute path for `cwd`
- Codex operates autonomously — review its output before accepting
- If Codex times out, break the task into smaller pieces
- For non-git directories, use `sandbox: "read-only"` + `skip_git_check: true`

## Output habit

After receiving results: summarize what was done, review diffs, apply or iterate.
