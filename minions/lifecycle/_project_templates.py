"""Project markdown template rendering.

Pure functions extracted from :mod:`minions.lifecycle.project` so the
2292-line orchestrator can shed the 80 lines of CLAUDE.md / AGENTS.md
boilerplate. The originals are re-exported from
:mod:`minions.lifecycle.project` so existing imports keep working.
"""

from __future__ import annotations


def render_project_claude_md(
    port: int,
    real_name: str,
    venue: str | None,
    branch: str,
    workspace_abs: str,
    brief: str | None,
    topic_doc: str | None,
    template_dir: str | None,
) -> str:
    """Render a default project CLAUDE.md skeleton."""
    lines: list[str] = []
    lines.append(f"# {real_name} — Project CLAUDE.md")
    lines.append("")
    lines.append(
        "> Project-scoped narrative. Authored jointly by the human and Gru; other Roles read-only."
    )
    lines.append("")
    lines.append("## Facts")
    lines.append("")
    lines.append(f"- **Port:** `{port}`")
    lines.append(f"- **Real name:** {real_name}")
    if venue:
        lines.append(f"- **Venue:** {venue}")
    lines.append(f"- **Git branch:** `{branch}`")
    lines.append(f"- **Workspace (absolute):** `{workspace_abs}`")
    if topic_doc:
        lines.append(f"- **Topic doc:** `{topic_doc}`")
    if template_dir:
        lines.append(f"- **Venue template dir:** `{template_dir}`")
    lines.append("")
    lines.append("## Brief")
    lines.append("")
    lines.append(brief.strip() if brief else "_TODO: write a 1-3 paragraph project brief._")
    lines.append("")
    lines.append("## Working rules")
    lines.append("")
    lines.append("- All inter-Role communication goes through EACN3 on this port.")
    lines.append(
        "- Branch checkouts live under `branches/`: `branches/main/` is Gru's "
        "branch (the primary integration tree); every other role has its own "
        "branch at `branches/<role>/`; the shared cross-role tree lives at "
        "`branches/shared/` on its own branch."
    )
    lines.append(
        "- Cross-role artefacts (Ethics reports, Experimenter result bundles, "
        "Noter notes, free-form handoffs) go to `branches/shared/<subdir>/` via "
        "`mos_publish_to_shared`. Each role may only publish into its allowed "
        "subdirs (see role boundary text). The Scratchpad (L1) at "
        "`branches/shared/scratchpad/scratchpad.json` is updated in place by "
        "`mos_scratchpad_append`/`mos_scratchpad_annotate` and committed by "
        "Noter on a periodic cron via `mos_scratchpad_commit_shared`."
    )
    lines.append(
        "- The review surface `branches/shared/reviews/round-<n>/` is reserved "
        "for `mos_review_run`; the publish tool will reject any other caller."
    )
    lines.append(
        "- Root constitution at repo `CLAUDE.md` always wins on conflicts (see Hard rules)."
    )
    lines.append("")
    return "\n".join(lines)


def render_project_agents_md(real_name: str) -> str:
    """Render a Codex-compatible project context shim."""
    return "\n".join(
        [
            f"# {real_name} — Project Agent Context",
            "",
            "This project is managed by MinionsOS.",
            "",
            "Read `CLAUDE.md` in this directory for the project-scoped narrative, facts,",
            "working rules, and current brief. In this repository, `CLAUDE.md` is kept",
            "as the shared project context file for both Claude Code and Codex so the",
            "two agent hosts see the same operating assumptions.",
            "",
        ]
    )
