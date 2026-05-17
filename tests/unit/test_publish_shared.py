"""Tests for ``mos_publish_to_shared`` (cross-role shared-tree publishing).

Spins a real (small) git parent repo + real worktrees on a per-test
temp directory so the flock + commit semantics are exercised end-to-end.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from minions.errors import ProjectError
from minions.lifecycle import project as project_mod
from minions.paths import (
    project_dir,
    project_shared_branch_name,
    project_shared_workspace,
    project_state_dir,
    project_workspace_root,
)
from minions.tools.publish import (
    _ROLE_ALLOWED_SHARED_SUBDIRS,
    _validate_dst,
    mos_publish_to_shared,
)


def _git(args: list[str], cwd: Path) -> str:
    res = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )
    return res.stdout


def _git_log(workspace: Path) -> list[str]:
    return [
        line
        for line in _git(["log", "--oneline"], workspace).splitlines()
        if line.strip()
    ]


@pytest.fixture
def shared_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Create a real parent git repo + an initialised project_{port}/ tree
    with main and shared worktrees. Returns a dict with the resolved port,
    parent path, projects-root path, and convenience workspace paths.
    """
    parent = tmp_path / "parent"
    projects_root = tmp_path / "projects-root"
    parent.mkdir()
    projects_root.mkdir()
    _git(["init", "-q"], parent)
    _git(["config", "user.email", "t@e.com"], parent)
    _git(["config", "user.name", "test"], parent)
    (parent / "README.md").write_text("init\n", encoding="utf-8")
    _git(["add", "."], parent)
    _git(["commit", "-qm", "init"], parent)

    monkeypatch.setenv("MINIONS_PROJECT_PARENT_REPO", str(parent))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(projects_root))

    port = 39901
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))

    project_dir(port).mkdir(parents=True, exist_ok=True)
    project_workspace_root(port).mkdir(parents=True, exist_ok=True)
    project_state_dir(port).mkdir(parents=True, exist_ok=True)

    project_mod._create_worktree(port, "HEAD")
    project_mod._create_shared_worktree(port)

    return {
        "port": port,
        "parent": parent,
        "projects_root": projects_root,
        "shared_workspace": project_shared_workspace(port),
        "shared_branch": project_shared_branch_name(port),
        "tmp_path": tmp_path,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_dst_rejects_path_traversal() -> None:
    with pytest.raises(ProjectError, match="may not escape"):
        _validate_dst("gru", "../escape.md")


def test_validate_dst_rejects_absolute_paths() -> None:
    with pytest.raises(ProjectError, match="must be a relative path"):
        _validate_dst("gru", "/etc/passwd")


def test_validate_dst_rejects_reviews_for_any_role() -> None:
    for role in _ROLE_ALLOWED_SHARED_SUBDIRS:
        with pytest.raises(ProjectError, match="reserved for mos_review_run"):
            _validate_dst(role, "reviews/round-1/sneak.md")


def test_validate_dst_rejects_unknown_role() -> None:
    with pytest.raises(ProjectError, match="no shared-publish policy"):
        _validate_dst("intruder", "handoffs/x.md")


def test_validate_dst_enforces_role_subdir_policy() -> None:
    # Writer may publish only into handoffs/.
    with pytest.raises(ProjectError, match="may not publish"):
        _validate_dst("writer", "ethics/x.md")
    # Ethics may not publish into exploration/ (Noter-only).
    with pytest.raises(ProjectError, match="may not publish"):
        _validate_dst("ethics", "exploration/dag.json")
    # Gru can publish anywhere.
    _validate_dst("gru", "ethics/foo.md")
    _validate_dst("gru", "exp/exp-1/report.md")
    # Expert-<slug> normalises to expert.
    _validate_dst("expert-dl-arch", "handoffs/scratch.md")


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


def test_publish_writer_handoff_creates_commit(
    shared_project: dict[str, object], tmp_path: Path
) -> None:
    src = tmp_path / "writer-handoff.md"
    src.write_text("# Handoff\nresult.\n", encoding="utf-8")

    result = mos_publish_to_shared(
        role="writer",
        src_path=str(src),
        dst_subpath="handoffs/2026-05-17-writer.md",
        commit_message="handoff: writer dispatched draft to coder",
    )
    assert result["pushed"] is False
    assert result["push_branch"] is None
    assert result["dst_path"] == "handoffs/2026-05-17-writer.md"
    assert result["branch"] == shared_project["shared_branch"]
    assert isinstance(result["commit_sha"], str) and len(result["commit_sha"]) == 40

    log = _git_log(shared_project["shared_workspace"])  # type: ignore[arg-type]
    assert any("handoff: writer" in line for line in log)
    landed = shared_project["shared_workspace"] / "handoffs" / "2026-05-17-writer.md"  # type: ignore[operator]
    assert landed.read_text(encoding="utf-8") == "# Handoff\nresult.\n"


def test_publish_rejects_writer_into_ethics(
    shared_project: dict[str, object], tmp_path: Path
) -> None:
    src = tmp_path / "src.md"
    src.write_text("nope", encoding="utf-8")
    with pytest.raises(ProjectError, match="may not publish"):
        mos_publish_to_shared(
            role="writer",
            src_path=str(src),
            dst_subpath="ethics/sneak.md",
            commit_message="x",
        )


def test_publish_rejects_anyone_into_reviews(
    shared_project: dict[str, object], tmp_path: Path
) -> None:
    src = tmp_path / "src.md"
    src.write_text("x", encoding="utf-8")
    with pytest.raises(ProjectError, match="reserved for mos_review_run"):
        mos_publish_to_shared(
            role="gru",
            src_path=str(src),
            dst_subpath="reviews/round-1/x.md",
            commit_message="x",
        )


def test_publish_idempotent_when_no_diff(
    shared_project: dict[str, object], tmp_path: Path
) -> None:
    src = tmp_path / "same.md"
    src.write_text("static\n", encoding="utf-8")
    r1 = mos_publish_to_shared(
        role="gru",
        src_path=str(src),
        dst_subpath="handoffs/static.md",
        commit_message="initial",
    )
    assert r1["commit_sha"] is not None
    # Republish identical contents → no commit.
    r2 = mos_publish_to_shared(
        role="gru",
        src_path=str(src),
        dst_subpath="handoffs/static.md",
        commit_message="should be no-op",
    )
    assert r2["commit_sha"] is None


def test_publish_does_not_absorb_unrelated_dirty_paths(
    shared_project: dict[str, object], tmp_path: Path
) -> None:
    """A publish must commit ONLY its own dst_subpath. Other dirty files
    in the shared worktree (e.g. an in-flight DAG buffer or a partially
    staged ethics report) must remain uncommitted afterwards.

    This guards the buffered-DAG / committed-publish split: if publish
    swept up everything dirty, every role's publish would absorb the DAG
    buffer and Noter's flush would have nothing to commit.
    """
    workspace = shared_project["shared_workspace"]  # type: ignore[index]
    # Simulate a dirty DAG buffer in the shared worktree.
    dag_path = workspace / "exploration" / "dag.json"  # type: ignore[operator]
    dag_path.parent.mkdir(parents=True, exist_ok=True)
    dag_path.write_text('{"nodes": [{"id": "H-001"}]}', encoding="utf-8")
    assert dag_path.exists()

    # Writer publishes a totally unrelated handoff.
    src = tmp_path / "draft.md"
    src.write_text("# draft", encoding="utf-8")
    res = mos_publish_to_shared(
        role="writer",
        src_path=str(src),
        dst_subpath="handoffs/draft.md",
        commit_message="handoff: writer draft",
    )
    assert res["commit_sha"] is not None

    # The DAG file must STILL be dirty (untracked or unstaged) — writer's
    # publish must not have absorbed it.
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", "exploration/dag.json"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout.strip(), (
        "DAG buffer should remain dirty after writer's unrelated publish, "
        f"but git reports clean: {status.stdout!r}"
    )


def test_publish_in_place_dag_flush_works(
    shared_project: dict[str, object],
) -> None:
    """Source and destination resolving to the same file (DAG flush) must
    not raise SameFileError."""
    workspace = shared_project["shared_workspace"]
    dag_path = workspace / "exploration" / "dag.json"  # type: ignore[operator]
    dag_path.parent.mkdir(parents=True, exist_ok=True)
    dag_path.write_text(json.dumps({"nodes": [{"id": "H-001"}]}), encoding="utf-8")

    result = mos_publish_to_shared(
        role="noter",
        src_path=str(dag_path),
        dst_subpath="exploration/dag.json",
        commit_message="noter: dag flush",
    )
    assert result["commit_sha"] is not None
    assert dag_path.exists()


def test_publish_requires_shared_worktree_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the shared worktree is missing (project_create wasn't run), publish
    must raise rather than silently create something off-branch."""
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path / "p"))
    monkeypatch.setenv("MINIONS_PROJECT_PORT", "39902")
    monkeypatch.setenv("MINIONS_PROJECT_PARENT_REPO", str(tmp_path / "no-such-repo"))
    src = tmp_path / "x.md"
    src.write_text("x", encoding="utf-8")
    with pytest.raises(ProjectError, match="Shared worktree missing"):
        mos_publish_to_shared(
            role="gru",
            src_path=str(src),
            dst_subpath="handoffs/x.md",
            commit_message="x",
        )


def test_publish_requires_existing_src(shared_project: dict[str, object]) -> None:
    with pytest.raises(ProjectError, match="src_path does not exist"):
        mos_publish_to_shared(
            role="gru",
            src_path="/no/such/file.md",
            dst_subpath="handoffs/x.md",
            commit_message="x",
        )


def test_publish_requires_absolute_src(
    shared_project: dict[str, object], tmp_path: Path
) -> None:
    rel = "relative/path.md"
    with pytest.raises(ProjectError, match="src_path must be absolute"):
        mos_publish_to_shared(
            role="gru",
            src_path=rel,
            dst_subpath="handoffs/x.md",
            commit_message="x",
        )


# ---------------------------------------------------------------------------
# Shared worktree creation
# ---------------------------------------------------------------------------


def test_create_shared_worktree_idempotent(shared_project: dict[str, object]) -> None:
    port = shared_project["port"]
    branch1 = project_mod._create_shared_worktree(port)
    branch2 = project_mod._create_shared_worktree(port)
    assert branch1 == branch2 == shared_project["shared_branch"]


def test_create_shared_worktree_seeds_subdirs(shared_project: dict[str, object]) -> None:
    workspace = shared_project["shared_workspace"]
    seeded = sorted(p.name for p in workspace.iterdir() if p.is_dir())  # type: ignore[union-attr]
    assert seeded == ["ethics", "exp", "exploration", "handoffs", "notes", "reviews"]
    # Seed commit should exist on the shared branch.
    log = _git_log(workspace)  # type: ignore[arg-type]
    assert any("shared: seed cross-role layout" in line for line in log)
