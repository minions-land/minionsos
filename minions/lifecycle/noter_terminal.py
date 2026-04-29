"""Read-only project Noter terminal.

This is the human-side "Noter out" surface: a cheap Python observer that can
run in one terminal per project. It does not drain role EACN event queues.
Formal Noter summaries are still produced by the Noter role through EACN3.
"""

from __future__ import annotations

import select
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from minions.errors import ProjectError
from minions.lifecycle import eacn_client, gru_inbox, role_inbox
from minions.lifecycle.health import project_status_snapshot
from minions.lifecycle.project_eacn import project_eacn_send_message
from minions.paths import project_artifacts_dir
from minions.state.store import ProjectEntry, StateStore


@dataclass
class NoterSnapshot:
    project: ProjectEntry
    health: dict[str, Any]
    tasks: list[dict[str, Any]]
    notes: list[Path]
    role_buffers: dict[str, int]
    gru_unread: int
    errors: list[str]
    captured_at: str


def collect_noter_snapshot(
    port: int,
    store: StateStore | None = None,
    max_tasks: int = 12,
    max_notes: int = 6,
    task_offset: int = 0,
    task_status: str | None = None,
) -> NoterSnapshot:
    """Collect a read-only status snapshot for one project."""
    _store = store or StateStore()
    project = _store.get_project(port)
    if project is None:
        raise ProjectError(f"Project {port} not found.")

    errors: list[str] = []
    health = project_status_snapshot(project.port, project.status)
    tasks: list[dict[str, Any]] = []
    if health.get("backend_alive"):
        try:
            tasks = eacn_client.list_tasks(
                project.port,
                status=task_status,
                limit=max_tasks,
                offset=task_offset,
                order="desc",
            )
        except Exception as exc:
            errors.append(f"tasks: {exc}")

    notes = _latest_notes(port, max_notes)
    role_buffers = {
        role.name: role_inbox.count(project.port, role.name) for role in project.active_roles
    }
    try:
        gru_unread = gru_inbox.unread_count(project.port)
    except Exception:
        gru_unread = 0

    return NoterSnapshot(
        project=project,
        health=health,
        tasks=tasks,
        notes=notes,
        role_buffers=role_buffers,
        gru_unread=gru_unread,
        errors=[*health.get("recent_failures", []), *errors],
        captured_at=datetime.now(tz=UTC).isoformat(timespec="seconds"),
    )


def run_noter_terminal(
    port: int,
    interval_seconds: int = 30,
    once: bool = False,
    max_tasks: int = 12,
    task_offset: int = 0,
    task_status: str | None = None,
    console: Console | None = None,
) -> None:
    """Run a periodic read-only Noter terminal for one project."""
    out = console or Console()
    _print_help(out)
    previous_role_buffers: dict[str, int] | None = None
    while True:
        snapshot = collect_noter_snapshot(
            port,
            max_tasks=max_tasks,
            task_offset=task_offset,
            task_status=task_status,
        )
        render_snapshot(snapshot, out, previous_role_buffers=previous_role_buffers)
        previous_role_buffers = dict(snapshot.role_buffers)
        if once:
            return
        command = _wait_for_command(interval_seconds)
        if command is None:
            continue
        if not _handle_command(command, port, out, max_tasks, task_offset, task_status):
            return


def render_snapshot(
    snapshot: NoterSnapshot,
    console: Console,
    previous_role_buffers: dict[str, int] | None = None,
) -> None:
    """Render the default Noter status report."""
    project = snapshot.project
    alive = snapshot.health.get("backend_alive")
    backend = "up" if alive else ("down" if alive is False else "n/a")
    console.rule(f"Noter project {project.port} | {snapshot.captured_at}")
    console.print(
        f"[bold]{project.real_name}[/bold]  status={project.status}  "
        f"backend={backend}  gru_unread={snapshot.gru_unread}  "
        f"tasks={len(snapshot.tasks)}"
    )
    _render_roles(snapshot, console, previous_role_buffers=previous_role_buffers)
    _render_tasks(snapshot, console)
    _render_notes(snapshot, console)
    if snapshot.errors:
        console.print("[yellow]Recent issues:[/yellow]")
        for item in snapshot.errors[:6]:
            console.print(f"  - {_short(str(item), 140)}")
    console.print("[dim]Commands: status, tasks, roles, notes, wake [message], help, quit[/dim]")


def _handle_command(
    command: str,
    port: int,
    console: Console,
    max_tasks: int,
    task_offset: int = 0,
    task_status: str | None = None,
) -> bool:
    cmd, _, rest = command.partition(" ")
    cmd = cmd.strip().lower()
    rest = rest.strip()
    if cmd in {"", "status", "s"}:
        render_snapshot(
            collect_noter_snapshot(
                port,
                max_tasks=max_tasks,
                task_offset=task_offset,
                task_status=task_status,
            ),
            console,
        )
        return True
    if cmd in {"tasks", "t"}:
        _render_tasks(
            collect_noter_snapshot(
                port,
                max_tasks=max_tasks,
                task_offset=task_offset,
                task_status=task_status,
            ),
            console,
            force=True,
        )
        return True
    if cmd in {"roles", "r"}:
        _render_roles(
            collect_noter_snapshot(
                port,
                max_tasks=max_tasks,
                task_offset=task_offset,
                task_status=task_status,
            ),
            console,
        )
        return True
    if cmd in {"notes", "n"}:
        _render_notes(
            collect_noter_snapshot(
                port,
                max_tasks=max_tasks,
                task_offset=task_offset,
                task_status=task_status,
            ),
            console,
            force=True,
        )
        return True
    if cmd == "wake":
        message = rest or "Please produce an on-demand Noter status summary for Gru."
        result = project_eacn_send_message(
            port=port,
            content={"type": "noter_status_request", "text": message},
            to_role="noter",
        )
        console.print(f"[green]queued Noter request[/green] {result['to_agent_id']} on {port}")
        return True
    if cmd in {"help", "h", "?"}:
        _print_help(console)
        return True
    if cmd in {"quit", "q", "exit"}:
        return False
    console.print(f"[yellow]unknown command:[/yellow] {command}")
    _print_help(console)
    return True


def _wait_for_command(interval_seconds: int) -> str | None:
    if interval_seconds <= 0:
        return ""
    if not sys.stdin.isatty():
        time.sleep(interval_seconds)
        return None
    ready, _, _ = select.select([sys.stdin], [], [], interval_seconds)
    if not ready:
        return None
    return sys.stdin.readline().strip()


def _render_roles(
    snapshot: NoterSnapshot,
    console: Console,
    previous_role_buffers: dict[str, int] | None = None,
) -> None:
    table = Table(title="Roles", show_lines=False)
    table.add_column("Role")
    table.add_column("State")
    table.add_column("PID")
    table.add_column("EACN")
    table.add_column("Last seen")
    table.add_column("Task")
    table.add_column("Buffered")
    for role in snapshot.project.active_roles:
        table.add_row(
            role.name,
            role.state,
            str(role.pid or "-"),
            role.eacn_agent_id or role.name,
            role.last_seen or "-",
            _short(role.current_task or "-", 38),
            _format_buffer_count(
                role.name,
                snapshot.role_buffers.get(role.name, 0),
                previous_role_buffers,
            ),
        )
    console.print(table)


def _format_buffer_count(
    role_name: str,
    current: int,
    previous_role_buffers: dict[str, int] | None = None,
) -> str:
    if previous_role_buffers is None or role_name not in previous_role_buffers:
        return str(current)
    previous = previous_role_buffers[role_name]
    if previous == current:
        return str(current)
    return f"{current} (<- {previous})"


def _render_tasks(snapshot: NoterSnapshot, console: Console, force: bool = False) -> None:
    if not snapshot.tasks and not force:
        return
    table = Table(title="Recent EACN Tasks", show_lines=False)
    table.add_column("Task")
    table.add_column("Created")
    table.add_column("Status")
    table.add_column("Initiator")
    table.add_column("Domains")
    table.add_column("Description")
    for task in snapshot.tasks:
        content = task.get("content") if isinstance(task.get("content"), dict) else {}
        table.add_row(
            str(task.get("id", "-")),
            _short_created(task.get("created_at")),
            str(task.get("status", "-")),
            str(task.get("initiator_id", "-")),
            ", ".join(str(d) for d in task.get("domains", [])[:3]),
            _short(str(content.get("description", "")), 60),
        )
    console.print(table)


def _render_notes(snapshot: NoterSnapshot, console: Console, force: bool = False) -> None:
    if not snapshot.notes and not force:
        return
    table = Table(title="Latest Notes", show_lines=False)
    table.add_column("Path")
    table.add_column("Modified")
    for path in snapshot.notes:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(
                timespec="seconds"
            )
        except OSError:
            mtime = "-"
        table.add_row(str(path), mtime)
    console.print(table)


def _latest_notes(port: int, limit: int) -> list[Path]:
    notes_dir = project_artifacts_dir(port) / "notes"
    if not notes_dir.exists():
        return []
    files = [p for p in notes_dir.glob("*.md") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def _short(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)] + "..."


def _short_created(value: object) -> str:
    if not value:
        return "-"
    text = str(value)
    return text.replace("+00:00", "Z").replace("T", " ")[:19]


def _print_help(console: Console) -> None:
    console.print(
        "[dim]Noter terminal is read-only. It reports without draining EACN role queues. "
        "Press Enter for immediate status, or type help.[/dim]"
    )
