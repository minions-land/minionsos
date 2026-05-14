"""Role skill discovery.

Each Role may ship a ``minions/roles/{role}/skills/`` directory of
methodology / procedure skill files. Shared skills live under
``minions/roles/common/skills/`` and are discovered for every Role. This
module provides a small helper that enumerates them and extracts a one-line
summary for each, used by ``invoke_role_ephemeral`` to seed the Role's
wake-up message with a ``[Skills]`` block.

Skills are plain markdown. They MAY begin with a YAML frontmatter block
delimited by ``---`` lines; when present, a ``summary:`` field overrides
all other heuristics, and a ``status: deprecated`` or ``status: merged``
field hides the skill from discovery so deletions stay safe.

When no frontmatter summary is given, the body summary is extracted as:

1. Find the first non-blank line. If it starts with ``# ``, it is the H1
   title. Otherwise treat it as the summary directly.
2. If an H1 was found, use the next non-blank line that is not itself a
   heading as the summary.
3. Fall back to the H1 text (minus the leading ``# ``) if no suitable
   follow-up line exists.
4. Strip markdown emphasis (``*``, ``_``) and blockquote markers (``>``)
   and truncate to 100 characters.
"""

from __future__ import annotations

from pathlib import Path

from minions.paths import ROLES_DIR

_MAX_SUMMARY_LEN = 200
_HIDDEN_STATUSES = frozenset({"deprecated", "merged"})


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return ``(fields, body)``. ``fields`` is empty when no frontmatter.

    Recognises a leading ``---`` fence terminated by another ``---``. Only
    flat ``key: value`` lines are parsed; nested YAML or list values are
    intentionally ignored — frontmatter here is for discovery metadata,
    not arbitrary structured data.
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        return {}, text
    end = -1
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            end = i
            break
    if end == -1:
        return {}, text
    fields: dict[str, str] = {}
    for raw in lines[1:end]:
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    body = "".join(lines[end + 1 :])
    return fields, body


def _resolve_role_skills_dir(role_name: str) -> Path:
    """Map a registered role name to its skills directory.

    Expert roles are registered as ``expert-{slug}`` but all share the
    base ``expert/skills/`` directory.
    """
    base = "expert" if role_name.startswith("expert") else role_name
    return ROLES_DIR / base / "skills"


def _common_skills_dir() -> Path:
    return ROLES_DIR / "common" / "skills"


def _extract_summary(text: str) -> str:
    fields, body = _split_frontmatter(text)
    fm_summary = fields.get("summary", "").strip().strip('"').strip("'")
    chosen = fm_summary or _summary_from_body(body)
    chosen = chosen.lstrip("> ").strip()
    for ch in ("**", "__", "*", "_", "`"):
        chosen = chosen.replace(ch, "")
    chosen = " ".join(chosen.split())
    if len(chosen) > _MAX_SUMMARY_LEN:
        chosen = chosen[: _MAX_SUMMARY_LEN - 1].rstrip() + "…"
    return chosen


def _summary_from_body(text: str) -> str:
    lines = [ln.rstrip() for ln in text.splitlines()]
    non_blank = [ln for ln in lines if ln.strip()]
    if not non_blank:
        return ""

    first = non_blank[0].strip()
    title: str | None = None
    summary: str | None = None

    if first.startswith("# "):
        title = first[2:].strip()
        for ln in non_blank[1:]:
            s = ln.strip()
            if s.startswith("#"):
                continue
            summary = s
            break
    else:
        summary = first

    return summary or title or ""


def list_skills(role_name: str) -> list[tuple[str, str]]:
    """Return ``[(slug, summary), ...]`` for shared and role-specific skills.

    Returns an empty list if neither directory exists, both are empty, or no
    readable ``.md`` files exist. Shared skills are listed before role-specific
    skills; slugs are the file stem and each directory is sorted
    alphabetically for determinism.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for skills_dir in (_common_skills_dir(), _resolve_role_skills_dir(role_name)):
        if not skills_dir.is_dir():
            continue
        for path in sorted(skills_dir.glob("*.md")):
            if path.stem in seen:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            fields, _ = _split_frontmatter(text)
            if fields.get("status", "").strip().strip('"').strip("'") in _HIDDEN_STATUSES:
                seen.add(path.stem)
                continue
            summary = _extract_summary(text)
            out.append((path.stem, summary))
            seen.add(path.stem)
    return out
