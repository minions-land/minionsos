"""Experiment + GPU queue tools (mos_review_run lives here too).

All @mcp.tool functions in this module are thin dispatch over
:mod:`minions.tools.experiment_ssh` (aliased ``_exp``) and
:mod:`minions.tools.review` (aliased ``_review``).
"""

from __future__ import annotations

from minions.tools import experiment_ssh as _exp
from minions.tools import review as _review
from minions.tools.mcp import mcp
from minions.tools.mcp._common import _require_tool_allowed


@mcp.tool()
def mos_review_run(args: _review.ReviewRunArgs) -> dict:
    """Run one Area-Chair review round on a submission package.

    Gates on the submission checklist first: any unchecked Required item
    short-circuits with ``{"status": "rejected", ...}`` and no review is
    spawned. On pass, drives the 3-pass review procedure to completion and
    returns the round number, decision label, and produced artifact paths.

    This tool replaces the previous long-lived Reviewer role. Gru invokes it
    when the drafting Expert publishes a submission via EACN; the result is
    relayed back to that Expert on the project's Local EACN.
    """
    _require_tool_allowed("mos_review_run")
    return _review.review_run(args)


@mcp.tool()
def mos_exp_run(args: _exp.ExpRunArgs) -> dict:
    """Launch a detached local or SSH experiment run."""
    _require_tool_allowed("mos_exp_run")
    return _exp.exp_run(args)


@mcp.tool()
def mos_exp_status(args: _exp.ExpStatusArgs) -> _exp.ExperimentRunStatus:
    """Check an experiment run state."""
    _require_tool_allowed("mos_exp_status")
    return _exp.exp_status(args)


@mcp.tool()
def mos_exp_wait(args: _exp.ExpWaitArgs) -> _exp.ExperimentRunStatus:
    """Poll up to timeout seconds for a run to exit."""
    _require_tool_allowed("mos_exp_wait")
    return _exp.exp_wait(args)


@mcp.tool()
def mos_exp_kill(args: _exp.ExpKillArgs) -> dict:
    """Send SIGTERM to a running experiment process."""
    _require_tool_allowed("mos_exp_kill")
    return _exp.exp_kill(args)


@mcp.tool()
def mos_exp_list(args: _exp.ExpListArgs) -> list[dict]:
    """List known experiment runs on a target."""
    _require_tool_allowed("mos_exp_list")
    return _exp.exp_list(args)


@mcp.tool()
def mos_exp_put(args: _exp.ExpPutArgs) -> dict:
    """Upload a local file to a target workdir."""
    _require_tool_allowed("mos_exp_put")
    return _exp.exp_put(args)


@mcp.tool()
def mos_exp_get(args: _exp.ExpGetArgs) -> dict:
    """Download a target file, refusing files over the experiment size limit."""
    _require_tool_allowed("mos_exp_get")
    return _exp.exp_get(args)


@mcp.tool()
def mos_exp_tail(args: _exp.ExpTailArgs) -> dict:
    """Tail a target log file."""
    _require_tool_allowed("mos_exp_tail")
    return _exp.exp_tail(args)


@mcp.tool()
def mos_query_gpus(args: _exp.QueryGpusArgs) -> list[dict]:
    """Query GPU memory on a target."""
    _require_tool_allowed("mos_query_gpus")
    return _exp.query_gpus(args)


@mcp.tool()
def mos_exp_queue_submit(args: _exp.ExpQueueSubmitArgs) -> dict:
    """Append experiment units to the project-global GPU queue."""
    _require_tool_allowed("mos_exp_queue_submit")
    return _exp.exp_queue_submit(args)


@mcp.tool()
def mos_exp_queue_reconcile(args: _exp.ExpQueueReconcileArgs) -> dict:
    """Run one Python-side experiment queue reconcile pass."""
    _require_tool_allowed("mos_exp_queue_reconcile")
    return _exp.exp_queue_reconcile(args)


@mcp.tool()
def mos_exp_queue_status(args: _exp.ExpQueueStatusArgs) -> dict:
    """Return experiment queue status."""
    _require_tool_allowed("mos_exp_queue_status")
    return _exp.exp_queue_status(args)


@mcp.tool()
def mos_exp_queue_plan(args: _exp.ExpQueuePlanArgs) -> dict:
    """Dry-run a candidate submission against the live GPU snapshot.

    Returns per-unit placement (target/gpu_ids/reserve_mb) or a block reason
    plus the fleet snapshot used. Read-only — nothing is queued and no run
    is launched. Use before ``mos_exp_queue_submit`` when you want to know
    whether a sweep will actually spread or stall.
    """
    _require_tool_allowed("mos_exp_queue_plan")
    return _exp.exp_queue_plan(args)


@mcp.tool()
def mos_exp_gpu_pool_set(args: _exp.ExpQueueGpuPoolSetArgs) -> dict:
    """Set the dynamic GPU allow-list for new experiment runs."""
    _require_tool_allowed("mos_exp_gpu_pool_set")
    return _exp.exp_gpu_pool_set(args)


@mcp.tool()
def mos_exp_gpu_pool_get(args: _exp.ExpQueueGpuPoolGetArgs) -> dict:
    """Return dynamic GPU pool overrides."""
    _require_tool_allowed("mos_exp_gpu_pool_get")
    return _exp.exp_gpu_pool_get(args)
