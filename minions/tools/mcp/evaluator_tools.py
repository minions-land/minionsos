"""Evaluator MCP tools: mos_submit and mos_evaluate."""

from __future__ import annotations

from minions.tools.evaluator import (
    EvaluateArgs,
    SubmitArgs,
)
from minions.tools.evaluator import (
    mos_evaluate as _mos_evaluate,
)
from minions.tools.evaluator import (
    mos_submit as _mos_submit,
)
from minions.tools.mcp import mcp
from minions.tools.mcp._common import _require_tool_allowed


@mcp.tool()
def mos_submit(args: SubmitArgs) -> dict:
    """Persist a deliverable under branches/shared/submissions/.

    The calling Role (typically Expert or Writer) composes the payload and
    asks Gru to call this tool. Gru validates the payload against the
    project's profile deliverable schema, writes it to disk, and commits
    on the shared branch.

    Returns ``{port, kind, path, commit_sha}``.
    """
    _require_tool_allowed("mos_submit")
    return _mos_submit(args)


@mcp.tool()
def mos_evaluate(args: EvaluateArgs) -> dict:
    """Evaluate the project's deliverable using its profile-defined strategy.

    Reads the project's mission profile from meta.json, dispatches to the
    appropriate evaluator, and returns a score/verdict.

    Evaluation strategies:
    - ``scientific_peer_review`` — delegates to ``mos_review_run`` for full
      multi-pass peer review (the original MinionsOS behavior).
    - ``answer_grader`` — compares ``submissions/answer.json`` to
      ``input/expected.json`` (HLE, MMLU, GPQA, etc.).
    - ``test_runner`` — runs a test suite and reports pass/fail (SWE-bench, etc.).

    Returns ``{port, strategy, score, verdict, details}``.
    """
    _require_tool_allowed("mos_evaluate")
    return _mos_evaluate(args)
