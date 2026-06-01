"""Generate .mcp.json for Claude Code — conditional MCP server registration.

minionsos, eacn3, and keepalive are system-level (always registered).

GitHub Issue #27: every MCP server's command/args path must resolve to an
**absolute** path. Role processes are launched with ``cwd=branches/<role>/``
(the role's git worktree), not the MinionsOS repo root. ``node mcp-servers/
eacn3/plugin/dist/server.js`` then fails because Node does not walk up the
directory tree looking for the script. ``minionsos`` only worked by accident
because ``uv run --project .`` does walk up looking for ``pyproject.toml``.
We rewrite every relative arg to an absolute path under *project_root*.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: _gen_mcp_json.py <project_root>", file=sys.stderr)
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    servers: dict = {}

    # ``uv run --project <abs>`` — pin to MinionsOS root so role-cwd worktrees
    # also resolve the right project. (Previously ``--project .`` worked only
    # because uv walks up looking for pyproject.toml, but pinning is clearer.)
    servers["minionsos"] = {
        "type": "stdio",
        "command": "uv",
        "args": [
            "run",
            "--project",
            str(root),
            "python",
            "-m",
            "minions.tools.mcp_server",
        ],
        "env": {},
    }
    servers["eacn3"] = {
        "type": "stdio",
        "command": "node",
        "args": [str(root / "mcp-servers" / "eacn3" / "plugin" / "dist" / "server.js")],
        "env": {},
    }

    servers["keepalive"] = {
        "type": "stdio",
        "command": "uv",
        "args": [
            "run",
            "--quiet",
            "--no-project",
            "--with",
            "mcp[cli]",
            "python",
            str(root / "mcp-servers" / "keepalive" / "server.py"),
        ],
        "env": {},
    }

    mcp = {"mcpServers": servers}
    output = root / ".mcp.json"
    output.write_text(json.dumps(mcp, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
