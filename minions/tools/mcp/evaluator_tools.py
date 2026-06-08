"""Evaluator MCP tools: mos_submit, mos_evaluate, mos_promote_to_book."""

from __future__ import annotations

from minions.tools.evaluator import (
    EvaluateArgs,
    EvaluateResult,
    SubmitArgs,
    SubmitResult,
)
from minions.tools.evaluator import (
    mos_evaluate as _mos_evaluate,
)
from minions.tools.evaluator import (
    mos_submit as _mos_submit,
)
from minions.tools.mcp import mcp
from minions.tools.mcp._common import _require_tool_allowed
from minions.tools.promote import PromoteToBookArgs, PromoteToBookResult
from minions.tools.promote import mos_promote_to_book as _mos_promote_to_book


@mcp.tool()
def mos_submit(args: SubmitArgs) -> SubmitResult:
    """Persist the paper deliverable under branches/main/submissions/.

    The authoring Role composes the payload (with ``pdf_path``) and asks Gru
    to call this tool. Gru reads the compiled PDF and commits it on the
    project main branch.

    Returns ``{port, kind, path, commit_sha}``.
    """
    _require_tool_allowed("mos_submit")
    return _mos_submit(args)


@mcp.tool()
def mos_evaluate(args: EvaluateArgs) -> EvaluateResult:
    """Evaluate the project's paper deliverable via full peer review.

    Runs ``mos_review_run`` (multi-pass Area-Chair review) and returns the
    decision label. MinionsOS is scientific-discovery only — the single
    strategy is ``scientific_peer_review``.

    Returns ``{port, strategy, score, verdict, details}``.
    """
    _require_tool_allowed("mos_evaluate")
    return _mos_evaluate(args)


@mcp.tool()
def mos_promote_to_book(args: PromoteToBookArgs) -> PromoteToBookResult:
    """Promote an Ethics-sealed artifact into the main-branch Book (Gru-only).

    Copies (or appends) a sealed source file into its canonical Book-layout
    position (``logic/``, ``src/``, ``evidence/``, ``proposal/``, or
    ``Book.md``) on the main branch and commits. This is the control-plane
    "Gru moves Ethics-sealed content into main" step; only Gru is authorized.

    Returns ``{port, dst_path, commit_sha}``.
    """
    _require_tool_allowed("mos_promote_to_book")
    return _mos_promote_to_book(args)
