"""Signboard milestone-consensus tools."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from minions.tools import signboard as _signboard
from minions.tools.mcp import mcp
from minions.tools.mcp._common import _require_tool_allowed


class SignboardSetArgs(BaseModel):
    milestone: str = Field(
        description=(
            "Milestone slug. One of: experiments_ready, writing_ready, "
            "submit_ready, resubmit_ready, camera_ready."
        )
    )
    raised: bool = Field(
        description=(
            "True to raise your sign in favor of advancing to this milestone; "
            "False to withdraw a previously-raised sign. Default state is "
            "lowered — there is no need to call this with raised=False unless "
            "you previously raised."
        )
    )
    evidence: str | None = Field(
        default=None,
        description=(
            "Required when raising. Concrete artifact path, commit SHA, "
            "EACN event id, or URL backing your position."
        ),
    )
    reason: str | None = Field(
        default=None,
        description="Required when lowering. One short line explaining why.",
    )


class SignboardReadArgs(BaseModel):
    milestone: str | None = Field(
        default=None,
        description=("Optional milestone slug. Omit to read the full signboard state."),
    )


class SignboardMilestoneArgs(BaseModel):
    milestone: str = Field(
        description=(
            "Milestone slug. One of: experiments_ready, writing_ready, "
            "submit_ready, resubmit_ready, camera_ready."
        )
    )


@mcp.tool()
def mos_signboard_set(args: SignboardSetArgs) -> dict:
    """Raise or lower this role's sign for a milestone.

    The signboard is a lightweight consensus surface: each eligible role
    independently raises a sign (with evidence) when it thinks the
    project is ready to advance to a milestone. Gru watches the board
    and dispatches the next phase only when quorum is met (Ethics is a
    required signer on every paper-facing milestone — without Ethics,
    no quorum is achievable).

    Identity is read from the role process env (``MINIONS_AGENT_ID`` /
    ``MINIONS_ROLE_NAME``). You cannot raise on behalf of another role.

    Side effects:

    1. Atomic update of ``branches/shared/governance/signboard.json``
       under the per-project ``state/shared.lock``.
    2. Best-effort EACN direct message to Gru (``type:
       signboard_change``) so Gru reconsiders quorum on the same wake.

    Already-consumed milestones reject further mutations until Gru
    re-opens them (e.g. after rebuttal). The call returns ``noop_reason:
    milestone_already_consumed`` in that case.

    Returns the new slot state plus the caller's identity.
    """
    _require_tool_allowed("mos_signboard_set")
    return _signboard.mos_signboard_set(
        milestone=args.milestone,
        raised=args.raised,
        evidence=args.evidence,
        reason=args.reason,
    )


@mcp.tool()
def mos_signboard_read(args: SignboardReadArgs) -> dict:
    """Read current signboard state.

    Pure read — no lock, no notify, no side effects. Returns either the
    whole board (when ``milestone`` is omitted) or a single slot.
    """
    _require_tool_allowed("mos_signboard_read")
    return _signboard.mos_signboard_read(milestone=args.milestone)


@mcp.tool()
def mos_signboard_evaluate(args: SignboardMilestoneArgs) -> dict:
    """Evaluate quorum for a milestone — Gru-only.

    Reads the live signboard plus the EACN3 registered-expert roster and
    returns ``{milestone, fixed_required, experts_present,
    experts_required_count, experts_raised, raised, missing_fixed,
    experts_met, consumed_at, consumed_round, met}``.

    Pure read; no state change. Call this when a ``signboard_change``
    event arrives, or before dispatching a milestone-gated action, to
    decide whether the project may advance.
    """
    _require_tool_allowed("mos_signboard_evaluate")
    port = int(os.environ.get("MINIONS_PROJECT_PORT", "0") or 0)
    if port <= 0:
        raise PermissionError(
            "mos_signboard_evaluate: MINIONS_PROJECT_PORT must be set (Gru session)."
        )
    return _signboard.evaluate_quorum(port, args.milestone)


@mcp.tool()
def mos_signboard_consume(args: SignboardMilestoneArgs) -> dict:
    """Mark a milestone as consumed — Gru-only bookkeeping after dispatch.

    Call exactly once after Gru has dispatched the action a milestone
    gates (e.g. after spawning Writer for ``writing_ready``, or after
    invoking ``mos_review_run`` for ``submit_ready``). Idempotent:
    re-consuming a consumed milestone is a no-op but is logged.

    Once consumed, further ``mos_signboard_set`` calls on the same
    milestone return ``noop_reason: milestone_already_consumed`` until
    Gru calls ``mos_signboard_reopen``.
    """
    _require_tool_allowed("mos_signboard_consume")
    port = int(os.environ.get("MINIONS_PROJECT_PORT", "0") or 0)
    if port <= 0:
        raise PermissionError(
            "mos_signboard_consume: MINIONS_PROJECT_PORT must be set (Gru session)."
        )
    return _signboard.consume_milestone(port, args.milestone)


@mcp.tool()
def mos_signboard_reopen(args: SignboardMilestoneArgs) -> dict:
    """Reset a milestone for a fresh round — Gru-only.

    Clears all raised signs and the consumed marker on *milestone*,
    preserving ``consumed_round`` for audit. Use after reviewer feedback
    returns to gather a new ``resubmit_ready`` consensus, or any time a
    milestone needs to be re-deliberated.
    """
    _require_tool_allowed("mos_signboard_reopen")
    port = int(os.environ.get("MINIONS_PROJECT_PORT", "0") or 0)
    if port <= 0:
        raise PermissionError(
            "mos_signboard_reopen: MINIONS_PROJECT_PORT must be set (Gru session)."
        )
    return _signboard.reopen_milestone(port, args.milestone)
