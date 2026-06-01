"""Gru-only Book promotion: move Ethics-sealed content into the main Book.

``mos_promote_to_book`` is the v23 replacement for the old "publish a paper /
seal a claim onto the shared branch" flow. The model is:

1. A worker (Expert) produces an artifact on its own role branch and/or a
   Draft node.
2. **Ethics seals it** — annotates the Draft node (`support_status=verified`
   + `metadata.ratified_by=ethics`) or ratifies a Book page. Sealing is an
   audit act, not a move.
3. **Gru promotes it** — copies the sealed artifact into its canonical
   position in the main-branch Book layout (`logic/`, `src/`, `evidence/`,
   `proposal/`, or `Book.md`) and commits on the main branch.

Only Gru may call this (the control-plane "Gru moves things into main" rule).
The source must live inside the project tree; the destination must be a
Book-layout path. Commit happens on main under the project shared lock so it
serializes with Draft flushes and other main-branch writes.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from minions.errors import ProjectError
from minions.paths import project_dir, project_main_workspace
from minions.tools._returns import DictLikeBaseModel

logger = logging.getLogger(__name__)

# Canonical Book-layout roots a promotion may target on the main branch.
_BOOK_LAYOUT_ROOTS: frozenset[str] = frozenset({"logic", "src", "evidence", "proposal", "book"})
# Single-file Book targets (not under a layout root).
_BOOK_LAYOUT_FILES: frozenset[str] = frozenset({"Book.md"})
# SECTION-BELOW


class PromoteToBookArgs(BaseModel):
    port: int = Field(description="Project port.")
    src_path: str = Field(
        description=(
            "Path to the Ethics-sealed source file. Absolute (must live under "
            "project_{port}/) or relative to the project dir."
        )
    )
    dst_subpath: str = Field(
        description=(
            "Destination under the main Book layout, e.g. "
            "'logic/claims.md', 'evidence/tables/table1.md', 'src/configs/x.md', "
            "'proposal/topic.md', or 'Book.md'."
        )
    )
    commit_message: str | None = Field(
        default=None,
        description="Commit message (defaults to 'gru: promote <dst> to Book').",
    )
    mode: Literal["replace", "append"] = Field(
        default="replace",
        description=(
            "'replace' overwrites the destination file; 'append' concatenates "
            "the source onto an existing destination (e.g. adding one claim to "
            "logic/claims.md)."
        ),
    )


class PromoteToBookResult(DictLikeBaseModel):
    port: int = Field(description="Project port.")
    dst_path: str = Field(description="Book-relative destination path.")
    commit_sha: str | None = Field(
        default=None, description="Main-branch commit SHA, or None if no diff."
    )


def _validate_book_dst(dst_subpath: str) -> Path:
    """Return the cleaned Book-layout relative path, or raise ProjectError."""
    if not dst_subpath or dst_subpath.startswith("/"):
        raise ProjectError(
            f"dst_subpath must be a relative path under the main Book, got: {dst_subpath!r}"
        )
    candidate = Path(dst_subpath)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        raise ProjectError(f"dst_subpath may not escape the Book layout: {dst_subpath!r}")
    parts = candidate.parts
    if not parts:
        raise ProjectError("dst_subpath cannot be empty")
    root = parts[0]
    if root not in _BOOK_LAYOUT_ROOTS and dst_subpath not in _BOOK_LAYOUT_FILES:
        raise ProjectError(
            f"Promotion target must be a Book-layout position "
            f"({sorted(_BOOK_LAYOUT_ROOTS)} or {sorted(_BOOK_LAYOUT_FILES)}); "
            f"got root {root!r}."
        )
    return candidate


def mos_promote_to_book(args: PromoteToBookArgs) -> PromoteToBookResult:
    """Promote an Ethics-sealed artifact into the main-branch Book (Gru-only).

    Copies (or appends) ``src_path`` into ``dst_subpath`` under
    ``branches/main/`` and commits on the main branch under the project shared
    lock. Server-side authz restricts this to Gru.
    """
    from minions.lifecycle.git_utils import run_git
    from minions.state.store import StateStore
    from minions.tools.publish import _push_if_configured, _shared_lock  # reuse infra

    port = args.port
    rel_dst = _validate_book_dst(args.dst_subpath)

    # Resolve + bound the source to the project tree.
    src = Path(args.src_path)
    if not src.is_absolute():
        src = project_dir(port) / src
    src = src.resolve()
    proot = project_dir(port).resolve()
    try:
        src.relative_to(proot)
    except ValueError as exc:
        raise ProjectError(f"src_path must live under project_{port}/, got {src}") from exc
    if not src.is_file():
        raise ProjectError(f"Promotion source not found: {src}")

    workspace = project_main_workspace(port)
    dst_abs = (workspace / rel_dst).resolve()
    try:
        dst_abs.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ProjectError(f"Resolved destination escaped main worktree: {dst_abs}") from exc

    with _shared_lock(port):
        dst_abs.parent.mkdir(parents=True, exist_ok=True)
        if args.mode == "append" and dst_abs.exists():
            existing = dst_abs.read_text(encoding="utf-8")
            addition = src.read_text(encoding="utf-8")
            sep = "" if existing.endswith("\n") else "\n"
            dst_abs.write_text(f"{existing}{sep}{addition}", encoding="utf-8")
        else:
            shutil.copyfile(src, dst_abs)

        rel_str = str(rel_dst)
        run_git(["add", "--", rel_str], workspace, action="add")
        diff = run_git(["diff", "--cached", "--quiet"], workspace, check=False)
        commit_sha: str | None = None
        if diff.returncode != 0:  # staged changes exist
            msg = args.commit_message or f"gru: promote {rel_str} to Book"
            run_git(["commit", "-m", msg], workspace, action="commit")
            head = run_git(["rev-parse", "HEAD"], workspace, action="rev-parse")
            commit_sha = head.stdout.strip()
            try:
                _push_if_configured(workspace, port, StateStore())
            except Exception as exc:  # push is best-effort
                logger.warning("mos_promote_to_book: push failed (non-fatal): %s", exc)

    logger.info("mos_promote_to_book: port=%d dst=%s commit=%s", port, rel_str, commit_sha)
    return PromoteToBookResult(port=port, dst_path=rel_str, commit_sha=commit_sha)


__all__ = [
    "PromoteToBookArgs",
    "PromoteToBookResult",
    "mos_promote_to_book",
]
