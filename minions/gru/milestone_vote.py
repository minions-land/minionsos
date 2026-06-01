"""Stagnation-breaker: Gru proactively opens a milestone vote.

When a project sits silent for a long stretch — no Draft growth, no shared-
branch commits, no experiment runs — the most useful question Gru can
ask is *"are we actually done with the current phase?"*. The signboard
mechanism (``minions/tools/signboard.py``) already supports milestone
consensus, but it is **passively driven** — roles raise signs voluntarily
and Gru evaluates quorum on the resulting state. In a wedged project,
nobody raises a sign because each role is waiting for something from the
others, and the loop never breaks.

This module adds the missing **active trigger**:

1. ``detect_stagnation`` reads the project's recent activity (Draft
   ``created_at``, shared-branch ``git log``, experiment-queue
   ``runs``) and decides whether the project has been quiet for at
   least ``stagnation_window_seconds``.
2. ``pick_candidate_milestone`` maps the current project ``phase`` (and
   profile) to the milestone that *would* be voted on next. Today this
   is a small static table for ``scientific-paper`` (the only profile
   whose milestones the signboard recognises); other profiles return
   ``None`` and the vote is skipped.
3. ``open_vote`` broadcasts a structured EACN message
   (``type: "milestone_vote_request"``) to every eligible signer of
   the candidate milestone, asking them to raise the sign with evidence
   if ready, or reply with a ``blocker`` if not.
4. ``handle_vote_reply`` is invoked by Gru when a role replies. A
   ``raise: true`` reply nudges the role to call ``mos_signboard_set``
   itself (we never spoof signs server-side). A ``raise: false`` reply
   carries a ``blocker`` string; Gru uses ``eacn_client.create_task`` to
   broadcast a *resolution task* asking the project to clear that
   blocker, attributed to ``initiator_id="gru-stall-breaker"``.

A cooldown (``stagnation_vote_cooldown_seconds``, default 30 min) prevents
the detector from firing again while a previous vote is still in flight.
The vote state is persisted under ``state/milestone_vote.json`` so Gru
restarts don't lose the in-flight vote and can compute the cooldown.

Why this lives in ``gru/`` and not ``tools/``: the trigger is a Gru-only
control plane action. Other roles must continue to drive signs on their
own initiative; this module is the operator-style assist for the case
where everyone has stalled. Roles never call into it directly.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from minions.paths import (
    project_events_dir,
    project_shared_subdir,
    project_shared_workspace,
    project_state_dir,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants & data shapes
# ---------------------------------------------------------------------------


# Phase → candidate milestone for the scientific-paper profile. Anything
# not in this table returns ``None`` from ``pick_candidate_milestone``,
# which short-circuits the vote (we only know how to advance the
# scientific-paper profile right now — see CLAUDE.md, Mission Profiles).
_PHASE_TO_MILESTONE_SCIENTIFIC_PAPER: dict[str, str] = {
    "exploration": "experiments_ready",
    "experiment": "experiments_ready",
    "writing": "writing_ready",
    "review": "submit_ready",
}


@dataclass(frozen=True)
class StagnationSignal:
    """What ``detect_stagnation`` returned: enough evidence to act on?"""

    stalled: bool
    last_draft_at: str | None
    last_shared_commit_at: str | None
    last_run_at: str | None
    window_seconds: int
    reason: str


@dataclass(frozen=True)
class VoteState:
    """Persisted state for the in-flight (or last) milestone vote."""

    milestone: str | None
    opened_at_iso: str | None
    last_attempt_iso: str | None
    blocker_tasks: list[str]


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


# Persisted state file path. One per project.


def _state_path(port: int) -> Path:
    return project_state_dir(port) / "milestone_vote.json"


def _load_state(port: int) -> VoteState:
    path = _state_path(port)
    if not path.is_file():
        return VoteState(None, None, None, [])
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("milestone_vote: failed to read %s: %s", path, exc)
        return VoteState(None, None, None, [])
    return VoteState(
        milestone=d.get("milestone"),
        opened_at_iso=d.get("opened_at_iso"),
        last_attempt_iso=d.get("last_attempt_iso"),
        blocker_tasks=list(d.get("blocker_tasks", []) or []),
    )


def _save_state(port: int, state: VoteState) -> None:
    path = _state_path(port)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "milestone": state.milestone,
                    "opened_at_iso": state.opened_at_iso,
                    "last_attempt_iso": state.last_attempt_iso,
                    "blocker_tasks": list(state.blocker_tasks),
                }
            ),
            encoding="utf-8",
        )
        tmp.replace(path)
    except OSError as exc:
        logger.warning("milestone_vote: failed to write %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Stagnation detection
# ---------------------------------------------------------------------------


def _last_draft_created_at(port: int) -> datetime | None:
    """Return the newest ``created_at`` in the project Draft, or None."""
    draft_path = project_shared_subdir(port, "draft") / "draft.json"
    if not draft_path.is_file():
        return None
    try:
        d = json.loads(draft_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    newest: datetime | None = None
    for node in d.get("nodes", []) or []:
        ts_raw = node.get("created_at", "")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if newest is None or ts > newest:
            newest = ts
    return newest


def _last_shared_commit_at(port: int) -> datetime | None:
    """Return the timestamp of the most recent commit on ``branches/shared``."""
    import subprocess

    workdir = project_shared_workspace(port)
    if not workdir.is_dir():
        return None
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI"],
            cwd=str(workdir),
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    raw = (result.stdout or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _last_run_started_at(port: int) -> datetime | None:
    """Return the most recent experiment-run ``started_at``, or None.

    Reads the scheduler SQLite directly (read-only). Returns ``None`` if
    there is no scheduler DB yet (project never ran experiments).
    """
    try:
        from minions.tools.experiment_scheduler import default_db_path
    except Exception:
        return None
    db_path = default_db_path(port)
    if not db_path.is_file():
        return None
    import sqlite3

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute("SELECT MAX(started_at) AS s FROM runs").fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    raw = (row[0] or "").strip() if row else ""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def detect_stagnation(
    port: int,
    *,
    window_seconds: int,
    now: datetime | None = None,
) -> StagnationSignal:
    """Decide whether the project has been silent long enough to vote.

    Three signals are checked; if **any** of them is fresher than
    ``window_seconds`` ago, the project is moving and we don't fire. The
    point of OR-ing is conservatism — we only break the loop when the
    project is silent on every productive axis simultaneously.
    """
    cur = now or _now()
    window_start = cur - timedelta(seconds=window_seconds)

    last_draft = _last_draft_created_at(port)
    last_shared = _last_shared_commit_at(port)
    last_run = _last_run_started_at(port)

    fresh_draft = last_draft is not None and last_draft >= window_start
    fresh_shared = last_shared is not None and last_shared >= window_start
    fresh_run = last_run is not None and last_run >= window_start

    if fresh_draft or fresh_shared or fresh_run:
        reason = "fresh activity within window"
        stalled = False
    elif last_draft is None and last_shared is None and last_run is None:
        # Nothing has happened yet — too early to call it a stall.
        reason = "no activity recorded yet"
        stalled = False
    else:
        reason = f"no draft / shared / run activity in the last {window_seconds}s"
        stalled = True

    return StagnationSignal(
        stalled=stalled,
        last_draft_at=last_draft.isoformat(timespec="seconds") if last_draft else None,
        last_shared_commit_at=last_shared.isoformat(timespec="seconds") if last_shared else None,
        last_run_at=last_run.isoformat(timespec="seconds") if last_run else None,
        window_seconds=window_seconds,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Candidate milestone picker
# ---------------------------------------------------------------------------


def pick_candidate_milestone(
    *,
    profile_name: str | None,
    current_phase: str | None,
) -> str | None:
    """Map ``(profile, phase) -> milestone`` for the v15.18 stall breaker.

    Returns ``None`` for non-scientific-paper profiles or unrecognised
    phases. The signboard's ``KNOWN_MILESTONES`` set is paper-shaped
    today (experiments_ready / writing_ready / submit_ready / ...).
    CLAUDE.md \"Mission Profiles\" explains the split.
    """
    if (profile_name or "scientific-paper") != "scientific-paper":
        return None
    if not current_phase:
        # Phase has never been set yet — too early for a milestone vote.
        return None
    return _PHASE_TO_MILESTONE_SCIENTIFIC_PAPER.get(current_phase)


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------


def is_in_cooldown(
    state: VoteState,
    *,
    cooldown_seconds: int,
    now: datetime | None = None,
) -> bool:
    """True when a recent vote means we should wait before opening another.

    Uses ``last_attempt_iso`` (set when ``open_vote`` succeeds), so a
    crashed mid-vote attempt won't pin the cooldown. ``opened_at_iso``
    is the *most recent successfully open vote* — kept separately for
    audit logs.
    """
    if not state.last_attempt_iso:
        return False
    try:
        last = datetime.fromisoformat(state.last_attempt_iso.replace("Z", "+00:00"))
    except ValueError:
        return False
    cur = now or _now()
    return (cur - last).total_seconds() < cooldown_seconds


# ---------------------------------------------------------------------------
# Eligible signers (whom to ask)
# ---------------------------------------------------------------------------


def eligible_signers(port: int, milestone: str) -> list[str]:
    """Return the EACN agent_ids that are *required signers* for *milestone*.

    Wraps the signboard's eligibility table: fixed roles + every
    registered tier=expert agent (when policy says experts vote).
    Returns ``[]`` when the milestone is unknown or the backend is
    unreachable — the caller short-circuits the vote in that case.
    """
    try:
        from minions.tools.signboard import (
            _ELIGIBILITY,
            KNOWN_MILESTONES,
            _registered_expert_ids,
        )
    except Exception as exc:
        logger.debug("milestone_vote: signboard import failed: %s", exc)
        return []
    if milestone not in KNOWN_MILESTONES:
        return []
    policy = _ELIGIBILITY[milestone]
    out: list[str] = list(policy.get("fixed_roles", ()) or ())
    if policy.get("experts"):
        out.extend(_registered_expert_ids(port))
    # Stable order so log lines are diffable across ticks.
    seen: set[str] = set()
    deduped: list[str] = []
    for aid in out:
        if aid and aid not in seen:
            seen.add(aid)
            deduped.append(aid)
    return deduped


# ---------------------------------------------------------------------------
# Open a vote
# ---------------------------------------------------------------------------


def open_vote(
    port: int,
    milestone: str,
    *,
    signal: StagnationSignal,
    eligible: list[str] | None = None,
) -> dict[str, Any]:
    """Broadcast the vote-request message to every eligible signer.

    Returns ``{"milestone", "addressed": [...], "failed": [...]}``.

    The message body is a structured dict (the same convention as
    ``health_event``). Each role's await-events wrapper surfaces it as
    a normal EACN event; the role decides to call ``mos_signboard_set``
    (yes-vote) or reply with a ``blocker`` (no-vote) on its next wake.

    Persists the new ``last_attempt_iso`` and ``opened_at_iso`` to disk
    so the cooldown survives restarts. Failures to persist are logged
    and ignored: the worst case is a duplicate vote on the next tick,
    not a wedged role.
    """
    from minions.lifecycle import eacn_client

    targets = list(eligible) if eligible is not None else eligible_signers(port, milestone)
    addressed: list[str] = []
    failed: list[str] = []
    body: dict[str, Any] = {
        "type": "milestone_vote_request",
        "milestone": milestone,
        "reason": signal.reason,
        "evidence": {
            "last_draft_at": signal.last_draft_at,
            "last_shared_commit_at": signal.last_shared_commit_at,
            "last_run_at": signal.last_run_at,
            "window_seconds": signal.window_seconds,
        },
        "instructions": (
            f"Project has been silent on every productive axis for at least "
            f"{signal.window_seconds}s. If you believe milestone {milestone!r} "
            f"is met, call mos_signboard_set(milestone={milestone!r}, raised=True, "
            "evidence=...). If not, reply with a `blocker` field naming the one "
            "specific thing missing — Gru will broadcast a resolution task on your "
            "behalf so the project converges on clearing it."
        ),
        "opened_at": _now_iso(),
    }
    for aid in targets:
        try:
            eacn_client.send_message(
                port=port,
                to_agent_id=aid,
                from_agent_id="gru-stall-breaker",
                content=body,
                timeout=2.0,
            )
            addressed.append(aid)
        except Exception as exc:
            logger.warning(
                "milestone_vote: send_message to %s on port %d failed: %s",
                aid,
                port,
                exc,
            )
            failed.append(aid)

    if addressed:
        prev = _load_state(port)
        new_state = VoteState(
            milestone=milestone,
            opened_at_iso=body["opened_at"],
            last_attempt_iso=body["opened_at"],
            blocker_tasks=list(prev.blocker_tasks),
        )
        _save_state(port, new_state)
    # If every send failed (EACN backend briefly down), we deliberately do
    # NOT arm the cooldown — the next tick will retry. Persisting a
    # last_attempt_iso here would silently skip the breaker for the whole
    # cooldown window after a transient outage, which is the opposite of
    # what we want.

    return {
        "milestone": milestone,
        "addressed": addressed,
        "failed": failed,
    }


# ---------------------------------------------------------------------------
# Reply handler (no-votes auto-broadcast a resolution task)
# ---------------------------------------------------------------------------


def handle_vote_reply(
    port: int,
    *,
    from_role: str,
    raise_sign: bool,
    blocker: str | None,
    milestone: str | None = None,
) -> dict[str, Any]:
    """Process one role's reply to a milestone-vote request.

    A ``raise_sign=True`` reply is a soft signal — the role is expected
    to call ``mos_signboard_set`` itself; this handler just records it.
    A ``raise_sign=False`` reply with a non-empty ``blocker`` triggers
    an EACN broadcast task asking the project to resolve the named
    blocker. Returns ``{"action", "task_id"}`` so the caller can log
    the outcome.

    The task is broadcast (no specific bidder) with ``initiator_id="gru-
    stall-breaker"`` so it shows up clearly in EACN traces. Budget is
    zero; this is a coordination signal, not a paid task.
    """
    if raise_sign:
        return {"action": "noted_yes", "task_id": None}

    blocker_text = (blocker or "").strip()
    if not blocker_text:
        # No-vote without a blocker is unusable — just log and exit.
        logger.info(
            "milestone_vote: no-vote from %s on port %d had empty blocker; ignored",
            from_role,
            port,
        )
        return {"action": "noted_no_empty_blocker", "task_id": None}

    state = _load_state(port)
    target_milestone = milestone or state.milestone or "unknown"
    description = (
        f"[stall-breaker] Resolve blocker for milestone {target_milestone!r}.\n\n"
        f"Raised by: {from_role}\n"
        f"Blocker: {blocker_text}\n\n"
        "Whichever role can clear this should bid and submit a result that "
        "either (a) ships the missing artifact directly or (b) declares the "
        "blocker invalid with an explicit refutation. Once cleared, the "
        "original signers should re-evaluate the milestone."
    )

    from minions.lifecycle import eacn_client

    try:
        result = eacn_client.create_task(
            port=port,
            description=description,
            domains=["coordination", "stall_breaker"],
            initiator_id="gru-stall-breaker",
            budget=0.0,
            level="project",
        )
    except Exception as exc:
        logger.warning(
            "milestone_vote: create_task for blocker on port %d failed: %s",
            port,
            exc,
        )
        return {"action": "task_failed", "task_id": None, "error": str(exc)}

    task_id = str(result.get("task_id") or result.get("id") or "")
    new_blockers = list(state.blocker_tasks)
    if task_id and task_id not in new_blockers:
        new_blockers.append(task_id)
    _save_state(
        port,
        VoteState(
            milestone=state.milestone,
            opened_at_iso=state.opened_at_iso,
            last_attempt_iso=state.last_attempt_iso,
            blocker_tasks=new_blockers,
        ),
    )
    return {"action": "broadcast_blocker_task", "task_id": task_id}


# ---------------------------------------------------------------------------
# Orchestrator (called from gru/loop.py)
# ---------------------------------------------------------------------------


def tick_for_project(
    port: int,
    *,
    profile_name: str | None,
    current_phase: str | None,
    window_seconds: int,
    cooldown_seconds: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """One Gru-loop tick for *port*: detect, decide, optionally broadcast.

    Returns a small status dict for the caller's logger:
    ``{"acted": bool, "reason": str, "milestone": str | None,
       "addressed": [...], "failed": [...]}``. Never raises — this is a
    best-effort breaker; logging is left to the caller (Gru loop).
    """
    signal = detect_stagnation(port, window_seconds=window_seconds, now=now)
    if not signal.stalled:
        return {"acted": False, "reason": signal.reason}

    state = _load_state(port)
    if is_in_cooldown(state, cooldown_seconds=cooldown_seconds, now=now):
        return {
            "acted": False,
            "reason": f"in cooldown (last_attempt_iso={state.last_attempt_iso})",
        }

    milestone = pick_candidate_milestone(profile_name=profile_name, current_phase=current_phase)
    if milestone is None:
        return {
            "acted": False,
            "reason": (
                f"no candidate milestone for profile={profile_name!r} phase={current_phase!r}"
            ),
        }

    eligible = eligible_signers(port, milestone)
    if not eligible:
        return {
            "acted": False,
            "reason": f"no eligible signers for milestone {milestone!r}",
            "milestone": milestone,
        }

    open_result = open_vote(port, milestone, signal=signal, eligible=eligible)
    return {
        "acted": True,
        "reason": signal.reason,
        "milestone": milestone,
        "addressed": open_result["addressed"],
        "failed": open_result["failed"],
    }


# Public surface
__all__ = [
    "StagnationSignal",
    "VoteState",
    "detect_stagnation",
    "eligible_signers",
    "handle_vote_reply",
    "is_in_cooldown",
    "open_vote",
    "pick_candidate_milestone",
    "tick_for_project",
]


# Reference unused imports so the module's narrowly-typed surface stays
# stable across refactors.
_ = (Path, project_events_dir, time)
