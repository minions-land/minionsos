---
slug: delegate-heavy-task
summary: Codex GPT-5.5 (via codex-subagent MCP) is an opt-in tool, not a required tier. Workflow is the canonical Act mechanism (common §4); a Workflow agent MAY call codex when GPT-5.5 xhigh materially helps. Direct codex calls from main are host-fallback only.
layer: logical
tools: codex
version: 4
status: active
supersedes:
references: think-then-act, dialectical-synthesis
provenance: human+agent
---

# Skill — Delegate Heavy Task

## What changed

In v17 the forced dispatch ladder (Codex-as-required-tier with Sonnet
fallback) was retired. The canonical Act mechanism is the **Workflow
tool** — common SYSTEM.md §4. Codex remains useful as an opt-in tool a
Workflow agent can call when xhigh GPT-5.5 reasoning materially helps:
deep paper-PDF reasoning, multi-file root-cause analysis, cross-stack
code synthesis. It is no longer the required default.

## When to call codex

Inside a Workflow agent (preferred):

- Deep PDF / large-document analysis where Claude's context window or
  visual reasoning falls short.
- Multi-file refactor where xhigh deliberation about side effects pays
  off.
- Cross-stack debugging that needs to read source across multiple
  languages and runtimes.
- Second-opinion on a finding the Workflow's primary agent landed.

From main (host-fallback only, per common §4 host-fallback ladder):

- The Workflow tool is unreachable AND a Task subagent cannot satisfy
  the acceptance criterion.
- The task is read-and-judge work that does NOT need Claude Code
  harness-native tools (`Read`/`Edit`/`Write`/`SendMessage`/
  Plan mode/`TodoWrite`) as actions to satisfy the criterion. (If it
  does, Sonnet is the right fallback, not codex.)

## Procedure

1. Call `mcp__codex-subagent__codex` with `task` (string) and `cwd`
   (absolute path; defaults to the role's branch worktree). Do not
   override `model`, `reasoning_effort`, or `sandbox` unless the user
   explicitly asks.
2. The 5-retry CODEX_UNAVAILABLE relay envelope from
   `~/.claude/skills/codex/SKILL.md` applies; that skill is host-level.
3. Pass the same scratchpad-isolation prompt fragment the Workflow
   spec carries (common §10.1):

   ```
   SCRATCHPAD: Write only inside ./.claude/scratchpad/ (resolves to $MINIONS_ROLE_BRANCH/.claude/scratchpad/). Do not cd, do not write to ~/.claude/, /Users/mjm/MinionsOS/.claude/, projects/project_*/.claude/ outside your own branch, or any other branches/<role>/.claude/.
   ```

4. Review the structured return before relaying through EACN.

## Parameters

- `sandbox: "read-only"` — for analysis in non-git directories.
- `skip_git_check: true` — when cwd is not a git repo.
- `add_dirs: [...]` — extra directories Codex can access.
- `timeout_seconds: N` — extend for large tasks.

## Pitfalls

- Codex operates autonomously — review its output before accepting.
- For multi-file tasks, spell out NON-GOALS explicitly in the `task`
  string; this stops Codex from drifting into adjacent work.
- Always provide an absolute path for `cwd`. Under hermetic mode the
  branch path is in `MINIONS_ROLE_BRANCH`; the hermetic stub is in
  `MINIONS_ROLE_HERMETIC_DIR` (when set).
- If Codex times out twice, break the task into smaller pieces — do
  NOT bypass the Workflow contract by enlarging the inline call.

## Output habit

After Codex returns: summarize what was done, review diffs, verify
acceptance criteria, then `mos_publish_to_shared` (main only) or
relay through EACN. Mark derived claims with
`[derived: codex-<task-id>]` per `evidence-driven-proposal`.
