"""Typer subcommands for ``mos scaffold`` and ``mos audit``.

Wired into the top-level ``mos`` CLI in :mod:`minions.cli` via
``app.add_typer(scaffold_app, name="scaffold")`` and
``app.command(name="audit")(audit_command)``.
"""

from __future__ import annotations

import json as _json
from collections import Counter
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from minions.scaffold import audit as audit_module
from minions.scaffold import generators

console = Console()
err_console = Console(stderr=True)

scaffold_app = typer.Typer(
    name="scaffold",
    help="Stub generators for MinionsOS extension points.",
    no_args_is_help=True,
)


_SEVERITY_STYLE = {
    "error": "red bold",
    "warning": "yellow",
    "info": "cyan",
}


def _print_result(result: generators.GenerationResult) -> None:
    console.print(f"[green]wrote[/green] ({result.extension_point}):")
    for path in result.paths_written:
        try:
            shown = path.relative_to(Path.cwd())
        except ValueError:
            shown = path
        console.print(f"  - {shown}")
    if result.manual_followups:
        console.print("[bold]manual follow-ups:[/bold]")
        for item in result.manual_followups:
            console.print(f"  • {item}")


def _handle(call) -> None:
    try:
        _print_result(call())
    except generators.ScaffoldError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1) from exc


@scaffold_app.command("role")
def scaffold_role(
    name: str = typer.Argument(..., help="Role slug, e.g. 'librarian'."),
    title: str = typer.Option(None, help="Display title (defaults to capitalised name)."),
    force: bool = typer.Option(False, help="Overwrite if SYSTEM.md already exists."),
) -> None:
    """Create minions/roles/<name>/SYSTEM.md plus an empty skills/ dir."""
    _handle(lambda: generators.generate_role(name, title=title, force=force))


@scaffold_app.command("skill")
def scaffold_skill(
    role: str = typer.Argument(..., help="Existing role directory name, e.g. 'expert'."),
    name: str = typer.Argument(..., help="Skill name, e.g. 'evidence-audit'."),
    summary: str = typer.Option(None, help="One-line summary used by skill discovery."),
    force: bool = typer.Option(False, help="Overwrite if the skill file already exists."),
) -> None:
    """Create minions/roles/<role>/skills/<slug>.md."""
    _handle(lambda: generators.generate_role_skill(role, name, summary=summary, force=force))


@scaffold_app.command("review-template")
def scaffold_review_template(
    name: str = typer.Argument(..., help="Template name, e.g. 'rebuttal-note'."),
    title: str = typer.Option(None, help="Display title shown at the top of the template."),
    force: bool = typer.Option(False, help="Overwrite if the template already exists."),
) -> None:
    """Create minions/review/templates/<slug>.md."""
    _handle(lambda: generators.generate_review_template(name, title=title, force=force))


@scaffold_app.command("domain")
def scaffold_domain(
    name: str = typer.Argument(..., help="Domain name, e.g. 'rl-theory'."),
    title: str = typer.Option(None, help="Display title for the domain pack."),
    force: bool = typer.Option(False, help="Overwrite if the domain pack already exists."),
) -> None:
    """Create minions/domains/<slug>.md."""
    _handle(lambda: generators.generate_domain(name, title=title, force=force))


@scaffold_app.command("tool")
def scaffold_tool(
    name: str = typer.Argument(..., help="Tool name, must start with `mos_`."),
    module: str = typer.Option(None, help="Module file stem under minions/tools/."),
    force: bool = typer.Option(False, help="Overwrite if the module already exists."),
) -> None:
    """Create minions/tools/<module>.py with an MCP-tool stub."""
    _handle(lambda: generators.generate_mcp_tool(name, module_name=module, force=force))


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def audit_command(
    json: bool = typer.Option(False, "--json", help="Emit issues as JSON."),
    fail_on_warning: bool = typer.Option(
        False, help="Exit non-zero on warnings as well as errors."
    ),
    refresh_wildcards: bool = typer.Option(
        False,
        "--refresh-wildcards",
        help=(
            "Recompute the wildcard baseline (minions/scaffold/_wildcard_baseline.txt)"
            " from the current whitelist + tool registrations. Use after intentionally"
            " adding a tool that auto-grants via wildcard."
        ),
    ),
) -> None:
    """Cross-check MinionsOS extension contracts against the live codebase."""
    if refresh_wildcards:
        _refresh_wildcard_baseline()
        console.print("[green]wildcard baseline refreshed.[/green]")
        return
    issues = audit_module.audit()

    if json:
        typer.echo(_json.dumps([issue.as_dict() for issue in issues], indent=2))
    else:
        if not issues:
            console.print("[green]audit clean[/green] — every contract matches the live repo.")
        else:
            table = Table(show_header=True, header_style="bold")
            table.add_column("severity", width=8)
            table.add_column("surface", width=10)
            table.add_column("message")
            for issue in issues:
                style = _SEVERITY_STYLE.get(issue.severity, "")
                table.add_row(
                    f"[{style}]{issue.severity}[/{style}]" if style else issue.severity,
                    issue.surface,
                    issue.message + (f"\n[dim]hint: {issue.hint}[/dim]" if issue.hint else ""),
                )
            console.print(table)
            counts = Counter(issue.severity for issue in issues)
            console.print(
                "summary: " + ", ".join(f"{sev}={count}" for sev, count in sorted(counts.items()))
            )

    severity_counts = Counter(issue.severity for issue in issues)
    if severity_counts.get("error", 0) > 0:
        raise typer.Exit(1)
    if fail_on_warning and severity_counts.get("warning", 0) > 0:
        raise typer.Exit(2)


__all__ = ["audit_command", "scaffold_app"]


def _refresh_wildcard_baseline() -> None:
    """Recompute and write minions/scaffold/_wildcard_baseline.txt."""
    from minions.scaffold import contracts

    universe = set(contracts.list_registered_mcp_tools())
    seen: set[str] = set()
    rows: list[tuple[str, int]] = []
    for tools in contracts.whitelist_table().values():
        for entry in tools:
            if not entry.endswith("*") or not entry.startswith("mos_"):
                continue
            if entry in seen:
                continue
            seen.add(entry)
            prefix = entry[:-1]
            rows.append((entry, sum(1 for t in universe if t.startswith(prefix))))
    rows.sort()
    header = (
        "# auto-generated baseline of how many @mcp.tool()s match each wildcard.\n"
        "# update via: mos audit --refresh-wildcards (or hand-edit after review).\n"
    )
    body = "".join(f"{pattern}={count}\n" for pattern, count in rows)
    target = contracts.PACKAGE_ROOT / "scaffold" / "_wildcard_baseline.txt"
    target.write_text(header + body, encoding="utf-8")
