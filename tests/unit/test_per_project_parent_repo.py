"""Tests for the per-project parent-repo seed model.

These cover behavior that is specific to v7.7 — every project owns a
private bare git repo seeded from the author repo's HEAD, so worktrees
never branch off the author's own ``.git``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from minions.lifecycle import project as project_mod
from minions.paths import (
    project_dir,
    project_main_workspace,
    project_parent_repo_dir,
    project_shared_workspace,
    project_state_dir,
    project_workspace_root,
)


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    ).stdout


def _make_author_repo(root: Path) -> Path:
    author = root / "author"
    author.mkdir()
    _git(["init", "-q"], author)
    _git(["config", "user.email", "t@e.com"], author)
    _git(["config", "user.name", "test"], author)
    (author / "README.md").write_text("hello\n", encoding="utf-8")
    (author / "main.py").write_text("print('hi')\n", encoding="utf-8")
    _git(["add", "."], author)
    _git(["commit", "-qm", "init"], author)
    return author


@pytest.fixture
def seeded_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Create an author repo, seed a per-project bare repo, return paths."""
    author = _make_author_repo(tmp_path)
    projects_root = tmp_path / "projects-root"
    projects_root.mkdir()

    monkeypatch.setenv("MINIONS_AUTHOR_REPO", str(author))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(projects_root))

    port = 41000
    project_dir(port).mkdir(parents=True, exist_ok=True)
    project_workspace_root(port).mkdir(parents=True, exist_ok=True)
    project_state_dir(port).mkdir(parents=True, exist_ok=True)

    project_mod._seed_per_project_repo(port)
    project_mod._create_worktree(port, "HEAD")
    project_mod._create_shared_worktree(port)
    return {"port": port, "author": author, "tmp_path": tmp_path}


def test_seed_creates_bare_repo_with_main_branch(seeded_project: dict[str, object]) -> None:
    port = int(seeded_project["port"])  # type: ignore[arg-type]
    bare = project_parent_repo_dir(port)
    assert bare.exists()
    # ``--is-bare-repository`` returns "true" for bare repos.
    bare_check = subprocess.run(
        ["git", "rev-parse", "--is-bare-repository"],
        cwd=str(bare),
        capture_output=True,
        text=True,
        check=True,
    )
    assert bare_check.stdout.strip() == "true"
    branches = _git(["branch", "--list"], bare).split()
    assert f"minionsos/project-{port}" in " ".join(branches)


def test_seed_imports_author_head_contents(seeded_project: dict[str, object]) -> None:
    port = int(seeded_project["port"])  # type: ignore[arg-type]
    main = project_main_workspace(port)
    assert (main / "README.md").read_text(encoding="utf-8") == "hello\n"
    assert (main / "main.py").read_text(encoding="utf-8") == "print('hi')\n"


def test_seed_records_author_sha_in_commit_message(
    seeded_project: dict[str, object],
) -> None:
    port = int(seeded_project["port"])  # type: ignore[arg-type]
    author = seeded_project["author"]
    author_sha = _git(["rev-parse", "HEAD"], author).strip()  # type: ignore[arg-type]
    seed_log = _git(
        ["log", "--format=%s", f"minionsos/project-{port}"],
        project_parent_repo_dir(port),
    )
    assert any(author_sha[:12] in line for line in seed_log.splitlines())


def test_seed_excludes_minions_os_subdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The author repo may have MinionsOS placed inside it; seed must skip it."""
    author = _make_author_repo(tmp_path)
    nested = author / "MinionsOS"
    nested.mkdir()
    (nested / "marker.txt").write_text("should not appear", encoding="utf-8")
    _git(["add", "."], author)
    _git(["commit", "-qm", "add MinionsOS"], author)

    projects_root = tmp_path / "projects-root"
    projects_root.mkdir()
    monkeypatch.setenv("MINIONS_AUTHOR_REPO", str(author))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(projects_root))

    port = 41001
    project_dir(port).mkdir(parents=True, exist_ok=True)
    project_workspace_root(port).mkdir(parents=True, exist_ok=True)
    project_state_dir(port).mkdir(parents=True, exist_ok=True)

    project_mod._seed_per_project_repo(port)
    project_mod._create_worktree(port, "HEAD")

    main = project_main_workspace(port)
    assert not (main / "MinionsOS").exists(), "MinionsOS subdir leaked into seed"


def test_seed_skips_files_larger_than_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Files exceeding the 500 MB threshold must be dropped from the seed."""
    author = _make_author_repo(tmp_path)
    # Don't actually create a 500 MB file — patch the threshold instead.
    big = author / "big.bin"
    big.write_bytes(b"x" * 1024)
    _git(["add", "."], author)
    _git(["commit", "-qm", "add big"], author)

    projects_root = tmp_path / "projects-root"
    projects_root.mkdir()
    monkeypatch.setenv("MINIONS_AUTHOR_REPO", str(author))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(projects_root))
    monkeypatch.setattr(project_mod, "_LARGE_FILE_THRESHOLD_BYTES", 512)

    port = 41002
    project_dir(port).mkdir(parents=True, exist_ok=True)
    project_workspace_root(port).mkdir(parents=True, exist_ok=True)
    project_state_dir(port).mkdir(parents=True, exist_ok=True)

    project_mod._seed_per_project_repo(port)
    project_mod._create_worktree(port, "HEAD")

    main = project_main_workspace(port)
    assert (main / "README.md").exists()
    assert not (main / "big.bin").exists(), "Oversized file leaked into seed"


def test_seed_does_not_pollute_author_repo(seeded_project: dict[str, object]) -> None:
    """The author repo must not gain any minionsos/ branches from project_create."""
    author = seeded_project["author"]
    branches = _git(["branch", "--list", "minionsos/*"], author)  # type: ignore[arg-type]
    assert branches.strip() == "", "Author repo gained minionsos/* branches: " + branches


def test_remove_all_worktrees_cleans_branches_dir(
    seeded_project: dict[str, object],
) -> None:
    """``_remove_all_worktrees`` strips working dirs but keeps branches."""
    port = int(seeded_project["port"])  # type: ignore[arg-type]
    main = project_main_workspace(port)
    shared = project_shared_workspace(port)
    assert main.exists()
    assert shared.exists()

    project_mod._remove_all_worktrees(port)

    assert not main.exists(), "main worktree dir should be removed"
    assert not shared.exists(), "shared worktree dir should be removed"

    bare = project_parent_repo_dir(port)
    branches = _git(["branch", "--list"], bare)
    assert f"minionsos/project-{port}" in branches
    assert f"minionsos/project-{port}-shared" in branches


def test_remove_all_worktrees_is_safe_when_already_clean(
    seeded_project: dict[str, object],
) -> None:
    """Calling cleanup twice must not raise."""
    port = int(seeded_project["port"])  # type: ignore[arg-type]
    project_mod._remove_all_worktrees(port)
    project_mod._remove_all_worktrees(port)


def test_author_repo_resolves_configured_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    author = _make_author_repo(tmp_path)
    monkeypatch.setenv("MINIONS_AUTHOR_REPO", str(author))
    resolved = project_mod.author_repo()
    assert resolved.resolve() == author.resolve()


def test_seed_fails_clearly_when_author_is_not_a_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    not_a_repo = tmp_path / "plain-dir"
    not_a_repo.mkdir()
    monkeypatch.setenv("MINIONS_AUTHOR_REPO", str(not_a_repo))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path / "p"))

    port = 41003
    project_dir(port).mkdir(parents=True, exist_ok=True)
    project_state_dir(port).mkdir(parents=True, exist_ok=True)

    from minions.errors import ProjectError

    with pytest.raises(ProjectError, match="not a git repository"):
        project_mod._seed_per_project_repo(port)


def test_seed_refuses_when_b_is_not_git_but_lives_inside_outer_a_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """User layout: A/.git exists, A/B is a plain dir, A/B/MinionsOS is the
    checkout. Without an explicit MINIONS_AUTHOR_REPO override, ``author_repo()``
    used to silently resolve to A (because ``git rev-parse --is-inside-work-tree``
    walks up). That would seed every sibling of B from A's HEAD.

    The fix: refuse with an actionable error pointing at both options
    (init B, or explicitly opt into A via MINIONS_AUTHOR_REPO).
    """
    a = tmp_path / "A"
    a.mkdir()
    _git(["init", "-q"], a)
    _git(["config", "user.email", "t@e.com"], a)
    _git(["config", "user.name", "test"], a)
    (a / "sibling-of-B.txt").write_text("not part of the project\n", encoding="utf-8")
    (a / "secrets.env").write_text("API_KEY=do-not-leak\n", encoding="utf-8")
    _git(["add", "."], a)
    _git(["commit", "-qm", "init A"], a)
    b = a / "B"
    b.mkdir()
    # B is *not* git-initialized.

    monkeypatch.setenv("MINIONS_AUTHOR_REPO", str(b))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path / "p"))

    port = 41004
    project_dir(port).mkdir(parents=True, exist_ok=True)
    project_state_dir(port).mkdir(parents=True, exist_ok=True)

    from minions.errors import ProjectError

    with pytest.raises(ProjectError) as excinfo:
        project_mod._seed_per_project_repo(port)
    msg = str(excinfo.value)
    assert "inside an outer git work tree" in msg
    assert str(a.resolve()) in msg
    assert "MINIONS_AUTHOR_REPO" in msg


def test_author_repo_does_not_walk_up_into_outer_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``author_repo()`` must not silently resolve to an *ancestor* git repo.

    Layout: A/.git, A/B (plain). ``MINIONS_ROOT`` points at A/B. Before the
    fix, ``_is_git_work_tree(A/B)`` returned True via ``--is-inside-work-tree``
    and ``author_repo()`` returned ``A/B`` while every git command run with
    ``cwd=A/B`` operated on A. Now the strict check says "B is not a work-tree
    root", so ``author_repo()`` falls through to ``MINIONS_ROOT.parent`` (which
    is B and also not a root) — leaving the seed step to raise the actionable
    error.
    """
    a = tmp_path / "A"
    a.mkdir()
    _git(["init", "-q"], a)
    _git(["config", "user.email", "t@e.com"], a)
    _git(["config", "user.name", "test"], a)
    _git(["commit", "-q", "--allow-empty", "-m", "init"], a)
    b = a / "B"
    b.mkdir()

    from minions.lifecycle.git_utils import is_git_work_tree

    assert not is_git_work_tree(b), "B is not its own git root, must not be reported as one"
    assert is_git_work_tree(a), "A is its own git root"
