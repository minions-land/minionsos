"""``mos`` CLI — MinionsOS command-line interface.

Subcommands:
  status          — projects dashboard
  logs            — tail / follow log files
  doctor          — environment check
  upgrade         — pull latest + incremental install
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
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast

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


def _config_key_drift(config_dir: Path) -> list[str]:
    """Top-level keys present in each ``*.yaml.example`` but missing from its
    live ``*.yaml`` sibling.

    install.sh copies ``*.yaml.example`` → ``*.yaml`` only when the target is
    ABSENT, so an upgrade that adds new example keys never merges them into an
    existing live config. Pydantic defaults prevent a crash, but the operator
    silently never gains the new tunable. Each returned entry is
    ``"<file>: [missing, keys]"``. Targets that don't exist yet are ignored
    (install.sh will seed them). Files that fail to parse surface as an
    ``"<file>: <error>"`` entry rather than being silently dropped.
    """
    import yaml

    drift: list[str] = []
    for example in sorted(config_dir.glob("*.yaml.example")):
        target = example.with_suffix("")  # drops ".example" → "*.yaml"
        if not target.exists():
            continue
        try:
            example_keys = set((yaml.safe_load(example.read_text()) or {}).keys())
            live_keys = set((yaml.safe_load(target.read_text()) or {}).keys())
        except Exception as exc:
            drift.append(f"{target.name}: parse error: {exc}")
            continue
        missing = sorted(example_keys - live_keys)
        if missing:
            drift.append(f"{target.name}: {missing}")
    return drift


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
            str(len([r for r in p.active_roles if r.state != "dismissed"])),
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

    # tmux — every Role launches inside a named tmux session via
    # minions/lifecycle/role_launcher.py. Without tmux, role spawn silently
    # no-ops and the EACN bus stays dark even though Gru looks healthy.
    # Platform note: on native Windows (cmd / PowerShell) tmux does not exist;
    # the supported path is WSL2 where uname returns "Linux" and apt-get tmux
    # works the same as on a regular Linux host.
    try:
        tr = subprocess.run(["tmux", "-V"], capture_output=True, text=True)
        tmux_ok = tr.returncode == 0
        if tmux_ok:
            tmux_detail = tr.stdout.strip()
        else:
            tmux_detail = (
                "tmux not on PATH — Roles cannot launch. "
                "macOS: brew install tmux. Linux: apt-get/dnf/pacman install tmux. "
                "Windows: use WSL2 (wsl --install -d Ubuntu)."
            )
    except FileNotFoundError:
        tmux_ok = False
        tmux_detail = (
            "tmux not installed — run ./install.sh, or install manually "
            "(brew/apt-get/dnf/pacman). On Windows use WSL2."
        )
    _check("tmux", tmux_ok, tmux_detail)

    # Author seed repo is a git repo (required for project_create — its HEAD
    # is imported into each project's per-project bare repo). The check is
    # strict: ``src`` must be the *root* of a git work tree, not just inside
    # one. Otherwise dropping MinionsOS into a non-git folder under an outer
    # repo (layout ``A/.git``, ``A/B``, ``A/B/MinionsOS``) would silently
    # treat ``A`` as the seed source and pull in B's siblings.
    from minions.lifecycle.git_utils import (
        find_enclosing_git_work_tree,
        is_git_work_tree,
    )
    from minions.lifecycle.project import author_repo

    src = author_repo()
    author_is_repo = is_git_work_tree(src)
    if author_is_repo:
        detail = str(src)
    else:
        enclosing = find_enclosing_git_work_tree(src) if src.exists() else None
        if enclosing is not None and enclosing != src.resolve():
            detail = (
                f"{src} — not a git repo itself but inside {enclosing}. "
                f"Either run `cd {src} && git init && git add -A && git commit`, "
                f"or set MINIONS_AUTHOR_REPO={enclosing} to seed from the outer repo."
            )
        else:
            detail = (
                f"{src} — run: git init && git add -A && git commit, or set gru.yaml:author_repo"
            )
    _check("author-repo-is-git-repo", author_is_repo, detail)

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

    # Visual extras (opencv-python-headless / pdf2image / pillow / numpy).
    # These power mos_visual_* tools. install.sh installs them in the
    # background — surface progress here so users can see when it lands.
    try:
        for mod in ("cv2", "pdf2image", "numpy", "PIL"):
            importlib.import_module(mod)
        _check("visual-extras", True, "installed")
    except ImportError as exc:
        log_path = MINIONS_ROOT / ".install_visual.log"
        pid_path = MINIONS_ROOT / ".install_visual.pid"
        still_running = False
        if pid_path.exists():
            try:
                pid = int(pid_path.read_text().strip())
                import os as _os

                _os.kill(pid, 0)
                still_running = True
            except (OSError, ValueError):
                pass
        if still_running:
            detail = f"installing in background (tail -f {log_path})"
        else:
            detail = f"missing ({exc}); run: uv sync --extra visual"
        _check("visual-extras", False, detail)

    # EACN3 MCP plugin built (required so Roles have eacn3_* tools).
    plugin_dist = MINIONS_ROOT / "mcp-servers" / "eacn3" / "plugin" / "dist" / "server.js"
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
        required = {"minionsos", "eacn3", "keepalive"}
        missing = required - servers
        _check(
            "mcp-config-mounts-core",
            not missing,
            f"present: {sorted(servers)}" if not missing else f"missing: {sorted(missing)}",
        )
    except Exception as exc:
        _check("mcp-config-mounts-core", False, str(exc))

    # Codex project MCP config mounts the same servers for Codex host sessions.
    try:
        import tomllib

        codex_cfg_path = MINIONS_ROOT / ".codex" / "config.toml"
        codex_cfg = tomllib.loads(codex_cfg_path.read_text(encoding="utf-8"))
        servers = set((codex_cfg.get("mcp_servers") or {}).keys())
        missing = {"minionsos", "eacn3", "keepalive"} - servers
        _check(
            "codex-mcp-config-mounts-core",
            not missing,
            f"present: {sorted(servers)}" if not missing else f"missing: {sorted(missing)}",
        )
        eacn3 = (codex_cfg.get("mcp_servers") or {}).get("eacn3") or {}
        eacn_cmd = str(eacn3.get("command") or "")
        eacn_args = eacn3.get("args") or []
        eacn_direct = eacn_cmd == "node" and any(
            "mcp-servers/eacn3/plugin/dist/server.js" in str(arg) for arg in eacn_args
        )
        _check(
            "codex-mcp-eacn3-direct",
            eacn_direct,
            (
                "node mcp-servers/eacn3/plugin/dist/server.js"
                if eacn_direct
                else f"cmd={eacn_cmd!r} args={eacn_args}"
            ),
        )
    except Exception as exc:
        _check("codex-mcp-config-mounts-core", False, str(exc))
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

    # Config-key drift: install.sh seeds *.yaml from *.yaml.example only when
    # the target is ABSENT, so a `mos upgrade` that ships new example keys never
    # merges them into an existing live config. Pydantic defaults keep it from
    # crashing, but the operator silently never gains the new tunable. Surface
    # any top-level key present in *.yaml.example but missing from the live YAML.
    try:
        drift = _config_key_drift(CONFIG_DIR)
        _check(
            "config-keys-current",
            not drift,
            "all *.yaml have every *.yaml.example key"
            if not drift
            else (
                "new example keys not in live config (defaults apply; "
                "merge manually to tune): " + "; ".join(drift)
            ),
        )
    except Exception as exc:
        _check("config-keys-current", False, str(exc))

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

    if not all(
        c["ok"]
        for c in checks
        if not c["name"].startswith("viz-")
        and c["name"] not in {"visual-extras", "config-keys-current"}
    ):
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# heartbeats — per-role liveness audit (Issue #37)
# ---------------------------------------------------------------------------

# Issue #37 thresholds: a heartbeat older than 5 min is suspicious, 30 min is
# almost certainly a wedge, > 1 h is a hard failure that warrants respawn.
# These bands map to the emoji ladder in the audit output.
_HEARTBEAT_OK_SEC = 5 * 60
_HEARTBEAT_WARN_SEC = 30 * 60
_HEARTBEAT_STALE_SEC = 60 * 60


def _heartbeat_band(age_sec: float) -> tuple[str, str]:
    """Return (emoji, label) for a heartbeat age in seconds."""
    if age_sec < _HEARTBEAT_OK_SEC:
        return ("🟢", "fresh")
    if age_sec < _HEARTBEAT_WARN_SEC:
        return ("🟡", "slow")
    if age_sec < _HEARTBEAT_STALE_SEC:
        return ("🔴", "stale")
    return ("⛔", "wedged")


def _collect_heartbeats(port: int) -> list[dict[str, object]]:
    """Read every active role's heartbeat file under project *port*.

    Walks the role registry, locates the per-role workspace, reads the
    ``.minionsos/heartbeat`` JSON written by ``await_events._touch_heartbeat``
    / ``noter_wait._touch_heartbeat``, and returns a row per role with the
    age delta in seconds. Roles with no heartbeat file (e.g. just spawned)
    are reported with ``age_sec=None`` so the caller can render them
    differently.
    """
    from datetime import UTC, datetime

    from minions.lifecycle.role import list_roles

    now = datetime.now(tz=UTC)
    rows: list[dict[str, object]] = []
    for role in list_roles(port):
        ws = role.get("workspace_path")
        if not ws:
            rows.append({"name": role["name"], "age_sec": None, "detail": "no workspace"})
            continue
        hb_path = Path(str(ws)) / ".minionsos" / "heartbeat"
        if not hb_path.is_file():
            rows.append({"name": role["name"], "age_sec": None, "detail": "no heartbeat file"})
            continue
        try:
            payload = json.loads(hb_path.read_text(encoding="utf-8"))
            alive_at = datetime.fromisoformat(str(payload.get("alive_at")))
            age_sec = (now - alive_at).total_seconds()
            rows.append(
                {
                    "name": role["name"],
                    "age_sec": age_sec,
                    "alive_at": payload.get("alive_at"),
                    "pid": payload.get("pid"),
                }
            )
        except (OSError, ValueError, KeyError) as exc:
            rows.append({"name": role["name"], "age_sec": None, "detail": f"parse error: {exc}"})
    return rows


@app.command(name="heartbeats")
def heartbeats_cmd(
    port: int = typer.Argument(..., help="Project port to audit."),
    json_flag: bool = typer.Option(False, "--json"),
    exit_on_stale: bool = typer.Option(
        False,
        "--exit-on-stale",
        help="Exit with code 2 if any heartbeat is in the 'stale' or 'wedged' band.",
    ),
) -> None:
    """Show heartbeat freshness for every active role in a project (Issue #37).

    Bands: 🟢 <5min, 🟡 <30min, 🔴 <1h, ⛔ ≥1h. ``--exit-on-stale`` makes this
    suitable for cron-driven health alerting: a non-zero exit on red/⛔ rows.
    """
    rows = _collect_heartbeats(port)
    if json_flag:
        typer.echo(json.dumps(rows, indent=2))
    else:
        console = Console()
        table = Table(title=f"Heartbeats for project {port}")
        table.add_column("role")
        table.add_column("status")
        table.add_column("age")
        table.add_column("detail")
        for r in rows:
            age = r.get("age_sec")
            if not isinstance(age, (int, float)):
                table.add_row(str(r["name"]), "⚪", "—", str(r.get("detail", "")))
            else:
                emoji, label = _heartbeat_band(float(age))
                table.add_row(
                    str(r["name"]),
                    f"{emoji} {label}",
                    f"{float(age):.0f}s",
                    str(r.get("alive_at", "")),
                )
        console.print(table)
    if exit_on_stale:
        bad = any(
            isinstance(age_val, (int, float)) and float(age_val) >= _HEARTBEAT_WARN_SEC
            for r in rows
            for age_val in (r.get("age_sec"),)
        )
        if bad:
            raise typer.Exit(2)


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


@app.command(name="upgrade")
def upgrade_cmd(
    force: bool = typer.Option(
        False, "--force", help="Force full reinstall (MINIONS_FORCE_INSTALL=1)."
    ),
) -> None:
    """Pull latest MinionsOS and run incremental install.

    Equivalent to: git pull --ff-only && ./install.sh
    Only rebuilds components whose inputs changed since the last install.
    Use --force to bypass freshness stamps and rebuild everything.
    """
    console = Console()
    console.print("[bold]Upgrading MinionsOS...[/bold]")

    pull = subprocess.run(
        ["git", "pull", "--ff-only"],
        cwd=str(MINIONS_ROOT),
        capture_output=True,
        text=True,
    )
    if pull.returncode != 0:
        console.print(f"[red]git pull failed:[/red]\n{pull.stderr.strip()}")
        console.print("[yellow]Hint: stash or commit local changes first.[/yellow]")
        raise typer.Exit(1)

    pull_msg = pull.stdout.strip()
    if "Already up to date" in pull_msg:
        console.print("[green]Already up to date.[/green]")
    else:
        console.print(f"[green]{pull_msg}[/green]")

    env = {**os.environ}
    if force:
        env["MINIONS_FORCE_INSTALL"] = "1"

    install = subprocess.run(
        ["bash", str(MINIONS_ROOT / "install.sh")],
        cwd=str(MINIONS_ROOT),
        env=env,
    )
    if install.returncode != 0:
        raise typer.Exit(install.returncode)

    # New code/prompts are on disk, but nothing already running has reloaded.
    # Roles freeze SYSTEM.md + whitelist + MCP authz at launch; the Gru monitor
    # snapshots gru.yaml once. Detect live processes and tell the operator how
    # to apply the upgrade to them. This is advisory — never fails the upgrade.
    try:
        from minions.lifecycle.restart import (
            gru_monitor_status,
            list_active_projects,
        )

        mon = gru_monitor_status()
        active = list_active_projects()
        if mon.get("running") or active:
            bits = []
            if mon.get("running"):
                bits.append(f"Gru monitor (pid {mon.get('pid')})")
            if active:
                preview = ", ".join(str(p) for p in active[:8])
                if len(active) > 8:
                    preview += f", … (+{len(active) - 8} more)"
                bits.append(f"{len(active)} active project(s): {preview}")
            console.print(
                "[yellow]Note: running processes are still on the OLD code — "
                + "; ".join(bits)
                + ".[/yellow]"
            )
            console.print(
                "[yellow]Roles do not hot-reload SYSTEM.md / whitelist / MCP. "
                "Apply the upgrade to them with:[/yellow]\n"
                "  [bold]mos restart --all[/bold]    (Gru monitor + every running role)\n"
                "  [bold]mos restart --gru[/bold]    (just the Gru monitor)\n"
                "  [bold]mos restart <port>[/bold]   (one project's running roles)"
            )
    except Exception as exc:  # advisory only
        logger.debug("post-upgrade live-process check failed: %s", exc)

    raise typer.Exit(0)


@app.command(name="restart")
def restart_cmd(
    port: int | None = typer.Argument(None, help="Project port to restart all active roles for."),
    role: str | None = typer.Option(
        None, "--role", "-r", help="Restart only this role (requires a port)."
    ),
    gru: bool = typer.Option(False, "--gru", help="Restart the Gru monitor / watchdog sidecar."),
    all_: bool = typer.Option(
        False, "--all", help="Restart the Gru monitor AND every active project's roles."
    ),
    json_flag: bool = typer.Option(False, "--json"),
) -> None:
    """Cold-restart live processes so an upgrade's on-disk code/prompts take effect.

    A running Role froze its SYSTEM.md, tool whitelist, and MCP authz at launch;
    the Gru monitor snapshotted gru.yaml once. After `mos upgrade` (or any edit
    to a role prompt / whitelist / gru.yaml) the change only reaches a process
    when it restarts. This command recycles the tmux sessions / monitor process
    WITHOUT touching project data, EACN DBs, worktrees, or the Draft — roles
    cold-start and reconstruct context from the Draft (L1).

    Targets:
      mos restart --all                 Gru monitor + all active projects' roles
      mos restart --gru                 just the Gru monitor sidecar
      mos restart <port>                all active roles of one project
      mos restart <port> --role NAME    one role of one project
    """
    from minions.lifecycle.restart import (
        gru_monitor_status,
        list_active_projects,
        restart_gru_monitor,
        restart_project_roles,
        restart_role,
    )

    if role is not None and port is None:
        raise _fail("--role requires a project port: `mos restart <port> --role NAME`.")
    if not (all_ or gru or port is not None):
        raise _fail(
            "Specify a target: --all, --gru, or a project <port> (optionally with --role NAME)."
        )

    result: dict[str, object] = {}
    try:
        if all_:
            result["gru_monitor"] = restart_gru_monitor()
            ports = list_active_projects()
            result["projects"] = [restart_project_roles(p) for p in ports]
        else:
            if gru:
                result["gru_monitor"] = restart_gru_monitor()
            if port is not None:
                if role is not None:
                    result["role"] = restart_role(port, role)
                else:
                    result["projects"] = [restart_project_roles(port)]
    except MinionsError as e:
        raise _fail(str(e)) from e

    if json_flag:
        _json_out(result)
        return

    if "gru_monitor" in result:
        gm = cast(dict[str, object], result["gru_monitor"])
        console.print(
            f"[green]Gru monitor restarted[/green] "
            f"(killed {gm.get('killed_pid')} → new pid {gm.get('new_pid')}, host {gm.get('host')})."
        )
    if "role" in result:
        rr = cast(dict[str, object], result["role"])
        console.print(
            f"[green]Restarted role {rr.get('role')}[/green] on project {port} "
            f"(session {rr.get('session_name')})."
        )
    projects = cast(list[dict[str, object]], result.get("projects", []) or [])
    shown = 0
    for proj in projects:
        restarted = cast(list[dict[str, object]], proj.get("restarted", []))
        failed = proj.get("failed", [])
        # Suppress no-op projects (no live role recycled, nothing failed) so a
        # fleet restart against hundreds of stale `active` entries stays quiet.
        if not restarted and not failed:
            continue
        shown += 1
        names = ", ".join(str(r.get("role")) for r in restarted) or "none"
        console.print(
            f"[green]Project {proj.get('port')}:[/green] restarted [{names}]"
            + (f"; [red]failed {failed}[/red]" if failed else "")
        )
    if projects and shown == 0:
        console.print(
            f"[dim]No live roles to restart across {len(projects)} project(s) "
            "(none had a running tmux session).[/dim]"
        )
    # Surface any monitor that ended up not running (defensive).
    status = gru_monitor_status()
    if ("gru_monitor" in result) and not status.get("running"):
        console.print(
            "[yellow]Warning: Gru monitor does not appear to be running after restart; "
            "check minions/state/logs/gru-monitor.log[/yellow]"
        )


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


@project_app.command(name="reimport")
def project_reimport_cmd(port: int = typer.Argument(..., help="Project port.")) -> None:
    """Rebuild a missing projects.json entry from project_<port>/meta.json."""
    from minions.lifecycle.project import project_reimport

    try:
        entry = project_reimport(port)
    except MinionsError as e:
        raise _fail(str(e)) from e
    console.print(
        f"[green]Reimported project {entry.port}[/green] status={entry.status} "
        f"real_name={entry.real_name}"
    )


@project_app.command(name="relocate")
def project_relocate_cmd(
    port: int = typer.Argument(..., help="Project port."),
    new_path: Path = typer.Argument(..., help="New absolute path for project_<port>/."),  # noqa: B008
) -> None:
    """Move project_<port>/ to a new path and rewrite all absolute-path references."""
    from minions.lifecycle.project import project_relocate

    try:
        entry = project_relocate(port, new_path)
    except MinionsError as e:
        raise _fail(str(e)) from e
    console.print(f"[green]Relocated project {entry.port} to {new_path}.[/green]")


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
        result = dismiss_role(port, name, caller="cli:mos role dismiss")
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


@role_app.command(name="capture")
def role_capture(
    port: int = typer.Argument(..., help="Project port."),
    name: str = typer.Argument(..., help="Role name."),
    lines: int = typer.Option(
        100,
        "--lines",
        "-n",
        help="Number of lines to capture from scrollback (default: 100).",
    ),
) -> None:
    """Capture and print the role's current tmux pane output (issue #60).

    Shows what the role is currently doing by capturing its tmux pane.
    ANSI escape sequences are stripped for readability. Use this for quick
    inspection during incident triage when the role appears stuck.
    """
    from minions.lifecycle.role_launcher import session_name as _session_name

    sess = _session_name(port, name)
    # tmux capture-pane -t <session> -S <start-line> -p | strip ANSI
    cmd = [
        "tmux",
        "capture-pane",
        "-t",
        sess,
        "-S",
        f"-{lines}",
        "-p",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Strip ANSI escape sequences
        from minions.tools.utils import strip_ansi_escapes

        clean = strip_ansi_escapes(result.stdout)
        console.print(clean, markup=False, highlight=False)
    except subprocess.CalledProcessError as exc:
        raise _fail(
            f"tmux capture-pane failed for session {sess}. Is the role running? Error: {exc.stderr}"
        ) from exc


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


@role_app.command(name="kick")
def role_kick(
    port: int = typer.Argument(..., help="Project port."),
    name: str = typer.Argument(..., help="Role name."),
    prompt: str | None = typer.Option(
        None,
        "--prompt",
        "-p",
        help="Inline prompt text. Mutually exclusive with --prompt-file.",
    ),
    prompt_file: Path | None = typer.Option(  # noqa: B008
        None,
        "--prompt-file",
        "-f",
        exists=True,
        readable=True,
        help="Path to a file containing the prompt to inject.",
    ),
    retries: int = typer.Option(
        3,
        "--retries",
        help="How many submit attempts before giving up. Default 3.",
    ),
    wait: float = typer.Option(
        2.0,
        "--wait",
        help="Seconds between paste and Enter (and between Enter retries).",
    ),
) -> None:
    """Inject a recovery prompt into a live role pane (GitHub Issue #17).

    Uses the literal-string `tmux send-keys -l` path which bypasses the
    Claude Code TUI's bracketed-paste interpretation. After the text
    lands, sends Enter; if no submit is observed within --wait seconds,
    sends Enter again up to --retries times. This is the operator-side
    counterpart to the wedge watchdog (#15): the watchdog kills wedged
    sessions automatically; `mos role kick` lets a human inject a
    targeted nudge into a live (possibly stuck) pane without resorting
    to the unreliable paste-buffer + send-keys Enter dance.
    """
    import time

    from minions.lifecycle.role_launcher import session_alive
    from minions.lifecycle.role_launcher import session_name as _session_name

    if (prompt is None) == (prompt_file is None):
        raise _fail("Provide exactly one of --prompt or --prompt-file.")
    if prompt is not None:
        text = prompt
    else:
        assert prompt_file is not None  # narrowed by the XOR check above
        text = prompt_file.read_text(encoding="utf-8")
    if not text.strip():
        raise _fail("Prompt is empty.")
    if not session_alive(port, name):
        raise _fail(
            f"No live tmux session for role={name!r} on port {port}. "
            f"Use `mos role list {port}` to see registered roles."
        )
    sess = _session_name(port, name)
    # `send-keys -l` writes the literal bytes (no key-binding interpretation),
    # which is the empirically reliable path through the Claude Code input
    # widget. The bracketed-paste path used by `paste-buffer` is what
    # sometimes fails to commit before Enter (Issue #17).
    rc = subprocess.run(
        ["tmux", "send-keys", "-t", sess, "-l", text],
        capture_output=True,
    ).returncode
    if rc != 0:
        raise _fail(f"tmux send-keys -l failed (rc={rc}) for session {sess!r}.")
    console.print(f"[dim]Pasted {len(text)} bytes into {sess}; sending Enter…[/dim]")
    for attempt in range(1, max(1, retries) + 1):
        time.sleep(max(0.0, wait))
        rc = subprocess.run(
            ["tmux", "send-keys", "-t", sess, "Enter"],
            capture_output=True,
        ).returncode
        if rc != 0:
            console.print(f"[yellow]send-keys Enter rc={rc} (attempt {attempt}/{retries})[/yellow]")
            continue
        console.print(f"[green]Enter sent (attempt {attempt}/{retries}).[/green]")
    console.print(
        "[dim]Note: tmux cannot confirm the role processed the submission. "
        "Tail `mos role inspect` or `tmux attach` to verify.[/dim]"
    )


# ---------------------------------------------------------------------------
# issues subcommands
# ---------------------------------------------------------------------------

issues_app = typer.Typer(help="Read runtime issue reports filed by Roles.")
app.add_typer(issues_app, name="issues")


def _format_issue_row(rec: dict) -> tuple[str, str, str, str, str, str]:
    reporter = rec.get("reporter") or {}
    role = str(reporter.get("role") or "?") if isinstance(reporter, dict) else "?"
    return (
        str(rec.get("id") or "?"),
        str(rec.get("ts") or "?"),
        str(rec.get("severity") or "?"),
        str(rec.get("component") or "?"),
        role,
        str(rec.get("title") or ""),
    )


@issues_app.command("list")
def issues_list(
    port: int = typer.Argument(..., help="Project port."),
    json_flag: bool = typer.Option(False, "--json"),
) -> None:
    """List all issue reports filed against a live project."""
    from minions.tools.issues import list_issues

    records = list_issues(port)
    if json_flag:
        _json_out(records)
        return
    if not records:
        console.print(f"No issues filed for project {port}.")
        return
    table = Table(title=f"Issues for project {port}", show_lines=True)
    table.add_column("ID")
    table.add_column("When")
    table.add_column("Sev")
    table.add_column("Component")
    table.add_column("Role")
    table.add_column("Title", overflow="fold")
    for rec in records:
        table.add_row(*_format_issue_row(rec))
    console.print(table)


@issues_app.command("tail")
def issues_tail(
    port: int = typer.Argument(..., help="Project port."),
    n: int = typer.Option(10, "--n", "-n", help="How many recent issues to show."),
    json_flag: bool = typer.Option(False, "--json"),
) -> None:
    """Show the most recent N issue reports for a project."""
    from minions.tools.issues import tail_issues

    records = tail_issues(port, n)
    if json_flag:
        _json_out(records)
        return
    if not records:
        console.print(f"No issues filed for project {port}.")
        return
    for rec in records:
        console.print("─" * 60)
        reporter = rec.get("reporter")
        if isinstance(reporter, dict):
            reporter_role = cast(dict[str, object], reporter).get("role", "?")
        else:
            reporter_role = "?"
        console.print(
            f"[cyan]{rec.get('id')}[/cyan]  "
            f"[dim]{rec.get('ts')}[/dim]  "
            f"[bold]{rec.get('severity')}[/bold]/{rec.get('component')}  "
            f"[magenta]{reporter_role}[/magenta]"
        )
        console.print(f"[bold]{rec.get('title', '')}[/bold]")
        if rec.get("summary"):
            console.print(rec["summary"])
        if rec.get("evidence"):
            console.print(f"[dim]evidence:[/dim] {rec['evidence']}")
        if rec.get("workaround"):
            console.print(f"[dim]workaround:[/dim] {rec['workaround']}")


@issues_app.command("archive")
def issues_archive(
    json_flag: bool = typer.Option(False, "--json"),
) -> None:
    """List archived issue files under ~/.minionsos/issues/.

    These are snapshots taken at project_close / project_dormant time;
    use them when the live project tree no longer exists.
    """
    from minions.paths import host_issues_archive_dir

    archive = host_issues_archive_dir()
    if not archive.exists():
        console.print("No archived issue files yet.")
        return
    files = sorted(archive.glob("*.jsonl"))
    if json_flag:
        _json_out([str(p) for p in files])
        return
    if not files:
        console.print(f"No archived issue files in {archive}.")
        return
    table = Table(title=f"Archived issues ({archive})", show_lines=True)
    table.add_column("File")
    table.add_column("Size", justify="right")
    for f in files:
        try:
            size = f.stat().st_size
        except OSError:
            size = 0
        table.add_row(str(f), f"{size}B")
    console.print(table)


# ---------------------------------------------------------------------------
# viz subcommands (dispatch to minions/bin/viz)
# ---------------------------------------------------------------------------

viz_app = typer.Typer(help="MinionsOS Observatory (minions-viz) control.")
app.add_typer(viz_app, name="viz")


# ---------------------------------------------------------------------------
# scaffold + audit subcommands (extension-point stubs and contract drift check)
# ---------------------------------------------------------------------------

from minions.scaffold.cli import audit_command as _audit_command  # noqa: E402
from minions.scaffold.cli import scaffold_app as _scaffold_app  # noqa: E402

app.add_typer(_scaffold_app, name="scaffold")
app.command(name="audit", help=_audit_command.__doc__)(_audit_command)


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


@app.command(name="cache-stats")
def cache_stats_cmd(
    port: int | None = typer.Argument(None, help="Project port. Omit for --session mode."),
    role: str | None = typer.Argument(None, help="Role name. Omit to list all Roles."),
    session: Path | None = typer.Option(None, "--session", help="Single jsonl path."),  # noqa: B008
    repo_root: Path = typer.Option(  # noqa: B008
        MINIONS_ROOT,
        "--repo-root",
        help="MinionsOS repo root (where projects/ lives).",
    ),
) -> None:
    """Report token/cache usage for a Role, project, or single session.

    Three modes:

    \b
      mos cache-stats <port> <role>   per-Role rollup across sessions
      mos cache-stats <port>          per-project rollup (all Roles)
      mos cache-stats --session FILE  raw single-session report

    Identifies cold-start sessions (cache_read=0 on the first turn) so you
    can see how many ``mos_reset_context`` calls / watchdog respawns
    happened, and what each cost in cache_creation tokens.
    """
    from minions.tools import cache_stats as _cs

    if session is not None:
        if not session.exists():
            raise _fail(f"file not found: {session}")
        turns = _cs._load_turns(session)
        console.print(_cs._format_session_report(session, turns))
        return

    if port is None:
        raise _fail(
            "Pass either <port> [<role>] for a Role/project rollup, "
            "or --session FILE for a single-session report."
        )

    repo_root_path = repo_root
    claude_root = Path.home() / ".claude" / "projects"

    if role is not None:
        target = _cs._role_cwd(port, role, repo_root_path)
        sessions = _cs._discover_sessions_for_cwd(target, claude_root)
        console.print(_cs._format_role_report(port, role, target, sessions))
        return

    console.print(_cs._format_project_report(port, repo_root_path, claude_root))


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
# benchmark subcommands
# ---------------------------------------------------------------------------

benchmark_app = typer.Typer(help="Run benchmark suites (HLE, MMLU, etc.).")
app.add_typer(benchmark_app, name="benchmark")


@benchmark_app.command(name="run")
def benchmark_run(
    jsonl_path: Path = typer.Argument(..., help="JSONL file with one task per line."),  # noqa: B008
    profile: str = typer.Option("hle-answer", "--profile", "-P", help="Mission profile name."),
    name_prefix: str | None = typer.Option(
        None, "--prefix", help="Project name prefix (defaults to JSONL stem)."
    ),
    auto_evaluate: bool = typer.Option(
        True, "--auto-eval/--no-auto-eval", help="Run mos_evaluate after submissions."
    ),
    output_dir: Path | None = typer.Option(  # noqa: B008
        None, "--output", "-o", help="Where to save the run summary JSON."
    ),
    json_flag: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Run a benchmark from a JSONL task file.

    Each line should be a JSON object with: task_id, question, expected.
    Optional: metadata.

    Example::

        mos benchmark run hle_easy.jsonl --profile hle-answer
    """
    from minions.tools.benchmark import benchmark_run_from_jsonl, benchmark_save_run

    try:
        run = benchmark_run_from_jsonl(
            jsonl_path,
            profile=profile,
            name_prefix=name_prefix,
            auto_evaluate=auto_evaluate,
        )
    except MinionsError as e:
        raise _fail(str(e)) from e

    saved_path = benchmark_save_run(run, output_dir=output_dir)

    if json_flag:
        _json_out(run.model_dump())
        return

    console.print(f"[green]Benchmark run {run.run_id}[/green] saved to {saved_path}")
    if run.aggregate:
        agg = run.aggregate
        console.print(
            f"  total={agg.get('total_tasks')} "
            f"correct={agg.get('correct')} "
            f"incorrect={agg.get('incorrect')} "
            f"failed={agg.get('failed')} "
            f"accuracy={agg.get('accuracy', 0):.2%}"
        )


@benchmark_app.command(name="list-profiles")
def benchmark_list_profiles() -> None:
    """List available mission profiles."""
    from minions.profiles import list_profiles

    profiles = list_profiles()
    if not profiles:
        console.print("[yellow]No profiles available.[/yellow]")
        return

    table = Table(title="Available Mission Profiles", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Path")
    from minions.profiles import PROFILES_DIR

    for name in profiles:
        table.add_row(name, str(PROFILES_DIR / f"{name}.yaml"))
    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Console-script entry point for the ``mos`` CLI.

    Wired through ``pyproject.toml`` ``[project.scripts]``; delegates to the
    Typer app so subcommands receive the standard ``argv`` / exit-code flow.
    """
    app()


if __name__ == "__main__":
    main()
