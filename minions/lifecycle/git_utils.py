"""Thin wrappers around ``git`` invocations.

Centralises ``subprocess.run(["git", ...])`` so lifecycle helpers can stop
repeating the same argv-build + rc-check + ProjectError-raising pattern.

Only behaviours shared by more than one caller live here. Call-site specific
logic (e.g. "nothing to commit" detection, commit-then-rev-parse) stays in the
caller.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from minions.errors import ProjectError


def run_git(
    argv: list[str],
    cwd: Path,
    *,
    check: bool = True,
    action: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``git <argv>`` in *cwd*.

    *action* labels the operation for error messages ("status", "commit",
    etc). When *check* is False the caller inspects ``returncode`` itself.
    """
    result = subprocess.run(
        ["git", *argv],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        label = action or (argv[0] if argv else "git")
        raise ProjectError(f"git {label} failed in {cwd}: {result.stderr.strip()}")
    return result


def is_git_work_tree(path: Path) -> bool:
    """Return True if *path* is itself the root of a git work tree.

    This is the *strict* check: ``path`` must equal the work-tree's
    ``--show-toplevel``. ``git rev-parse --is-inside-work-tree`` walks up
    the directory tree, so a plain subdirectory of an outer repo would
    answer ``true`` — which silently turns "the directory the user
    dropped MinionsOS into" into "whatever ancestor happens to be a git
    repo". Use :func:`is_inside_git_work_tree` if the loose semantic is
    what you want.
    """
    try:
        result = run_git(
            ["rev-parse", "--show-toplevel"],
            path,
            check=False,
        )
    except FileNotFoundError:
        return False
    if result.returncode != 0:
        return False
    toplevel = result.stdout.strip()
    if not toplevel:
        return False
    try:
        return Path(toplevel).resolve() == path.resolve()
    except OSError:
        return False


def is_inside_git_work_tree(path: Path) -> bool:
    """Return True if *path* is anywhere inside a git work tree.

    Loose check — answers true for subdirectories of an outer repo. Use
    :func:`is_git_work_tree` for the strict "is this the root?" check.
    """
    try:
        result = run_git(
            ["rev-parse", "--is-inside-work-tree"],
            path,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def find_enclosing_git_work_tree(path: Path) -> Path | None:
    """Return the toplevel of the work tree containing *path*, if any.

    Returns ``None`` when *path* is not inside any git work tree. Used to
    produce actionable error messages when the user drops MinionsOS into
    a non-git directory that happens to live inside a larger git repo.
    """
    try:
        result = run_git(
            ["rev-parse", "--show-toplevel"],
            path,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    toplevel = result.stdout.strip()
    if not toplevel:
        return None
    try:
        return Path(toplevel).resolve()
    except OSError:
        return None


def git_ref_exists(repo: Path, ref: str) -> bool:
    """Return True if *ref* resolves inside *repo*."""
    return (
        run_git(
            ["rev-parse", "--verify", "--quiet", ref],
            repo,
            check=False,
        ).returncode
        == 0
    )


def is_git_dirty(workspace: Path) -> bool:
    """Return True when *workspace* has uncommitted changes."""
    return bool(run_git(["status", "--porcelain"], workspace, action="status").stdout.strip())
