"""Project worktree creation + thin git wrappers.

Extracted from :mod:`minions.lifecycle.project` to reduce the orchestrator
file size. Nothing here is monkeypatched by tests, so moving it out is
safe. Functions are re-exported from ``project`` under their original
underscore-prefixed names.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from minions.errors import ProjectError
from minions.lifecycle.git_utils import (
    git_ref_exists as _gu_git_ref_exists,
)
from minions.lifecycle.git_utils import (
    is_git_dirty as _gu_is_git_dirty,
)
from minions.lifecycle.git_utils import (
    run_git as _gu_run_git,
)
from minions.paths import (
    project_branch_name,
    project_main_workspace,
    project_parent_repo_dir,
)

logger = logging.getLogger(__name__)


SHARED_SUBDIRS = (
    "draft",
    "notes",
    "ethics",
    "exp",
    "reviews",
    "submissions",
    "handoffs",
    "governance",
    "book",
    "logic",
    "src",
    "evidence",
    "proposal",
)
SHARED_README = """\
# Project main branch — the team's shared surface (the "Book")

This is the main branch checkout (`minionsos/project-{port}`). In the v23
rebuild the standalone `-shared` branch was eliminated: the team's shared
surface IS the main branch. Gru owns it; Ethics seals content and Gru
promotes it into the Book layout.

## Live process surface (written directly)

- `draft/draft.json` — L1 process graph. The single graph structure; every
  role appends via `mos_draft_append`; Ethics curates and flushes it.
- `governance/signboard.json` — milestone consensus state.
- `reviews/round-<n>/` — `mos_review_run` output (tool-owned).
- `submissions/` — `mos_submit` deliverables.
- `notes/`, `ethics/`, `exp/`, `handoffs/` — staged reports, audit reports,
  experiment bundles, cross-role handoffs.

## Book layout (Ethics-sealed → Gru-promoted)

- `Book.md` — root manifest + layer index.
- `logic/` — cognitive layer: problem, claims, concepts, experiments,
  solution/ (architecture, algorithm, constraints, heuristics), related_work.
- `src/` — physical layer: configs, environment.
- `evidence/` — raw proof: tables, figures.
- `proposal/` — pre-project materials.

Per-role private scratch lives on each role's own branch
(`branches/<role>/`); only this shared surface is on main.
"""


def create_worktree(port: int, base_branch: str) -> str:
    """Create the main worktree for *port* against its bare parent repo.

    The seed step has already created branch ``minionsos/project-{port}``
    in the bare repo, pointing at the seed commit. This function just
    checks that branch out into ``branches/main/``.

    *base_branch* is accepted for API compatibility (callers may pass
    ``"HEAD"`` or a tag like the upstream branch name) but is currently
    ignored — every project starts on its own freshly-seeded branch.
    """
    del base_branch  # reserved for future "fork from existing branch" support
    branch = f"minionsos/project-{port}"
    workspace = project_main_workspace(port)
    workspace.parent.mkdir(parents=True, exist_ok=True)

    parent_repo = project_parent_repo_dir(port)

    cmd = [
        "git",
        "worktree",
        "add",
        str(workspace),
        branch,
    ]
    logger.info("Creating worktree: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(parent_repo),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ProjectError(f"git worktree add failed for port {port}: {result.stderr.strip()}")

    # Seed the shared-surface + Book layout directly on the main branch.
    # The standalone -shared branch is gone; main IS the shared surface.
    for subdir in SHARED_SUBDIRS:
        sub = workspace / subdir
        sub.mkdir(parents=True, exist_ok=True)
        (sub / ".gitkeep").write_text("", encoding="utf-8")
    (workspace / "README.md").write_text(SHARED_README.format(port=port), encoding="utf-8")
    seed_commit = git_commit_workspace(workspace, "main: seed Book layout + shared surface")
    if seed_commit is None:
        logger.debug("main worktree seed produced no commit (already clean)")
    return branch


def create_shared_worktree(port: int) -> str:
    """No-op shim: the standalone shared worktree was eliminated in v23.

    The team's shared surface is now the main branch (seeded by
    :func:`create_worktree`). Retained so existing call sites keep working;
    returns the main branch name.
    """
    return project_branch_name(port)


def git_ref_exists(repo: Path, ref: str) -> bool:
    return _gu_git_ref_exists(repo, ref)


def git_status_porcelain(workspace: Path) -> list[str]:
    """Return the workspace's porcelain status lines."""
    result = _gu_run_git(["status", "--porcelain"], workspace, action="status")
    return [line for line in result.stdout.splitlines() if line.strip()]


def is_git_dirty(workspace: Path) -> bool:
    return _gu_is_git_dirty(workspace)


def git_commit_workspace(workspace: Path, message: str) -> str | None:
    """Commit the workspace if there are staged changes, returning HEAD sha."""
    _gu_run_git(["add", "-A"], workspace, action="add")
    commit_result = _gu_run_git(["commit", "-m", message], workspace, check=False)
    if commit_result.returncode != 0:
        output = f"{commit_result.stdout}\n{commit_result.stderr}".lower()
        if "nothing to commit" in output or "nothing added to commit" in output:
            return None
        raise ProjectError(
            f"git commit failed for workspace {workspace}: {commit_result.stderr.strip()}"
        )
    head = _gu_run_git(["rev-parse", "HEAD"], workspace, action="rev-parse")
    return head.stdout.strip() or None


def git_push_checkpoint(workspace: Path, target: str, remote_branch: str) -> None:
    """Push the current HEAD to *target* under *remote_branch*."""
    result = _gu_run_git(
        ["push", target, f"HEAD:{remote_branch}"],
        workspace,
        check=False,
    )
    if result.returncode != 0:
        raise ProjectError(
            f"git push failed for workspace {workspace} -> {target}:{remote_branch}: "
            f"{result.stderr.strip()}"
        )
