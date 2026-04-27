"""Regression tests for the MinionsOS team bug-report batch (2026-04-24).

Covers:
- #1 project_create fails fast + actionable error when parent is not a git repo
- #7 register_role / register_expert with init_brief publishes an EACN task
     (gru → role), does NOT spawn a local ephemeral Claude
- #9 WakeupScheduler accepts 'state_store=' as a kwarg alias for 'store='
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from minions.errors import ProjectError
from minions.lifecycle import project as project_mod
from minions.lifecycle import role as role_mod
from minions.lifecycle.wakeup import WakeupScheduler
from minions.state.store import ProjectEntry, StateStore

# ---------------------------------------------------------------------------
# #1 parent-git precheck
# ---------------------------------------------------------------------------


class TestParentGitPrecheck:
    def test_raises_actionable_error_when_parent_not_git(self, tmp_path: Path) -> None:
        fake_parent = tmp_path / "not-a-repo"
        fake_parent.mkdir()
        fake_root = fake_parent / "MinionsOS_V4"
        fake_root.mkdir()
        with (
            patch.object(project_mod, "MINIONS_ROOT", fake_root),
            pytest.raises(ProjectError) as exc_info,
        ):
            project_mod._ensure_parent_is_git_repo()
        msg = str(exc_info.value)
        assert "not a git repository" in msg
        # Must contain an actionable hint so the user knows what to run.
        assert "git init" in msg
        assert "git commit" in msg

    def test_passes_when_parent_is_git(self, tmp_path: Path, monkeypatch) -> None:
        import subprocess

        parent = tmp_path / "parent"
        parent.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=parent, check=True)
        fake_root = parent / "MinionsOS_V4"
        fake_root.mkdir()
        with patch.object(project_mod, "MINIONS_ROOT", fake_root):
            # Should not raise.
            project_mod._ensure_parent_is_git_repo()


# ---------------------------------------------------------------------------
# #7 init_brief routes via EACN task
# ---------------------------------------------------------------------------


class _FakeStore:
    def __init__(self) -> None:
        self.projects: dict[int, ProjectEntry] = {
            37596: ProjectEntry(
                port=37596,
                real_name="test",
                status="active",
                created="2026-01-01T00:00:00+00:00",
                active_roles=[],
            )
        }
        self.upserts: list = []

    def get_project(self, port: int) -> ProjectEntry | None:
        return self.projects.get(port)

    def upsert_role(self, port: int, role_entry) -> None:
        self.upserts.append(role_entry)


class TestInitBriefGoesThroughEacn:
    def test_register_role_publishes_eacn_task(self) -> None:
        store = _FakeStore()
        with (
            patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])),
            patch("minions.lifecycle.eacn_client.create_task", return_value={}) as create_task,
            patch.object(role_mod, "invoke_role_ephemeral") as invoke,
        ):
            role_mod.register_role(
                37596,
                "coder",
                init_brief="kick off please",
                store=store,
                poll_interval="1m",
            )
        # init_brief must go through EACN, NOT through a local ephemeral spawn.
        create_task.assert_called_once()
        invoke.assert_not_called()

        kwargs = create_task.call_args.kwargs
        assert kwargs["port"] == 37596
        assert kwargs["initiator_id"] == "gru"
        assert kwargs["invited_agent_ids"] == ["coder"]
        assert kwargs["description"] == "kick off please"
        assert kwargs["budget"] == 0.0

    def test_register_expert_publishes_eacn_task(self) -> None:
        store = _FakeStore()
        with (
            patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])),
            patch("minions.lifecycle.eacn_client.create_task", return_value={}) as create_task,
            patch.object(role_mod, "invoke_role_ephemeral") as invoke,
        ):
            role_mod.register_expert(
                37596,
                "deep learning architecture",
                init_brief=None,  # expert injects a default
                store=store,
                poll_interval="1m",
            )
        create_task.assert_called_once()
        invoke.assert_not_called()
        assert create_task.call_args.kwargs["invited_agent_ids"][0].startswith("expert-")

    def test_register_role_fails_if_init_brief_cannot_queue(self) -> None:
        """A role is not active unless its first message is queued through EACN."""
        store = _FakeStore()
        with (
            patch.object(role_mod, "register_project_role_agent", return_value=("tok", [])),
            patch(
                "minions.lifecycle.eacn_client.create_task",
                side_effect=role_mod.BackendError("EACN is down"),
            ),
            pytest.raises(role_mod.RoleError),
        ):
            role_mod.register_role(
                37596,
                "coder",
                init_brief="kick",
                store=store,
                poll_interval="1m",
            )
        assert store.upserts == []


# ---------------------------------------------------------------------------
# #9 WakeupScheduler kwarg alias
# ---------------------------------------------------------------------------


class TestWakeupSchedulerStateStoreAlias:
    def test_state_store_alias_accepted(self) -> None:
        ss = StateStore()
        sched = WakeupScheduler(state_store=ss)
        assert sched._store is ss

    def test_store_still_works(self) -> None:
        ss = StateStore()
        sched = WakeupScheduler(store=ss)
        assert sched._store is ss

    def test_both_raises(self) -> None:
        ss = StateStore()
        with pytest.raises(TypeError, match="not both"):
            WakeupScheduler(store=ss, state_store=ss)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
