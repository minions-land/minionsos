"""Resident-Role process launcher.

Each MinionsOS Role runs as a long-lived ``claude`` process inside its own
``tmux`` session. This module is the only place that knows how to start
that session, detect whether it is still alive, attach to it, or kill it.

Why tmux:

- Long-lived ``claude`` is interactive and wants a TTY.
- The author needs an emergency hatch to drop into a Role's session and see
  exactly what the model sees ("hop in over its shoulder").
- A named tmux session is trivial to ``has-session`` / ``attach`` / ``kill``
  from outside, and survives a closed terminal.

Naming: each session is named ``mos-{port}-{role}`` so any operator can
``tmux ls`` to see all live Roles or ``tmux attach -t mos-37596-coder`` to
inspect one.

The launcher does NOT manage role state in ``projects.json`` — that is the
caller's job. The launcher only owns the tmux session and the ``claude``
argv it dispatches.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from minions.config import GruConfig, load_gru_config, whitelist_csv
from minions.errors import RoleError
from minions.lifecycle.agent_host import build_role_invocation
from minions.lifecycle.eacn_identity import (
    plugin_state_dir,
    resolve_agent_id,
)
from minions.paths import (
    MINIONS_ROOT,
    common_role_system_md,
    project_role_log,
    project_role_workspace,
    project_session_name,
    project_workspace,
    project_workspace_root,
    role_system_md,
)
from minions.state.store import RoleEntry

logger = logging.getLogger(__name__)


def session_name(project_port: int, role_name: str) -> str:
    """Return the tmux session name for *(port, role)*."""
    return f"mos-{project_port}-{role_name}"


def session_alive(project_port: int, role_name: str) -> bool:
    """Return True if a tmux session for this Role is currently alive."""
    if not _have_tmux():
        return False
    name = session_name(project_port, role_name)
    return _tmux_has_session(name)


def kill_session(project_port: int, role_name: str) -> bool:
    """Kill the tmux session for this Role. Returns True if a session was killed."""
    if not _have_tmux():
        return False
    name = session_name(project_port, role_name)
    if not _tmux_has_session(name):
        return False
    try:
        subprocess.run(
            ["tmux", "kill-session", "-t", name],
            check=True,
            capture_output=True,
        )
        logger.info("kill_session: tmux session=%s killed", name)
        return True
    except subprocess.CalledProcessError as exc:
        logger.warning("kill_session: tmux kill-session failed for %s: %s", name, exc)
        return False


def attach_command(project_port: int, role_name: str) -> list[str]:
    """Return the argv the operator can run to attach to a Role session.

    The launcher itself never attaches; it only reports the command so the
    user can ``tmux attach -t ...`` from their own terminal.
    """
    return ["tmux", "attach", "-t", session_name(project_port, role_name)]


def launch_role_process(
    role_entry: RoleEntry,
    project_port: int,
    *,
    cfg: GruConfig | None = None,
    resume: bool = False,
) -> dict[str, object]:
    """Start a long-lived ``claude`` process for *role_entry* in tmux.

    Idempotent in the "session already alive" sense: if the named tmux
    session is already running, the function returns without launching a
    second one. Callers wanting to force-restart should ``kill_session``
    first.

    When ``resume=True``, the launched ``claude`` is invoked with
    ``--resume <session_name>`` so Claude Code reattaches to the prior
    conversation persisted under the role's cwd in
    ``~/.claude/projects/<cwd-slug>/``. **This resets the prompt cache** —
    Claude Code rebuilds the cache from scratch and replays the prior
    history as fresh uncached input, which for a long-running Role
    typically costs hundreds of thousands of tokens. Pass ``resume=True``
    only for explicit operator debugging; ``project_revive`` and the
    crash-watchdog respawn path both pass ``resume=False`` so Roles cold-
    start and rebuild context from the Exploration DAG instead.

    Returns a small status dict with ``session_name``, ``cwd``,
    ``log_path``, ``attach_cmd``, ``started`` (True if a fresh session was
    launched, False if an existing session was found), and ``resumed``
    (mirrors the *resume* argument when a fresh session was launched).
    """
    if not _have_tmux():
        raise RoleError("tmux is not installed; resident-Role launcher requires tmux on PATH.")

    role_name = role_entry.name
    name = session_name(project_port, role_name)

    if _tmux_has_session(name):
        logger.info(
            "launch_role_process: tmux session=%s already alive; skipping launch",
            name,
        )
        return {
            "session_name": name,
            "started": False,
            "resumed": False,
            "attach_cmd": attach_command(project_port, role_name),
        }

    cfg = cfg or load_gru_config()
    workspace = (
        Path(role_entry.workspace_path)
        if role_entry.workspace_path
        else project_role_workspace(project_port, role_name)
    )
    if not workspace.exists() and project_workspace(project_port).exists():
        workspace = project_workspace(project_port)

    log_path = project_role_log(project_port, role_name)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    invocation = build_role_invocation(
        cfg=cfg,
        role_name=role_name,
        project_port=project_port,
        project_agent_id=role_entry.eacn_agent_id or role_name,
        system_path=_combined_system_prompt(role_name),
        allowed_tools=whitelist_csv(role_name, "main"),
        workspace=workspace,
        session_name=role_entry.session_name or project_session_name(project_port, role_name),
        resume=resume,
        model=_role_model(cfg, role_name),
    )

    env = _role_env(
        role_name=role_name,
        project_port=project_port,
        role_entry=role_entry,
        workspace=workspace,
    )
    _spawn_tmux(
        session_name=name,
        cwd=invocation.cwd,
        env=env,
        argv=invocation.command,
        initial_prompt=invocation.initial_prompt,
        log_path=log_path,
    )
    logger.info(
        "launch_role_process: tmux session=%s launched role=%s port=%d resume=%s",
        name,
        role_name,
        project_port,
        resume,
    )
    return {
        "session_name": name,
        "started": True,
        "resumed": bool(resume),
        "cwd": str(invocation.cwd),
        "log_path": str(log_path),
        "attach_cmd": attach_command(project_port, role_name),
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _have_tmux() -> bool:
    return shutil.which("tmux") is not None


def _tmux_has_session(name: str) -> bool:
    try:
        proc = subprocess.run(
            ["tmux", "has-session", "-t", name],
            capture_output=True,
        )
        return proc.returncode == 0
    except FileNotFoundError:
        return False


def _spawn_tmux(
    *,
    session_name: str,
    cwd: Path,
    env: dict[str, str],
    argv: list[str],
    initial_prompt: str,
    log_path: Path,
) -> None:
    """Start a detached tmux session running *argv*, then send *initial_prompt*.

    The session is created with ``tmux new-session -d`` so it never
    daemonizes inside the caller's TTY. After creation we ``send-keys`` the
    initial prompt followed by ``Enter`` so the long-lived ``claude``
    receives its first user message and starts the forever loop.
    """
    cmd_str = " ".join(_quote(a) for a in argv) + f" 2>&1 | tee -a {_quote(str(log_path))}"
    new_session_cmd = [
        "tmux",
        "new-session",
        "-d",
        "-s",
        session_name,
        "-c",
        str(cwd),
    ]
    for key, value in env.items():
        new_session_cmd += ["-e", f"{key}={value}"]
    new_session_cmd.append(cmd_str)

    try:
        subprocess.run(new_session_cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
        raise RoleError(
            f"tmux new-session failed for {session_name}: {stderr.strip() or exc}"
        ) from exc

    # Give claude a moment to come up, then deliver the initial prompt.
    # We send the prompt as a single block followed by Enter so claude reads
    # it as the first user message.
    _tmux_send_initial_prompt(session_name, initial_prompt)


def _tmux_send_initial_prompt(session_name: str, prompt: str) -> None:
    """Type *prompt* into the tmux session as if the operator typed it."""
    try:
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "-l", prompt],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "Enter"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "_tmux_send_initial_prompt: send-keys failed for %s: %s",
            session_name,
            exc,
        )


def _role_env(
    *,
    role_name: str,
    project_port: int,
    role_entry: RoleEntry,
    workspace: Path,
) -> dict[str, str]:
    """Build the environment passed to the Role's claude process.

    Only includes the variables ``mos_await_events`` and the role contract
    actually need: project port, agent id, workspace path, role name,
    EACN3 plugin state dir.
    """
    eacn_agent_id = role_entry.eacn_agent_id or resolve_agent_id(project_port, role_name)
    return {
        "MINIONS_AGENT_HOST": "claude",
        "MINIONS_ROLE_NAME": role_name,
        "MINIONS_AGENT_TYPE": "main",
        "MINIONS_PROJECT_PORT": str(project_port),
        "MINIONS_AGENT_ID": eacn_agent_id,
        "MINIONS_WORKSPACE": str(workspace),
        "MINIONS_WORKSPACE_ROOT": str(project_workspace_root(project_port)),
        "MINIONS_WORKSPACE_MAIN": str(project_workspace(project_port)),
        "MINIONS_ROLE_WORKSPACE": str(workspace),
        "MINIONS_ROLE_WORKSPACE_BRANCH": role_entry.workspace_branch or "",
        "EACN3_NETWORK_URL": f"http://127.0.0.1:{project_port}",
        "EACN3_STATE_DIR": str(plugin_state_dir(project_port, eacn_agent_id).resolve()),
        "MINIONS_GITHUB_PUSH_TARGET": role_entry.github_push_target or "",
        # Long-horizon cache hit-rate optimization: opt the Role's claude
        # process into 1-hour prompt cache TTL on backends that honor it
        # (direct Anthropic API key, Bedrock, Vertex, Foundry — see
        # claude-code CHANGELOG 2.1.108). Third-party gateways may strip
        # the 1h cache_control flag and silently fall back to the 5-minute
        # default; in that case the wall-clock keepalive in mos_await_events
        # (cache_keepalive_seconds, default 270s) carries the load instead.
        # Either way the env var is harmless — when honored it lifts the
        # cliff to 60 min, when ignored we still have keepalive at 4m30s.
        # Requires claude CLI ≥ 2.1.131 (earlier versions silently
        # downgraded 1h to 5 min). DISABLE_TELEMETRY would force a 5-min
        # fallback for subscription auth, so we deliberately do not set it.
        "ENABLE_PROMPT_CACHING_1H": "1",
        "PATH": os.environ.get("PATH", ""),
    }


def _role_model(cfg: GruConfig, role_name: str) -> str | None:
    """Return the model override for a role, or None for the default."""
    if role_name == "noter":
        return cfg.noter_model
    return None


def _combined_system_prompt(role_name: str) -> Path | None:
    """Return the path to the combined common+role SYSTEM.md, or None."""
    role_path = role_system_md(role_name if not role_name.startswith("expert") else "expert")
    common_path = common_role_system_md()
    paths = [path for path in (common_path, role_path) if path.exists()]
    if not paths:
        return None
    if paths == [role_path]:
        return role_path

    import hashlib
    import tempfile

    parts: list[str] = []
    for path in paths:
        label = "Common Role System" if path == common_path else f"{role_name} Role System"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        parts.append(f"# {label}\n\n{text.strip()}\n")
    if not parts:
        return None
    combined = "\n\n---\n\n".join(parts) + "\n"
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:12]
    safe = role_name.replace("/", "_").replace("..", "_")
    out_dir = Path(tempfile.gettempdir()) / "minionsos-role-prompts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{safe}-{digest}.md"
    if not out_path.exists() or out_path.read_text(encoding="utf-8") != combined:
        out_path.write_text(combined, encoding="utf-8")
    return out_path


def _quote(value: str) -> str:
    """Minimal shell quoting for tmux command-string concatenation."""
    if not value:
        return "''"
    safe = all(c.isalnum() or c in "@%+=:,./-_" for c in value)
    if safe:
        return value
    return "'" + value.replace("'", "'\\''") + "'"


# Surface MINIONS_ROOT for tests / callers that need it relative to this module.
__all__ = [
    "MINIONS_ROOT",
    "attach_command",
    "kill_session",
    "launch_role_process",
    "session_alive",
    "session_name",
]
