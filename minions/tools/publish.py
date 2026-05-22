"""Cross-role shared-worktree publishing tool.

Provides ``mos_publish_to_shared``, the only sanctioned way for a Role to
land a file under ``project_{port}/branches/shared/``. The tool:

1. Acquires a per-project ``flock`` on ``state/shared.lock`` so concurrent
   publishes from different Roles serialize cleanly.
2. Validates the destination subpath against the calling Role's allowed
   shared subdirs (e.g. only Noter may publish under ``notes/`` or
   ``draft/``; only Ethics may publish under ``ethics/``;
   ``reviews/`` is reserved for ``mos_review_run`` and rejected here).
3. Copies the source file into the shared worktree.
4. ``git add`` + ``git commit`` on the shared branch with the supplied
   message.
5. Optionally ``git push`` if the project has ``github_push_target``
   configured.

The shared worktree itself is created at ``project_create`` time
(``minions/lifecycle/project.py:_create_shared_worktree``).

Draft flushes
==================

Noter's periodic Draft flush (``mos_draft_commit_shared``) is
implemented on top of this tool: it publishes
``branches/shared/draft/draft.json`` in-place under itself. The
Draft file is buffered to disk by ``mos_draft_append`` between
flushes and only commits when Noter's cron ticks, keeping shared-branch
commit churn bounded.
"""

from __future__ import annotations

import fcntl
import logging
import os
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from minions.errors import ProjectError
from minions.lifecycle.git_utils import is_git_work_tree, run_git
from minions.paths import (
    project_shared_branch_name,
    project_shared_lock,
    project_shared_workspace,
)
from minions.state.store import StateStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-role allowed shared subdirs
# ---------------------------------------------------------------------------

# Tier 1: subdirs each role may publish into.
# - "*" means any subdir is allowed (Gru only).
# - "reviews/" is intentionally absent everywhere — that surface is owned
#   exclusively by ``mos_review_run`` which writes commits directly without
#   going through this tool.
# - "book/" is owned exclusively by Noter (Book pattern: one curated page
#   per ingested artefact, Noter-compiled); other roles publish raw artefacts
#   to their own subdir + Noter ingest-compiles them into book/.
_ROLE_ALLOWED_SHARED_SUBDIRS: dict[str, set[str]] = {
    "gru": {"*"},
    # Book ownership invariant: Noter is the only non-Gru role that may publish book/.
    "noter": {"notes", "draft", "handoffs", "book"},
    "ethics": {"ethics", "handoffs", "governance"},
    "writer": {"handoffs", "governance"},
    "coder": {"exp", "handoffs", "governance"},
    "expert": {"handoffs", "governance"},
}

# Reserved roots no role may publish into via this tool. ``mos_review_run``
# writes directly under ``reviews/`` while holding its own coordination.
_RESERVED_SUBDIR_ROOTS: frozenset[str] = frozenset({"reviews"})


def _normalise_role(role_name: str) -> str:
    """Collapse expert-* roles onto the shared 'expert' policy."""
    if role_name.startswith("expert-") or role_name == "expert":
        return "expert"
    return role_name


def _validate_dst(role_name: str, dst_subpath: str) -> Path:
    """Return the cleaned relative shared subpath, or raise ProjectError."""
    if not dst_subpath or dst_subpath.startswith("/"):
        raise ProjectError(
            f"dst_subpath must be a relative path under branches/shared/, got: {dst_subpath!r}"
        )
    candidate = Path(dst_subpath)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        raise ProjectError(
            f"dst_subpath may not escape branches/shared/ "
            f"(no .. or absolute paths): {dst_subpath!r}"
        )
    if not candidate.parts:
        raise ProjectError("dst_subpath cannot be empty")
    root = candidate.parts[0]
    if root in _RESERVED_SUBDIR_ROOTS:
        raise ProjectError(
            f"branches/shared/{root}/ is reserved for mos_review_run; "
            "publish through that surface instead."
        )
    allowed = _ROLE_ALLOWED_SHARED_SUBDIRS.get(_normalise_role(role_name))
    if allowed is None:
        raise ProjectError(f"Role {role_name!r} has no shared-publish policy registered.")
    if "*" not in allowed and root not in allowed:
        raise ProjectError(
            f"Role {role_name!r} may not publish under branches/shared/{root}/. "
            f"Allowed roots: {sorted(allowed)}."
        )
    return candidate


@contextmanager
def _shared_lock(port: int) -> Iterator[None]:
    """Block until this process holds the per-project shared write lock."""
    lock_path = project_shared_lock(port)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _resolve_port(explicit: int | None) -> int:
    """Resolve the project port from an explicit arg or MINIONS_PROJECT_PORT."""
    if explicit is not None:
        return int(explicit)
    raw = os.environ.get("MINIONS_PROJECT_PORT", "").strip()
    if not raw:
        raise ProjectError(
            "mos_publish_to_shared: project port must be passed explicitly or "
            "set in MINIONS_PROJECT_PORT (auto-set in role processes)."
        )
    try:
        return int(raw)
    except ValueError as exc:
        raise ProjectError(f"MINIONS_PROJECT_PORT is not a valid int: {raw!r}") from exc


def _push_if_configured(workspace: Path, port: int, store: StateStore) -> str | None:
    """Push the shared HEAD if a GitHub push target is configured."""
    entry = store.get_project(port)
    if entry is None:
        return None
    push_target = getattr(entry, "github_push_target", None)
    if not push_target:
        return None
    push_branch_prefix = (getattr(entry, "github_push_branch_prefix", None) or "minionsos").strip(
        "/"
    ) or "minionsos"
    remote_branch = f"{push_branch_prefix}/p{port}/shared"
    result = run_git(
        ["push", str(push_target), f"HEAD:{remote_branch}"],
        workspace,
        check=False,
    )
    if result.returncode != 0:
        raise ProjectError(f"git push for shared on port {port} failed: {result.stderr.strip()}")
    return remote_branch


def mos_publish_to_shared(
    *,
    role: str,
    src_path: str,
    dst_subpath: str,
    commit_message: str,
    port: int | None = None,
    store: StateStore | None = None,
) -> dict[str, object]:
    """Atomically publish *src_path* into ``branches/shared/<dst_subpath>``.

    The tool serialises concurrent writers via a per-project flock,
    enforces per-role subdir policy, and commits each publish on the
    shared branch (``minionsos/project-{port}-shared``) with
    *commit_message*. Returns a small status dict:

    ``{"port": int, "role": str, "dst_path": str, "commit_sha": str | None,
       "pushed": bool, "push_branch": str | None, "branch": str}``

    A ``commit_sha`` of ``None`` means the publish was a no-op (the file
    on disk already matched and no diff was produced).
    """
    resolved_port = _resolve_port(port)
    rel_dst = _validate_dst(role, dst_subpath)

    src = Path(src_path).expanduser()
    if not src.is_absolute():
        raise ProjectError(f"src_path must be absolute, got: {src_path!r}")
    if not src.exists() or not src.is_file():
        raise ProjectError(f"src_path does not exist or is not a file: {src}")

    workspace = project_shared_workspace(resolved_port)
    if not workspace.exists() or not is_git_work_tree(workspace):
        raise ProjectError(
            f"Shared worktree missing for port {resolved_port}: {workspace}. "
            "Was project_create run?"
        )

    dst_abs = workspace / rel_dst
    _store = store or StateStore()

    with _shared_lock(resolved_port):
        dst_abs.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dst_abs.resolve():
            shutil.copy2(src, dst_abs)
        # If src == dst (in-place publish, e.g. Draft flush), skip the copy
        # and let the git diff check below decide whether to commit.

        # Scope ``add`` and dirty-check to ``rel_dst`` — never to the whole
        # worktree. Other roles may have uncommitted changes in unrelated
        # paths (a Draft buffer file mid-flush, a partially-staged ethics
        # report) that this publish must not absorb into its commit.
        run_git(["add", "--", str(rel_dst)], workspace, action="add")
        diff_check = run_git(
            ["diff", "--cached", "--quiet", "--", str(rel_dst)],
            workspace,
            check=False,
        )
        if diff_check.returncode == 0:
            # No staged diff for this path → publish is a no-op.
            logger.info(
                "publish_to_shared no-op: port=%d role=%s dst=%s (no diff)",
                resolved_port,
                role,
                rel_dst,
            )
            commit_sha = None
        else:
            commit_proc = subprocess.run(
                ["git", "commit", "-m", commit_message, "--", str(rel_dst)],
                cwd=str(workspace),
                capture_output=True,
                text=True,
            )
            if commit_proc.returncode != 0:
                output = f"{commit_proc.stdout}\n{commit_proc.stderr}".lower()
                if "nothing to commit" in output:
                    commit_sha = None
                else:
                    raise ProjectError(
                        f"git commit failed in shared worktree for port {resolved_port}: "
                        f"{commit_proc.stderr.strip()}"
                    )
            else:
                head = run_git(["rev-parse", "HEAD"], workspace, action="rev-parse").stdout.strip()
                commit_sha = head or None

        push_branch = None
        pushed = False
        if commit_sha:
            push_branch = _push_if_configured(workspace, resolved_port, _store)
            pushed = push_branch is not None

    logger.info(
        "publish_to_shared done: port=%d role=%s dst=%s commit=%s pushed=%s",
        resolved_port,
        role,
        rel_dst,
        commit_sha,
        pushed,
    )

    # Nudge Noter to wake early so it ingests the new artifact promptly.
    try:
        from minions.tools.noter_wait import nudge_noter

        nudge_noter(resolved_port)
    except Exception:
        pass

    return {
        "port": resolved_port,
        "role": role,
        "dst_path": str(rel_dst),
        "commit_sha": commit_sha,
        "pushed": pushed,
        "push_branch": push_branch,
        "branch": project_shared_branch_name(resolved_port),
    }


__all__ = ["mos_publish_to_shared"]
