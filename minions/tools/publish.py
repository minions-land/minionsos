"""Cross-role publishing onto the project's shared surface (the main branch).

Provides ``mos_publish_to_shared``, the sanctioned way for a Role to land a
file on the project's shared surface — which, since the v23 rebuild, is the
**main branch** (``project_{port}/branches/main/``). The standalone
``-shared`` branch was eliminated; main IS the shared surface (the Book).
The tool:

1. Acquires a per-project ``flock`` on ``state/shared.lock`` so concurrent
   publishes from different Roles serialize cleanly onto the one main
   worktree.
2. Validates the destination subpath against the calling Role's allowed
   subdirs (e.g. Ethics may publish under ``ethics/``/``notes/``/``draft/``/
   ``book/``; Expert under ``exp/``; ``reviews/`` is reserved for
   ``mos_review_run``).
3. Copies the source file into the main worktree.
4. ``git add -- <relpath>`` + ``git commit`` on the main branch (path-scoped
   add, so concurrent publishers touching different files don't clobber).
5. Optionally ``git push`` if the project has ``github_push_target`` set.

The main worktree (and its Book layout) is seeded at ``project_create`` time
(``minions/lifecycle/_project_worktree.py:create_worktree``).

Draft flushes
==================

Ethics' periodic Draft flush (``mos_draft_commit_shared``) is implemented on
top of this tool: it publishes ``branches/main/draft/draft.json`` in-place.
The Draft file is buffered to disk by ``mos_draft_append`` between flushes
and only commits when Ethics' idle tick fires, keeping main-branch commit
churn bounded.
"""

from __future__ import annotations

import errno
import fcntl
import logging
import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import Field

from minions.errors import ProjectError
from minions.lifecycle.git_utils import is_git_work_tree, run_git
from minions.paths import (
    project_shared_branch_name,
    project_shared_lock,
    project_shared_workspace,
)
from minions.state.store import StateStore
from minions.tools._returns import DictLikeBaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed return shapes
# ---------------------------------------------------------------------------


class PublishToSharedResult(DictLikeBaseModel):
    """Result shape for ``mos_publish_to_shared``.

    Returned after a single-file publish on the shared branch. ``commit_sha``
    is ``None`` when the publish was a no-op (``src`` already matched the
    on-disk destination — no diff). ``pushed`` is ``True`` only when a
    GitHub push target is configured for the project AND the commit landed.
    """

    port: int = Field(description="Project port the publish was scoped to.")
    role: str = Field(description="Calling role (gru/ethics/expert/...).")
    dst_path: str = Field(description="Relative path under branches/shared/ that was written.")
    commit_sha: str | None = Field(
        default=None,
        description="SHA of the shared-branch commit, or None on a no-op publish.",
    )
    pushed: bool = Field(
        default=False,
        description="True if the commit was also pushed to the configured GitHub remote.",
    )
    push_branch: str | None = Field(
        default=None,
        description="Remote branch name written by the push, or None when not pushed.",
    )
    branch: str = Field(description="Shared-branch name (minionsos/project-{port}-shared).")


class PublishFilesToSharedResult(DictLikeBaseModel):
    """Result shape for ``mos_publish_files_to_shared`` (multi-file batched publish).

    The same lock + commit pipeline as :class:`PublishToSharedResult`, but lands
    multiple files in one commit so a logical Noter ingest doesn't fragment
    into N separate commits (see GitHub Issue #13). ``dst_paths`` is the list
    of relative paths committed; ``commit_sha`` covers the union diff.
    """

    port: int = Field(description="Project port the publish was scoped to.")
    role: str = Field(description="Calling role (gru/ethics/expert/...).")
    dst_paths: list[str] = Field(
        description="Relative paths under branches/shared/ written in this commit."
    )
    commit_sha: str | None = Field(
        default=None,
        description="SHA of the union commit, or None on a no-op publish.",
    )
    pushed: bool = Field(
        default=False,
        description="True if the commit was also pushed to the configured GitHub remote.",
    )
    push_branch: str | None = Field(
        default=None,
        description="Remote branch name written by the push, or None when not pushed.",
    )
    branch: str = Field(description="Shared-branch name (minionsos/project-{port}-shared).")


# ---------------------------------------------------------------------------
# Per-role allowed shared subdirs
# ---------------------------------------------------------------------------

# Default per-role policy (scientific-paper profile baseline).
# Can be overridden per-project by setting ``profile_deliverable_schema``
# in meta.json (loaded from the project's mission profile at create time).
#
# - "*" means any subdir is allowed (Gru only).
# - "reviews/" is intentionally absent everywhere — that surface is owned
#   exclusively by ``mos_review_run`` which writes commits directly without
#   going through this tool.
# - "book/" is owned exclusively by Noter (Book pattern: one curated page
#   per ingested artefact, Ethics-curated); other roles publish raw artefacts
#   to their own subdir + Ethics ingest-compiles them into book/.
_DEFAULT_ROLE_ALLOWED_SHARED_SUBDIRS: dict[str, set[str]] = {
    "gru": {"*"},
    # Ethics is the merged memory curator + auditor: it owns book/, notes/,
    # draft/, ethics/, handoffs/, governance/.
    "ethics": {"ethics", "notes", "draft", "handoffs", "governance", "book"},
    # Expert is the unified worker — it publishes experiment bundles plus
    # handoffs and governance.
    "expert": {"exp", "handoffs", "governance"},
}

# Backward-compat alias for callers that import the old name.
_ROLE_ALLOWED_SHARED_SUBDIRS = _DEFAULT_ROLE_ALLOWED_SHARED_SUBDIRS

# Reserved roots no role may publish into via this tool. ``mos_review_run``
# writes directly under ``reviews/`` while holding its own coordination.
_RESERVED_SUBDIR_ROOTS: frozenset[str] = frozenset({"reviews"})


def _profile_publish_whitelist(port: int) -> dict[str, set[str]] | None:
    """Read profile-defined publish whitelist from meta.json, if any.

    Returns None if no profile-aware whitelist is configured on the project,
    in which case callers fall back to ``_DEFAULT_ROLE_ALLOWED_SHARED_SUBDIRS``.
    """
    try:
        from minions.paths import project_meta_json

        meta_path = project_meta_json(port)
        if not meta_path.exists():
            return None
        import json as _json

        data = _json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        deliverable = data.get("profile_deliverable_schema")
        if not isinstance(deliverable, dict):
            return None
        whitelist = deliverable.get("publish_whitelist")
        if not isinstance(whitelist, dict):
            return None
        return {
            str(role): set(str(s) for s in subs)
            for role, subs in whitelist.items()
            if isinstance(subs, (list, set, tuple))
        }
    except Exception:
        return None


def _allowed_subdirs_for_role(role_name: str, port: int) -> set[str] | None:
    """Resolve allowed shared subdirs for *role_name* on *port*.

    Lookup order:
    1. Project's mission profile ``publish_whitelist`` (if defined).
    2. Default scientific-paper baseline.
    3. None (caller raises "no policy registered").
    """
    profile_wl = _profile_publish_whitelist(port)
    canonical = _normalise_role(role_name)
    if profile_wl is not None and canonical in profile_wl:
        return profile_wl[canonical]
    return _DEFAULT_ROLE_ALLOWED_SHARED_SUBDIRS.get(canonical)


def _normalise_role(role_name: str) -> str:
    """Collapse expert-shaped roles onto the shared 'expert' policy.

    Accepts ``expert``, ``expert-<slug>``, and ``<slug>-expert``.
    """
    if role_name == "expert" or role_name.startswith("expert-") or role_name.endswith("-expert"):
        return "expert"
    return role_name


def _validate_dst(role_name: str, dst_subpath: str, port: int | None = None) -> Path:
    """Return the cleaned relative shared subpath, or raise ProjectError.

    *port* is used to look up profile-defined publish whitelist overrides.
    When None, only the default whitelist is consulted (the original
    pre-profile behavior).
    """
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
    if port is None:
        # No port: use the default whitelist directly (original behavior).
        allowed = _DEFAULT_ROLE_ALLOWED_SHARED_SUBDIRS.get(_normalise_role(role_name))
    else:
        allowed = _allowed_subdirs_for_role(role_name, port)
    if allowed is None:
        raise ProjectError(f"Role {role_name!r} has no shared-publish policy registered.")
    if "*" not in allowed and root not in allowed:
        raise ProjectError(
            f"Role {role_name!r} may not publish under branches/shared/{root}/. "
            f"Allowed roots: {sorted(allowed)}."
        )
    return candidate


# Maximum wall-clock time _shared_lock waits before raising. Issue #37: an
# unbounded fcntl.flock(LOCK_EX) is the cascade vector — if one role wedges
# while holding the lock, every subsequent publisher (including the audit
# snapshot path triggered by mos_await_events) blocks indefinitely, freezing
# every role in the project. The env var lets ops dial it; the default of 60s
# is long enough for honest contention (large draft flush) but short enough
# that a wedged holder surfaces as a loud error instead of a silent hang.
_SHARED_LOCK_TIMEOUT_SEC = float(os.environ.get("MINIONS_SHARED_LOCK_TIMEOUT_SEC", "60"))
_SHARED_LOCK_POLL_INTERVAL_SEC = 0.1


@contextmanager
def _shared_lock(port: int, timeout_sec: float | None = None) -> Iterator[None]:
    """Acquire the per-project shared write lock with a bounded wait.

    Issue #37: never block indefinitely on a stale lock. A non-blocking
    LOCK_NB + retry loop trades a tiny bit of latency for a strict upper
    bound — if we can't acquire within ``timeout_sec`` we raise, letting
    the caller (mos_publish_to_shared, draft flush, signboard write, etc.)
    fail loudly instead of cascading every peer role into a wedge.
    """
    budget = _SHARED_LOCK_TIMEOUT_SEC if timeout_sec is None else float(timeout_sec)
    lock_path = project_shared_lock(port)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + budget
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                    raise
                if time.monotonic() >= deadline:
                    raise ProjectError(
                        f"shared.lock contended for >{budget:.0f}s on port {port}; "
                        "likely a wedged peer role. Check `mos doctor --port "
                        f"{port}` for stale heartbeats before retrying."
                    ) from exc
                time.sleep(_SHARED_LOCK_POLL_INTERVAL_SEC)
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
) -> PublishToSharedResult:
    """Atomically publish *src_path* into ``branches/shared/<dst_subpath>``.

    The tool serialises concurrent writers via a per-project flock,
    enforces per-role subdir policy, and commits each publish on the
    shared branch (``minionsos/project-{port}-shared``) with
    *commit_message*. Returns a :class:`PublishToSharedResult` with
    ``port``, ``role``, ``dst_path``, ``commit_sha``, ``pushed``,
    ``push_branch``, and ``branch``. The result is dict-like so callers
    using ``result["dst_path"]`` or ``result.get("commit_sha")`` keep
    working unchanged.

    A ``commit_sha`` of ``None`` means the publish was a no-op (the file
    on disk already matched and no diff was produced).
    """
    resolved_port = _resolve_port(port)
    rel_dst = _validate_dst(role, dst_subpath, resolved_port)

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

    return PublishToSharedResult(
        port=resolved_port,
        role=role,
        dst_path=str(rel_dst),
        commit_sha=commit_sha,
        pushed=pushed,
        push_branch=push_branch,
        branch=project_shared_branch_name(resolved_port),
    )


def mos_publish_files_to_shared(
    *,
    role: str,
    files: list[dict[str, str]],
    commit_message: str,
    port: int | None = None,
    store: StateStore | None = None,
) -> PublishFilesToSharedResult:
    """Atomically publish *multiple* files into ``branches/shared/`` in one commit.

    Each entry in ``files`` is ``{"src_path": str, "dst_subpath": str}``. All
    destinations are validated against *role*'s shared-publish policy, the
    per-project flock is acquired once, every file is copied + staged, then a
    single ``git commit`` lands the union diff. Optional push runs once at the
    end if configured.

    This avoids the ingest commit amplification (one logical Noter event
    landing as 3-10 separate commits — see GitHub Issue #13). Use the single
    :func:`mos_publish_to_shared` for one-file publishes.

    Returns a :class:`PublishFilesToSharedResult` (dict-like) with
    ``port``, ``role``, ``dst_paths``, ``commit_sha``, ``pushed``,
    ``push_branch``, and ``branch``.
    """
    resolved_port = _resolve_port(port)
    if not files:
        return PublishFilesToSharedResult(
            port=resolved_port,
            role=role,
            dst_paths=[],
            commit_sha=None,
            pushed=False,
            push_branch=None,
            branch=project_shared_branch_name(resolved_port),
        )

    validated: list[tuple[Path, Path]] = []
    for entry in files:
        src_raw = entry.get("src_path")
        dst_raw = entry.get("dst_subpath")
        if not isinstance(src_raw, str) or not isinstance(dst_raw, str):
            raise ProjectError(
                "mos_publish_files_to_shared: each entry needs str src_path + dst_subpath"
            )
        rel_dst = _validate_dst(role, dst_raw, resolved_port)
        src = Path(src_raw).expanduser()
        if not src.is_absolute():
            raise ProjectError(f"src_path must be absolute, got: {src_raw!r}")
        if not src.exists() or not src.is_file():
            raise ProjectError(f"src_path does not exist or is not a file: {src}")
        validated.append((src, rel_dst))

    workspace = project_shared_workspace(resolved_port)
    if not workspace.exists() or not is_git_work_tree(workspace):
        raise ProjectError(
            f"Shared worktree missing for port {resolved_port}: {workspace}. "
            "Was project_create run?"
        )

    _store = store or StateStore()
    rel_dst_strs = [str(rel_dst) for _, rel_dst in validated]

    with _shared_lock(resolved_port):
        for src, rel_dst in validated:
            dst_abs = workspace / rel_dst
            dst_abs.parent.mkdir(parents=True, exist_ok=True)
            if src.resolve() != dst_abs.resolve():
                shutil.copy2(src, dst_abs)

        run_git(["add", "--", *rel_dst_strs], workspace, action="add")
        diff_check = run_git(
            ["diff", "--cached", "--quiet", "--", *rel_dst_strs],
            workspace,
            check=False,
        )
        if diff_check.returncode == 0:
            logger.info(
                "publish_files_to_shared no-op: port=%d role=%s files=%d (no diff)",
                resolved_port,
                role,
                len(validated),
            )
            commit_sha = None
        else:
            commit_proc = subprocess.run(
                ["git", "commit", "-m", commit_message, "--", *rel_dst_strs],
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
        "publish_files_to_shared done: port=%d role=%s files=%d commit=%s pushed=%s",
        resolved_port,
        role,
        len(validated),
        commit_sha,
        pushed,
    )

    return PublishFilesToSharedResult(
        port=resolved_port,
        role=role,
        dst_paths=rel_dst_strs,
        commit_sha=commit_sha,
        pushed=pushed,
        push_branch=push_branch,
        branch=project_shared_branch_name(resolved_port),
    )


__all__ = [
    "PublishFilesToSharedResult",
    "PublishToSharedResult",
    "mos_publish_files_to_shared",
    "mos_publish_to_shared",
]
