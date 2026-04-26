"""``mos`` CLI — MinionsOS V2 command-line interface.

Subcommands:
  status          — projects dashboard
  logs            — tail / follow log files
  doctor          — environment check
  config          — print paths / open config dir
  project list|close|revive [PORT]
  role list|dismiss [PORT] [NAME]
  wipe [PORT]     — wipe project data (EACN DB + artifacts)

Run ``mos --help`` for full usage.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from minions.errors import MinionsError
from minions.logging_setup import configure_logging
from minions.paths import CONFIG_DIR, GRU_LOG, MINIONS_ROOT, STATE_DIR, project_dir

configure_logging()
logger = logging.getLogger(__name__)

app = typer.Typer(
    name="mos",
    help="MinionsOS V2 — project and role management CLI.",
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
        projects = store.list_projects()
    except MinionsError as e:
        raise _fail(f"{e}\nHint: back up and remove minions/state/projects.json to reset.") from e

    if json_flag:
        rows = []
        for p in projects:
            snap = project_status_snapshot(p.port, p.status)
            rows.append(
                {
                    "port": p.port,
                    "name": p.real_name,
                    "status": p.status,
                    "venue": p.venue,
                    "roles": len(p.active_roles),
                    "backend_alive": snap["backend_alive"],
                    "agents": snap["agents"],
                    "queue_depth": snap["queue_depth"],
                    "recent_failures": snap["recent_failures"],
                }
            )
        _json_out(rows)
        return

    table = Table(title="MinionsOS Projects", show_lines=True)
    table.add_column("Port", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Venue")
    table.add_column("Health")
    table.add_column("Roles")

    for p in projects:
        snap = project_status_snapshot(p.port, p.status)
        alive = snap["backend_alive"]
        health_str = "✓" if alive else ("✗" if alive is False else "—")
        table.add_row(
            str(p.port),
            p.real_name,
            p.status,
            p.venue or "—",
            health_str,
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

    # Parent directory is a git repo (required for project_create worktree).
    from minions.paths import MINIONS_ROOT

    parent = MINIONS_ROOT.parent
    pr = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(parent),
        capture_output=True,
        text=True,
    )
    parent_is_repo = pr.returncode == 0 and pr.stdout.strip() == "true"
    _check(
        "parent-dir-is-git-repo",
        parent_is_repo,
        str(parent) if parent_is_repo else f"{parent} — run: git init && git add -A && git commit",
    )

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

    # Port range probe
    from minions.state.store import _bind_probe

    probe_port = 37596
    _check("port-probe", _bind_probe(probe_port), f"port {probe_port}")

    # Model registry consistency
    try:
        from minions.config import load_gru_config as _load_cfg

        _cfg = _load_cfg()
        _ok, _detail = _cfg.model_registry_valid()
        _check("model-registry", _ok, _detail)
    except Exception as exc:
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

    # Per-project: gru passive-mailbox agent present on each active backend.
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
    data = {
        "MINIONS_ROOT": str(MINIONS_ROOT),
        "CONFIG_DIR": str(CONFIG_DIR),
        "STATE_DIR": str(STATE_DIR),
        "GRU_LOG": str(GRU_LOG),
    }
    if json_flag:
        _json_out(data)
        return
    for k, v in data.items():
        console.print(f"[cyan]{k}[/cyan] = {v}")


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
    """Repair a running project's EACN state (currently: register the ``gru`` mailbox agent)."""
    from minions.lifecycle.project import project_repair_gru_agent

    try:
        result = project_repair_gru_agent(port)
    except MinionsError as e:
        raise _fail(str(e)) from e
    if result["status"] == "already":
        console.print(
            f"[yellow]gru agent already registered on port {port} "
            f"(id={result['gru_agent_id']}).[/yellow]"
        )
    else:
        console.print(
            f"[green]Registered gru agent on port {port} (id={result['gru_agent_id']}).[/green]"
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
