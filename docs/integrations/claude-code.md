# Claude Code — Role Host Process

## What we use

| Surface | Purpose | Where |
|---|---|---|
| `claude` CLI binary | Long-lived Role host process | `minions/lifecycle/agent_host.py:build_role_invocation()` |
| `--append-system-prompt @<path>` | Inject role SYSTEM.md + common contract | `agent_host.py` |
| `--allowed-tools <list>` | Per-role tool gating | `minions/config/__init__.py:resolve_whitelist()` |
| `/compact` command (via tmux send-keys) | In-process context compression | `minions/tools/compact.py` |
| PreToolUse / PostToolUse hooks | Write-boundary guard, bg-keepalive nudge, large-file guard, edit-failure rescue | `.claude/settings.json` + `minions/hooks/` |
| Prompt caching (5-min TTL, or 1h with patch) | System-prompt prefix stays cached across turns | `~/.claude/skills/claude-cache-1h-patch/` |
| `Agent` tool (subagent dispatch) | Roles spawn local teams for heavy work | Used by Coder, Gru, Ethics |
| `Task` tool (background bash) | Async shell execution | Used by Noter, Coder |

## Version lock

No explicit pin — we use whatever `claude` binary is installed system-wide.
Version is tracked in `dev-log/claude-code-upstream-changelog.md` (copy of Anthropic's release notes).
Current: **2.1.143**.

## What we explicitly avoid

- **`claude --print` mode** for roles — roles are long-lived interactive
  processes, not one-shot. Only `mos_review_run` uses `--print` (for the
  review persona, which is not a Role).
- **`--dangerously-skip-permissions`** in production role processes. Roles
  run with explicit `--allowed-tools` whitelists.
- **IDE extensions** (VS Code, JetBrains) — MinionsOS uses CLI only.
- **Plugin system** — we don't distribute MinionsOS as a Claude Code plugin.

## Brittle points

1. **`--append-system-prompt` flag.** If renamed or removed, every role
   fails to start. Mitigation: this is a stable, documented flag.
2. **Hook schema.** If `settings.json` hook format changes (matcher syntax,
   env vars passed to hook scripts), all our hooks break. Mitigation: hooks
   are a stable feature; changes are documented in CHANGELOG.
3. **`/compact` command.** If the command name changes or tmux send-keys
   delivery breaks, `mos_compact_context` fails silently. Mitigation: the
   tool logs success/failure; Gru watchdog detects stuck roles.
4. **Prompt cache TTL.** Default 5-min TTL means any inter-turn gap >5 min
   cold-starts the system prompt. The 1h-cache patch mitigates this but
   requires re-patching on every Claude Code update.
5. **`Agent` tool model parameter.** If `model: "haiku"` stops being valid,
   our Tier-2 codex dispatch pattern breaks. Mitigation: model names are
   stable across minor versions.

## Upgrade path

1. Claude Code auto-updates (or manual `claude update`).
2. Check `dev-log/claude-code-upstream-changelog.md` for breaking changes.
3. Re-apply 1h-cache patch if needed: `~/.claude/skills/claude-cache-1h-patch/`.
4. Run `uv run pytest tests/unit/ -x -q` — hooks and agent_host tests catch regressions.
5. Smoke: `./mos doctor` verifies claude binary is reachable.

## Fallback when unavailable

If `claude` binary is missing, nothing works. MinionsOS is built on Claude Code
as the sole agent host. There is no fallback runtime.

## Key references

- Anthropic docs: claude.ai/code
- Our CHANGELOG mirror: `dev-log/claude-code-upstream-changelog.md`
- Hook scripts: `minions/hooks/` (project) + `~/.claude/hooks/` (global)
- Settings: `.claude/settings.json` (project) + `.claude/settings.local.json`
