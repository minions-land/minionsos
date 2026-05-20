"""Memory layer tools: Scratchpad, Library, Atlas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from minions.tools import atlas as _atlas
from minions.tools import library as _library
from minions.tools import scratchpad as _scratchpad
from minions.tools.mcp import mcp
from minions.tools.mcp._common import _require_tool_allowed

# ── Scratchpad tools ──────────────────────────────────────────────


class ScratchpadQueryArgs(BaseModel):
    node_type: str | None = Field(default=None, description="Filter by node type.")
    support_status: str | None = Field(default=None, description="Filter by support status.")
    author_role: str | None = Field(default=None, description="Filter by author role.")
    text_contains: str | None = Field(default=None, description="Substring search in node text.")
    related_to: str | None = Field(
        default=None, description="Return subgraph connected to this node ID."
    )
    limit: int = Field(default=50, description="Max nodes to return.")


class ScratchpadAppendArgs(BaseModel):
    nodes: list[dict] | None = Field(
        default=None, description="Nodes to add (type+text required; id auto-gen)."
    )
    edges: list[dict] | None = Field(
        default=None, description="Edges to add (from_id, to_id, relation required)."
    )


class ScratchpadAnnotateArgs(BaseModel):
    node_id: str = Field(description="ID of the node to annotate.")
    support_status: str | None = Field(default=None, description="New support status.")
    evidence_tag: str | None = Field(default=None, description="Evidence reference.")
    metadata_update: dict | None = Field(default=None, description="Metadata keys to merge.")


class ScratchpadPathArgs(BaseModel):
    target_node_id: str = Field(description="Target node ID.")
    from_node_id: str | None = Field(default=None, description="Start node (default: root).")


class ScratchpadCommitSharedArgs(BaseModel):
    message: str | None = Field(
        default=None,
        description=(
            "Optional git commit message; defaults to 'noter: scratchpad flush <iso-ts>'."
        ),
    )


@mcp.tool()
def mos_scratchpad_query(args: ScratchpadQueryArgs) -> dict:
    """Query the Scratchpad. Returns matching nodes and their edges."""
    _require_tool_allowed("mos_scratchpad_query")
    return _scratchpad.mos_scratchpad_query(
        node_type=args.node_type,
        support_status=args.support_status,
        author_role=args.author_role,
        text_contains=args.text_contains,
        related_to=args.related_to,
        limit=args.limit,
    )


@mcp.tool()
def mos_scratchpad_append(args: ScratchpadAppendArgs) -> dict:
    """Add nodes and/or edges to the Scratchpad. IDs auto-generated if omitted."""
    _require_tool_allowed("mos_scratchpad_append")
    return _scratchpad.mos_scratchpad_append(nodes=args.nodes, edges=args.edges)


@mcp.tool()
def mos_scratchpad_annotate(args: ScratchpadAnnotateArgs) -> dict:
    """Update a node's support_status, evidence_tag, or metadata."""
    _require_tool_allowed("mos_scratchpad_annotate")
    return _scratchpad.mos_scratchpad_annotate(
        node_id=args.node_id,
        support_status=args.support_status,
        evidence_tag=args.evidence_tag,
        metadata_update=args.metadata_update,
    )


@mcp.tool()
def mos_scratchpad_path(args: ScratchpadPathArgs) -> dict:
    """Extract the path from root (or from_node_id) to target_node_id."""
    _require_tool_allowed("mos_scratchpad_path")
    return _scratchpad.mos_scratchpad_path(
        target_node_id=args.target_node_id,
        from_node_id=args.from_node_id,
    )


@mcp.tool()
def mos_scratchpad_summary() -> dict:
    """Return a high-level Scratchpad summary: node counts, active hypotheses, blocked paths."""
    _require_tool_allowed("mos_scratchpad_summary")
    return _scratchpad.mos_scratchpad_summary()


@mcp.tool()
def mos_scratchpad_commit_shared(args: ScratchpadCommitSharedArgs) -> dict:
    """Flush the buffered Scratchpad to a single commit on the shared branch.

    Owned by Noter (whitelist also grants Gru). Other roles must not call
    this — they update the Scratchpad via ``mos_scratchpad_append`` /
    ``mos_scratchpad_annotate`` and let Noter's cron flush the accumulated state.

    Returns the publish result dict (port, role, dst_path, commit_sha,
    pushed, push_branch, branch). ``commit_sha`` is None when the on-disk
    Scratchpad already matches HEAD (no diff).
    """
    _require_tool_allowed("mos_scratchpad_commit_shared")
    return _scratchpad.mos_scratchpad_commit_shared(message=args.message)


# ── Library Layer 2 tools ─────────────────────────────────────────────────


@mcp.tool()
async def mos_library_ingest(
    src_path: str,
    source_role: str,
    source_slug: str,
    title: str | None = None,
    summary: str | None = None,
) -> dict:
    """Ingest a shared artifact into Library; see minions.tools.library.mos_library_ingest."""
    _require_tool_allowed("mos_library_ingest")
    return _library.mos_library_ingest(
        src_path=src_path,
        source_role=source_role,
        source_slug=source_slug,
        title=title,
        summary=summary,
    )


@mcp.tool()
async def mos_library_query(text: str, max_pages: int = 5) -> dict:
    """Query Library index entries; see minions.tools.library.mos_library_query."""
    _require_tool_allowed("mos_library_query")
    return _library.mos_library_query(text=text, max_pages=max_pages)


@mcp.tool()
async def mos_library_hot_get() -> dict:
    """Read Library hot cache; see minions.tools.library.mos_library_hot_get."""
    _require_tool_allowed("mos_library_hot_get")
    return _library.mos_library_hot_get()


@mcp.tool()
async def mos_library_hot_update(
    recent_ingests: list[dict[str, str]] | None = None,
    active_hypotheses: int = 0,
    recently_verified: list[str] | None = None,
    recently_refuted: list[str] | None = None,
    unresolved_contradictions: int = 0,
) -> dict:
    """Generate and publish Library hot cache; see minions.tools.library.mos_library_hot_update."""
    _require_tool_allowed("mos_library_hot_update")
    return _library.mos_library_hot_update(
        recent_ingests=recent_ingests,
        active_hypotheses=active_hypotheses,
        recently_verified=recently_verified,
        recently_refuted=recently_refuted,
        unresolved_contradictions=unresolved_contradictions,
    )


@mcp.tool()
async def mos_library_lint() -> dict:
    """Audit library/ structure. See library.mos_library_lint."""
    _require_tool_allowed("mos_library_lint")
    return _library.mos_library_lint()


# ── Gru-only global Atlas tools ─────────────────────────────────────────


@mcp.tool()
async def mos_atlas_register(port: int) -> dict:
    """Register a project atlas; see minions.tools.atlas."""
    _require_tool_allowed("mos_atlas_register")
    return _atlas.mos_atlas_register(port=port)


@mcp.tool()
async def mos_atlas_query(text: str, max_results: int = 10) -> dict:
    """Query the Gru-only global Atlas; see minions.tools.atlas."""
    _require_tool_allowed("mos_atlas_query")
    return _atlas.mos_atlas_query(text=text, max_results=max_results)


@mcp.tool()
async def mos_atlas_shared_concepts(
    port_a: int,
    port_b: int,
    min_score: float = 0.5,
) -> dict:
    """Find shared concepts across two projects; see minions.tools.atlas."""
    _require_tool_allowed("mos_atlas_shared_concepts")
    return _atlas.mos_atlas_shared_concepts(
        port_a=port_a,
        port_b=port_b,
        min_score=min_score,
    )
