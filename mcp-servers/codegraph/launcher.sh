#!/usr/bin/env bash
# Launcher for codegraph MCP stdio server, scoped to a MinionsOS project.
#
# Resolves the per-scope Coder graph (.codegraph/codegraph.db) and execs
# `codegraph serve --mcp` from this directory's local node_modules.
#
# Scope resolution:
#   MINIONS_PROJECT_PORT set + branches/coder exists  -> project scope
#   MINIONS_PROJECT_PORT set + branches/coder missing -> repo scope (project mid-creation)
#   MINIONS_PROJECT_PORT unset                         -> repo scope (system maintenance)
#
# This launcher is INTENTIONALLY fail-fast on a missing index. We do NOT
# run `codegraph init -i` here, because:
#   1. Initial indexing on a large project takes tens of seconds and would
#      block / time out the MCP handshake.
#   2. `codegraph init` calls clack interactive prompts. Running it from a
#      non-TTY MCP launcher risks blocking on stdin or polluting stderr.
#
# Index bootstrap is handled out-of-band:
#   - Repo scope: install.sh warms `<repo>/.codegraph/` once during setup.
#   - Project scope: `ensure_role_workspace(port, "coder")` in
#     minions/lifecycle/project.py runs `codegraph init -i` once when the
#     Coder branch worktree is created. Idempotent + non-fatal: if the
#     bootstrap fails, the launcher's error message tells the operator how
#     to recover manually.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CG_BIN="$SCRIPT_DIR/node_modules/.bin/codegraph"
if [[ ! -x "$CG_BIN" ]]; then
    echo "codegraph launcher: $CG_BIN missing." >&2
    echo "Install with: cd $SCRIPT_DIR && npm install" >&2
    exit 1
fi

PORT="${MINIONS_PROJECT_PORT:-}"
if [[ -n "$PORT" ]]; then
    SCOPE="$REPO_ROOT/project_${PORT}/branches/coder"
    if [[ ! -d "$SCOPE" ]]; then
        echo "codegraph launcher: $SCOPE missing; falling back to repo scope." >&2
        SCOPE="$REPO_ROOT"
    fi
else
    SCOPE="$REPO_ROOT"
fi

if [[ ! -d "$SCOPE/.codegraph" ]]; then
    echo "codegraph launcher: index missing at $SCOPE/.codegraph" >&2
    echo "" >&2
    echo "Bootstrap with:" >&2
    echo "  cd $SCOPE" >&2
    echo "  $CG_BIN init -i" >&2
    echo "" >&2
    echo "(Repo scope is normally warmed by install.sh; project scope" >&2
    echo " requires a one-time init in branches/coder/ on first use.)" >&2
    exit 1
fi

cd "$SCOPE"

# `serve --mcp` blocks; its bundled OS-event watcher keeps the index fresh
# (~1s debounce on save, $0 in API spend).
exec "$CG_BIN" serve --mcp
