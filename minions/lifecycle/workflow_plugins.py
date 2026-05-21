"""Workflow-plugin manifest parsing and per-instance config generation.

A workflow plugin is an external workflow packaged under ``workflow-plugins/{slug}/``
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

WORKFLOW_PLUGINS_DIR: Path = MINIONS_ROOT / "workflow-plugins"

_TMP_DIR = Path(tempfile.gettempdir()) / "minionsos-role-prompts"


@dataclass
class MCPServerSpec:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)


@dataclass
class WorkflowPluginManifest:
    slug: str
    name: str
    description: str
    version: str = "0.1.0"
    mcp_server: MCPServerSpec | None = None
    skills: list[str] = field(default_factory=list)
    domain_pack: str | None = None
    eacn_domains: list[str] = field(default_factory=list)

    @property
    def plugin_dir(self) -> Path:
        return WORKFLOW_PLUGINS_DIR / self.slug

    @property
    def domain_pack_path(self) -> Path | None:
        if not self.domain_pack:
            return None
        return self.plugin_dir / self.domain_pack

    @property
    def skills_dir(self) -> Path | None:
        d = self.plugin_dir / "skills"
        return d if d.is_dir() else None


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


def load_manifest(slug: str) -> WorkflowPluginManifest:
    """Parse ``workflow-plugins/{slug}/manifest.yaml`` into a typed manifest."""
    plugin_dir = WORKFLOW_PLUGINS_DIR / slug
    manifest_path = plugin_dir / "manifest.yaml"
    if not manifest_path.exists():
        raise WorkflowPluginError(
            f"Workflow plugin {slug!r}: manifest not found at {manifest_path}"
        )

    raw: dict[str, Any] = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}

    mcp_spec: MCPServerSpec | None = None
    if mcp_raw := raw.get("mcp_server"):
        mcp_spec = MCPServerSpec(
            command=mcp_raw["command"],
            args=mcp_raw.get("args", []),
            env=mcp_raw.get("env", {}),
            tools=mcp_raw.get("tools", []),
        )

    return WorkflowPluginManifest(
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
    manifest: WorkflowPluginManifest,
    instance_id: str,
) -> Path:
    """Merge base ``.mcp.json`` with the workflow plugin's MCP server.

    Returns path to a temporary JSON file suitable for ``--mcp-config``.
    If the workflow plugin has no MCP server, returns *base_config* unchanged.
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
    logger.info("workflow_plugins: generated instance MCP config at %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Whitelist extension
# ---------------------------------------------------------------------------


def resolve_extra_allowed_tools(manifest: WorkflowPluginManifest) -> list[str]:
    """Return MCP tool names from the workflow plugin that need whitelisting."""
    if not manifest.mcp_server:
        return []
    prefix = f"mcp__{manifest.slug}__"
    return [f"{prefix}{t}" for t in manifest.mcp_server.tools]


# ---------------------------------------------------------------------------
# Skill injection
# ---------------------------------------------------------------------------


def inject_skills_to_workspace(manifest: WorkflowPluginManifest, workspace: Path) -> None:
    """Symlink workflow plugin's skills into the workspace for Claude Code discovery.

    Creates ``.claude/skills/`` in the workspace and symlinks each skill
    file from the plugin's ``skills/`` directory.
    """
    skills_src = manifest.skills_dir
    if not skills_src:
        return

    target_dir = workspace / ".claude" / "skills"
    target_dir.mkdir(parents=True, exist_ok=True)

    for md_file in skills_src.glob("*.md"):
        link = target_dir / f"workflow-plugin-{manifest.slug}-{md_file.name}"
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(md_file.resolve())
        logger.debug("workflow_plugins: symlinked %s → %s", link, md_file)


# ---------------------------------------------------------------------------
# Registry scan
# ---------------------------------------------------------------------------


def list_available() -> list[dict[str, Any]]:
    """Scan ``workflow-plugins/`` for directories with valid manifests."""
    if not WORKFLOW_PLUGINS_DIR.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for child in sorted(WORKFLOW_PLUGINS_DIR.iterdir()):
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
            logger.warning("workflow_plugins: skipping %s: %s", child.name, exc)
    return results


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WorkflowPluginError(Exception):
    """Raised when a workflow plugin manifest is invalid or missing."""
