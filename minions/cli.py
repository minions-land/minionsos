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

import typer
from rich.console import Console
from rich.table import Table

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


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@app.command()
def status(
    json_flag: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a dashboard of all projects and their health."""
    from minions.lifecycle.health import backend_health

    store = _get_store()
    projects = store.list_projects()

    if json_flag:
        rows = []
        for p in projects:
            healthy = backend_health(p.port) if p.status == "active" else None
            rows.append(
                {
                    "port": p.port,
                    "name": p.real_name,
                    "status": p.status,
                    "venue": p.venue,
                    "healthy": healthy,
                    "roles": len(p.active_roles),
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
        healthy = backend_health(p.port) if p.status == "active" else None
        health_str = "✓" if healthy else ("✗" if healthy is False else "—")
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

    subprocess.run(cmd)


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

    # EACN3 importable
    try:
        import importlib

        importlib.import_module("eacn")
        _check("eacn3-importable", True)
    except ImportError as exc:
        _check("eacn3-importable", False, str(exc))

    # Port range probe
    from minions.state.store import _bind_probe

    probe_port = 37596
    _check("port-probe", _bind_probe(probe_port), f"port {probe_port}")

    # State dir writable
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        test_file = STATE_DIR / ".doctor_probe"
        test_file.write_text("ok")
        test_file.unlink()
        _check("state-dir-writable", True, str(STATE_DIR))
    except Exception as exc:
        _check("state-dir-writable", False, str(exc))

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

    if not all(c["ok"] for c in checks):
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

    entry = project_close(port)
    console.print(f"[green]Closed project {entry.port}.[/green]")


@project_app.command(name="revive")
def project_revive_cmd(port: int = typer.Argument(..., help="Project port.")) -> None:
    """Revive a dormant project."""
    from minions.lifecycle.project import project_revive

    entry = project_revive(port)
    console.print(f"[green]Revived project {entry.port}.[/green]")


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

    roles = list_roles(port)
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

    result = dismiss_role(port, name)
    console.print(f"[green]Dismissed role {result['name']}.[/green]")


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
