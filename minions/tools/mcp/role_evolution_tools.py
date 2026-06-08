"""MCP tools for evidence-gated Role evolution (SPLIT / MERGE / DISMISS).

Gru-only by design. Three primitives, each with a separate apply tool:

  - mos_role_evolve_evaluate: read-only; returns recommendations.
  - mos_role_split:   spawn specialists, dismiss source.
  - mos_role_merge:   spawn unified role, dismiss sources (convergence).
  - mos_role_evolve_dismiss: dismiss one role with no recent work.

The split/merge/dismiss tools require non-empty evidence_refs (paths
under branches/shared/...). This bakes the evidence-gating contract
into the API surface so callers cannot trigger restructuring on
diversity heuristics alone.
"""

from __future__ import annotations

from minions.lifecycle import role_evolution as RE
from minions.tools.mcp import mcp
from minions.tools.mcp._common import (
    RoleDismissEvolveArgs,
    RoleEvolveEvaluateArgs,
    RoleMergeArgs,
    RoleSplitArgs,
    _require_tool_allowed,
)


def _split_decision_to_dict(d: RE.SplitDecision) -> dict:
    return {
        "decision": d.decision,
        "role": d.role,
        "reason": d.reason,
        "clusters": [
            {
                "label": c.label,
                "n": c.n,
                "events": [
                    {"source": e.source, "artifact_path": e.artifact_path} for e in c.events[:10]
                ],
            }
            for c in d.clusters
        ],
        "proposed_specialists": d.proposed_specialists,
    }


def _merge_decision_to_dict(d: RE.MergeDecision) -> dict:
    return {
        "decision": d.decision,
        "kind": d.kind,
        "roles": d.roles,
        "reason": d.reason,
        "proposed_role": d.proposed_role,
        "convergence_score": d.convergence_score,
    }


def _dismiss_decision_to_dict(d: RE.DismissDecision) -> dict:
    return {
        "decision": d.decision,
        "role": d.role,
        "reason": d.reason,
        "n_tasks_recent": d.n_tasks_recent,
        "age_hours": d.age_hours,
    }


@mcp.tool()
def mos_role_evolve_evaluate(args: RoleEvolveEvaluateArgs) -> dict:
    """Evaluate whether any roles in this project should split, merge, or be dismissed.

    Read-only. Returns one ``SplitDecision`` per active role plus lists
    of ``MergeDecision`` (convergence-only) and ``DismissDecision``
    (starvation-only) candidates.

    Triggers are evidence-gated:
      - SPLIT: >= split_min_failures attributable failures, partitioned
        into >= split_min_subdomains labeled clusters each >=
        split_min_per_subdomain large.
      - MERGE-by-convergence: any pair of active roles whose
        artifact-overlap score >= merge_convergence_threshold. Works on
        independently-spawned roles, not just SPLIT children.
      - DISMISS-by-starvation: a role active >= dismiss_starve_min_age_hours
        with <= dismiss_starve_max_tasks tasks in the recent window. If new
        work appears later, a separate spawn trigger handles it.

    Returns ``{splits, merges, dismisses, when, project_port}``.
    """
    _require_tool_allowed("mos_role_evolve_evaluate")
    report = RE.evaluate(args.project_port)
    return {
        "project_port": report.project_port,
        "when": report.when.isoformat(),
        "splits": [_split_decision_to_dict(s) for s in report.splits],
        "merges": [_merge_decision_to_dict(m) for m in report.merges],
        "dismisses": [_dismiss_decision_to_dict(d) for d in report.dismisses],
    }


@mcp.tool()
def mos_role_split(args: RoleSplitArgs) -> dict:
    """Realize a SPLIT decision: spawn specialists, dismiss the source role.

    Requires non-empty ``evidence_refs``. New specialists are spawned via
    ``register_expert``; the source role is then dismissed. On partial
    failure (some specialists fail to spawn), the source role is kept
    alive to preserve coverage.

    Writes one line to ``branches/shared/governance/role_evolution.jsonl``.
    """
    _require_tool_allowed("mos_role_split")
    res = RE.apply_split(
        project_port=args.project_port,
        source_role=args.source_role,
        into_specs=[s.model_dump() for s in args.into_specs],
        evidence_refs=args.evidence_refs,
        reason=args.reason,
        dry_run=args.dry_run,
    )
    return {
        "kind": res.kind,
        "roles_in": res.roles_in,
        "roles_out": res.roles_out,
        "notes": res.notes,
    }


@mcp.tool()
def mos_role_merge(args: RoleMergeArgs) -> dict:
    """Realize a MERGE decision: spawn unified role, dismiss the sources.

    Use ONLY when two active Roles have converged in behaviour and one of
    them is genuinely redundant. Source roles do NOT need to share a SPLIT
    lineage. For a Role with no recent work, use ``mos_role_evolve_dismiss``
    instead — merging a starved Role into another Role's scope is the
    wrong primitive.

    Writes one line to ``branches/shared/governance/role_evolution.jsonl``.
    """
    _require_tool_allowed("mos_role_merge")
    res = RE.apply_merge(
        project_port=args.project_port,
        source_roles=args.source_roles,
        into_spec=args.into_spec.model_dump(),
        evidence_refs=args.evidence_refs,
        reason=args.reason,
        dry_run=args.dry_run,
    )
    return {
        "kind": res.kind,
        "roles_in": res.roles_in,
        "roles_out": res.roles_out,
        "notes": res.notes,
    }


@mcp.tool()
def mos_role_evolve_dismiss(args: RoleDismissEvolveArgs) -> dict:
    """Realize a DISMISS decision for a Role with no recent work.

    Distinct from generic ``mos_dismiss_role`` because it requires
    non-empty ``evidence_refs`` and writes to the role-evolution audit
    log. Used by the periodic Gru evaluator and by operator-driven
    evolution decisions; pass ``"auto:starvation:<role>"`` or a
    governance-log line ref as evidence.

    If new work appears later that no active Role can cover, the spawn
    trigger handles it (separate concern).
    """
    _require_tool_allowed("mos_role_evolve_dismiss")
    res = RE.apply_dismiss(
        project_port=args.project_port,
        role_name=args.role_name,
        evidence_refs=args.evidence_refs,
        reason=args.reason,
        dry_run=args.dry_run,
    )
    return {
        "kind": res.kind,
        "roles_in": res.roles_in,
        "roles_out": res.roles_out,
        "notes": res.notes,
    }
