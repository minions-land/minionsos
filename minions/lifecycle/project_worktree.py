"""Git worktree management for MinionsOS projects.

Handles creation, removal, and maintenance of per-project and per-role git
worktrees. Each project has a bare repo (parent_repo.git) and multiple
worktrees under branches/.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from minions.errors import ProjectError
from minions.lifecycle.git_utils import is_git_work_tree, run_git
from minions.paths import (
    MINIONS_ROOT,
    project_branch_name,
    project_main_workspace,
    project_parent_repo_dir,
    project_role_workspace,
)

logger = logging.getLogger(__name__)


# Shared surface subdirectories seeded at project creation
SHARED_SUBDIRS = [
    "draft",
    "notes",
    "ethics",
    "exp",
    "reviews",
    "submissions",
    "handoffs",
    "governance",
    "book",
]

SHARED_README = """# Shared Surface

Cross-role coordination artifacts live here. Roles publish via
`mos_publish_to_shared`; Gru orchestrates writes to `reviews/` and
`submissions/`.

## Directory roles

- `draft/` — L1 process memory (Draft graph), maintained by Ethics
- `notes/` — staged memory reports awaiting Ethics curation
- `ethics/` — Ethics-published audit reports (flat)
- `exp/` — Expert experiment result bundles
- `reviews/` — mos_review_run output (tool-owned)
- `submissions/` — mos_submit deliverables
- `handoffs/` — cross-role handoffs
- `governance/` — signboard.json (phase-transition consensus)
- `book/` — Layer 2 Compiled Knowledge (Ethics-curated)
"""


def create_worktree(port: int, base_branch: str) -> str:
    """Create the main worktree for *port* on branch minionsos/project-{port}.

    ``seed_per_project_repo`` has already pushed the seed commit to this
    branch and set the bare repo HEAD to it, so worktree creation must check
    out the existing branch instead of creating it with ``git worktree add -b``.

    Returns the branch name.
    """
    del base_branch  # project branches are seeded before worktree creation
    branch = project_branch_name(port)
    workspace = project_main_workspace(port)
    parent_repo = project_parent_repo_dir(port)

    if workspace.exists():
        if is_git_work_tree(workspace):
            return branch
        raise ProjectError(f"Main workspace already exists but is not a git worktree: {workspace}")

    workspace.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "git",
        "worktree",
        "add",
        str(workspace),
        branch,
    ]
    logger.info("Creating main worktree: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(parent_repo),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ProjectError(f"git worktree add failed for port {port}: {result.stderr.strip()}")
    return branch


def create_shared_worktree(port: int) -> str:
    """Seed the shared surface on the main branch (no separate -shared branch).

    v23 eliminated the standalone -shared branch; the shared surface now
    lives directly under branches/main/ (the Book). This function seeds
    the subdirectory structure + README on the main worktree.

    Returns the main branch name.
    """
    main_workspace = project_main_workspace(port)
    if not main_workspace.exists():
        raise ProjectError(
            f"Main workspace must exist before seeding shared surface: {main_workspace}"
        )

    # Seed subdirectories
    for subdir in SHARED_SUBDIRS:
        (main_workspace / subdir).mkdir(parents=True, exist_ok=True)

    # Seed README
    readme = main_workspace / "README.md"
    if not readme.exists():
        readme.write_text(SHARED_README, encoding="utf-8")

    # Commit the seed
    try:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(main_workspace),
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "seed: shared surface structure"],
            cwd=str(main_workspace),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.debug(
            "Shared surface seed commit skipped (may already exist): %s",
            exc.stderr if hasattr(exc, "stderr") else exc,
        )

    return project_branch_name(port)


def create_role_worktree(
    port: int,
    role_name: str,
    base_branch: str | None = None,
) -> tuple[str, Path]:
    """Create or verify the git worktree for one role.

    Gru resolves to the project's main worktree and main branch; this
    function treats it like any other role so the main worktree is
    guaranteed to exist before Gru is registered. Any other role gets
    its own branch minionsos/project-{port}-{role} rooted at the project
    main branch.

    Returns (branch_name, workspace_path).
    """
    branch = project_branch_name(port, role_name)
    workspace = project_role_workspace(port, role_name)
    if workspace.exists():
        if is_git_work_tree(workspace):
            return branch, workspace
        raise ProjectError(f"Role workspace already exists but is not a git worktree: {workspace}")

    workspace.parent.mkdir(parents=True, exist_ok=True)
    parent_repo = project_parent_repo_dir(port)
    resolved_base = base_branch if base_branch not in {None, ""} else project_branch_name(port)
    if resolved_base != "HEAD" and not git_ref_exists(parent_repo, resolved_base):
        logger.debug(
            "Role base branch %s missing in %s; falling back to HEAD.",
            resolved_base,
            parent_repo,
        )
        resolved_base = "HEAD"
    cmd = [
        "git",
        "worktree",
        "add",
        "-b",
        branch,
        str(workspace),
        resolved_base,
    ]
    logger.info("Creating role worktree: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(parent_repo),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ProjectError(
            f"git worktree add failed for role {role_name!r} on port {port}: "
            f"{result.stderr.strip()}"
        )
    return branch, workspace


def seed_claude_settings(workspace: Path) -> None:
    """Mirror MinionsOS/.claude/settings.json into the role workspace.

    Role workspaces are per-branch git worktrees, so any hook command
    that resolves paths via $(git rev-parse --show-toplevel) would
    land on the worktree path (which has no .venv and no minions/hooks/)
    and fail or hang. The canonical settings.json at the MinionsOS root
    uses a MINIONS_ROOT-anchored gate that the role launcher exports, so
    a verbatim copy is what we want here: every hook resolves against
    the real install, every event surface (PreToolUse, PostToolUse,
    PreCompact/PostCompact) fires.

    Idempotent: skips when the workspace already has its own
    .claude/settings.json. Non-fatal: if the source is missing
    (development environment without a checked-in settings.json), logs
    and returns — the role launches without hooks rather than crashing.
    """
    settings_path = workspace / ".claude" / "settings.json"
    if settings_path.exists():
        return
    source = MINIONS_ROOT / ".claude" / "settings.json"
    if not source.is_file():
        logger.warning(
            "seed_claude_settings: source settings.json missing at %s; "
            "role workspace at %s will launch without MinionsOS hooks.",
            source,
            workspace,
        )
        return
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = settings_path.with_suffix(".tmp")
    tmp.write_bytes(source.read_bytes())
    os.replace(tmp, settings_path)


def git_ref_exists(repo: Path, ref: str) -> bool:
    """Check if a git ref exists in *repo*."""
    result = run_git(["rev-parse", "--verify", ref], repo, check=False)
    return result.returncode == 0


def git_status_porcelain(workspace: Path) -> list[str]:
    """Return git status --porcelain lines for *workspace*."""
    result = run_git(["status", "--porcelain"], workspace, check=False)
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def is_git_dirty(workspace: Path) -> bool:
    """Return True if *workspace* has uncommitted changes."""
    return bool(git_status_porcelain(workspace))


def git_commit_workspace(workspace: Path, message: str) -> str | None:
    """Commit all changes in *workspace* with *message*.

    Returns the commit SHA if a commit was created, None if nothing to commit.
    """
    if not is_git_dirty(workspace):
        return None
    run_git(["add", "-A"], workspace, check=True)
    run_git(["commit", "-m", message], workspace, check=True)
    result = run_git(["rev-parse", "HEAD"], workspace, check=True)
    return result.stdout.strip()


def git_push_checkpoint(workspace: Path, target: str, remote_branch: str) -> None:
    """Push the workspace's current branch to *target*:*remote_branch*."""
    cmd = ["git", "push", target, f"HEAD:{remote_branch}"]
    result = subprocess.run(
        cmd,
        cwd=str(workspace),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning(
            "git push failed from %s to %s:%s: %s",
            workspace,
            target,
            remote_branch,
            result.stderr.strip(),
        )
    else:
        logger.info("Pushed checkpoint to %s:%s", target, remote_branch)


def remove_all_worktrees(port: int) -> None:
    """Remove every worktree registered against the project's bare repo.

    Branches and tags are retained — only the working directories under
    project_{port}/branches/ are removed, plus the bare repo's
    .git/worktrees/ registrations are pruned. Forensic recovery is
    still possible via git worktree add /tmp/inspect <branch> against
    the per-project bare repo.

    Best-effort: failures on individual worktrees are logged but do not
    abort the close operation, since by the time we get here the project
    is already being retired.
    """
    bare = project_parent_repo_dir(port)
    if not bare.exists():
        return

    list_proc = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(bare),
        capture_output=True,
        text=True,
    )
    if list_proc.returncode != 0:
        logger.warning(
            "project_close: could not list worktrees for port %d: %s",
            port,
            list_proc.stderr.strip(),
        )
        return

    worktree_paths: list[Path] = []
    for line in list_proc.stdout.splitlines():
        if line.startswith("worktree "):
            wt = Path(line[len("worktree ") :].strip())
            # Skip the bare repo's own listing (some git versions include it).
            if wt.resolve() == bare.resolve():
                continue
            worktree_paths.append(wt)

    for wt in worktree_paths:
        rm = subprocess.run(
            ["git", "worktree", "remove", "--force", str(wt)],
            cwd=str(bare),
            capture_output=True,
            text=True,
        )
        if rm.returncode != 0:
            logger.warning(
                "project_close: git worktree remove failed for %s: %s",
                wt,
                rm.stderr.strip(),
            )
        # If the directory still exists (force-remove couldn't clean it
        # because of permission issues, etc.), best-effort rmtree.
        if wt.exists():
            shutil.rmtree(wt, ignore_errors=True)

    # Prune any stale registrations left over from removed worktrees.
    prune = subprocess.run(
        ["git", "worktree", "prune"],
        cwd=str(bare),
        capture_output=True,
        text=True,
    )
    if prune.returncode != 0:
        logger.warning(
            "project_close: git worktree prune failed for port %d: %s",
            port,
            prune.stderr.strip(),
        )
