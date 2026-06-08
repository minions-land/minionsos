"""Memory layer tools: Draft and Book."""

from __future__ import annotations

from pydantic import BaseModel, Field

from minions.tools import book as _book
from minions.tools import book_query as _book_query
from minions.tools import draft as _draft
from minions.tools.draft import DraftNodeType, DraftSupportStatus
from minions.tools.mcp import mcp
from minions.tools.mcp._common import _require_tool_allowed

# ── Draft tools ──────────────────────────────────────────────


class DraftViewArgs(BaseModel):
    query: str | None = Field(
        default=None, description="Free-text relevance push (keyword overlap + type weighting)."
    )
    by_role: str | None = Field(default=None, description="Filter to nodes this role landed.")
    by_status: DraftSupportStatus | None = Field(
        default=None, description="Filter by support status (verified/refuted/unverified/…)."
    )
    by_type: DraftNodeType | None = Field(default=None, description="Filter by node type.")
    related_to: str | None = Field(
        default=None, description="Return the 1-hop neighbour subgraph of this node id."
    )
    sort: str = Field(
        default="time",
        description="'time' (newest first, default), 'relevance' (with query), or 'confidence'.",
    )
    limit: int = Field(default=20, description="Max nodes in the returned slice.")


class DraftAppendArgs(BaseModel):
    nodes: list[dict] | None = Field(
        default=None, description="Nodes to add (type+text required; id auto-gen)."
    )
    edges: list[dict] | None = Field(
        default=None, description="Edges to add (from_id, to_id, relation required)."
    )
    resolves_pending: list[str] | None = Field(
        default=None,
        description=(
            "Pending-plan node id(s) this append replaces. When you execute a "
            "pending plan and land its real result/decision node, pass the plan "
            "id here: the plan node is removed in the same atomic write so the "
            "Draft never keeps a stale 'verified question' placeholder. Only "
            "nodes with metadata.pending_plan=true can be removed — any other "
            "id is ignored, so a real landed node can never be deleted."
        ),
    )


class DraftAnnotateArgs(BaseModel):
    node_id: str = Field(description="ID of the node to annotate.")
    support_status: DraftSupportStatus | None = Field(
        default=None, description="New support status."
    )
    evidence_tag: str | None = Field(default=None, description="Evidence reference.")
    metadata_update: dict | None = Field(default=None, description="Metadata keys to merge.")


class DraftPathArgs(BaseModel):
    target_node_id: str = Field(description="Target node ID.")
    from_node_id: str | None = Field(default=None, description="Start node (default: root).")


class DraftCommitSharedArgs(BaseModel):
    message: str | None = Field(
        default=None,
        description=("Optional git commit message; defaults to 'ethics: draft flush <iso-ts>'."),
    )


class DraftUnmarkedAuditArgs(BaseModel):
    threshold: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Flag roles whose unmarked-claim ratio exceeds this (default 0.2).",
    )


@mcp.tool()
def mos_draft_view(args: DraftViewArgs) -> dict:
    """Unified read over the team Draft graph — the role-facing memory lens.

    One tool, orthogonal dimensions. Returns an orientation header (totals,
    pending_plans, counts) plus the requested slice of nodes + incident edges.
    Call with no args at wake to orient (header + newest nodes); pass `query`
    for relevance; `related_to` for a node's 1-hop neighbourhood; combine
    by_role/by_status/by_type/sort to focus.
    """
    _require_tool_allowed("mos_draft_view")
    return _draft.mos_draft_view(
        query=args.query,
        by_role=args.by_role,
        by_status=args.by_status,
        by_type=args.by_type,
        related_to=args.related_to,
        sort=args.sort,
        limit=args.limit,
    )


@mcp.tool()
def mos_draft_append(args: DraftAppendArgs) -> dict:
    """Add nodes and/or edges to the Draft. IDs auto-generated if omitted."""
    _require_tool_allowed("mos_draft_append")
    return _draft.mos_draft_append(
        nodes=args.nodes,
        edges=args.edges,
        resolves_pending=args.resolves_pending,
    )


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
def mos_draft_unmarked_audit(args: DraftUnmarkedAuditArgs) -> dict:
    """Per-role unmarked-claim ratio over Draft nodes; advisory threshold flag.

    Descriptive Ethics signal — measures evidence-tag coverage on claim-bearing
    Draft nodes (result/decision/hypothesis/insight) per authoring role and
    flags roles above ``threshold`` (default 0.2). Does not mutate the Draft and
    does not auto-trigger any action. Whitelisted to Ethics + Gru.
    """
    _require_tool_allowed("mos_draft_unmarked_audit")
    return _draft.mos_draft_unmarked_audit(threshold=args.threshold)


@mcp.tool()
def mos_draft_commit_shared(args: DraftCommitSharedArgs) -> dict:
    """Flush the buffered Draft to a single commit on the project main branch.

    Owned by Ethics (whitelist also grants Gru). Other roles must not call
    this — they update the Draft via ``mos_draft_append`` /
    ``mos_draft_annotate`` and let Ethics' cron flush the accumulated state.

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
    any node — the curator is forbidden from making claims, so decay is
    reported, never enforced. ``mos_draft_view()`` joins this sidecar when
    present so every waking role sees most-decayed and most-reinforced
    nodes. Whitelisted to Ethics and Gru.
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
    reel_ref: str | None = None,
    claim_refs: dict[str, str] | None = None,
) -> dict:
    """Ingest a shared artifact into Book; see minions.tools.book.mos_book_ingest.

    If ``reel_ref`` is provided (form: ``<role>/<session_id>[/<task_id>]``),
    it is embedded in the source page frontmatter AND appended as
    ``^[reel_ref]`` to every substantive claim line for drill-down audit.
    Defaults to the caller's MINIONS_ROLE_NAME + MINIONS_SESSION_ID env vars.

    If ``claim_refs`` is provided, it overrides the page default for specific
    claims: ``{sentence_prefix: reel_ref}``. Use this when sentences in one
    summary come from different subagent transcripts.
    """
    _require_tool_allowed("mos_book_ingest")
    return _book.mos_book_ingest(
        src_path=src_path,
        source_role=source_role,
        source_slug=source_slug,
        title=title,
        summary=summary,
        reel_ref=reel_ref,
        claim_refs=claim_refs,
    )


@mcp.tool()
async def mos_book_ingest_batch(sources: list[dict]) -> dict:
    """Ingest multiple shared artifacts into Book as one ordered batch.

    Each entry in ``sources`` is a dict with keys ``src_path``,
    ``source_role``, ``source_slug``, plus optional ``title``, ``summary``,
    ``reel_ref``, ``claim_refs`` (same shape as :func:`mos_book_ingest`).

    **Why batch:** single-source ingest is order-dependent — contradiction
    detection only sees pages already on disk. Batch ingest stages all
    sources in memory first, then runs contradiction detection over the
    full set (existing pages + entire incoming batch). Use this when
    publishing several related artifacts (e.g. an Expert experiment plus its
    Ethics audit at the same time).

    Returns:
        {"ingested": [<per-source result>, ...], "total_contradictions": N}
    """
    _require_tool_allowed("mos_book_ingest_batch")
    return _book.mos_book_ingest_batch(sources=sources)


@mcp.tool()
async def mos_book_query(
    text: str,
    max_pages: int = 5,
    include_status: bool = True,
    include_contradictions: bool = False,
) -> _book_query.BookQueryResult:
    """Query Book pages (title + filename + body) with progressive disclosure.

    Scoring is body-aware (title/filename token overlap + BM25 over the page
    body), so a content question retrieves a distilled page even when the
    query words are not in its filename. Each match includes ``status``
    (frontmatter ``status:`` value) when ``include_status=True`` (default),
    so a role can see at a glance whether a hit is contradicted/resolved/
    active before opening it. ``contradiction-*`` pages are excluded unless
    ``include_contradictions=True`` — reach them via each match's
    ``relations`` edges.
    """
    _require_tool_allowed("mos_book_query")
    return _book.mos_book_query(
        text=text,
        max_pages=max_pages,
        include_status=include_status,
        include_contradictions=include_contradictions,
    )


@mcp.tool()
async def mos_book_save_synthesis(
    question: str,
    answer: str,
    sources: list[str] | None = None,
    slug: str | None = None,
    reel_ref: str | None = None,
) -> dict:
    """Save a synthesized question→answer as a compounding Book page.

    The caller (a role) does the synthesis; this tool only writes it
    verbatim to ``book/queries/<slug>.md``. Future ``mos_book_query``
    calls match the question text and surface this answer first, so
    knowledge compounds across sessions.
    """
    _require_tool_allowed("mos_book_save_synthesis")
    return _book.mos_book_save_synthesis(
        question=question,
        answer=answer,
        sources=sources,
        slug=slug,
        reel_ref=reel_ref,
    )


@mcp.tool()
async def mos_book_audit_walk(
    status_filter: str | None = "unresolved",
    max_pages: int = 20,
) -> dict:
    """List Book pages awaiting audit, with reel_refs surfaced for drill-down.

    Ethics primary entry point: returns every page matching the status
    filter together with all reel_ref pointers (frontmatter + inline
    ``^[ref]`` markers). Walk the refs via ``mos_reel_get`` to drill
    from a flagged claim to its raw execution context, then write a
    verdict via ``mos_book_resolve_contradiction``.
    """
    _require_tool_allowed("mos_book_audit_walk")
    return _book.mos_book_audit_walk(status_filter=status_filter, max_pages=max_pages)


@mcp.tool()
async def mos_book_resolve_contradiction(
    slug: str,
    verdict: str,
    rationale: str,
    auditor_role: str | None = None,
) -> dict:
    """Ethics writes a verdict on a contradiction page.

    Flips the page frontmatter ``status:`` and appends a verdict section
    verbatim. The original detection block stays untouched so the audit
    trail is replayable.

    Standard verdict values: ``"resolved"``, ``"superseded"``,
    ``"out_of_scope"``, ``"escalate"``.
    """
    _require_tool_allowed("mos_book_resolve_contradiction")
    return _book.mos_book_resolve_contradiction(
        slug=slug,
        verdict=verdict,
        rationale=rationale,
        auditor_role=auditor_role,
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

    Strict verbatim contract — the curator never restates. The page body is the
    node's exact text plus a citation list of supporting edges. Idempotent.
    Whitelisted to Ethics and Gru.
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
    Ethics and Gru. Ethics audits the result through its normal Book +
    mock-review path.
    """
    _require_tool_allowed("mos_book_crystallize_session")
    return _book.mos_book_crystallize_session(
        role=role,
        window_minutes=window_minutes,
        max_chars=max_chars,
    )


# ── Book V2 tools ────────────────────────────────────────────────────────


@mcp.tool()
async def mos_book_ratify(
    slug: str,
    evidence_review: str,
    ratifier_role: str,
    port: int | None = None,
) -> dict:
    """Ethics ratifies a promoted Book page; see minions.tools.book.mos_book_ratify."""
    _require_tool_allowed("mos_book_ratify")
    return _book.mos_book_ratify(
        slug=slug,
        evidence_review=evidence_review,
        ratifier_role=ratifier_role,
        port=port,
    )


@mcp.tool()
async def mos_book_open_question(
    question: str,
    related_pages: list[str] | None = None,
    slug: str | None = None,
    port: int | None = None,
) -> dict:
    """Record an open research question as a durable Book page."""
    _require_tool_allowed("mos_book_open_question")
    return _book.mos_book_open_question(
        question=question,
        related_pages=related_pages,
        slug=slug,
        port=port,
    )


@mcp.tool()
async def mos_book_dead_end(
    claim: str,
    refutation_evidence: str,
    slug: str | None = None,
    port: int | None = None,
) -> dict:
    """Record a refuted claim as a permanent dead-end Book page."""
    _require_tool_allowed("mos_book_dead_end")
    return _book.mos_book_dead_end(
        claim=claim,
        refutation_evidence=refutation_evidence,
        slug=slug,
        port=port,
    )
