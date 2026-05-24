"""Tests for the Gru stall-breaker milestone vote (v15.18)."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from minions.gru import milestone_vote
from minions.lifecycle import eacn_client


@pytest.fixture()
def project_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Create a minimal project_<port>/ scaffold and an initialised shared worktree."""
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    port = 41001
    proot = tmp_path / f"project_{port}"
    shared = proot / "branches" / "shared"
    draft = shared / "draft"
    state = proot / "state"
    for d in (shared, draft, state, proot / "events"):
        d.mkdir(parents=True, exist_ok=True)
    # Init the shared dir as a git repo so `git log -1 --format=%cI` works.
    subprocess.run(
        ["git", "init", "-q", "-b", "main"], cwd=str(shared), check=True
    )
    subprocess.run(
        ["git", "-c", "user.email=test@x", "-c", "user.name=test", "commit",
         "--allow-empty", "-m", "init", "-q"],
        cwd=str(shared),
        check=True,
    )
    # Roll the commit's date back so detect_stagnation sees a stale shared HEAD
    # by default. Tests that need a fresh commit will overwrite it.
    long_ago = "2024-01-01T00:00:00+00:00"
    subprocess.run(
        ["git", "commit", "--amend", "--allow-empty", "--date", long_ago,
         "-m", "init", "-q"],
        cwd=str(shared),
        env={**__import__("os").environ, "GIT_COMMITTER_DATE": long_ago},
        check=True,
    )
    return {"port": port, "proot": proot, "shared": shared, "draft": draft, "state": state}


def _write_draft(draft_dir: Path, nodes: list[dict]) -> None:
    (draft_dir / "draft.json").write_text(
        json.dumps({"project_port": 0, "root_question": "", "nodes": nodes, "edges": []}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Stagnation detection
# ---------------------------------------------------------------------------


def test_detect_stagnation_silent_project_is_stalled(project_dirs) -> None:
    port = int(project_dirs["port"])
    _write_draft(project_dirs["draft"], [])  # no nodes
    sig = milestone_vote.detect_stagnation(port, window_seconds=1200)
    assert sig.stalled is True
    assert "no draft / shared / run activity" in sig.reason


def test_detect_stagnation_fresh_draft_is_not_stalled(project_dirs) -> None:
    port = int(project_dirs["port"])
    now = datetime.now(tz=UTC)
    fresh = (now - timedelta(seconds=30)).isoformat()
    _write_draft(
        project_dirs["draft"],
        [{"id": "n1", "author_role": "coder", "created_at": fresh}],
    )
    sig = milestone_vote.detect_stagnation(port, window_seconds=1200)
    assert sig.stalled is False


def test_detect_stagnation_old_draft_only_is_stalled(project_dirs) -> None:
    port = int(project_dirs["port"])
    old = (datetime.now(tz=UTC) - timedelta(hours=2)).isoformat()
    _write_draft(
        project_dirs["draft"],
        [{"id": "n1", "author_role": "coder", "created_at": old}],
    )
    sig = milestone_vote.detect_stagnation(port, window_seconds=1200)
    assert sig.stalled is True


def test_detect_stagnation_empty_project_is_not_stalled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A brand-new project with no Draft, no shared commits, and no
    scheduler DB is *too early* to be called a stall — there's nothing
    to compare against."""
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    port = 41099
    proot = tmp_path / f"project_{port}"
    (proot / "branches" / "shared" / "draft").mkdir(parents=True, exist_ok=True)
    # Note: no git init on the shared dir → _last_shared_commit_at returns None.
    sig = milestone_vote.detect_stagnation(port, window_seconds=1200)
    assert sig.stalled is False
    assert "no activity recorded" in sig.reason


# ---------------------------------------------------------------------------
# Milestone picker
# ---------------------------------------------------------------------------


def test_pick_candidate_milestone_paper_phases() -> None:
    pick = milestone_vote.pick_candidate_milestone
    assert pick(profile_name="scientific-paper", current_phase="exploration") == "experiments_ready"
    assert pick(profile_name="scientific-paper", current_phase="experiment") == "experiments_ready"
    assert pick(profile_name="scientific-paper", current_phase="writing") == "writing_ready"
    assert pick(profile_name="scientific-paper", current_phase="review") == "submit_ready"


def test_pick_candidate_milestone_unknown_profile_returns_none() -> None:
    assert milestone_vote.pick_candidate_milestone(
        profile_name="hle-answer", current_phase="experiment"
    ) is None


def test_pick_candidate_milestone_no_phase_returns_none() -> None:
    assert milestone_vote.pick_candidate_milestone(
        profile_name="scientific-paper", current_phase=None
    ) is None


def test_pick_candidate_milestone_default_profile_is_scientific_paper() -> None:
    assert milestone_vote.pick_candidate_milestone(
        profile_name=None, current_phase="experiment"
    ) == "experiments_ready"


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------


def test_cooldown_blocks_within_window() -> None:
    state = milestone_vote.VoteState(
        milestone="experiments_ready",
        opened_at_iso=None,
        last_attempt_iso=(datetime.now(tz=UTC) - timedelta(seconds=600)).isoformat(),
        blocker_tasks=[],
    )
    assert milestone_vote.is_in_cooldown(state, cooldown_seconds=1800) is True


def test_cooldown_clear_after_window() -> None:
    state = milestone_vote.VoteState(
        milestone="experiments_ready",
        opened_at_iso=None,
        last_attempt_iso=(datetime.now(tz=UTC) - timedelta(seconds=3600)).isoformat(),
        blocker_tasks=[],
    )
    assert milestone_vote.is_in_cooldown(state, cooldown_seconds=1800) is False


def test_cooldown_no_prior_attempt_is_clear() -> None:
    state = milestone_vote.VoteState(
        milestone=None, opened_at_iso=None, last_attempt_iso=None, blocker_tasks=[]
    )
    assert milestone_vote.is_in_cooldown(state, cooldown_seconds=1800) is False


# ---------------------------------------------------------------------------
# Open vote (broadcaster)
# ---------------------------------------------------------------------------


def test_open_vote_sends_one_message_per_eligible(
    project_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each eligible signer must receive exactly one EACN message; the
    persisted state must record the opening time so the cooldown engages."""
    port = int(project_dirs["port"])
    sent: list[dict] = []

    def fake_send_message(*, port, to_agent_id, from_agent_id, content, timeout):
        sent.append(
            {
                "port": port,
                "to": to_agent_id,
                "from": from_agent_id,
                "content": content,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(eacn_client, "send_message", fake_send_message)

    sig = milestone_vote.StagnationSignal(
        stalled=True,
        last_draft_at=None,
        last_shared_commit_at=None,
        last_run_at=None,
        window_seconds=1200,
        reason="silent",
    )
    out = milestone_vote.open_vote(
        port,
        "experiments_ready",
        signal=sig,
        eligible=["ethics", "coder", "expert-a"],
    )
    assert sorted(out["addressed"]) == ["coder", "ethics", "expert-a"]
    assert out["failed"] == []
    assert len(sent) == 3
    # Every message has the right type + the milestone we asked about.
    for m in sent:
        assert m["from"] == "gru-stall-breaker"
        assert m["content"]["type"] == "milestone_vote_request"
        assert m["content"]["milestone"] == "experiments_ready"

    # State persisted.
    state = milestone_vote._load_state(port)
    assert state.milestone == "experiments_ready"
    assert state.opened_at_iso is not None
    assert state.last_attempt_iso is not None


def test_open_vote_records_partial_failure(
    project_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = int(project_dirs["port"])
    failures = {"expert-a"}

    def fake_send(*, port, to_agent_id, from_agent_id, content, timeout):
        if to_agent_id in failures:
            raise RuntimeError("simulated send failure")
        return {"ok": True}

    monkeypatch.setattr(eacn_client, "send_message", fake_send)

    sig = milestone_vote.StagnationSignal(
        True, None, None, None, 1200, "silent"
    )
    out = milestone_vote.open_vote(
        port, "experiments_ready", signal=sig, eligible=["ethics", "coder", "expert-a"]
    )
    assert "expert-a" in out["failed"]
    assert sorted(out["addressed"]) == ["coder", "ethics"]


# ---------------------------------------------------------------------------
# Reply handler — auto-broadcast a blocker resolution task
# ---------------------------------------------------------------------------


def test_handle_yes_vote_is_a_noop(project_dirs) -> None:
    out = milestone_vote.handle_vote_reply(
        int(project_dirs["port"]),
        from_role="ethics",
        raise_sign=True,
        blocker=None,
    )
    assert out == {"action": "noted_yes", "task_id": None}


def test_handle_no_vote_with_blocker_broadcasts_task(
    project_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = int(project_dirs["port"])
    created: list[dict] = []

    def fake_create_task(*, port, description, domains, initiator_id, budget,
                        level=None, **kwargs):
        created.append(
            {
                "port": port,
                "description": description,
                "domains": domains,
                "initiator_id": initiator_id,
                "budget": budget,
                "level": level,
            }
        )
        return {"task_id": "t-blk-001"}

    monkeypatch.setattr(eacn_client, "create_task", fake_create_task)

    out = milestone_vote.handle_vote_reply(
        port,
        from_role="ethics",
        raise_sign=False,
        blocker="No experiment results have hit branches/shared/exp/ in 2 hours.",
        milestone="experiments_ready",
    )
    assert out["action"] == "broadcast_blocker_task"
    assert out["task_id"] == "t-blk-001"
    assert len(created) == 1
    task = created[0]
    assert task["initiator_id"] == "gru-stall-breaker"
    assert task["level"] == "project"
    assert "experiments_ready" in task["description"]
    assert "ethics" in task["description"]
    assert "branches/shared/exp/" in task["description"]

    # Persisted state records the blocker task id.
    state = milestone_vote._load_state(port)
    assert "t-blk-001" in state.blocker_tasks


def test_handle_no_vote_empty_blocker_is_ignored(project_dirs) -> None:
    out = milestone_vote.handle_vote_reply(
        int(project_dirs["port"]),
        from_role="coder",
        raise_sign=False,
        blocker="   ",
    )
    assert out == {"action": "noted_no_empty_blocker", "task_id": None}


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def test_tick_for_project_skips_when_not_stalled(project_dirs) -> None:
    port = int(project_dirs["port"])
    fresh = (datetime.now(tz=UTC) - timedelta(seconds=30)).isoformat()
    _write_draft(
        project_dirs["draft"],
        [{"id": "n1", "author_role": "coder", "created_at": fresh}],
    )
    out = milestone_vote.tick_for_project(
        port,
        profile_name="scientific-paper",
        current_phase="experiment",
        window_seconds=1200,
        cooldown_seconds=1800,
    )
    assert out["acted"] is False


def test_tick_for_project_skips_in_cooldown(
    project_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = int(project_dirs["port"])
    _write_draft(project_dirs["draft"], [])
    # Plant a recent attempt.
    state = milestone_vote.VoteState(
        milestone="experiments_ready",
        opened_at_iso=None,
        last_attempt_iso=(datetime.now(tz=UTC) - timedelta(seconds=300)).isoformat(),
        blocker_tasks=[],
    )
    milestone_vote._save_state(port, state)
    out = milestone_vote.tick_for_project(
        port,
        profile_name="scientific-paper",
        current_phase="experiment",
        window_seconds=1200,
        cooldown_seconds=1800,
    )
    assert out["acted"] is False
    assert "cooldown" in out["reason"]


def test_tick_for_project_acts_on_stall(
    project_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = int(project_dirs["port"])
    _write_draft(project_dirs["draft"], [])
    sent: list[dict] = []

    def fake_send_message(*, port, to_agent_id, from_agent_id, content, timeout):
        sent.append({"to": to_agent_id})
        return {"ok": True}

    monkeypatch.setattr(eacn_client, "send_message", fake_send_message)
    # Fake the eligible-signers helper so we don't need a live EACN backend.
    monkeypatch.setattr(
        milestone_vote, "eligible_signers",
        lambda port, milestone: ["ethics", "coder", "expert-a"],
    )

    out = milestone_vote.tick_for_project(
        port,
        profile_name="scientific-paper",
        current_phase="experiment",
        window_seconds=1200,
        cooldown_seconds=1800,
    )
    assert out["acted"] is True
    assert out["milestone"] == "experiments_ready"
    assert sorted(out["addressed"]) == ["coder", "ethics", "expert-a"]
    assert len(sent) == 3


def test_tick_for_project_skips_unknown_profile(
    project_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = int(project_dirs["port"])
    _write_draft(project_dirs["draft"], [])
    out = milestone_vote.tick_for_project(
        port,
        profile_name="hle-answer",
        current_phase="experiment",
        window_seconds=1200,
        cooldown_seconds=1800,
    )
    assert out["acted"] is False
    assert "no candidate milestone" in out["reason"]
