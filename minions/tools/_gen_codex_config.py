"""Generate .codex/config.toml for Codex MCP integration."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: _gen_codex_config.py <output_path>", file=sys.stderr)
        sys.exit(1)
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    config = (
        "[mcp_servers.minionsos]\n"
        'command = "uv"\n'
        'args = ["run", "--project", ".", "python", "-m", "minions.tools.mcp_server"]\n'
        "enabled = true\n"
        "\n"
        "[mcp_servers.eacn3]\n"
        'command = "node"\n'
        'args = ["mcp-servers/eacn3/plugin/dist/server.js"]\n'
        "enabled = true\n"
    )
    output.write_text(config, encoding="utf-8")


if __name__ == "__main__":
    main()
