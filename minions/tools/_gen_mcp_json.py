"""Generate .mcp.json for Claude Code — conditional MCP server registration.

minionsos, eacn3, keepalive, graphify, and codegraph are always registered
(core stack). codex-subagent is only registered if its dist/server.js exists.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: _gen_mcp_json.py <project_root>", file=sys.stderr)
        sys.exit(1)
    root = Path(sys.argv[1])
    servers: dict = {}

    servers["minionsos"] = {
        "type": "stdio",
        "command": "uv",
        "args": ["run", "--project", ".", "python", "-m", "minions.tools.mcp_server"],
        "env": {},
    }
    servers["eacn3"] = {
        "type": "stdio",
        "command": "node",
        "args": ["mcp-servers/eacn3/plugin/dist/server.js"],
        "env": {},
    }

    codex_dist = root / "mcp-servers" / "codex-subagent" / "dist" / "server.js"
    if codex_dist.is_file():
        servers["codex-subagent"] = {
            "type": "stdio",
            "command": "node",
            "args": ["mcp-servers/codex-subagent/dist/server.js"],
            "env": {},
        }
        print("  codex-subagent: registered (dist/server.js found)")
    else:
        print("  codex-subagent: skipped (not built)")

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
            "mcp-servers/keepalive/server.py",
        ],
        "env": {},
    }
    servers["graphify"] = {
        "type": "stdio",
        "command": "bash",
        "args": ["mcp-servers/graphify/launcher.sh"],
        "env": {},
    }
    servers["codegraph"] = {
        "type": "stdio",
        "command": "bash",
        "args": ["mcp-servers/codegraph/launcher.sh"],
        "env": {},
    }

    mcp = {"mcpServers": servers}
    output = root / ".mcp.json"
    output.write_text(json.dumps(mcp, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
