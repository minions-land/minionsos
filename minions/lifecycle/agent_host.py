"""Agent-host command builders for Claude Code and Codex.

MinionsOS keeps project lifecycle, EACN routing, and role wake-up logic
provider-neutral. This module contains the narrow layer that turns a role
activation into a concrete local agent CLI invocation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from minions.config import GruConfig
from minions.paths import MINIONS_ROOT, project_dir


@dataclass(frozen=True)
class RoleInvocation:
    """Concrete subprocess invocation for one ephemeral role wake-up."""

    host_name: str
    command: list[str]
    cwd: Path
    stdin_text: str


def build_role_invocation(
    *,
    cfg: GruConfig,
    role_name: str,
    project_port: int,
    system_path: Path | None,
    allowed_tools: str,
    message: str,
    workspace: Path,
) -> RoleInvocation:
    """Build the configured agent-host command for an ephemeral role."""
    host = cfg.effective_agent_host()
    if host == "codex":
        return _build_codex_role_invocation(
            cfg=cfg,
            role_name=role_name,
            project_port=project_port,
            system_path=system_path,
            allowed_tools=allowed_tools,
            message=message,
            workspace=workspace,
        )
    return _build_claude_role_invocation(
        system_path=system_path,
        allowed_tools=allowed_tools,
        message=message,
        workspace=workspace,
    )


def _build_claude_role_invocation(
    *,
    system_path: Path | None,
    allowed_tools: str,
    message: str,
    workspace: Path,
) -> RoleInvocation:
    """Preserve the existing Claude Code role invocation exactly."""
    cmd = [
        "uv",
        "run",
        "--project",
        str(MINIONS_ROOT),
        "claude",
    ]
    if system_path and system_path.exists():
        cmd += ["--append-system-prompt", f"@{system_path}"]
    cmd += [
        "--mcp-config",
        str(MINIONS_ROOT / ".mcp.json"),
        "--allowed-tools",
        allowed_tools,
        "--permission-mode",
        "bypassPermissions",
        "-p",
    ]
    return RoleInvocation(
        host_name="claude",
        command=cmd,
        cwd=workspace if workspace.exists() else MINIONS_ROOT,
        stdin_text=message,
    )


def _build_codex_role_invocation(
    *,
    cfg: GruConfig,
    role_name: str,
    project_port: int,
    system_path: Path | None,
    allowed_tools: str,
    message: str,
    workspace: Path,
) -> RoleInvocation:
    """Build a Codex non-interactive role invocation.

    Codex does not expose Claude's ``--append-system-prompt`` or
    ``--allowed-tools`` flags. We inline the combined system prompt in stdin
    and rely on MinionsOS MCP server-side authorization for project lifecycle
    tools. The Codex working root stays at ``MINIONS_ROOT`` so project-local
    ``.codex/config.toml`` can be loaded, while the runtime project directory is
    added as a writable directory.
    """
    cmd = [
        "codex",
        "exec",
        "--cd",
        str(MINIONS_ROOT),
        "--add-dir",
        str(project_dir(project_port)),
        "--sandbox",
        cfg.codex_sandbox,
        "--ask-for-approval",
        cfg.codex_approval_policy,
        "--ephemeral",
    ]
    if cfg.codex_model:
        cmd += ["--model", cfg.codex_model]
    cmd.append("-")

    stdin_text = _codex_stdin(
        role_name=role_name,
        project_port=project_port,
        system_path=system_path,
        allowed_tools=allowed_tools,
        message=message,
        workspace=workspace,
    )
    return RoleInvocation(
        host_name="codex",
        command=cmd,
        cwd=MINIONS_ROOT,
        stdin_text=stdin_text,
    )


def _codex_stdin(
    *,
    role_name: str,
    project_port: int,
    system_path: Path | None,
    allowed_tools: str,
    message: str,
    workspace: Path,
) -> str:
    pdir = project_dir(project_port)
    parts = [
        "# MinionsOS Codex Role Invocation",
        "",
        f"You are the MinionsOS `{role_name}` role for project `{project_port}`.",
        "This is an ephemeral role wake-up. Complete or checkpoint the event batch, then exit.",
        "",
        "Paths:",
        f"- MinionsOS root: `{MINIONS_ROOT}`",
        f"- Project directory: `{pdir}`",
        f"- Workspace: `{workspace}`",
        f"- Codex MCP config: `{MINIONS_ROOT / '.codex' / 'config.toml'}`",
        "",
        "Codex host notes:",
        "- Follow the role contract below as system-level instruction.",
        "- Use MCP tools only within the MinionsOS role boundary.",
        "- MinionsOS MCP server enforces project lifecycle tool permissions.",
        f"- Intended role tool allowlist: `{allowed_tools}`.",
        "- Allowlist names are MinionsOS contract labels. `Task` means the "
        "current host's native subagent/delegation capability, not a required "
        "Codex tool with that literal name.",
        "",
    ]
    if system_path and system_path.exists():
        try:
            parts.extend(
                [
                    "# Role System Prompt",
                    "",
                    system_path.read_text(encoding="utf-8").strip(),
                    "",
                ]
            )
        except Exception:
            parts.extend(
                [
                    "# Role System Prompt",
                    "",
                    f"Read and follow `{system_path}` before handling the event batch.",
                    "",
                ]
            )
    parts.extend(["# Event Batch", "", message])
    return "\n".join(parts).rstrip() + "\n"
