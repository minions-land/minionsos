"""Project paths and directory structure management.

Helper functions for resolving project directories, seeding git repos, and
managing workspace layout.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from minions.errors import ProjectError
from minions.lifecycle.git_utils import (
    find_enclosing_git_work_tree,
    is_git_work_tree,
    run_git,
)
from minions.paths import (
    MINIONS_ROOT,
    configured_author_repo,
    project_branch_name,
    project_parent_repo_dir,
    project_state_dir,
    project_workspace_root,
)

logger = logging.getLogger(__name__)

_LARGE_FILE_THRESHOLD_BYTES = 500 * 1024 * 1024  # 500 MB
_SEED_SKIP_DIR_NAMES: frozenset[str] = frozenset({".git", "MinionsOS", "minionsos"})


def author_repo() -> Path:
    """Return the author's source git repo used as the seed for new projects.

    Resolution order:
    1. MINIONS_AUTHOR_REPO env var or gru.yaml:author_repo.
    2. MINIONS_ROOT.parent if it is **itself** a git work-tree root —
       the directory the user placed MinionsOS inside.
    3. MINIONS_ROOT itself if it is a git work-tree root.

    The author repo is touched **only at project_create time** to read its
    HEAD; it is never branched into, written to, or pushed against. After
    seeding, project history lives entirely inside
    project_{port}/parent_repo.git/.

    The mental model: the user opens their repo B and drops
    MinionsOS underneath it (B/MinionsOS). MinionsOS only ever
    treats B as the seed source. If the user instead drops
    MinionsOS into a non-git directory that happens to live under
    *another* git repo A (layout A/B/MinionsOS where only A
    is initialized), we refuse rather than silently importing A's
    HEAD — that would pull in A's siblings of B which the user
    never intended to ship into the project. The check is enforced in
    ensure_author_repo_is_git_repo.
    """
    configured = configured_author_repo()
    if configured is not None:
        return configured
    if is_git_work_tree(MINIONS_ROOT.parent):
        return MINIONS_ROOT.parent
    if is_git_work_tree(MINIONS_ROOT):
        return MINIONS_ROOT
    return MINIONS_ROOT.parent


def ensure_author_repo_is_git_repo() -> Path:
    """Verify that the author seed repo is a git work tree, return its path.

    The seed needs to read a real HEAD off some git work tree. If neither the
    configured author_repo nor MINIONS_ROOT.parent is a git repo, bail with an
    actionable message rather than letting git rev-parse fail mid-create.

    Special case: if the candidate itself is not a work-tree *root* but is
    nested inside an outer git repo (e.g. A/.git exists, A/B does not, and
    MinionsOS is at A/B/MinionsOS), we refuse and tell the user. Silently
    seeding the outer repo would import sibling directories of B that the user
    never wanted in their project.
    """
    src = author_repo()
    if not is_git_work_tree(src):
        configured = configured_author_repo()
        enclosing = find_enclosing_git_work_tree(src) if src.exists() else None
        if enclosing is not None and enclosing != src.resolve():
            raise ProjectError(
                f"The author seed repo ({src}) is not its own git repository, "
                f"but it lives inside an outer git work tree ({enclosing}).\n"
                f"MinionsOS will not silently seed from the outer repo — that "
                f"would pull in everything under {enclosing} that is a "
                f"sibling of {src}, which you almost certainly do not want.\n"
                "Pick one fix:\n"
                f"  - If you meant to seed from {src}, run:\n"
                f"      cd {src} && git init && git add -A && git commit -m 'init'\n"
                f"  - If you meant to seed from {enclosing}, set explicitly:\n"
                f"      export MINIONS_AUTHOR_REPO={enclosing}\n"
                "    (or set author_repo in gru.yaml).\n"
            )
        config_hint = (
            "Check MINIONS_AUTHOR_REPO or gru.yaml:author_repo.\n"
            if configured is not None
            else "Set gru.yaml:author_repo if the source you want to seed from "
            "lives somewhere other than the directory containing MinionsOS.\n"
        )
        raise ProjectError(
            f"The author seed repo ({src}) is not a git repository. "
            "MinionsOS imports the author's HEAD into each per-project "
            "bare repo at project_create time, so the source must be "
            "git-initialized.\n"
            "Fix with:\n"
            f"    cd {src} && git init && git add -A && git commit -m 'init'\n"
            f"{config_hint}"
        )
    return src


def seed_postfilter_tree(staging: Path) -> None:
    """Drop entries that survived git archive but should not be seeded.

    - Any directory named MinionsOS / minionsos (avoid recursive seed).
    - Any regular file larger than 500 MB.

    .git is already excluded by git archive so we don't need to
    revisit it here.
    """
    for path in list(staging.rglob("*")):
        if not path.exists():
            continue  # may have been deleted by an earlier iteration
        try:
            if path.is_dir() and path.name in _SEED_SKIP_DIR_NAMES:
                shutil.rmtree(path, ignore_errors=True)
                continue
            if path.is_file():
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if size > _LARGE_FILE_THRESHOLD_BYTES:
                    logger.info(
                        "seed: skipping large file (%.1f MB): %s",
                        size / (1024 * 1024),
                        path.relative_to(staging),
                    )
                    path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("seed postfilter encountered %s on %s; continuing", exc, path)


def seed_per_project_repo(port: int) -> tuple[str, str]:
    """Create the per-project bare repo and seed an initial commit.

    Steps:
    1. git init --bare project_{port}/parent_repo.git.
    2. Build a temp work tree under state/.seed-staging-{port}/.
    3. Resolve the author's HEAD SHA (recorded in meta).
    4. git -C author_repo archive HEAD | tar -x into the staging tree
       (git archive already excludes .git/ and respects export-ignore
       attributes; we then post-filter to drop the embedded MinionsOS
       directory and any file > 500 MB).
    5. git init inside the staging tree, add+commit, then push the
       resulting commit into the bare repo as minionsos/project-{port}.

    Returns (seed_commit_sha, author_head_sha).
    """
    src = ensure_author_repo_is_git_repo()
    bare = project_parent_repo_dir(port)
    if bare.exists():
        raise ProjectError(
            f"Per-project bare repo already exists for port {port}: {bare}. "
            "project_create should not be called against an existing project tree."
        )

    bare.parent.mkdir(parents=True, exist_ok=True)
    init_bare = subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)],
        capture_output=True,
        text=True,
    )
    if init_bare.returncode != 0:
        raise ProjectError(f"git init --bare failed for port {port}: {init_bare.stderr.strip()}")

    head_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(src),
        capture_output=True,
        text=True,
    )
    if head_proc.returncode != 0:
        raise ProjectError(f"Could not read author HEAD from {src}: {head_proc.stderr.strip()}")
    author_sha = head_proc.stdout.strip()

    staging = project_state_dir(port) / f".seed-staging-{port}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    archive_proc = subprocess.Popen(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=str(src),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    untar_proc = subprocess.Popen(
        ["tar", "-x", "-C", str(staging)],
        stdin=archive_proc.stdout,
        stderr=subprocess.PIPE,
    )
    if archive_proc.stdout is not None:
        archive_proc.stdout.close()
    untar_err = untar_proc.communicate()[1]
    archive_err = archive_proc.communicate()[1]
    if archive_proc.returncode != 0 or untar_proc.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise ProjectError(
            f"git archive | tar failed when seeding port {port}: "
            f"archive={archive_err!r} tar={untar_err!r}"
        )

    seed_postfilter_tree(staging)

    init_proc = subprocess.run(
        ["git", "init", "-q", "-b", f"minionsos/project-{port}"],
        cwd=str(staging),
        capture_output=True,
        text=True,
    )
    if init_proc.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise ProjectError(
            f"git init in seed staging failed for port {port}: {init_proc.stderr.strip()}"
        )
    # Use a stable identity for the seed commit so projects on hosts without
    # global git config still seed cleanly.
    seed_env = {
        "GIT_AUTHOR_NAME": "MinionsOS",
        "GIT_AUTHOR_EMAIL": "minionsos@localhost",
        "GIT_COMMITTER_NAME": "MinionsOS",
        "GIT_COMMITTER_EMAIL": "minionsos@localhost",
        **os.environ,
    }
    add_proc = subprocess.run(
        ["git", "add", "-A"],
        cwd=str(staging),
        capture_output=True,
        text=True,
        env=seed_env,
    )
    if add_proc.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise ProjectError(
            f"git add in seed staging failed for port {port}: {add_proc.stderr.strip()}"
        )
    msg = f"seed: import author HEAD {author_sha[:12]} (port {port})"
    commit_proc = subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", msg],
        cwd=str(staging),
        capture_output=True,
        text=True,
        env=seed_env,
    )
    if commit_proc.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise ProjectError(
            f"git commit in seed staging failed for port {port}: {commit_proc.stderr.strip()}"
        )
    seed_sha_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(staging),
        capture_output=True,
        text=True,
    )
    seed_sha = seed_sha_proc.stdout.strip()
    push_branch = f"minionsos/project-{port}"
    push_proc = subprocess.run(
        ["git", "push", str(bare), f"HEAD:refs/heads/{push_branch}"],
        cwd=str(staging),
        capture_output=True,
        text=True,
        env=seed_env,
    )
    if push_proc.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise ProjectError(
            f"Could not push seed commit into per-project bare repo for port {port}: "
            f"{push_proc.stderr.strip()}"
        )
    # Set the bare repo's HEAD to the project's main branch so subsequent
    # git worktree add ... HEAD resolves cleanly.
    sym_proc = subprocess.run(
        ["git", "symbolic-ref", "HEAD", f"refs/heads/{push_branch}"],
        cwd=str(bare),
        capture_output=True,
        text=True,
    )
    if sym_proc.returncode != 0:
        logger.warning(
            "Could not set HEAD on per-project bare repo for port %d: %s",
            port,
            sym_proc.stderr.strip(),
        )
    shutil.rmtree(staging, ignore_errors=True)
    return seed_sha, author_sha


def git_tag(port: int, tag: str) -> None:
    """Create a git tag in the per-project bare repo."""
    result = run_git(["tag", tag], project_parent_repo_dir(port), check=False)
    if result.returncode != 0:
        logger.warning("git tag %s failed: %s", tag, result.stderr.strip())


def ensure_workspace_layout(port: int) -> None:
    """Create the non-worktree workspace containers for *port*.

    Does NOT create the main workspace dir — that is the main-branch git
    worktree, added by create_worktree (which refuses a pre-existing
    non-empty target). The shared surface lives on main and is seeded there.
    """
    from minions.paths import project_roles_workspace_dir, project_state_dir

    project_workspace_root(port).mkdir(parents=True, exist_ok=True)
    project_roles_workspace_dir(port).mkdir(parents=True, exist_ok=True)
    project_state_dir(port).mkdir(parents=True, exist_ok=True)


def migrate_legacy_memory_dirs(port: int) -> None:
    """Rename legacy memory directories from v11 naming to v12 naming.

    v11: branches/shared/scratchpad/ → v12: branches/shared/draft/
    v11: branches/shared/library/   → v12: branches/shared/book/

    Runs git mv inside the shared worktree so history is preserved.
    Idempotent: skips if old dir doesn't exist or new dir already exists.
    """
    from minions.paths import project_shared_workspace

    shared = project_shared_workspace(port)
    if not shared.exists():
        return
    migrations = [
        ("scratchpad", "draft"),
        ("library", "book"),
    ]
    for old_name, new_name in migrations:
        old_dir = shared / old_name
        new_dir = shared / new_name
        if old_dir.exists() and not new_dir.exists():
            try:
                result = subprocess.run(
                    ["git", "mv", old_name, new_name],
                    cwd=str(shared),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    subprocess.run(
                        ["git", "commit", "-m", f"migrate: {old_name} → {new_name} (v12 rename)"],
                        cwd=str(shared),
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    logger.info("migrated %s->%s port=%d", old_name, new_name, port)
                else:
                    old_dir.rename(new_dir)
                    logger.info("renamed %s->%s (non-git) port=%d", old_name, new_name, port)
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.warning(
                    "migration %s->%s failed port=%d: %s",
                    old_name,
                    new_name,
                    port,
                    exc,
                )
                if old_dir.exists() and not new_dir.exists():
                    old_dir.rename(new_dir)


_PROJECT_GITIGNORE = """\
# MinionsOS project workspace hygiene.
# Only structured subdirectories are tracked; stray files are ignored.
*
!.gitignore
!CLAUDE.md
!meta.json
!branches/
!branches/**

# Workflow / Task / Sonnet scratchpad — ephemeral run artefacts
# (run scripts, transcripts, session metadata) written by Role processes
# under their branch's .claude/. Skill symlinks at branches/*/.claude/skills/
# remain tracked because workflow_plugins.inject_skills_to_workspace
# recreates them on respawn. See common SYSTEM.md §10.1.
branches/*/.claude/scratchpad/
branches/*/.claude/scratchpad/**
"""


def write_project_gitignore(pdir: Path) -> None:
    """Write a restrictive .gitignore into the project directory."""
    gi = pdir / ".gitignore"
    if not gi.exists():
        gi.write_text(_PROJECT_GITIGNORE, encoding="utf-8")
