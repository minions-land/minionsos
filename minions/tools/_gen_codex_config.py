"""Generate .codex/config.toml for Codex MCP integration.

GitHub Issue #27: every MCP server's command/args path must resolve to an
**absolute** path. Codex spawns its MCP children from whichever cwd it
was started in (typically the role's branch worktree), and a relative
``mcp-servers/...`` arg fails to resolve there. We rewrite every relative
arg to an absolute path under *project_root* so the file works no matter
where Codex was launched from.

Usage:
    _gen_codex_config.py <output_path> [project_root]

If *project_root* is omitted it defaults to the parent of *output_path*'s
parent (i.e. the project root that contains the ``.codex/`` directory),
which matches the install.sh invocation.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _block(title: str, command: str, args_repr: str) -> str:
    return f'[mcp_servers.{title}]\ncommand = "{command}"\nargs = {args_repr}\nenabled = true\n'


def _args_toml(args: list[str]) -> str:
    quoted = ", ".join(f'"{a}"' for a in args)
    return f"[{quoted}]"


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: _gen_codex_config.py <output_path> [project_root]",
            file=sys.stderr,
        )
        sys.exit(1)
    output = Path(sys.argv[1]).resolve()
    if len(sys.argv) >= 3:
        project_root = Path(sys.argv[2]).resolve()
    else:
        # output is .codex/config.toml; project root is its grandparent.
        project_root = output.parent.parent.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    parts: list[str] = []
    parts.append(
        _block(
            "minionsos",
            "uv",
            _args_toml(
                [
                    "run",
                    "--project",
                    str(project_root),
                    "python",
                    "-m",
                    "minions.tools.mcp_server",
                ]
            ),
        )
    )
    parts.append('\n[mcp_servers.minionsos.tools.list_roles]\napproval_mode = "approve"\n')
    parts.append(
        "\n# The EACN3 plugin is mounted directly: MinionsOS exposes the full eacn3_*\n"
        "# surface to the role and lets the plugin handle the traffic. Filtering /\n"
        "# draining / ACKing used to live in a MinionsOS proxy; that encapsulation\n"
        "# has been removed. The only MinionsOS wrapper over EACN3 is the Python-side\n"
        "# long-poll scheduler that delivers events to roles in their init prompt.\n"
    )
    parts.append(
        _block(
            "eacn3",
            "node",
            _args_toml(
                [str(project_root / "mcp-servers" / "eacn3" / "plugin" / "dist" / "server.js")]
            ),
        )
    )
    codex_dist = project_root / "mcp-servers" / "codex-subagent" / "dist" / "server.js"
    if codex_dist.is_file():
        parts.append(
            "\n"
            + _block(
                "codex-subagent",
                "node",
                _args_toml([str(codex_dist)]),
            )
        )
    parts.append(
        "\n"
        + _block(
            "keepalive",
            "uv",
            _args_toml(
                [
                    "run",
                    "--quiet",
                    "--no-project",
                    "--with",
                    "mcp[cli]",
                    "python",
                    str(project_root / "mcp-servers" / "keepalive" / "server.py"),
                ]
            ),
        )
    )

    output.write_text("".join(parts), encoding="utf-8")


if __name__ == "__main__":
    main()
