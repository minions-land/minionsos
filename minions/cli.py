"""``mos`` CLI — MinionsOS command-line interface.

Subcommands:
  status          — projects dashboard
  logs            — tail / follow log files
  doctor          — environment check
  config          — print paths / open config dir
  noter           — read-only project Noter terminal
  project list|kill|close|revive [PORT]
  role list|dismiss [PORT] [NAME]
  wipe [PORT]     — wipe project data (EACN DB + artifacts)

Run ``mos --help`` for full usage.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from minions.errors import MinionsError
from minions.logging_setup import configure_logging
from minions.paths import CONFIG_DIR, GRU_LOG, MINIONS_ROOT, STATE_DIR, project_dir, projects_root

configure_logging()
logger = logging.getLogger(__name__)

app = typer.Typer(
    name="mos",
    help="MinionsOS — project and role management CLI.",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_store():
    from minions.state.store import StateStore

    return StateStore()


def _json_out(data: object) -> None:
    typer.echo(json.dumps(data, indent=2, default=str))


def _fail(msg: str, code: int = 1) -> typer.Exit:
    """Emit a terse one-line error and exit with ``code``.

    Used to wrap ``MinionsError`` subclasses so the CLI shows an actionable
    message instead of a full Rich traceback for user-facing conditions like
    "project not found" or "corrupt state file".
    """
    console.print(f"[red]error:[/red] {msg}")
    return typer.Exit(code)


def _project_port_from_dir(path: Path) -> int | None:
    if not path.name.startswith("project_"):
        return None
    try:
        return int(path.name.removeprefix("project_"))
    except ValueError:
        return None


def _find_orphan_project_dirs(root: Path, known_ports: set[int]) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    for path in sorted(root.glob("project_*")):
        if not path.is_dir():
            continue
        port = _project_port_from_dir(path)
        if port is None or port not in known_ports or not (path / "meta.json").exists():
            out.append(path)
    return out


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@app.command()
def status(
    json_flag: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a dashboard of all projects and their health."""
    from minions.lifecycle.health import project_status_snapshot

    store = _get_store()
    try:
        data = store.load()
    except MinionsError as e:
        raise _fail(f"{e}\nHint: back up and remove minions/state/projects.json to reset.") from e

    if json_flag:
        _json_out(data.model_dump())
        return

    projects = data.projects
    table = Table(title="MinionsOS Projects", show_lines=True)
    table.add_column("Port", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Venue")
    table.add_column("Health")
    table.add_column("EACN Q")
    table.add_column("Failures")
    table.add_column("Roles")

    for p in projects:
        snap = project_status_snapshot(p.port, p.status)
        alive = snap["backend_alive"]
        health_str = "✓" if alive else ("✗" if alive is False else "—")
        failures = snap.get("recent_failures", [])
        table.add_row(
            str(p.port),
            p.real_name,
            p.status,
            p.venue or "—",
            health_str,
            str(snap.get("queue_depth", 0)),
            str(len(failures)) if failures else "—",
            str(len(p.active_roles)),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


@app.command()
def logs(
    project: int | None = typer.Option(None, "--project", "-p", help="Project port."),
    role: str | None = typer.Option(None, "--role", "-r", help="Role name."),
    tail: int = typer.Option(50, "--tail", "-n", help="Number of lines to show."),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow the log (like tail -f)."),
) -> None:
    """Tail or follow log files."""
    if project is None:
        log_path = GRU_LOG
    elif role is not None:
        from minions.paths import project_role_log

        log_path = project_role_log(project, role)
    else:
        from minions.paths import project_backend_log

        log_path = project_backend_log(project)

    if not log_path.exists():
        err_console.print(f"[red]Log file not found:[/red] {log_path}")
        raise typer.Exit(1)

    cmd = ["tail", f"-n{tail}"]
    if follow:
        cmd.append("-f")
    cmd.append(str(log_path))

    try:
        raise typer.Exit(subprocess.run(cmd).returncode)
    except FileNotFoundError:
        raise _fail("`tail` not found on PATH.") from None


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@app.command()
def doctor(
    json_flag: bool = typer.Option(False, "--json"),
) -> None:
    """Check environment dependencies (uv, node, git, EACN3, port range)."""
    checks: list[dict] = []

    def _check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    # uv
    r = subprocess.run(["uv", "--version"], capture_output=True, text=True)
    _check("uv", r.returncode == 0, r.stdout.strip())

    # node
    r = subprocess.run(["node", "--version"], capture_output=True, text=True)
    _check("node", r.returncode == 0, r.stdout.strip())

    # git
    r = subprocess.run(["git", "--version"], capture_output=True, text=True)
    _check("git", r.returncode == 0, r.stdout.strip())

    # Author seed repo is a git repo (required for project_create — its HEAD
    # is imported into each project's per-project bare repo).
    from minions.lifecycle.project import author_repo

    src = author_repo()
    try:
        pr = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(src),
            capture_output=True,
            text=True,
        )
        author_is_repo = pr.returncode == 0 and pr.stdout.strip() == "true"
    except FileNotFoundError:
        author_is_repo = False
    _check(
        "author-repo-is-git-repo",
        author_is_repo,
        str(src)
        if author_is_repo
        else (f"{src} — run: git init && git add -A && git commit, or set gru.yaml:author_repo"),
    )

    # Orphan project directories: present on disk but absent from projects.json,
    # or missing meta.json. They confuse humans and dashboards.
    try:
        from minions.state.store import StateStore

        known_ports = {p.port for p in StateStore().list_projects(filter="all")}
        root = projects_root()
        orphans = _find_orphan_project_dirs(root, known_ports)
        _check(
            "project-dir-orphans",
            not orphans,
            f"none under {root}"
            if not orphans
            else "orphan project dirs: " + ", ".join(str(p) for p in orphans[:5]),
        )
    except Exception as exc:
        _check("project-dir-orphans", False, str(exc))

    # EACN3 importable
    try:
        import importlib

        importlib.import_module("eacn")
        _check("eacn3-importable", True)
    except ImportError as exc:
        _check("eacn3-importable", False, str(exc))

    # EACN3 MCP plugin built (required so Roles have eacn3_* tools).
    plugin_dist = MINIONS_ROOT / "EACN3" / "plugin" / "dist" / "server.js"
    _check(
        "eacn3-plugin-built",
        plugin_dist.exists(),
        str(plugin_dist) if plugin_dist.exists() else "run ./install.sh",
    )

    # Node >= 16 (needed to run the plugin).
    node_ok = False
    node_detail = ""
    try:
        nr = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if nr.returncode == 0:
            ver = nr.stdout.strip().lstrip("v")
            major = int(ver.split(".", 1)[0]) if ver else 0
            node_ok = major >= 16
            node_detail = f"v{ver} ({'>=16' if node_ok else '<16 — upgrade'})"
        else:
            node_detail = "node not on PATH"
    except Exception as exc:
        node_detail = str(exc)
    _check("node>=16", node_ok, node_detail)

    # .mcp.json mounts both minionsos and eacn3 servers.
    try:
        import json as _json

        mcp_cfg = _json.loads((MINIONS_ROOT / ".mcp.json").read_text(encoding="utf-8"))
        servers = set(mcp_cfg.get("mcpServers", {}).keys())
        missing = {"minionsos", "eacn3"} - servers
        _check(
            "mcp-config-mounts-eacn3",
            not missing,
            f"present: {sorted(servers)}" if not missing else f"missing: {sorted(missing)}",
        )
    except Exception as exc:
        _check("mcp-config-mounts-eacn3", False, str(exc))

    # Codex project MCP config mounts the same servers for Codex host sessions.
    try:
        import tomllib

        codex_cfg_path = MINIONS_ROOT / ".codex" / "config.toml"
        codex_cfg = tomllib.loads(codex_cfg_path.read_text(encoding="utf-8"))
        servers = set((codex_cfg.get("mcp_servers") or {}).keys())
        missing = {"minionsos", "eacn3"} - servers
        _check(
            "codex-mcp-config-mounts-eacn3",
            not missing,
            f"present: {sorted(servers)}" if not missing else f"missing: {sorted(missing)}",
        )
        eacn3 = (codex_cfg.get("mcp_servers") or {}).get("eacn3") or {}
        eacn_cmd = str(eacn3.get("command") or "")
        eacn_args = eacn3.get("args") or []
        eacn_direct = eacn_cmd == "node" and any(
            "EACN3/plugin/dist/server.js" in str(arg) for arg in eacn_args
        )
        _check(
            "codex-mcp-eacn3-direct",
            eacn_direct,
            (
                "node EACN3/plugin/dist/server.js"
                if eacn_direct
                else f"cmd={eacn_cmd!r} args={eacn_args}"
            ),
        )
    except Exception as exc:
        _check("codex-mcp-config-mounts-eacn3", False, str(exc))
        _check("codex-mcp-eacn3-direct", False, str(exc))

    # Port range probe. The allocator can skip an occupied first port, so
    # doctor should only fail when the whole configured range is exhausted.
    from minions.errors import PortError
    from minions.state.port_allocator import PORT_MAX, PORT_MIN, PortAllocator

    try:
        available_port = PortAllocator(PORT_MIN, PORT_MAX).allocate(set())
        _check(
            "port-probe",
            True,
            f"available port {available_port} in range {PORT_MIN}-{PORT_MAX}",
        )
    except PortError as exc:
        _check("port-probe", False, str(exc))

    # Model registry consistency
    try:
        from minions.config import load_gru_config as _load_cfg

        _cfg = _load_cfg()
        _host = _cfg.effective_agent_host()
        _check("agent-host", True, _host)
        _ok, _detail = _cfg.model_registry_valid()
        _check("model-registry", _ok, _detail)

        if _host == "codex":
            automation_ok = _cfg.codex_bypass_approvals_and_sandbox or (
                _cfg.codex_sandbox == "danger-full-access" and _cfg.codex_approval_policy == "never"
            )
            _check(
                "codex-automation",
                automation_ok,
                (
                    "bypass approvals+sandbox"
                    if _cfg.codex_bypass_approvals_and_sandbox
                    else (
                        f"sandbox={_cfg.codex_sandbox}, "
                        f"approval_policy={_cfg.codex_approval_policy}"
                    )
                ),
            )
            codex_path = shutil.which("codex")
            if codex_path:
                cr = subprocess.run(["codex", "--version"], capture_output=True, text=True)
                _check("codex-cli", cr.returncode == 0, cr.stdout.strip() or codex_path)
            else:
                _check("codex-cli", False, "codex not on PATH")
        else:
            claude_path = shutil.which("claude")
            if claude_path:
                cr = subprocess.run(["claude", "--version"], capture_output=True, text=True)
                _check("claude-cli", cr.returncode == 0, cr.stdout.strip() or claude_path)
            else:
                cr = subprocess.run(
                    ["uv", "run", "--project", str(MINIONS_ROOT), "claude", "--version"],
                    capture_output=True,
                    text=True,
                )
                _check(
                    "claude-cli",
                    cr.returncode == 0,
                    cr.stdout.strip() if cr.returncode == 0 else "claude not on PATH",
                )
    except Exception as exc:
        _check("agent-host", False, str(exc))
        _check("model-registry", False, str(exc))

    # Claude --debug should be off by default; only enabled via MINIONS_DEBUG
    import os as _os

    _debug_on = bool(_os.environ.get("MINIONS_DEBUG", "").strip())
    _check(
        "claude-debug-disabled",
        not _debug_on,
        "MINIONS_DEBUG is unset (good)" if not _debug_on else "MINIONS_DEBUG is set — debug active",
    )

    # State dir writable
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        test_file = STATE_DIR / ".doctor_probe"
        test_file.write_text("ok")
        test_file.unlink()
        _check("state-dir-writable", True, str(STATE_DIR))
    except Exception as exc:
        _check("state-dir-writable", False, str(exc))

    # Per-project: Gru queue agent and active/sleeping Role AgentCards present.
    try:
        from minions.config import load_gru_config
        from minions.lifecycle import eacn_client
        from minions.state.store import StateStore

        gru_id = load_gru_config().gru_eacn_agent_id
        for p in StateStore().list_projects():
            if p.status != "active":
                continue
            snap = eacn_client.probe_backend(p.port)
            if not snap["health"]:
                _check(f"gru-agent[{p.port}]", False, "backend /health not 200")
                continue
            ids = {a.get("agent_id") for a in snap.get("agents", [])}
            present = gru_id in ids
            _check(
                f"gru-agent[{p.port}]",
                present,
                f"id={gru_id}" if present else f"missing; run `./mos project repair {p.port}`",
            )
            expected_roles = {
                r.eacn_agent_id or r.name
                for r in p.active_roles
                if r.state in {"active", "sleeping"}
            }
            missing_roles = sorted(expected_roles - ids)
            _check(
                f"project-role-agents[{p.port}]",
                not missing_roles,
                "all active/sleeping roles registered"
                if not missing_roles
                else f"missing: {missing_roles}",
            )
    except Exception as exc:
        _check("gru-agent-scan", False, str(exc))

    # viz: build freshness + daemon reachability
    viz_build = MINIONS_ROOT / "minions-viz" / "dist" / "web" / "index.html"
    _check(
        "viz-build",
        viz_build.exists(),
        str(viz_build) if viz_build.exists() else "run ./install.sh or ./viz start",
    )

    try:
        import urllib.request

        port_file = Path.home() / ".minionsos" / "viz.port"
        viz_port = int(port_file.read_text().strip()) if port_file.exists() else 7891
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{viz_port}/", timeout=1).read(1)
            _check("viz-daemon", True, f"http://127.0.0.1:{viz_port}")
        except Exception as exc:
            _check("viz-daemon", False, f"port {viz_port}: {exc}")
    except Exception as exc:
        _check("viz-daemon", False, str(exc))

    if json_flag:
        _json_out(checks)
        return

    table = Table(title="MinionsOS Doctor", show_lines=True)
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for c in checks:
        status_str = "[green]OK[/green]" if c["ok"] else "[red]FAIL[/red]"
        table.add_row(c["name"], status_str, c.get("detail", ""))
    console.print(table)

    if not all(c["ok"] for c in checks if not c["name"].startswith("viz-")):
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


@app.command(name="config")
def config_cmd(
    json_flag: bool = typer.Option(False, "--json"),
) -> None:
    """Print MinionsOS path configuration."""
    data: dict[str, object] = {
        "MINIONS_ROOT": str(MINIONS_ROOT),
        "CONFIG_DIR": str(CONFIG_DIR),
        "STATE_DIR": str(STATE_DIR),
        "GRU_LOG": str(GRU_LOG),
    }
    try:
        from minions.config import load_gru_config

        cfg = load_gru_config()
        data["AGENT_HOST"] = cfg.effective_agent_host()
        data["CLAUDE_MODEL"] = cfg.claude_model
        data["CODEX_MODEL"] = cfg.codex_model
        data["CODEX_REASONING_EFFORT"] = cfg.codex_reasoning_effort
        data["CODEX_BYPASS_APPROVALS_AND_SANDBOX"] = cfg.codex_bypass_approvals_and_sandbox
        data["AUTHOR_REPO"] = cfg.author_repo
        data["PROJECTS_ROOT"] = str(projects_root())
        data["HEALTH_EVENT_EACN_NOTIFICATIONS"] = cfg.health_event_eacn_notifications
    except Exception as exc:
        data["AGENT_HOST_ERROR"] = str(exc)
    if json_flag:
        _json_out(data)
        return
    for k, v in data.items():
        console.print(f"[cyan]{k}[/cyan] = {v}")


# ---------------------------------------------------------------------------
# noter
# ---------------------------------------------------------------------------


@app.command(name="noter")
def noter_cmd(
    port: int = typer.Argument(..., help="Project port to observe."),
    interval: int = typer.Option(30, "--interval", "-i", help="Report interval in seconds."),
    once: bool = typer.Option(False, "--once", help="Print one report and exit."),
    max_tasks: int = typer.Option(12, "--max-tasks", help="Maximum recent tasks to show."),
    task_offset: int = typer.Option(0, "--task-offset", help="Offset into newest-first tasks."),
    task_status: str | None = typer.Option(None, "--task-status", help="Filter tasks by status."),
) -> None:
    """Run a read-only Noter terminal for one project."""
    from minions.lifecycle.noter_terminal import run_noter_terminal

    try:
        run_noter_terminal(
            port=port,
            interval_seconds=interval,
            once=once,
            max_tasks=max_tasks,
            task_offset=task_offset,
            task_status=task_status,
            console=console,
        )
    except MinionsError as e:
        raise _fail(str(e)) from e


# ---------------------------------------------------------------------------
# project subcommands
# ---------------------------------------------------------------------------

project_app = typer.Typer(help="Project management.")
app.add_typer(project_app, name="project")


@project_app.command(name="list")
def project_list(
    filter: str = typer.Argument("all", help="all|active|dormant|closed"),
    json_flag: bool = typer.Option(False, "--json"),
) -> None:
    """List projects."""
    store = _get_store()
    projects = store.list_projects(filter=filter)  # type: ignore[arg-type]
    if json_flag:
        _json_out([p.model_dump() for p in projects])
        return
    table = Table(title=f"Projects ({filter})", show_lines=True)
    table.add_column("Port", style="cyan")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Venue")
    for p in projects:
        table.add_row(str(p.port), p.real_name, p.status, p.venue or "—")
    console.print(table)


@project_app.command(name="close")
def project_close_cmd(port: int = typer.Argument(..., help="Project port.")) -> None:
    """Close a project permanently."""
    from minions.lifecycle.project import project_close

    try:
        entry = project_close(port)
    except MinionsError as e:
        raise _fail(str(e)) from e
    console.print(f"[green]Closed project {entry.port}.[/green]")


@project_app.command(name="kill")
def project_kill_cmd(port: int = typer.Argument(..., help="Project port.")) -> None:
    """Hard-stop a project's runtime while preserving EACN data and port."""
    from minions.lifecycle.project import project_kill

    try:
        result = project_kill(port)
    except MinionsError as e:
        raise _fail(str(e)) from e
    roles = result.get("roles", [])
    role_count = len(roles) if isinstance(roles, list) else 0
    console.print(
        f"[green]Killed project {result['port']} runtime.[/green] "
        f"status={result['status']} roles={role_count}; EACN data preserved."
    )


@project_app.command(name="revive")
def project_revive_cmd(port: int = typer.Argument(..., help="Project port.")) -> None:
    """Revive a dormant project."""
    from minions.lifecycle.project import project_revive

    try:
        entry = project_revive(port)
    except MinionsError as e:
        raise _fail(str(e)) from e
    console.print(f"[green]Revived project {entry.port}.[/green]")


@project_app.command(name="repair")
def project_repair_cmd(port: int = typer.Argument(..., help="Project port.")) -> None:
    """Repair a running project's project-local EACN registrations and stale role PIDs."""
    from minions.lifecycle.project import project_repair_eacn_agents

    try:
        result = project_repair_eacn_agents(port)
    except MinionsError as e:
        raise _fail(str(e)) from e
    if result["status"] == "already":
        console.print(f"[yellow]Project {port} EACN state already healthy.[/yellow]")
        return
    roles_raw = result.get("role_agents_registered", [])
    roles_items = roles_raw if isinstance(roles_raw, list) else []
    roles = ", ".join(str(item) for item in roles_items) or "none"
    cleared_raw = result.get("stale_pids_cleared", [])
    cleared_items = cleared_raw if isinstance(cleared_raw, list) else []
    cleared = ", ".join(str(item) for item in cleared_items) or "none"
    console.print(
        f"[green]Repaired project {port} EACN state.[/green] "
        f"gru={result.get('gru_status')} roles_registered={roles} stale_pids_cleared={cleared}"
    )


# ---------------------------------------------------------------------------
# role subcommands
# ---------------------------------------------------------------------------

role_app = typer.Typer(help="Role management.")
app.add_typer(role_app, name="role")


@role_app.command(name="list")
def role_list(
    port: int = typer.Argument(..., help="Project port."),
    json_flag: bool = typer.Option(False, "--json"),
) -> None:
    """List roles for a project."""
    from minions.lifecycle.role import list_roles

    try:
        roles = list_roles(port)
    except MinionsError as e:
        raise _fail(str(e)) from e
    if json_flag:
        _json_out(roles)
        return
    table = Table(title=f"Roles for project {port}", show_lines=True)
    table.add_column("Name")
    table.add_column("State")
    table.add_column("PID")
    for r in roles:
        table.add_row(str(r["name"]), str(r["state"]), str(r["pid"] or "—"))
    console.print(table)


@role_app.command(name="dismiss")
def role_dismiss(
    port: int = typer.Argument(..., help="Project port."),
    name: str = typer.Argument(..., help="Role name."),
) -> None:
    """Dismiss a role."""
    from minions.lifecycle.role import dismiss_role

    try:
        result = dismiss_role(port, name)
    except MinionsError as e:
        raise _fail(str(e)) from e
    console.print(f"[green]Dismissed role {result['name']}.[/green]")


@role_app.command(name="attach")
def role_attach(
    port: int = typer.Argument(..., help="Project port."),
    name: str = typer.Argument(..., help="Role name."),
) -> None:
    """Attach to a role's live tmux session (read-mostly).

    What you see is exactly what the resident `claude` process sees right
    now. Detach with `Ctrl-b d`. Anything you type is fed to the live
    session, so by convention this is the "look, don't drive" path. For a
    technically read-only forensic view, use `mos role inspect`.
    """
    from minions.lifecycle.role_launcher import attach_command, session_alive

    if not session_alive(port, name):
        raise _fail(
            f"No live tmux session for role={name!r} on port {port}. "
            f"Run `mos role list {port}` to see registered roles."
        )
    raise typer.Exit(subprocess.run(attach_command(port, name)).returncode)


@role_app.command(name="inspect")
def role_inspect(
    port: int = typer.Argument(..., help="Project port."),
    name: str = typer.Argument(..., help="Role name."),
) -> None:
    """Open a forked Claude session over the role's history (read-only for the role).

    Spawns `claude --resume <session_name> --fork-session` in the role's
    branch worktree. The role's own jsonl is left untouched; you get a new
    branch session for forensic reading. The live role process keeps
    running undisturbed.
    """
    from minions.lifecycle.role_launcher import session_name as _session_name
    from minions.paths import project_role_workspace

    workspace = project_role_workspace(port, name)
    if not workspace.exists():
        raise _fail(
            f"Role workspace not found at {workspace}. "
            f"Has role={name!r} ever been registered on port {port}?"
        )
    sess = _session_name(port, name)
    cmd = [
        "claude",
        "--name",
        f"{sess}-inspect",
        "--resume",
        sess,
        "--fork-session",
        "--permission-mode",
        "default",
    ]
    console.print(
        f"[dim]Forking read-only inspect session over role={name} (port={port}). "
        f"The live role is unaffected.[/dim]"
    )
    raise typer.Exit(subprocess.run(cmd, cwd=workspace).returncode)


@role_app.command(name="drive")
def role_drive(
    port: int = typer.Argument(..., help="Project port."),
    name: str = typer.Argument(..., help="Role name."),
    confirm: bool = typer.Option(
        False,
        "--i-know-this-kills-autonomy",
        help=(
            "Required acknowledgement. `drive` kills the live tmux session "
            "and takes over its conversation; this is a maintenance back "
            "door, not normal operation."
        ),
    ),
) -> None:
    """Take over a role's conversation (autonomy off — maintenance back door).

    Kills the live tmux session, then opens `claude --resume <session_name>`
    in the role's branch worktree. The new conversation continues the role's
    jsonl, so anything you say becomes part of the role's history when the
    role next revives. Use this only for diagnosis and repair; running a
    role manually defeats the autonomous design.
    """
    if not confirm:
        raise _fail(
            "drive requires --i-know-this-kills-autonomy. This is a "
            "maintenance back door — running a role by hand defeats the "
            "autonomous loop and writes operator turns into the role's jsonl."
        )

    from minions.lifecycle.role_launcher import (
        kill_session,
        session_alive,
    )
    from minions.lifecycle.role_launcher import (
        session_name as _session_name,
    )
    from minions.paths import project_role_workspace

    workspace = project_role_workspace(port, name)
    if not workspace.exists():
        raise _fail(
            f"Role workspace not found at {workspace}. "
            f"Has role={name!r} ever been registered on port {port}?"
        )
    if session_alive(port, name):
        kill_session(port, name)
        console.print(f"[yellow]Killed live tmux session for {name} (port {port}).[/yellow]")
    sess = _session_name(port, name)
    cmd = [
        "claude",
        "--name",
        sess,
        "--resume",
        sess,
        "--permission-mode",
        "bypassPermissions",
    ]
    console.print(
        f"[bold red]DRIVING role={name} (port={port}). "
        f"Anything you type lands in the role's jsonl.[/bold red]"
    )
    raise typer.Exit(subprocess.run(cmd, cwd=workspace).returncode)


# ---------------------------------------------------------------------------
# viz subcommands (dispatch to minions/bin/viz)
# ---------------------------------------------------------------------------

viz_app = typer.Typer(help="MinionsOS Observatory (minions-viz) control.")
app.add_typer(viz_app, name="viz")


def _viz_script() -> str:
    return str(MINIONS_ROOT / "minions" / "bin" / "viz")


@viz_app.command("start")
def viz_start(
    port: int | None = typer.Option(None, "--port", help="Override port."),
    foreground: bool = typer.Option(False, "--foreground", "-F"),
) -> None:
    """Start the Observatory (default: daemon, port 7891)."""
    cmd = [_viz_script(), "start"]
    if port is not None:
        cmd += ["--port", str(port)]
    if foreground:
        cmd.append("--foreground")
    raise typer.Exit(subprocess.run(cmd).returncode)


@viz_app.command("stop")
def viz_stop() -> None:
    """Stop the Observatory."""
    raise typer.Exit(subprocess.run([_viz_script(), "stop"]).returncode)


@viz_app.command("status")
def viz_status() -> None:
    """Show Observatory status."""
    raise typer.Exit(subprocess.run([_viz_script(), "status"]).returncode)


@viz_app.command("open")
def viz_open() -> None:
    """Open the Observatory in your browser."""
    raise typer.Exit(subprocess.run([_viz_script(), "open"]).returncode)


@viz_app.command("logs")
def viz_logs(
    tail: int = typer.Option(50, "--tail", "-n"),
    follow: bool = typer.Option(False, "--follow", "-f"),
) -> None:
    """Tail/follow the Observatory log."""
    cmd = [_viz_script(), "logs", "--tail", str(tail)]
    if follow:
        cmd.append("--follow")
    raise typer.Exit(subprocess.run(cmd).returncode)


@viz_app.command("register")
def viz_register() -> None:
    """Register this Gru in ~/.minionsos/grus.json."""
    raise typer.Exit(subprocess.run([_viz_script(), "register"]).returncode)


@viz_app.command("deregister")
def viz_deregister() -> None:
    """Remove this Gru from the registry."""
    raise typer.Exit(subprocess.run([_viz_script(), "deregister"]).returncode)


@viz_app.command("heartbeat")
def viz_heartbeat() -> None:
    """Refresh this Gru's last_seen."""
    raise typer.Exit(subprocess.run([_viz_script(), "heartbeat"]).returncode)


@viz_app.command("ensure")
def viz_ensure() -> None:
    """Register this Gru, then start viz (no-op if already running)."""
    raise typer.Exit(subprocess.run([_viz_script(), "ensure"]).returncode)


# ---------------------------------------------------------------------------
# wipe
# ---------------------------------------------------------------------------


@app.command()
def wipe(
    port: int = typer.Argument(..., help="Project port to wipe."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Wipe a project's EACN DB and artifacts (irreversible)."""
    pdir = project_dir(port)
    targets = [
        pdir / "eacn3_data",
        pdir / "artifacts",
        pdir / "logs",
    ]
    existing = [t for t in targets if t.exists()]
    if not existing:
        console.print(f"Nothing to wipe for project {port}.")
        return

    if not yes:
        typer.confirm(
            f"Wipe {len(existing)} directories for project {port}? This is irreversible.",
            abort=True,
        )

    import shutil

    for t in existing:
        shutil.rmtree(t)
        console.print(f"[red]Removed[/red] {t}")
    console.print(f"[green]Wipe complete for project {port}.[/green]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    app()


if __name__ == "__main__":
    main()
