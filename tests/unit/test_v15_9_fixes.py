"""Tests for v15.9 fixes:
- Issue #9: PreCompact hook now emits a "Resume_protocol" tail so the
  post-compact agent has a concrete first tool-call cue.
- Issue #10: Ethics has mos_adjudicate authz (server-side).
- Issue #11: shelf.json is bootstrapped at project_create.
- Issue #12: mos_compact_context filters empty pending_plans.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Issue #9 — Resume_protocol block in pre_compact output
# ---------------------------------------------------------------------------


class TestPreCompactResumeProtocol:
    # The pre-compact hook gates the science-compact prompt to Role main
    # processes; without these env vars it correctly passes through to the
    # default summariser, so the body assertions below would never fire.
    _ROLE_ENV: ClassVar[dict[str, str]] = {
        "MINIONS_ROLE_NAME": "coder",
        "MINIONS_AGENT_TYPE": "main",
    }

    def test_resume_protocol_section_present(self) -> None:
        """The hook output must end with the Resume_protocol block so
        Claude's compact summary inherits the continuation cue."""
        hook = REPO_ROOT / "minions" / "hooks" / "pre_compact_science.py"
        env = os.environ.copy()
        env.update(self._ROLE_ENV)
        result = subprocess.run(
            [sys.executable, str(hook)],
            input="{}",
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert result.returncode == 0
        assert "## Resume_protocol" in result.stdout
        assert "mos_draft_summary()" in result.stdout
        assert "mos_await_events()" in result.stdout

    def test_resume_protocol_explains_failure_mode(self) -> None:
        """The block should reference Issue #9 / 'parks the Role' so a
        future maintainer knows why the cue is load-bearing."""
        hook = REPO_ROOT / "minions" / "hooks" / "pre_compact_science.py"
        env = os.environ.copy()
        env.update(self._ROLE_ENV)
        result = subprocess.run(
            [sys.executable, str(hook)],
            input="{}",
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert "parks" in result.stdout.lower() or "park" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Issue #10 — Ethics has mos_adjudicate authz
# ---------------------------------------------------------------------------


class TestEthicsAdjudicateAuthz:
    def test_ethics_can_call_mos_adjudicate(self) -> None:
        """mos_adjudicate must be allowed for Ethics — its SYSTEM.md
        directs the role to call it. Pre-v15.9 the server-side authz
        omitted it and 4 queued adjudication_tasks went unanswerable."""
        from minions.tools.mcp_server import _require_tool_allowed

        with patch.dict(os.environ, {"MINIONS_ROLE_NAME": "ethics"}, clear=False):
            _require_tool_allowed("mos_adjudicate")  # must not raise

    def test_non_ethics_roles_unchanged(self) -> None:
        """The fix is targeted: only Ethics + Gru should get mos_adjudicate.
        Coder/Writer/Noter must still be denied."""
        from minions.tools.mcp_server import _require_tool_allowed

        for role in ["coder", "writer", "noter"]:
            with (
                patch.dict(os.environ, {"MINIONS_ROLE_NAME": role}, clear=False),
                pytest.raises(PermissionError),
            ):
                _require_tool_allowed("mos_adjudicate")


# ---------------------------------------------------------------------------
# Issue #11 — Shelf bootstrap at project_create (SUPERSEDED by Memory V2,
# 2026-05). The shared per-project shelf path was removed; the L3 Shelf
# is now Gru-aggregated cross-project from Book (V3-pending). We invert the
# original assertion to guard against a regression that silently re-adds
# shared/shelf/.
# ---------------------------------------------------------------------------


class TestShelfBootstrap:
    def test_create_shared_worktree_does_not_seed_shelf(self, tmp_path: Path) -> None:
        """create_shared_worktree must NOT write branches/shared/shelf/ after
        the Memory V2 downgrade.
        """
        from minions.lifecycle._project_worktree import create_shared_worktree

        # Build a minimal git-init'd parent_repo so the worktree add
        # has somewhere to branch off.
        port = 99201
        projects_root = tmp_path / "minionsos-projects"
        projects_root.mkdir()
        with patch.dict(
            os.environ,
            {"MINIONS_PROJECTS_ROOT": str(projects_root)},
            clear=False,
        ):
            from minions.paths import (
                project_dir as _pd,
            )
            from minions.paths import (
                project_parent_repo_dir,
                project_shared_workspace,
            )

            pdir = _pd(port)
            pdir.mkdir(parents=True, exist_ok=True)
            parent_repo = project_parent_repo_dir(port)
            parent_repo.mkdir(parents=True, exist_ok=True)

            # Initialize a real bare repo + a single empty commit on the
            # main branch so worktree add has a base.
            subprocess.run(
                ["git", "init", "--bare", str(parent_repo)], check=True, capture_output=True
            )
            seed = tmp_path / "seed-clone"
            subprocess.run(
                ["git", "clone", str(parent_repo), str(seed)],
                check=True,
                capture_output=True,
            )
            subprocess.run(["git", "config", "user.name", "Test"], cwd=seed, check=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=seed, check=True)
            (seed / "README").write_text("seed", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=seed, check=True)
            subprocess.run(
                ["git", "commit", "-m", "seed"], cwd=seed, check=True, capture_output=True
            )
            # Push to the bare repo's main branch under the project's
            # canonical project-branch name (matches what _seed_per_project_repo
            # produces in real flow).
            from minions.paths import project_branch_name

            subprocess.run(
                ["git", "push", "origin", f"main:{project_branch_name(port)}"],
                cwd=seed,
                check=True,
                capture_output=True,
            )

            create_shared_worktree(port)
            shared = project_shared_workspace(port)
            assert not (shared / "shelf").exists(), (
                "shared/shelf/ must not be seeded; L3 Shelf is Gru cross-project "
                "(V3-pending)."
            )


# ---------------------------------------------------------------------------
# Issue #12 — mos_compact_context filters empty pending_plans
# ---------------------------------------------------------------------------


class TestCompactContextEmptyPlanFilter:
    """Verify mos_compact_context drops pending_plans with empty/missing text
    BEFORE persisting, so the post-compact agent doesn't see stub Q-001
    nodes it has to triage and abandon."""

    def test_empty_text_plan_is_dropped(self, tmp_path: Path, monkeypatch) -> None:
        # Set up a fake project tree so mos_compact_context's tmux send-keys
        # path is short-circuited, and isolate the draft writes.
        monkeypatch.setenv("MINIONS_PROJECT_PORT", "99001")
        monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
        # Bootstrap an empty draft.json so mos_draft_append has a place to write.
        draft_dir = tmp_path / "project_99001" / "branches" / "shared" / "draft"
        draft_dir.mkdir(parents=True, exist_ok=True)
        (draft_dir / "draft.json").write_text(
            json.dumps({"project_port": 99001, "nodes": [], "edges": []}),
            encoding="utf-8",
        )

        from minions.tools import compact as _compact

        with patch.object(_compact, "_schedule_compact", return_value=True):
            result = _compact.mos_compact_context(
                reason="test-empty-filter",
                pending_plans=[
                    {"type": "question", "text": "real plan body"},
                    {"type": "question", "text": ""},  # empty — must be dropped
                    {"type": "decision"},  # missing text — must be dropped
                    {"type": "question", "text": "   "},  # whitespace-only — drop
                ],
            )

        # Only one plan should land in the Draft.
        assert len(result["draft_nodes_persisted"]) == 1
        # And three should be reported as skipped.
        assert len(result["skipped_empty_plans"]) == 3
        # Verify no empty-body node was actually written to disk.
        draft = json.loads((draft_dir / "draft.json").read_text(encoding="utf-8"))
        bodies = [n.get("text", "") for n in draft["nodes"]]
        assert all(b.strip() for b in bodies), f"empty body slipped through: {bodies}"
        assert "real plan body" in bodies

    def test_all_empty_plans_results_in_no_draft_writes(self, tmp_path: Path, monkeypatch) -> None:
        """Edge case: every plan is empty → no Draft writes at all,
        skipped_empty_plans surfaces all of them."""
        monkeypatch.setenv("MINIONS_PROJECT_PORT", "99001")
        monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
        draft_dir = tmp_path / "project_99001" / "branches" / "shared" / "draft"
        draft_dir.mkdir(parents=True, exist_ok=True)
        (draft_dir / "draft.json").write_text(
            json.dumps({"project_port": 99001, "nodes": [], "edges": []}),
            encoding="utf-8",
        )

        from minions.tools import compact as _compact

        with patch.object(_compact, "_schedule_compact", return_value=True):
            result = _compact.mos_compact_context(
                reason="all-empty",
                pending_plans=[
                    {"type": "question"},
                    {"type": "decision", "text": ""},
                ],
            )
        assert result["draft_nodes_persisted"] == []
        assert len(result["skipped_empty_plans"]) == 2
        draft = json.loads((draft_dir / "draft.json").read_text(encoding="utf-8"))
        assert draft["nodes"] == []

    def test_normal_plans_still_persist(self, tmp_path: Path, monkeypatch) -> None:
        """Sanity: the filter must NOT regress the happy path."""
        monkeypatch.setenv("MINIONS_PROJECT_PORT", "99001")
        monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
        draft_dir = tmp_path / "project_99001" / "branches" / "shared" / "draft"
        draft_dir.mkdir(parents=True, exist_ok=True)
        (draft_dir / "draft.json").write_text(
            json.dumps({"project_port": 99001, "nodes": [], "edges": []}),
            encoding="utf-8",
        )

        from minions.tools import compact as _compact

        with patch.object(_compact, "_schedule_compact", return_value=True):
            result = _compact.mos_compact_context(
                reason="happy-path",
                pending_plans=[
                    {"type": "question", "text": "Is the tokenizer matched?"},
                    {"type": "decision", "text": "Use Adam optimizer"},
                ],
            )
        assert len(result["draft_nodes_persisted"]) == 2
        assert result["skipped_empty_plans"] == []
