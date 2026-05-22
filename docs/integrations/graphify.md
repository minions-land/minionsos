# graphify — Layer 3 Structural Index

## What we use

| Surface | Purpose | Where |
|---|---|---|
| `graphify extract <path> --backend claude-cli --no-cluster` | Build corpus graph from `branches/shared/` artifacts | `mcp-servers/graphify/extract.py` |
| `python -m graphify.serve <graph.json>` | Stdio MCP server exposing read-only graph queries | `.mcp.json` → `mcp-servers/graphify/launcher.sh` |
| MCP tools: `query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path` | All roles query the corpus graph | Whitelisted in `minions/config/__init__.py:_GRAPHIFY_READ_TOOLS` |

## Version lock

```
# mcp-servers/graphify/pyproject.toml
dependencies = ["graphifyy>=0.8.13,<0.9", "mcp>=1.0"]
```

Installed in an isolated `.venv` at `mcp-servers/graphify/.venv/` — does
NOT pollute the main MinionsOS venv. Install:
```bash
cd mcp-servers/graphify && VIRTUAL_ENV=$PWD/.venv uv venv && VIRTUAL_ENV=$PWD/.venv uv pip install -e .
```

## What we explicitly avoid

- **Skill-mode extraction** (the `/graphify` Claude Code skill pipeline with
  parallel subagents). We use headless `extract` CLI only.
- **`--backend` other than `claude-cli`**. We route through the host Claude
  Code session so there's zero API cost and no key management.
- **`graphify prs`** — deferred to Phase 8 (review-scope decider).
- **`~/.graphify/global.json`** cross-project graph — deferred to Phase 9.
- **Obsidian / HTML / SVG / Neo4j exports** — agents don't need visual output.
  Viz dashboard could consume `graph.html` later.

## Brittle points (what breaks on upstream update)

1. **`extract` CLI flags.** If `--no-cluster` or `--backend claude-cli` are
   renamed/removed, `mcp-servers/graphify/extract.py` breaks. Mitigation:
   pin `<0.9`; test on upgrade.
2. **MCP tool names.** If `graphify.serve` renames `query_graph` → something
   else, our whitelist + role prompts break. Mitigation: the MCP server is
   versioned with the package; pin ceiling.
3. **`graph.json` schema.** We read `nodes` and `links` keys. If the schema
   changes (e.g. `links` → `edges` happened historically in v0.7.10), the
   launcher's stub graph and any direct reads break. Mitigation: graphify
   normalizes on load; our stub uses `links`.
4. **`--backend claude-cli` routing.** This routes extraction through the
   host Claude Code CLI. If Claude Code changes its stdin/stdout protocol,
   graphify's claude-cli backend breaks. Mitigation: this is graphify's
   problem to fix; we just pin version.

## Upgrade path

1. Bump version in `mcp-servers/graphify/pyproject.toml`.
2. `cd mcp-servers/graphify && VIRTUAL_ENV=$PWD/.venv uv pip install -e .`
3. Run: `.venv/bin/graphify --help | grep extract` — confirm subcommand exists.
4. Run: `uv run pytest tests/unit/test_graphify_mount.py -x -q` — confirm mocks pass.
5. Smoke: create a temp dir with one .md file, run `.venv/bin/graphify extract <dir>`,
   confirm `graph.json` written.
6. If all green, commit with dev-log entry noting the version bump + what changed upstream.

## Fallback when unavailable

`_maybe_rebuild_shelf_graph` in `noter_wait.py` returns `{"rebuilt": False, "reason": "graphify venv not installed"}`. All roles still function — they just can't query the Shelf. The Book layer (Layer 2) works independently.

## Key upstream references

- Repo: `safishamsi/graphify` (default branch `v8`, ~49k stars)
- Changelog: in-repo `CHANGELOG.md` (we have a snapshot at `~/.claude/projects/.../tool-results/`)
- MCP server source: `graphify/serve.py` in the package
- Our SKILL.md (for human operator use): `~/.claude/skills/graphify/SKILL.md` (currently v0.7-era; needs refresh to v0.8.13)
