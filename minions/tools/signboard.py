"""Lightweight "signboard" for milestone consensus.

Each project keeps a single state file at
``branches/shared/governance/signboard.json`` listing, per milestone, which
agents are currently *raising the sign* (in favor of advancing the project
to that milestone) along with the evidence they're standing on. Two tools:

* ``mos_signboard_set(milestone, raised, evidence?, reason?)`` — caller
  identity comes from the role process env (``MINIONS_AGENT_ID`` /
  ``MINIONS_ROLE_NAME``); the file is updated atomically under the
  per-project ``state/shared.lock`` and a notification message is sent to
  Gru so Gru can re-evaluate quorum on the same wake cycle.
* ``mos_signboard_read(milestone?)`` — pure read. No lock, no commit.

State is the authority; messages are notifications. Quorum policy lives
on the Gru side (``evaluate_quorum``) so this module ships only the
state machine plus a static eligibility table.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any, Literal, get_args, Literal, get_args

from minions.errors import ProjectError
from minions.lifecycle import eacn_client
from minions.paths import project_shared_workspace, project_signboard_json
from minions.tools.publish import _shared_lock

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Eligibility & quorum policy
# ---------------------------------------------------------------------------

# Milestones recognised by the signboard. Anything else is rejected — we
# do not want a free-form milestone string blossoming into an unbounded
# state file.
MilestoneSlug = Literal[
    "experiments_ready",
    "writing_ready",
    "submit_ready",
    "resubmit_ready",
    "camera_ready",
]
KNOWN_MILESTONES: frozenset[str] = frozenset(get_args(MilestoneSlug))


# Eligibility describes *which roles must be present* for each milestone.
# "ethics" is a hard requirement for every paper-facing milestone — the
# evidence-first audit gatekeeper has a single-vote veto by being a
# required signer. ``experts: True`` means every currently-registered
# tier=expert agent on the project's EACN is also required.
_ELIGIBILITY: dict[str, dict[str, Any]] = {
    "experiments_ready": {
        "fixed_roles": ("ethics", "coder"),
        "experts": True,
        "expert_quorum_fraction": 2 / 3,
    },
    "writing_ready": {
        "fixed_roles": ("ethics", "coder"),
        "experts": True,
        "expert_quorum_fraction": 2 / 3,
    },
    "submit_ready": {
        "fixed_roles": ("ethics", "coder", "writer"),
        "experts": True,
        "expert_quorum_fraction": 1.0,
    },
    "resubmit_ready": {
        "fixed_roles": ("ethics", "coder", "writer"),
        "experts": True,
        "expert_quorum_fraction": 1.0,
    },
    "camera_ready": {
        "fixed_roles": ("ethics", "writer"),
        "experts": True,
        "expert_quorum_fraction": 1.0,
    },
}


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------


def _env_port() -> int:
    raw = os.environ.get("MINIONS_PROJECT_PORT", "").strip()
    if not raw:
        raise ProjectError(
            "mos_signboard_*: MINIONS_PROJECT_PORT not set; "
            "this tool must be called from inside a Role process."
        )
    try:
        return int(raw)
    except ValueError as exc:
        raise ProjectError(f"MINIONS_PROJECT_PORT is not a valid int: {raw!r}") from exc


def _env_caller() -> tuple[str, str]:
    """Return ``(agent_id, role_name)`` from the role process env.

    The signboard never accepts a caller-supplied identity. Spoofing is
    blocked at the source: whoever runs the tool is whoever the process
    was launched as.
    """
    agent_id = os.environ.get("MINIONS_AGENT_ID", "").strip()
    role_name = os.environ.get("MINIONS_ROLE_NAME", "").strip()
    if not role_name:
        raise ProjectError(
            "mos_signboard_*: MINIONS_ROLE_NAME not set; "
            "this tool must be called from inside a Role process."
        )
    # Noter has no EACN agent_id by design — every other role does. For
    # Gru-side direct uses (where agent_id defaults to "gru") we just
    # fall back to the role name.
    return (agent_id or role_name, role_name)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------


def _empty_state() -> dict[str, Any]:
    return {
        "milestones": {
            m: {"raised": {}, "consumed_at": None, "consumed_round": 0}
            for m in sorted(KNOWN_MILESTONES)
        }
    }


def _load_state(port: int) -> dict[str, Any]:
    path = project_signboard_json(port)
    if not path.exists():
        return _empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectError(f"signboard.json is corrupt for port {port}: {exc}") from exc
    if not isinstance(data, dict) or "milestones" not in data:
        raise ProjectError(f"signboard.json has unexpected shape for port {port}.")
    # Heal any milestone the file is missing (e.g. when KNOWN_MILESTONES
    # grew since the file was last written). New milestones start empty.
    milestones = data["milestones"]
    if not isinstance(milestones, dict):
        raise ProjectError(f"signboard.json milestones is not an object for port {port}.")
    for m in KNOWN_MILESTONES:
        if m not in milestones:
            milestones[m] = {"raised": {}, "consumed_at": None, "consumed_round": 0}
    return data


def _save_state(port: int, state: dict[str, Any]) -> None:
    path = project_signboard_json(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------


def _notify_gru(
    port: int,
    *,
    agent_id: str,
    role_name: str,
    milestone: str,
    raised: bool,
    evidence: str | None,
    reason: str | None,
) -> None:
    """Send a single direct message to Gru about a signboard change.

    Best-effort: a failure here does not invalidate the state mutation —
    Gru can still read the file directly on its next wake. We log a
    warning and move on.
    """
    payload = {
        "type": "signboard_change",
        "milestone": milestone,
        "agent_id": agent_id,
        "role_name": role_name,
        "raised": bool(raised),
        "evidence": evidence or "",
        "reason": reason or "",
        "at": _now_iso(),
    }
    try:
        eacn_client.send_message(
            port=port,
            to_agent_id="gru",
            from_agent_id=agent_id,
            content=payload,
        )
    except Exception as exc:
        logger.warning(
            "signboard: failed to notify Gru on port=%d milestone=%s: %s",
            port,
            milestone,
            exc,
        )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def mos_signboard_set(
    *,
    milestone: MilestoneSlug,
    raised: bool,
    evidence: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Raise or lower this caller's sign for *milestone*.

    Caller identity is read from the process env — never from arguments.
    Already-consumed milestones reject further mutations until Gru
    resets them via ``reopen_milestone``. Raising requires ``evidence``;
    lowering requires ``reason``.

    Returns ``{port, milestone, agent_id, role_name, raised, raised_now,
    consumed_at, eligibility, state}``.
    """
    if milestone not in KNOWN_MILESTONES:
        raise ProjectError(
            f"Unknown milestone {milestone!r}. Known milestones: {sorted(KNOWN_MILESTONES)}."
        )
    if raised and not (evidence and evidence.strip()):
        raise ProjectError(
            "mos_signboard_set: evidence is required when raising. "
            "Cite an artifact path, commit SHA, EACN event id, or URL."
        )
    if (not raised) and not (reason and reason.strip()):
        raise ProjectError(
            "mos_signboard_set: reason is required when lowering. "
            "Explain briefly why the sign is being withdrawn."
        )

    port = _env_port()
    agent_id, role_name = _env_caller()

    # Shared worktree must exist or there is nowhere to land the state file.
    if not project_shared_workspace(port).exists():
        raise ProjectError(f"Shared worktree missing for port {port}; was project_create run?")

    with _shared_lock(port):
        state = _load_state(port)
        slot = state["milestones"][milestone]
        if slot.get("consumed_at"):
            # Already-consumed milestones don't accept further edits.
            return {
                "port": port,
                "milestone": milestone,
                "agent_id": agent_id,
                "role_name": role_name,
                "raised": raised,
                "raised_now": False,
                "consumed_at": slot.get("consumed_at"),
                "consumed_round": slot.get("consumed_round", 0),
                "noop_reason": "milestone_already_consumed",
                "state": slot,
            }

        raised_map: dict[str, dict[str, Any]] = slot.get("raised", {}) or {}
        if raised:
            raised_map[agent_id] = {
                "role": role_name,
                "at": _now_iso(),
                "evidence": evidence,
            }
        else:
            raised_map.pop(agent_id, None)
        slot["raised"] = raised_map
        _save_state(port, state)

    _notify_gru(
        port,
        agent_id=agent_id,
        role_name=role_name,
        milestone=milestone,
        raised=raised,
        evidence=evidence,
        reason=reason,
    )

    return {
        "port": port,
        "milestone": milestone,
        "agent_id": agent_id,
        "role_name": role_name,
        "raised": raised,
        "raised_now": agent_id in raised_map,
        "consumed_at": None,
        "consumed_round": slot.get("consumed_round", 0),
        "state": slot,
    }


def mos_signboard_read(milestone: MilestoneSlug | None = None) -> dict[str, Any]:
    """Return the current signboard state. Pure read — no lock, no notify.

    With *milestone* unset, returns the full state. With *milestone* set,
    returns just that slot. Unknown milestones raise.
    """
    port = _env_port()
    state = _load_state(port)
    if milestone is None:
        return {"port": port, **state}
    if milestone not in KNOWN_MILESTONES:
        raise ProjectError(
            f"Unknown milestone {milestone!r}. Known milestones: {sorted(KNOWN_MILESTONES)}."
        )
    return {"port": port, "milestone": milestone, "slot": state["milestones"][milestone]}


# ---------------------------------------------------------------------------
# Gru-side helpers
# ---------------------------------------------------------------------------


def _registered_expert_ids(port: int) -> list[str]:
    """Return EACN agent_ids for currently-registered tier=expert agents."""
    try:
        from minions.lifecycle.eacn_client import probe_backend

        probe = probe_backend(port)
    except Exception as exc:
        logger.warning("signboard: cannot probe backend on port=%d: %s", port, exc)
        return []
    out: list[str] = []
    for agent in probe.get("agents", []) or []:
        if str(agent.get("tier", "")).lower() == "expert":
            aid = str(agent.get("agent_id", "")).strip()
            if aid:
                out.append(aid)
    return out


def evaluate_quorum(port: int, milestone: MilestoneSlug) -> dict[str, Any]:
    """Return whether *milestone* has met its quorum on *port*.

    Gru-side helper — not advertised as an MCP tool because Gru can drive
    it directly from Python. Returns ``{milestone, eligible_required,
    eligible_experts_required, raised, missing, met}``.
    """
    if milestone not in KNOWN_MILESTONES:
        raise ProjectError(f"Unknown milestone {milestone!r}.")
    policy = _ELIGIBILITY[milestone]
    state = _load_state(port)
    slot = state["milestones"][milestone]
    raised_map: dict[str, dict[str, Any]] = slot.get("raised", {}) or {}
    raised_ids = set(raised_map.keys())

    fixed_required = set(policy["fixed_roles"])
    expert_ids = _registered_expert_ids(port) if policy.get("experts") else []
    fraction = float(policy.get("expert_quorum_fraction", 1.0))
    n_required_experts = (
        len(expert_ids)
        if fraction >= 1.0
        else max(1, int((fraction * len(expert_ids)) + 0.999))  # ceiling
    )

    missing_fixed = sorted(r for r in fixed_required if r not in raised_ids)
    raised_experts = [e for e in expert_ids if e in raised_ids]
    experts_met = len(raised_experts) >= n_required_experts

    met = not missing_fixed and experts_met and not slot.get("consumed_at")
    return {
        "milestone": milestone,
        "fixed_required": sorted(fixed_required),
        "experts_present": sorted(expert_ids),
        "experts_required_count": n_required_experts,
        "experts_raised": sorted(raised_experts),
        "raised": sorted(raised_ids),
        "missing_fixed": missing_fixed,
        "experts_met": experts_met,
        "consumed_at": slot.get("consumed_at"),
        "consumed_round": slot.get("consumed_round", 0),
        "met": met,
    }


def consume_milestone(port: int, milestone: MilestoneSlug) -> dict[str, Any]:
    """Mark *milestone* as consumed (Gru-side bookkeeping after dispatch).

    Idempotent: re-consuming a consumed milestone is a no-op. Always
    bumps ``consumed_round`` on first transition.
    """
    if milestone not in KNOWN_MILESTONES:
        raise ProjectError(f"Unknown milestone {milestone!r}.")
    port = int(port)
    with _shared_lock(port):
        state = _load_state(port)
        slot = state["milestones"][milestone]
        if slot.get("consumed_at"):
            return {"milestone": milestone, "consumed_at": slot["consumed_at"], "changed": False}
        slot["consumed_at"] = _now_iso()
        slot["consumed_round"] = int(slot.get("consumed_round", 0)) + 1
        _save_state(port, state)
        return {
            "milestone": milestone,
            "consumed_at": slot["consumed_at"],
            "consumed_round": slot["consumed_round"],
            "changed": True,
        }


def reopen_milestone(port: int, milestone: MilestoneSlug) -> dict[str, Any]:
    """Clear *milestone*'s raised map and consumed marker.

    Used by Gru after reviewer feedback returns and a new round of
    consensus is needed (e.g. clearing ``submit_ready`` to gather
    ``resubmit_ready`` signs after rebuttal). Preserves ``consumed_round``
    so audit history is not lost.
    """
    if milestone not in KNOWN_MILESTONES:
        raise ProjectError(f"Unknown milestone {milestone!r}.")
    port = int(port)
    with _shared_lock(port):
        state = _load_state(port)
        slot = state["milestones"][milestone]
        slot["raised"] = {}
        slot["consumed_at"] = None
        _save_state(port, state)
    return {
        "milestone": milestone,
        "reset_at": _now_iso(),
        "consumed_round": slot["consumed_round"],
    }


__all__ = [
    "KNOWN_MILESTONES",
    "MilestoneSlug",
    "consume_milestone",
    "evaluate_quorum",
    "mos_signboard_read",
    "mos_signboard_set",
    "reopen_milestone",
]
