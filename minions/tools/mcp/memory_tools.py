"""Memory layer tools: Draft, Book, Atlas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from minions.tools import book as _book
from minions.tools import draft as _draft
from minions.tools import shelf as _shelf
from minions.tools.mcp import mcp
from minions.tools.mcp._common import _require_tool_allowed

# ── Draft tools ──────────────────────────────────────────────


class DraftQueryArgs(BaseModel):
    node_type: str | None = Field(default=None, description="Filter by node type.")
    support_status: str | None = Field(default=None, description="Filter by support status.")
    author_role: str | None = Field(default=None, description="Filter by author role.")
    text_contains: str | None = Field(default=None, description="Substring search in node text.")
    related_to: str | None = Field(
        default=None, description="Return subgraph connected to this node ID."
    )
    limit: int = Field(default=50, description="Max nodes to return.")


class DraftAppendArgs(BaseModel):
    nodes: list[dict] | None = Field(
        default=None, description="Nodes to add (type+text required; id auto-gen)."
    )
    edges: list[dict] | None = Field(
        default=None, description="Edges to add (from_id, to_id, relation required)."
    )


class DraftAnnotateArgs(BaseModel):
    node_id: str = Field(description="ID of the node to annotate.")
    support_status: str | None = Field(default=None, description="New support status.")
    evidence_tag: str | None = Field(default=None, description="Evidence reference.")
    metadata_update: dict | None = Field(default=None, description="Metadata keys to merge.")


class DraftPathArgs(BaseModel):
    target_node_id: str = Field(description="Target node ID.")
    from_node_id: str | None = Field(default=None, description="Start node (default: root).")


class DraftCommitSharedArgs(BaseModel):
    message: str | None = Field(
        default=None,
        description=("Optional git commit message; defaults to 'noter: draft flush <iso-ts>'."),
    )


@mcp.tool()
def mos_draft_query(args: DraftQueryArgs) -> dict:
    """Query the Draft. Returns matching nodes and their edges."""
    _require_tool_allowed("mos_draft_query")
    return _draft.mos_draft_query(
        node_type=args.node_type,
        support_status=args.support_status,
        author_role=args.author_role,
        text_contains=args.text_contains,
        related_to=args.related_to,
        limit=args.limit,
    )


@mcp.tool()
def mos_draft_append(args: DraftAppendArgs) -> dict:
    """Add nodes and/or edges to the Draft. IDs auto-generated if omitted."""
    _require_tool_allowed("mos_draft_append")
    return _draft.mos_draft_append(nodes=args.nodes, edges=args.edges)


@mcp.tool()
def mos_draft_annotate(args: DraftAnnotateArgs) -> dict:
    """Update a node's support_status, evidence_tag, or metadata."""
    _require_tool_allowed("mos_draft_annotate")
    return _draft.mos_draft_annotate(
        node_id=args.node_id,
        support_status=args.support_status,
        evidence_tag=args.evidence_tag,
        metadata_update=args.metadata_update,
    )


@mcp.tool()
def mos_draft_path(args: DraftPathArgs) -> dict:
    """Extract the path from root (or from_node_id) to target_node_id."""
    _require_tool_allowed("mos_draft_path")
    return _draft.mos_draft_path(
        target_node_id=args.target_node_id,
        from_node_id=args.from_node_id,
    )


@mcp.tool()
def mos_draft_summary() -> dict:
    """Return a high-level Draft summary: node counts, active hypotheses, blocked paths."""
    _require_tool_allowed("mos_draft_summary")
    return _draft.mos_draft_summary()


@mcp.tool()
def mos_draft_commit_shared(args: DraftCommitSharedArgs) -> dict:
    """Flush the buffered Draft to a single commit on the shared branch.

    Owned by Noter (whitelist also grants Gru). Other roles must not call
    this — they update the Draft via ``mos_draft_append`` /
    ``mos_draft_annotate`` and let Noter's cron flush the accumulated state.

    Returns the publish result dict (port, role, dst_path, commit_sha,
    pushed, push_branch, branch). ``commit_sha`` is None when the on-disk
    Draft already matches HEAD (no diff).
    """
    _require_tool_allowed("mos_draft_commit_shared")
    return _draft.mos_draft_commit_shared(message=args.message)


@mcp.tool()
def mos_draft_decay_compute() -> dict:
    """Compute the Draft decay sidecar at draft/decay.json.

    Pure observation. Walks every node, records age and support/contradicts
    edge counts, and writes effective_confidence per node. Does not mutate
    any node — Noter is forbidden from making claims, so decay is reported,
    never enforced. ``mos_draft_summary()`` joins this sidecar when
    present so every waking role sees most-decayed and most-reinforced
    nodes. Whitelisted to Noter only.
    """
    _require_tool_allowed("mos_draft_decay_compute")
    return _draft.mos_draft_decay_compute()


# ── Book Layer 2 tools ─────────────────────────────────────────────────


@mcp.tool()
async def mos_book_ingest(
    src_path: str,
    source_role: str,
    source_slug: str,
    title: str | None = None,
    summary: str | None = None,
) -> dict:
    """Ingest a shared artifact into Book; see minions.tools.book.mos_book_ingest."""
    _require_tool_allowed("mos_book_ingest")
    return _book.mos_book_ingest(
        src_path=src_path,
        source_role=source_role,
        source_slug=source_slug,
        title=title,
        summary=summary,
    )


@mcp.tool()
async def mos_book_query(text: str, max_pages: int = 5) -> dict:
    """Query Book index entries; see minions.tools.book.mos_book_query."""
    _require_tool_allowed("mos_book_query")
    return _book.mos_book_query(text=text, max_pages=max_pages)


@mcp.tool()
async def mos_book_hot_get() -> dict:
    """Read Book hot cache; see minions.tools.book.mos_book_hot_get."""
    _require_tool_allowed("mos_book_hot_get")
    return _book.mos_book_hot_get()


@mcp.tool()
async def mos_book_hot_update(
    recent_ingests: list[dict[str, str]] | None = None,
    active_hypotheses: int = 0,
    recently_verified: list[str] | None = None,
    recently_refuted: list[str] | None = None,
    unresolved_contradictions: int = 0,
) -> dict:
    """Generate and publish Book hot cache; see minions.tools.book.mos_book_hot_update."""
    _require_tool_allowed("mos_book_hot_update")
    return _book.mos_book_hot_update(
        recent_ingests=recent_ingests,
        active_hypotheses=active_hypotheses,
        recently_verified=recently_verified,
        recently_refuted=recently_refuted,
        unresolved_contradictions=unresolved_contradictions,
    )


@mcp.tool()
async def mos_book_lint() -> dict:
    """Audit book/ structure. See book.mos_book_lint."""
    _require_tool_allowed("mos_book_lint")
    return _book.mos_book_lint()


@mcp.tool()
async def mos_book_promote_verified(
    min_age_days: float = 7.0,
    min_supporting_edges: int = 2,
    max_promotions: int = 5,
) -> dict:
    """Promote verified Draft insights to durable Book pages.

    Knowledge promotion: Draft nodes of type ∈ {insight, method, result}
    that reached support_status=verified, accumulated >= min_supporting_edges
    `supports` edges, are at least min_age_days old, and aren't already cited
    by any Book page get promoted to verbatim Book source pages.

    Strict verbatim contract — Noter never restates. The page body is the
    node's exact text plus a citation list of supporting edges. Idempotent.
    Whitelisted to Noter only.
    """
    _require_tool_allowed("mos_book_promote_verified")
    return _book.mos_book_promote_verified(
        min_age_days=min_age_days,
        min_supporting_edges=min_supporting_edges,
        max_promotions=max_promotions,
    )


@mcp.tool()
async def mos_book_crystallize_session(
    role: str,
    window_minutes: int = 60,
    max_chars: int = 24000,
) -> dict:
    """Crystallize a role's recent reasoning window into a verbatim Book page.

    Captures the closed reasoning interval before a context-reset boundary
    erases it. Digests the role's recent Draft nodes and EACN messages
    verbatim (no paraphrase) into a single durable page. Whitelisted to
    Noter only. Ethics audits the result through its normal Book +
    mock-review path.
    """
    _require_tool_allowed("mos_book_crystallize_session")
    return _book.mos_book_crystallize_session(
        role=role,
        window_minutes=window_minutes,
        max_chars=max_chars,
    )


# ── Gru-only global Atlas tools ─────────────────────────────────────────


@mcp.tool()
async def mos_shelf_register(port: int) -> dict:
    """Register a project atlas; see minions.tools.shelf."""
    _require_tool_allowed("mos_shelf_register")
    return _shelf.mos_shelf_register(port=port)


@mcp.tool()
async def mos_shelf_query(text: str, max_results: int = 10) -> dict:
    """Query the Gru-only global Atlas; see minions.tools.shelf."""
    _require_tool_allowed("mos_shelf_query")
    return _shelf.mos_shelf_query(text=text, max_results=max_results)


@mcp.tool()
async def mos_shelf_shared_concepts(
    port_a: int,
    port_b: int,
    min_score: float = 0.5,
) -> dict:
    """Find shared concepts across two projects; see minions.tools.shelf."""
    _require_tool_allowed("mos_shelf_shared_concepts")
    return _shelf.mos_shelf_shared_concepts(
        port_a=port_a,
        port_b=port_b,
        min_score=min_score,
    )
