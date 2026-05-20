#!/usr/bin/env bash
# Launcher for graphify MCP stdio server, scoped to a MinionsOS project.
#
# Resolves the per-project Atlas (atlas.json) from MINIONS_PROJECT_PORT
# and execs `python -m graphify.serve` from this directory's .venv.
#
# If the atlas.json does not yet exist (project freshly created, Noter has
# not run extract yet), an empty stub graph is written so graphify.serve
# starts cleanly and hot-reloads when Noter writes the real atlas later.
#
# Wired into .mcp.json as the `graphify` server entry. Read-only MCP tools
# (query_graph / get_node / get_neighbors / get_community / god_nodes /
# graph_stats / shortest_path) are whitelisted in
# minions/config/__init__.py for every main role.

set -euo pipefail

# Resolve script dir robustly even when invoked via symlink.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

VENV_PY="$SCRIPT_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
    echo "graphify launcher: $VENV_PY missing." >&2
    echo "Install with: cd $SCRIPT_DIR && VIRTUAL_ENV=\$PWD/.venv uv pip install -e ." >&2
    exit 1
fi

PORT="${MINIONS_PROJECT_PORT:-}"
if [[ -z "$PORT" ]]; then
    echo "graphify launcher: MINIONS_PROJECT_PORT must be set." >&2
    exit 1
fi

GRAPH_PATH="$REPO_ROOT/project_${PORT}/branches/shared/atlas/atlas.json"
mkdir -p "$(dirname "$GRAPH_PATH")"

if [[ ! -s "$GRAPH_PATH" ]]; then
    cat > "$GRAPH_PATH" <<'JSON'
{"directed": true, "graph": {}, "nodes": [], "links": [], "communities": {}}
JSON
fi

exec "$VENV_PY" -m graphify.serve "$GRAPH_PATH"
