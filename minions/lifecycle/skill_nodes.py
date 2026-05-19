"""Skill-node manifest parsing and per-instance config generation.

A skill node is an external workflow packaged under ``skill-nodes/{slug}/``
that integrates into MinionsOS as an on-demand Expert instance. This module
handles manifest loading, per-instance MCP config generation, skill injection,
and registry scanning.
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from minions.paths import MINIONS_ROOT

logger = logging.getLogger(__name__)

SKILL_NODES_DIR: Path = MINIONS_ROOT / "skill-nodes"

_TMP_DIR = Path(tempfile.gettempdir()) / "minionsos-role-prompts"


@dataclass
class MCPServerSpec:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)


@dataclass
class SkillNodeManifest:
    slug: str
    name: str
    description: str
    version: str = "0.1.0"
    mcp_server: MCPServerSpec | None = None
    skills: list[str] = field(default_factory=list)
    domain_pack: str | None = None
    eacn_domains: list[str] = field(default_factory=list)

    @property
    def node_dir(self) -> Path:
        return SKILL_NODES_DIR / self.slug

    @property
    def domain_pack_path(self) -> Path | None:
        if not self.domain_pack:
            return None
        return self.node_dir / self.domain_pack

    @property
    def skills_dir(self) -> Path | None:
        d = self.node_dir / "skills"
        return d if d.is_dir() else None


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


def load_manifest(slug: str) -> SkillNodeManifest:
    """Parse ``skill-nodes/{slug}/manifest.yaml`` into a typed manifest."""
    node_dir = SKILL_NODES_DIR / slug
    manifest_path = node_dir / "manifest.yaml"
    if not manifest_path.exists():
        raise SkillNodeError(f"Skill node {slug!r}: manifest not found at {manifest_path}")

    raw: dict[str, Any] = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}

    mcp_spec: MCPServerSpec | None = None
    if mcp_raw := raw.get("mcp_server"):
        mcp_spec = MCPServerSpec(
            command=mcp_raw["command"],
            args=mcp_raw.get("args", []),
            env=mcp_raw.get("env", {}),
            tools=mcp_raw.get("tools", []),
        )

    return SkillNodeManifest(
        slug=slug,
        name=raw.get("name", slug),
        description=raw.get("description", ""),
        version=raw.get("version", "0.1.0"),
        mcp_server=mcp_spec,
        skills=raw.get("skills", []),
        domain_pack=raw.get("domain_pack"),
        eacn_domains=raw.get("eacn_domains", []),
    )


# ---------------------------------------------------------------------------
# Per-instance MCP config generation
# ---------------------------------------------------------------------------


def generate_instance_mcp_config(
    base_config: Path,
    manifest: SkillNodeManifest,
    instance_id: str,
) -> Path:
    """Merge base ``.mcp.json`` with the skill node's MCP server.

    Returns path to a temporary JSON file suitable for ``--mcp-config``.
    If the skill node has no MCP server, returns *base_config* unchanged.
    """
    if not manifest.mcp_server:
        return base_config

    base: dict[str, Any] = json.loads(base_config.read_text(encoding="utf-8"))
    servers = base.get("mcpServers", {})

    spec = manifest.mcp_server
    resolved_args = [str(MINIONS_ROOT / a) if not Path(a).is_absolute() else a for a in spec.args]
    servers[manifest.slug] = {
        "type": "stdio",
        "command": spec.command,
        "args": resolved_args,
        "env": spec.env,
    }

    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _TMP_DIR / f"mcp-{instance_id}.json"
    out_path.write_text(json.dumps(base, indent=2), encoding="utf-8")
    logger.info("skill_nodes: generated instance MCP config at %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Whitelist extension
# ---------------------------------------------------------------------------


def resolve_extra_allowed_tools(manifest: SkillNodeManifest) -> list[str]:
    """Return MCP tool names from the skill node that need whitelisting."""
    if not manifest.mcp_server:
        return []
    prefix = f"mcp__{manifest.slug}__"
    return [f"{prefix}{t}" for t in manifest.mcp_server.tools]


# ---------------------------------------------------------------------------
# Skill injection
# ---------------------------------------------------------------------------


def inject_skills_to_workspace(manifest: SkillNodeManifest, workspace: Path) -> None:
    """Symlink skill node's skills into the workspace for Claude Code discovery.

    Creates ``.claude/skills/`` in the workspace and symlinks each skill
    file from the node's ``skills/`` directory.
    """
    skills_src = manifest.skills_dir
    if not skills_src:
        return

    target_dir = workspace / ".claude" / "skills"
    target_dir.mkdir(parents=True, exist_ok=True)

    for md_file in skills_src.glob("*.md"):
        link = target_dir / f"skill-node-{manifest.slug}-{md_file.name}"
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(md_file.resolve())
        logger.debug("skill_nodes: symlinked %s → %s", link, md_file)


# ---------------------------------------------------------------------------
# Registry scan
# ---------------------------------------------------------------------------


def list_available() -> list[dict[str, Any]]:
    """Scan ``skill-nodes/`` for directories with valid manifests."""
    if not SKILL_NODES_DIR.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for child in sorted(SKILL_NODES_DIR.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.yaml"
        if not manifest_path.exists():
            continue
        try:
            m = load_manifest(child.name)
            results.append(
                {
                    "slug": m.slug,
                    "name": m.name,
                    "description": m.description,
                    "version": m.version,
                    "has_mcp": m.mcp_server is not None,
                    "has_domain_pack": m.domain_pack is not None,
                    "skills_count": len(list(m.skills_dir.glob("*.md"))) if m.skills_dir else 0,
                    "eacn_domains": m.eacn_domains,
                }
            )
        except Exception as exc:
            logger.warning("skill_nodes: skipping %s: %s", child.name, exc)
    return results


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SkillNodeError(Exception):
    """Raised when a skill node manifest is invalid or missing."""
