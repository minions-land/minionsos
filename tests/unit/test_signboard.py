"""Unit tests for ``mos_signboard_set`` / ``mos_signboard_read`` and the
Gru-side quorum / consume / reopen helpers.

Spins a real per-test author repo + project tree (per-project bare repo,
main + shared worktrees) so the flock + on-disk JSON state is exercised
end-to-end. The EACN3 backend is *not* spun up — ``send_message`` is
patched to a no-op so the notification side-effect doesn't try to hit
``127.0.0.1:<port>``. Quorum tests use a stub for the registered-experts
probe.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from minions.errors import ProjectError
from minions.lifecycle import project as project_mod
from minions.paths import (
    project_dir,
    project_signboard_json,
    project_state_dir,
    project_workspace_root,
)


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    author = tmp_path / "author"
    projects_root = tmp_path / "projects-root"
    author.mkdir()
    projects_root.mkdir()
    _git(["init", "-q"], author)
    _git(["config", "user.email", "t@e.com"], author)
    _git(["config", "user.name", "test"], author)
    (author / "README.md").write_text("init\n", encoding="utf-8")
    _git(["add", "."], author)
    _git(["commit", "-qm", "init"], author)

    monkeypatch.setenv("MINIONS_AUTHOR_REPO", str(author))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(projects_root))

    port = 39911
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))

    project_dir(port).mkdir(parents=True, exist_ok=True)
    project_workspace_root(port).mkdir(parents=True, exist_ok=True)
    project_state_dir(port).mkdir(parents=True, exist_ok=True)

    project_mod._seed_per_project_repo(port)
    project_mod._create_worktree(port, "HEAD")
    project_mod._create_shared_worktree(port)

    # Patch the Gru notifier to a no-op (no live EACN backend in the test).
    from minions.tools import signboard as sb

    monkeypatch.setattr(sb, "_notify_gru", lambda *_a, **_kw: None)

    return {"port": port}


def _set_caller(monkeypatch: pytest.MonkeyPatch, role: str, agent_id: str | None = None) -> None:
    monkeypatch.setenv("MINIONS_ROLE_NAME", role)
    monkeypatch.setenv("MINIONS_AGENT_ID", agent_id or role)


# ---------------------------------------------------------------------------
# mos_signboard_set
# ---------------------------------------------------------------------------


def test_set_raise_creates_state_file(
    project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from minions.tools import signboard as sb

    _set_caller(monkeypatch, "ethics")
    res = sb.mos_signboard_set(
        milestone="experiments_ready",
        raised=True,
        evidence="ethics/round-1/audit.md",
    )
    assert res["raised_now"] is True
    assert res["agent_id"] == "ethics"
    path = project_signboard_json(project["port"])
    assert path.exists()
    state = json.loads(path.read_text(encoding="utf-8"))
    raised = state["milestones"]["experiments_ready"]["raised"]
    assert "ethics" in raised
    assert raised["ethics"]["evidence"] == "ethics/round-1/audit.md"
    assert raised["ethics"]["role"] == "ethics"


def test_set_lower_clears_entry(project: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    from minions.tools import signboard as sb

    _set_caller(monkeypatch, "ethics")
    sb.mos_signboard_set(milestone="writing_ready", raised=True, evidence="ethics/x.md")
    res = sb.mos_signboard_set(
        milestone="writing_ready",
        raised=False,
        reason="evidence withdrawn after audit found gap",
    )
    assert res["raised_now"] is False
    state = json.loads(project_signboard_json(project["port"]).read_text(encoding="utf-8"))
    assert "ethics" not in state["milestones"]["writing_ready"]["raised"]


def test_set_raise_requires_evidence(
    project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from minions.tools import signboard as sb

    _set_caller(monkeypatch, "coder")
    with pytest.raises(ProjectError, match="evidence is required"):
        sb.mos_signboard_set(milestone="experiments_ready", raised=True)


def test_set_lower_requires_reason(
    project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from minions.tools import signboard as sb

    _set_caller(monkeypatch, "coder")
    with pytest.raises(ProjectError, match="reason is required"):
        sb.mos_signboard_set(milestone="experiments_ready", raised=False)


def test_set_rejects_unknown_milestone(
    project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from minions.tools import signboard as sb

    _set_caller(monkeypatch, "coder")
    with pytest.raises(ProjectError, match="Unknown milestone"):
        sb.mos_signboard_set(milestone="lunch_ready", raised=True, evidence="x")


def test_set_caller_identity_from_env_only(
    project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A coder process cannot raise on behalf of ethics — identity is env-only."""
    from minions.tools import signboard as sb

    _set_caller(monkeypatch, "coder", agent_id="coder")
    res = sb.mos_signboard_set(
        milestone="experiments_ready",
        raised=True,
        evidence="exp/exp-1/report.md",
    )
    assert res["agent_id"] == "coder"
    assert res["role_name"] == "coder"


def test_set_consumed_milestone_is_noop(
    project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from minions.tools import signboard as sb

    _set_caller(monkeypatch, "ethics")
    sb.mos_signboard_set(
        milestone="submit_ready", raised=True, evidence="ethics/ok.md"
    )
    sb.consume_milestone(project["port"], "submit_ready")
    res = sb.mos_signboard_set(
        milestone="submit_ready",
        raised=False,
        reason="late lower attempt",
    )
    assert res.get("noop_reason") == "milestone_already_consumed"


def test_reopen_clears_raised_and_consumed(
    project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from minions.tools import signboard as sb

    _set_caller(monkeypatch, "ethics")
    sb.mos_signboard_set(milestone="submit_ready", raised=True, evidence="ethics/ok.md")
    sb.consume_milestone(project["port"], "submit_ready")
    sb.reopen_milestone(project["port"], "submit_ready")
    state = sb.mos_signboard_read(milestone="submit_ready")
    assert state["slot"]["raised"] == {}
    assert state["slot"]["consumed_at"] is None
    # consumed_round is preserved as audit history.
    assert state["slot"]["consumed_round"] == 1


# ---------------------------------------------------------------------------
# mos_signboard_read
# ---------------------------------------------------------------------------


def test_read_full_returns_all_milestones(project: dict[str, Any]) -> None:
    from minions.tools import signboard as sb

    res = sb.mos_signboard_read()
    keys = set(res["milestones"].keys())
    assert keys == sb.KNOWN_MILESTONES


def test_read_specific_milestone(project: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    from minions.tools import signboard as sb

    _set_caller(monkeypatch, "ethics")
    sb.mos_signboard_set(milestone="camera_ready", raised=True, evidence="ethics/cr.md")
    res = sb.mos_signboard_read(milestone="camera_ready")
    assert res["milestone"] == "camera_ready"
    assert "ethics" in res["slot"]["raised"]


def test_read_unknown_milestone_raises(project: dict[str, Any]) -> None:
    from minions.tools import signboard as sb

    with pytest.raises(ProjectError, match="Unknown milestone"):
        sb.mos_signboard_read(milestone="lunch_ready")


# ---------------------------------------------------------------------------
# Quorum
# ---------------------------------------------------------------------------


def _stub_experts(monkeypatch: pytest.MonkeyPatch, expert_ids: list[str]) -> None:
    from minions.tools import signboard as sb

    monkeypatch.setattr(sb, "_registered_expert_ids", lambda _port: list(expert_ids))


def test_quorum_blocked_without_ethics(
    project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from minions.tools import signboard as sb

    _stub_experts(monkeypatch, ["expert-bio", "expert-chem", "expert-stat"])
    # Coder + all experts raise, but Ethics is missing.
    for role, evidence in [
        ("coder", "exp/exp-1/report.md"),
        ("expert-bio", "notes/bio.md"),
        ("expert-chem", "notes/chem.md"),
        ("expert-stat", "notes/stat.md"),
    ]:
        _set_caller(monkeypatch, role)
        sb.mos_signboard_set(
            milestone="experiments_ready", raised=True, evidence=evidence
        )
    q = sb.evaluate_quorum(project["port"], "experiments_ready")
    assert q["met"] is False
    assert "ethics" in q["missing_fixed"]


def test_quorum_passes_with_2_of_3_experts_plus_ethics_and_coder(
    project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from minions.tools import signboard as sb

    _stub_experts(monkeypatch, ["expert-bio", "expert-chem", "expert-stat"])
    for role, evidence in [
        ("ethics", "ethics/round-1.md"),
        ("coder", "exp/exp-1/report.md"),
        ("expert-bio", "notes/bio.md"),
        ("expert-chem", "notes/chem.md"),
    ]:
        _set_caller(monkeypatch, role)
        sb.mos_signboard_set(
            milestone="experiments_ready", raised=True, evidence=evidence
        )
    q = sb.evaluate_quorum(project["port"], "experiments_ready")
    assert q["missing_fixed"] == []
    assert q["experts_met"] is True
    assert q["met"] is True


def test_submit_ready_requires_all_experts(
    project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from minions.tools import signboard as sb

    _stub_experts(monkeypatch, ["expert-bio", "expert-chem"])
    # 1 of 2 experts + all fixed roles → still short on experts.
    for role, evidence in [
        ("ethics", "ethics/sub.md"),
        ("coder", "exp/exp-1/report.md"),
        ("writer", "writer/draft.tex"),
        ("expert-bio", "notes/bio.md"),
    ]:
        _set_caller(monkeypatch, role)
        sb.mos_signboard_set(milestone="submit_ready", raised=True, evidence=evidence)
    q = sb.evaluate_quorum(project["port"], "submit_ready")
    assert q["experts_met"] is False
    assert q["met"] is False
    # Add the second expert → quorum.
    _set_caller(monkeypatch, "expert-chem")
    sb.mos_signboard_set(
        milestone="submit_ready", raised=True, evidence="notes/chem.md"
    )
    q2 = sb.evaluate_quorum(project["port"], "submit_ready")
    assert q2["met"] is True


def test_quorum_blocked_after_consume(
    project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once consumed, quorum reports met=False until reopen — the milestone
    has already been spent for this round."""
    from minions.tools import signboard as sb

    _stub_experts(monkeypatch, ["expert-bio"])
    for role, evidence in [
        ("ethics", "e.md"),
        ("coder", "c.md"),
        ("writer", "w.md"),
        ("expert-bio", "b.md"),
    ]:
        _set_caller(monkeypatch, role)
        sb.mos_signboard_set(milestone="submit_ready", raised=True, evidence=evidence)
    assert sb.evaluate_quorum(project["port"], "submit_ready")["met"] is True
    sb.consume_milestone(project["port"], "submit_ready")
    assert sb.evaluate_quorum(project["port"], "submit_ready")["met"] is False
    sb.reopen_milestone(project["port"], "submit_ready")
    # After reopen the raised set is empty so quorum is False until re-raise.
    q = sb.evaluate_quorum(project["port"], "submit_ready")
    assert q["met"] is False
    assert q["missing_fixed"]  # ethics/coder/writer dropped


# ---------------------------------------------------------------------------
# Whitelist / boundary
# ---------------------------------------------------------------------------


def test_whitelist_grants_signboard_to_voters() -> None:
    from minions.config import resolve_whitelist

    for role in ("gru", "coder", "writer", "ethics", "expert"):
        tools = set(resolve_whitelist(role, "main"))
        assert "mos_signboard_set" in tools, f"{role} should be allowed to vote"
        assert "mos_signboard_read" in tools


def test_whitelist_denies_signboard_set_to_noter() -> None:
    """Noter is not registered on EACN and is not a voter — read-only access."""
    from minions.config import resolve_whitelist

    tools = set(resolve_whitelist("noter", "main"))
    assert "mos_signboard_set" not in tools
    assert "mos_signboard_read" in tools


def test_only_gru_can_evaluate_consume_reopen() -> None:
    """evaluate/consume/reopen are control-plane tools — Gru only at server side."""
    from minions.config import resolve_server_authz

    gru_authz = set(resolve_server_authz("gru", "main"))
    for tool in (
        "mos_signboard_evaluate",
        "mos_signboard_consume",
        "mos_signboard_reopen",
    ):
        assert tool in gru_authz

    for role in ("coder", "writer", "ethics", "expert", "noter"):
        authz = set(resolve_server_authz(role, "main"))
        for tool in (
            "mos_signboard_evaluate",
            "mos_signboard_consume",
            "mos_signboard_reopen",
        ):
            assert tool not in authz, f"{role} should not have {tool}"


def test_full_milestone_flow_evaluate_consume_reopen(
    project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: roles raise → quorum met → consume → board returns met=False
    until reopen."""
    from minions.tools import signboard as sb

    _stub_experts(monkeypatch, ["expert-bio"])
    for role, evidence in [
        ("ethics", "e.md"),
        ("coder", "c.md"),
        ("writer", "w.md"),
        ("expert-bio", "b.md"),
    ]:
        _set_caller(monkeypatch, role)
        sb.mos_signboard_set(
            milestone="submit_ready", raised=True, evidence=evidence
        )
    port = project["port"]
    q1 = sb.evaluate_quorum(port, "submit_ready")
    assert q1["met"] is True
    sb.consume_milestone(port, "submit_ready")
    q2 = sb.evaluate_quorum(port, "submit_ready")
    assert q2["met"] is False
    assert q2["consumed_round"] == 1
    # Reopen, gather a fresh round.
    sb.reopen_milestone(port, "submit_ready")
    for role, evidence in [
        ("ethics", "e2.md"),
        ("coder", "c2.md"),
        ("writer", "w2.md"),
        ("expert-bio", "b2.md"),
    ]:
        _set_caller(monkeypatch, role)
        sb.mos_signboard_set(
            milestone="submit_ready", raised=True, evidence=evidence
        )
    q3 = sb.evaluate_quorum(port, "submit_ready")
    assert q3["met"] is True
    sb.consume_milestone(port, "submit_ready")
    q4 = sb.evaluate_quorum(port, "submit_ready")
    assert q4["consumed_round"] == 2
