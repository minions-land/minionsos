# Third-Party Integrations

How MinionsOS uses, adapts, and depends on external projects. Each file
documents: what we use, where the version is locked, the specific surface
we depend on, what we explicitly avoid, brittle points that break on
updates, and the upgrade/fallback strategy.

## Index

| Dependency | Our surface | Version lock | Doc |
|---|---|---|---|
| **EACN3** | Per-project coordination backend (SQLite + HTTP + Node MCP plugin) | Editable dep in root `pyproject.toml` pointing at `mcp-servers/eacn3/` | [eacn3.md](eacn3.md) |
| **Claude Code** (Anthropic CLI) | Role host process, hooks, settings, prompt caching | System install; version tracked in `dev-log/CHANGELOG.md` | [claude-code.md](claude-code.md) |
| **Codex GPT-5.5** (OpenAI) | High-intensity execution subagent via `mcp-servers/codex-subagent/` | Node MCP bridge; model pinned to `gpt-5.5` in dispatch | [codex-subagent.md](codex-subagent.md) |

## Principles

1. **Boundary, not fork.** We consume these projects through their public
   CLI / MCP / HTTP surface. We never patch their source. If we need
   behavior they don't offer, we wrap (adapter module or MCP shim).
2. **Version pin with ceiling.** Every dep has a floor (minimum working
   version) and a ceiling (next major). Upgrades are deliberate events
   tested against our unit suite before merge.
3. **Fallback path.** Each integration has a degraded mode when the dep
   is unavailable (codex: fall back to Sonnet; EACN3: project can't
   start; Claude Code: nothing works).
4. **Audit trail.** Version bumps are logged in `dev-log/` with the
   reason, what changed in the upstream, and what we tested.
