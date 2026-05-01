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
    """Concrete subprocess invocation for one role wake-up."""

    host_name: str
    command: list[str]
    cwd: Path
    stdin_text: str
    session_name: str | None = None


def build_role_invocation(
    *,
    cfg: GruConfig,
    role_name: str,
    project_port: int,
    system_path: Path | None,
    allowed_tools: str,
    message: str,
    workspace: Path,
    session_name: str | None = None,
    resume_session: bool = False,
) -> RoleInvocation:
    """Build the configured agent-host command for a role wake-up."""
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
            session_name=session_name,
            resume_session=resume_session,
        )
    return _build_claude_role_invocation(
        system_path=system_path,
        allowed_tools=allowed_tools,
        message=message,
        workspace=workspace,
        session_name=session_name,
        resume_session=resume_session,
    )


def _build_claude_role_invocation(
    *,
    system_path: Path | None,
    allowed_tools: str,
    message: str,
    workspace: Path,
    session_name: str | None,
    resume_session: bool,
) -> RoleInvocation:
    """Preserve the existing Claude Code role invocation exactly."""
    cmd = [
        "uv",
        "run",
        "--project",
        str(MINIONS_ROOT),
        "claude",
    ]
    if session_name:
        cmd += ["--name", session_name]
    if resume_session:
        cmd.append("--continue")
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
        session_name=session_name,
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
    session_name: str | None,
    resume_session: bool,
) -> RoleInvocation:
    """Build a Codex non-interactive role invocation.

    Codex does not expose Claude's ``--append-system-prompt`` or
    ``--allowed-tools`` flags. We inline the combined system prompt in stdin
    and rely on MinionsOS MCP server-side authorization for project lifecycle
    tools. The Codex process still starts from ``MINIONS_ROOT`` so local config
    can be loaded, while ``--cd`` points the agent at the role workspace and the
    project directory is added as a writable directory.
    """
    if resume_session:
        cmd = [
            "codex",
            "exec",
            "resume",
            "--last",
        ]
    else:
        cmd = [
            "codex",
            "exec",
            "--cd",
            str(workspace),
            "--add-dir",
            str(project_dir(project_port)),
        ]
    if cfg.codex_bypass_approvals_and_sandbox:
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        cmd += [
            "--sandbox",
            cfg.codex_sandbox,
            "-c",
            f'approval_policy="{cfg.codex_approval_policy}"',
        ]
    cmd += [
        "-c",
        f'model_reasoning_effort="{cfg.codex_reasoning_effort}"',
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
        session_name=session_name,
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
        "This is a bounded role wake window. Complete or checkpoint the work, then exit.",
        "MinionsOS preserves the host session for later resume unless explicitly disabled.",
        "",
        "Paths:",
        f"- MinionsOS root: `{MINIONS_ROOT}`",
        f"- Project directory: `{pdir}`",
        f"- Workspace root: `{workspace.parent}`",
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
