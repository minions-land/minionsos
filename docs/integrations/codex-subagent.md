# Codex GPT-5.5 — High-Intensity Execution Subagent

## What we use

| Surface | Purpose | Where |
|---|---|---|
| `codex` MCP tool (single tool) | Delegate read-only analysis or full-access execution to GPT-5.5 | `mcp-servers/codex-subagent/dist/server.js` |
| `sandbox: "read-only"` | Safe analysis without writes | Used by Ethics, Expert for deep-dive |
| `sandbox: "danger-full-access"` | Full execution (file writes, shell, git) | Used by Coder for implementation |
| `reasoning_effort: "xhigh"` | Maximum reasoning depth | Default for all Tier-2 dispatches |

## Version lock

The codex-subagent MCP server is a Node.js bridge at `mcp-servers/codex-subagent/`.
It calls the `codex` CLI binary (OpenAI) which must be installed system-wide.
Model is pinned to `gpt-5.5` in the MCP server config (not configurable per-call
in the current bridge — the `model` field in the tool schema is accepted but
the bridge always uses gpt-5.5).

## Dispatch model

Two-tier (documented in `~/.claude/CLAUDE.md` and `~/.claude/skills/codex/SKILL.md`):

| Tier | Actor | Mechanism |
|---|---|---|
| 1 (trivial) | Haiku alone | `Agent(model: "haiku")` direct |
| 2 (default) | **Codex GPT-5.5 xhigh** | `Agent(model: "haiku", run_in_background: true)` as thin relay → calls `codex` MCP |

Sonnet is degraded fallback only (when codex returns `CODEX_UNAVAILABLE` or `CODEX_ERROR`).

The Haiku wrapper is plumbing — its only job is to expose Codex through Claude
Code's first-class Agent infrastructure (so we get `run_in_background`, cache
keepalive via `wait_bg`, and a clean structured summary back).

## What we explicitly avoid

- **Codex as Role host.** Codex never hosts a long-lived Role process. It is
  always a one-shot delegated execution within a Role's context.
- **Direct codex CLI invocation from role code.** Always go through the MCP
  bridge so the call is logged, sandboxed, and timeout-controlled.
- **Codex for trivial tasks.** Haiku alone handles lookups, formatting, narrow Q&A.

## Brittle points

1. **`codex` CLI binary.** If OpenAI renames or removes the CLI, the bridge
   breaks. Mitigation: the bridge catches `CODEX_UNAVAILABLE` and the
   dispatch skill falls back to Sonnet.
2. **Model name `gpt-5.5`.** If deprecated, the bridge needs a model update.
   Mitigation: single config point in `mcp-servers/codex-subagent/`.
3. **Sandbox enforcement.** The bridge trusts the `sandbox` parameter and
   passes it to codex. If codex changes its sandbox semantics, our security
   boundary shifts. Mitigation: we only use `read-only` for analysis and
   `danger-full-access` for implementation — no middle ground to break.
4. **Token limits.** Codex has its own context window. Very large tasks may
   hit it. Mitigation: split large tasks into parallel sub-tasks (Step 4
   in the /codex skill).

## Upgrade path

1. Update `mcp-servers/codex-subagent/` source if the codex CLI API changes.
2. `cd mcp-servers/codex-subagent && npm run build`.
3. Test: dispatch a trivial codex task and confirm structured result returns.
4. If model name changes, update the bridge config + `~/.claude/CLAUDE.md` tiering table.

## Fallback when unavailable

The `/codex` skill Step 5 automatically falls back to `Agent(model: "sonnet")`
when codex returns an error. The user sees "codex unavailable, fell back to
Sonnet" in the summary. No manual intervention needed.

## Key references

- Bridge source: `mcp-servers/codex-subagent/`
- Dispatch skill: `~/.claude/skills/codex/SKILL.md`
- Tiering config: `~/.claude/CLAUDE.md` "subagent dispatch defaults" section
