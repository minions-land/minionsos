"""mos_publish_to_shared."""

from __future__ import annotations

from minions.tools import publish as _publish
from minions.tools.mcp import mcp
from minions.tools.mcp._common import (
    PublishToSharedArgs,
    _enforce_caller_identity,
    _enforce_caller_project,
    _require_tool_allowed,
)


@mcp.tool()
def mos_publish_to_shared(args: PublishToSharedArgs) -> _publish.PublishToSharedResult:
    """Publish a file from the calling role's worktree into the shared tree.

    Behavior:

    1. Acquire a per-project flock on ``state/shared.lock`` to serialise
       concurrent writers.
    2. Validate ``dst_subpath`` against the calling role's policy. Each
       role may publish only into its own subdir(s):

       - Gru: any subdir
       - Noter: ``notes/``, ``draft/``, ``book/``, ``handoffs/``
       - Ethics: ``ethics/``, ``handoffs/``, ``governance/``
       - Coder: ``exp/``, ``handoffs/``, ``governance/``
       - Writer / Expert: ``handoffs/``, ``governance/``
       - ``reviews/`` is reserved for ``mos_review_run`` and rejected here.

    3. Copy ``src_path`` into ``branches/shared/<dst_subpath>``.
    4. ``git add -A`` + ``git commit -m <commit_message>`` on the shared
       branch.
    5. ``git push`` if ``github_push_target`` is configured.

    Returns ``{port, role, dst_path, commit_sha, pushed, push_branch,
    branch}``. ``commit_sha`` is ``None`` when the file already matched
    on disk (no-op publish).
    """
    _require_tool_allowed("mos_publish_to_shared")
    _enforce_caller_identity(args.role)
    _enforce_caller_project(args.port)
    return _publish.mos_publish_to_shared(
        role=args.role,
        src_path=args.src_path,
        dst_subpath=args.dst_subpath,
        commit_message=args.commit_message,
        port=args.port,
    )
