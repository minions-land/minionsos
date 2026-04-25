"""Role skill discovery.

Each Role may ship a ``minions/roles/{role}/skills/`` directory of
methodology / procedure skill files. This module provides a small helper
that enumerates them and extracts a one-line summary for each, used by
``invoke_role_ephemeral`` to seed the Role's wake-up message with a
``[Skills]`` block.

Skills are plain markdown. The summary is extracted as follows:

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

_MAX_SUMMARY_LEN = 100


def _resolve_role_skills_dir(role_name: str) -> Path:
    """Map a registered role name to its skills directory.

    Expert roles are registered as ``expert-{slug}`` but all share the
    base ``expert/skills/`` directory.
    """
    base = "expert" if role_name.startswith("expert") else role_name
    return ROLES_DIR / base / "skills"


def _extract_summary(text: str) -> str:
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

    chosen = summary or title or ""
    # Strip blockquote markers and light markdown emphasis.
    chosen = chosen.lstrip("> ").strip()
    for ch in ("**", "__", "*", "_", "`"):
        chosen = chosen.replace(ch, "")
    chosen = " ".join(chosen.split())
    if len(chosen) > _MAX_SUMMARY_LEN:
        chosen = chosen[: _MAX_SUMMARY_LEN - 1].rstrip() + "…"
    return chosen


def list_skills(role_name: str) -> list[tuple[str, str]]:
    """Return ``[(slug, summary), ...]`` for *role_name*'s skills directory.

    Returns an empty list if the directory does not exist, is empty, or
    contains no readable ``.md`` files. Slugs are the file stem; results
    are sorted alphabetically for determinism.
    """
    skills_dir = _resolve_role_skills_dir(role_name)
    if not skills_dir.is_dir():
        return []
    out: list[tuple[str, str]] = []
    for path in sorted(skills_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        summary = _extract_summary(text)
        out.append((path.stem, summary))
    return out
