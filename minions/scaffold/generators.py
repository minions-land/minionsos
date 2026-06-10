"""Stub generators for the five MinionsOS extension points.

Each generator writes a minimal, on-style markdown or Python stub that
matches the conventions established by the existing files (frontmatter
keys for skills, section order for SYSTEM.md, etc.). The functions return
a :class:`GenerationResult` describing every path written plus the manual
follow-up checklist the caller must apply. Generators never silently edit
``minions/config/__init__.py``, ``minions/lifecycle/role.py``, or
``CLAUDE.md`` — those edits are review-mandatory and stay with the human.

Each generator is idempotent: passing ``--force`` overwrites; without it,
the call raises if the target already exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from minions.config import slugify
from minions.errors import MinionsError
from minions.scaffold.contracts import (
    DOMAINS_DIR,
    EXTENSION_POINTS,
    REVIEW_DIR,
    ROLES_DIR,
    TOOLS_DIR,
)


class ScaffoldError(MinionsError):
    """Raised when a generator cannot safely write a stub."""


@dataclass(frozen=True)
class GenerationResult:
    extension_point: str
    paths_written: list[Path] = field(default_factory=list)
    manual_followups: list[str] = field(default_factory=list)


def _write(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise ScaffoldError(f"{path} already exists (pass force=True to overwrite).")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _result(point: str, paths: list[Path]) -> GenerationResult:
    return GenerationResult(
        extension_point=point,
        paths_written=paths,
        manual_followups=list(EXTENSION_POINTS[point].manual_followups),
    )


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------


_ROLE_SYSTEM_TEMPLATE = """# {title} — System Prompt

## Identity & scope

You are {title}, a MinionsOS Role. Describe in one paragraph what work you
own and what you defer to other Roles.

## Can do

- <verb + object — concrete capability>
- <verb + object — concrete capability>

## Cannot do

- <out-of-scope action — usually owned by another Role>
- <out-of-scope action — owned by Gru / the author>

Your tool access is governed by the runtime whitelist; see the common role contract.

## Workspace read/write constraints

- `branches/{slug}/`: full read/write — this is your branch worktree.
- Other roles' branches: **read-only** for reference; request edits through EACN.
- Publish cross-role handoffs to `branches/main/handoffs/` via `mos_publish_to_shared`.

## Collaboration rules

- **EACN3 is the only inter-role bus.** Receive incoming events by calling
  `mos_await_events()` and respond with `eacn3_send_message` /
  `eacn3_create_task`.
- Do not call `eacn3_await_events` / `eacn3_next` / `eacn3_get_events`
  directly — `mos_await_events` already wraps the long-poll.

## Skills

Methodology / procedure skills live on disk under
`minions/roles/{slug}/skills/` and the shared `minions/roles/common/skills/`.
The wake-up `[Skills]` block lists `slug: summary` pairs. `Read` the matching
markdown file on demand. Host-level personal Claude configuration is outside
the Role contract.
"""


def generate_role(
    role_name: str, *, title: str | None = None, force: bool = False
) -> GenerationResult:
    """Create ``minions/roles/<role>/SYSTEM.md`` and an empty ``skills/`` dir."""
    slug = slugify(role_name)
    if not slug:
        raise ScaffoldError(f"Cannot derive a slug from role name {role_name!r}.")
    role_dir = ROLES_DIR / slug
    system = role_dir / "SYSTEM.md"
    skills = role_dir / "skills"
    content = _ROLE_SYSTEM_TEMPLATE.format(title=title or role_name, slug=slug)
    _write(system, content, force)
    skills.mkdir(parents=True, exist_ok=True)
    (skills / ".gitkeep").touch()
    return _result("role", [system, skills])


# ---------------------------------------------------------------------------
# Role skill
# ---------------------------------------------------------------------------


_SKILL_TEMPLATE = """---
slug: {slug}
summary: {summary}
layer: logical
# Advisory Role metadata, not Claude Code allowed-tools.
tools:
version: 1
status: active
supersedes:
references:
provenance: human
---

# Skill — {title}

<one-paragraph summary of when and why to invoke>

## Core question

<the single question this skill is built around>

## When to invoke

- <trigger>
- <trigger>

## Procedure

1. <step>
2. <step>
3. <step>

## Pitfalls

- <pitfall>

## Output habit

Mark every claim with `[evidence: ...]`, `[derived: ...]`, or `[speculation]`
per the root CLAUDE.md evidence-first convention.
"""


def generate_role_skill(
    role: str,
    skill_name: str,
    *,
    summary: str | None = None,
    force: bool = False,
) -> GenerationResult:
    """Create ``minions/roles/<role>/skills/<slug>.md``."""
    if not (ROLES_DIR / role).is_dir():
        raise ScaffoldError(
            f"Role {role!r} does not exist; create it with `mos scaffold role` first."
        )
    slug = slugify(skill_name)
    if not slug:
        raise ScaffoldError(f"Cannot derive a slug from skill name {skill_name!r}.")
    target = ROLES_DIR / role / "skills" / f"{slug}.md"
    body = _SKILL_TEMPLATE.format(
        slug=slug,
        title=skill_name,
        summary=summary or f"<one-line summary of {skill_name!r}>",
    )
    _write(target, body, force)
    return _result("skill", [target])


# ---------------------------------------------------------------------------
# Review template
# ---------------------------------------------------------------------------


_REVIEW_TEMPLATE = """# {title}

Round: <n>
Reviewed target: <paper path | artifact bundle | commit>
Allowed context: <what this pass may read>

## Findings

- <finding + evidence>

## Questions

- <scoped question>

## Required Revisions

- <revision request>

## Evidence Pointers

- <citation, section, code pointer, table, figure, or artifact path>
"""


def generate_review_template(
    template_name: str,
    *,
    title: str | None = None,
    force: bool = False,
) -> GenerationResult:
    """Create ``minions/review/templates/<slug>.md``."""
    slug = slugify(template_name)
    target = REVIEW_DIR / "templates" / f"{slug}.md"
    body = _REVIEW_TEMPLATE.format(title=title or template_name)
    _write(target, body, force)
    return _result("review-template", [target])


# ---------------------------------------------------------------------------
# Domain pack
# ---------------------------------------------------------------------------


_DOMAIN_TEMPLATE = """# Domain Pack: {title} ({slug})

You are an expert in {title}. This pack gives you operational context for the specialty.

## Core scope

<what this domain covers>

## Canonical references

- <author (year) — title; one-line note>
- <author (year) — title; one-line note>

## Common methods

- <method>
- <method>

## Typical pitfalls

- <pitfall>

## Useful toolchains

- <library / framework>

## Evaluation norms

- <metric / convention>
"""


def generate_domain(
    domain_name: str,
    *,
    title: str | None = None,
    force: bool = False,
) -> GenerationResult:
    """Create ``minions/domains/<slug>.md``."""
    slug = slugify(domain_name)
    target = DOMAINS_DIR / f"{slug}.md"
    body = _DOMAIN_TEMPLATE.format(title=title or domain_name, slug=slug)
    _write(target, body, force)
    return _result("domain", [target])


# ---------------------------------------------------------------------------
# MCP tool
# ---------------------------------------------------------------------------


_TOOL_MODULE_TEMPLATE = '''"""MCP tool stub for ``{tool_name}``.

Wire this tool into the FastMCP server by importing :func:`{tool_name}`
in ``minions/tools/mcp_server.py`` and decorating it with ``@mcp.tool()``.
Update the per-role whitelist in ``minions/config/__init__.py:_WHITELIST``
and document the boundary in ``MANUAL/domains/publish.md``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class {args_class}(BaseModel):
    """Arguments for ``{tool_name}``."""

    project_port: int = Field(..., description="Project port the call targets.")


def {tool_name}(args: {args_class}) -> dict:
    """<one-paragraph contract of what this tool does>."""
    raise NotImplementedError("Implement {tool_name} before wiring it into the MCP server.")


__all__ = ["{args_class}", "{tool_name}"]
'''


def generate_mcp_tool(
    tool_name: str,
    *,
    module_name: str | None = None,
    force: bool = False,
) -> GenerationResult:
    """Create ``minions/tools/<module>.py`` with a ``mos_*`` stub.

    The generator deliberately stops short of editing
    ``minions/tools/mcp_server.py``: the human reviewing the PR confirms
    the new tool's name, signature, and per-role authorization before it
    is exposed.
    """
    if not tool_name.startswith("mos_"):
        raise ScaffoldError("MinionsOS MCP tools must be named `mos_<verb>_<object>`.")
    module = module_name or tool_name.removeprefix("mos_")
    target = TOOLS_DIR / f"{module}.py"
    args_class = "".join(part.capitalize() for part in tool_name.split("_")) + "Args"
    body = _TOOL_MODULE_TEMPLATE.format(
        tool_name=tool_name,
        args_class=args_class,
    )
    _write(target, body, force)
    return _result("tool", [target])


__all__ = [
    "GenerationResult",
    "ScaffoldError",
    "generate_domain",
    "generate_mcp_tool",
    "generate_review_template",
    "generate_role",
    "generate_role_skill",
]
