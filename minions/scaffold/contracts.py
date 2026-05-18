"""Single-source-of-truth introspection for MinionsOS extension contracts.

Every check in :mod:`minions.scaffold.audit` and every stub in
:mod:`minions.scaffold.generators` reads the *live* state of the codebase
through the helpers below — never a hardcoded duplicate. If the contract
surface ever moves, fix the parser here and every downstream check picks
up the new layout for free.

Five extension points are tracked, mirroring the headings in
``minions/CLAUDE.md``:

1. Role
2. Role skill
3. Review output shape (template + skill)
4. Expert domain pack
5. MCP tool
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from minions.config import ROLE_WRITE_BOUNDARIES
from minions.lifecycle.role import FIXED_ROLES
from minions.paths import MINIONS_ROOT
from minions.tools.publish import _ROLE_ALLOWED_SHARED_SUBDIRS

REPO_ROOT: Path = MINIONS_ROOT
PACKAGE_ROOT: Path = MINIONS_ROOT / "minions"
ROLES_DIR: Path = PACKAGE_ROOT / "roles"
REVIEW_DIR: Path = PACKAGE_ROOT / "review"
DOMAINS_DIR: Path = PACKAGE_ROOT / "domains"
TOOLS_DIR: Path = PACKAGE_ROOT / "tools"
MCP_SERVERS_DIR: Path = REPO_ROOT / "mcp-servers"
MCP_JSON: Path = REPO_ROOT / ".mcp.json"
ROOT_CLAUDE_MD: Path = REPO_ROOT / "CLAUDE.md"
PACKAGE_CLAUDE_MD: Path = PACKAGE_ROOT / "CLAUDE.md"


@dataclass(frozen=True)
class ExtensionPoint:
    """Static description of one of the five extension points."""

    key: str
    title: str
    template_dir: Path
    summary: str
    manual_followups: tuple[str, ...]


EXTENSION_POINTS: dict[str, ExtensionPoint] = {
    "role": ExtensionPoint(
        key="role",
        title="New Role",
        template_dir=ROLES_DIR,
        summary="Long-lived agent-host process with a SYSTEM.md, whitelist, and FIXED_ROLES entry.",
        manual_followups=(
            "Add (role, 'main') and (role, 'subagent') entries in"
            " minions/config/__init__.py:_WHITELIST.",
            "Add the role to ROLE_CLASSIFICATION and ROLE_WRITE_BOUNDARIES"
            " in minions/config/__init__.py.",
            "Add the role to FIXED_ROLES in minions/lifecycle/role.py if it is"
            " registered via mos_spawn_role.",
            "Add a row to the tool/write-boundary table in root CLAUDE.md.",
            "Add a _BOUNDARY_TEXT entry in minions/lifecycle/role.py if the"
            " role needs custom boundary copy.",
            "Add a unit test under tests/unit/ covering registration and whitelist resolution.",
        ),
    ),
    "skill": ExtensionPoint(
        key="skill",
        title="New Role skill",
        template_dir=ROLES_DIR,
        summary="Procedural markdown skill discovered automatically at wake-up.",
        manual_followups=(
            "No code change required — `minions.lifecycle.skills.list_skills`"
            " discovers it on next wake.",
            "If the skill exercises an unusual title format, extend"
            " tests/unit/test_skills_discovery.py.",
        ),
    ),
    "review-template": ExtensionPoint(
        key="review-template",
        title="New review output shape",
        template_dir=REVIEW_DIR / "templates",
        summary="Review pass artifact template consumed by mos_review_run.",
        manual_followups=(
            "Update or add the matching skill in minions/review/skills/.",
            "Update tests pinning mos_review_run invariants under tests/unit/.",
        ),
    ),
    "domain": ExtensionPoint(
        key="domain",
        title="New Expert domain pack",
        template_dir=DOMAINS_DIR,
        summary=(
            "Reusable domain prompt asset injected when an Expert is registered for that domain."
        ),
        manual_followups=(
            "If the new domain needs runtime injection or CLI discovery,"
            " extend minions/lifecycle/role.py and minions/paths.py and add focused tests.",
        ),
    ),
    "tool": ExtensionPoint(
        key="tool",
        title="New MCP tool",
        template_dir=TOOLS_DIR,
        summary="Server-side tool exposed by the minionsos MCP server.",
        manual_followups=(
            "Register the tool with @mcp.tool() in minions/tools/mcp_server.py "
            "(or import it from a new module).",
            "Update the per-role lists in minions/config/__init__.py:_WHITELIST.",
            "Add the tool to the tool/write-boundary table in root CLAUDE.md.",
            "Add a unit test under tests/unit/.",
        ),
    ),
}


def list_role_dirs() -> list[str]:
    """Return role directory names under minions/roles/ (excluding common/SYSTEM.md)."""
    if not ROLES_DIR.is_dir():
        return []
    return sorted(
        p.name
        for p in ROLES_DIR.iterdir()
        if p.is_dir() and p.name not in {"common", "__pycache__"}
    )


def role_has_system_md(role: str) -> bool:
    return (ROLES_DIR / role / "SYSTEM.md").is_file()


def list_role_skills(role: str) -> list[str]:
    skills_dir = ROLES_DIR / role / "skills"
    if not skills_dir.is_dir():
        return []
    return sorted(p.stem for p in skills_dir.glob("*.md"))


def list_review_templates() -> list[str]:
    tmpl_dir = REVIEW_DIR / "templates"
    if not tmpl_dir.is_dir():
        return []
    return sorted(p.stem for p in tmpl_dir.glob("*.md"))


def list_review_skills() -> list[str]:
    sk = REVIEW_DIR / "skills"
    if not sk.is_dir():
        return []
    return sorted(p.stem for p in sk.glob("*.md"))


def list_domains() -> list[str]:
    if not DOMAINS_DIR.is_dir():
        return []
    return sorted(p.stem for p in DOMAINS_DIR.glob("*.md"))


def load_mcp_json() -> dict[str, dict]:
    """Return the parsed ``mcpServers`` mapping from ``.mcp.json``."""
    if not MCP_JSON.is_file():
        return {}
    raw = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    return raw.get("mcpServers", {}) or {}


def list_mcp_server_dirs() -> list[str]:
    """Return subdirectory names under ``mcp-servers/`` that ship a server."""
    if not MCP_SERVERS_DIR.is_dir():
        return []
    return sorted(p.name for p in MCP_SERVERS_DIR.iterdir() if p.is_dir())


def list_mcp_server_doc_cards() -> list[str]:
    """Return the ``.md`` doc card stems under ``mcp-servers/`` (excluding README)."""
    if not MCP_SERVERS_DIR.is_dir():
        return []
    return sorted(p.stem for p in MCP_SERVERS_DIR.glob("*.md") if p.stem.lower() != "readme")


_TOOL_DECL_RE = re.compile(
    r"^@mcp\.tool\(\)\s*\n\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", re.MULTILINE
)


def list_registered_mcp_tools() -> list[str]:
    """Parse ``minions/tools/mcp_server.py`` and return registered tool names."""
    server = TOOLS_DIR / "mcp_server.py"
    if not server.is_file():
        return []
    text = server.read_text(encoding="utf-8")
    return sorted(set(_TOOL_DECL_RE.findall(text)))


def whitelist_table() -> dict[tuple[str, str], list[str]]:
    """Return a defensive copy of the live ``_WHITELIST`` mapping."""
    from minions.config import _WHITELIST

    return {key: list(value) for key, value in _WHITELIST.items()}


def role_publish_policy() -> dict[str, set[str]]:
    """Return the live publish-policy mapping (role → allowed shared subdirs)."""
    return {role: set(dirs) for role, dirs in _ROLE_ALLOWED_SHARED_SUBDIRS.items()}


def role_write_boundaries() -> dict[str, list[str]]:
    return {role: list(dirs) for role, dirs in ROLE_WRITE_BOUNDARIES.items()}


def fixed_roles() -> set[str]:
    return set(FIXED_ROLES)


__all__ = [
    "DOMAINS_DIR",
    "EXTENSION_POINTS",
    "MCP_JSON",
    "MCP_SERVERS_DIR",
    "PACKAGE_CLAUDE_MD",
    "REPO_ROOT",
    "REVIEW_DIR",
    "ROLES_DIR",
    "ROOT_CLAUDE_MD",
    "TOOLS_DIR",
    "ExtensionPoint",
    "fixed_roles",
    "list_domains",
    "list_mcp_server_dirs",
    "list_mcp_server_doc_cards",
    "list_registered_mcp_tools",
    "list_review_skills",
    "list_review_templates",
    "list_role_dirs",
    "list_role_skills",
    "load_mcp_json",
    "role_has_system_md",
    "role_publish_policy",
    "role_write_boundaries",
    "whitelist_table",
]
