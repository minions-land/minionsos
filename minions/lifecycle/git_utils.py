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
    """Return True if *path* is inside a git work tree."""
    try:
        result = run_git(
            ["rev-parse", "--is-inside-work-tree"],
            path,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


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
