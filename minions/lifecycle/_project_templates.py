"""Project markdown template rendering.

Pure functions extracted from :mod:`minions.lifecycle.project` so the
orchestrator can shed the CLAUDE.md boilerplate. The originals are
re-exported from :mod:`minions.lifecycle.project` so existing imports
keep working.
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
        "branch AND the team's shared surface (the Book); every other role has "
        "its own private scratch branch at `branches/<role>/`. There is no "
        "separate shared branch — main IS the shared surface."
    )
    lines.append(
        "- Cross-role artefacts (Ethics reports/curation, Expert experiment "
        "result bundles, free-form handoffs) go to `branches/main/<subdir>/` via "
        "`mos_publish_to_shared` (serialized by a per-project lock). Each role "
        "may only publish into its allowed subdirs (see role boundary text). "
        "The Draft (L1) at `branches/main/draft/draft.json` is the single live "
        "process graph: updated in place by `mos_draft_append`/"
        "`mos_draft_annotate` and committed by Ethics via `mos_draft_commit_shared`."
    )
    lines.append(
        "- The Book layout on main (`Book.md`, `logic/`, `src/`, `evidence/`, "
        "`proposal/`) is filled by Gru promoting Ethics-sealed content via "
        "`mos_promote_to_book`."
    )
    lines.append(
        "- The review surface `branches/main/reviews/round-<n>/` is reserved "
        "for `mos_review_run`; the publish tool will reject any other caller."
    )
    lines.append(
        "- Root constitution at repo `CLAUDE.md` always wins on conflicts (see Hard rules)."
    )
    lines.append("")
    return "\n".join(lines)
