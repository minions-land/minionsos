"""Per-project runtime issue tracker.

Roles drop a structured issue record here whenever they notice a
scaffolding-level problem during normal operation: a tool that keeps
failing, a SYSTEM.md instruction that contradicts observed behavior, a
referenced skill that does not exist, a tool-surface gap, an
environment misconfiguration. The intent is *issue filing*, not
remediation: the human pulls the project back to their workstation and
acts on the reports later.

Storage
=======

Each project owns ``project_{port}/issues/issues.jsonl`` —
append-only, gitignored, one JSON object per line. The schema mirrors
the standard GitHub / FB / Google bug-report template so a downstream
agent triaging the file does not need to parse free-form prose:

    {
      "id":         "ISS-<port>-<n>",
      "ts":         "<ISO-8601 UTC>",
      "reporter":   {"role": "...", "project_port": <int>, "phase": "..."},
      "title":      "<one-line summary>",
      "severity":   "P0" | "P1" | "P2" | "P3",
      "component":  "tool" | "prompt" | "boundary" | "skill" |
                    "mcp"  | "env"    | "workflow" | "other",
      "summary":    "<1-3 sentences>",
      "steps_to_reproduce": ["...", "..."],
      "expected":   "<what should have happened>",
      "actual":     "<what actually happened>",
      "evidence":   ["<path | commit SHA | EACN event id | log line>"],
      "impact":     "<what is blocked or degraded>",
      "workaround": null | "<description>"
    }

The reporter triplet is filled from the role process environment
(``MINIONS_ROLE_NAME``, ``MINIONS_PROJECT_PORT``, ``MINIONS_PROJECT_PHASE``)
so the caller cannot spoof identity.

There is intentionally no validation step beyond schema: filing is
free, no consensus, no EACN traffic. Noise gets digested by the
human-side triage workflow.

Archival
========

On ``project_close`` / ``project_dormant`` the lifecycle copies
``issues.jsonl`` to ``~/.minionsos/issues/{port}-{closed_ts}.jsonl``
so reports survive after the project tree is torn down.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from minions.errors import ProjectError
from minions.paths import (
    host_issues_archive_dir,
    project_issues_dir,
    project_issues_jsonl,
    project_issues_lock,
)

logger = logging.getLogger(__name__)


Severity = Literal["P0", "P1", "P2", "P3"]
Component = Literal[
    "tool",
    "prompt",
    "boundary",
    "skill",
    "mcp",
    "env",
    "workflow",
    "other",
]


class IssueReportArgs(BaseModel):
    """Caller-facing arguments accepted by ``mos_issue_report``."""

    title: str = Field(
        description=(
            "One-line summary in imperative mood "
            "(e.g. 'mos_scratchpad_append rejects valid edges')."
        ),
        min_length=1,
        max_length=200,
    )
    severity: Severity = Field(
        description=(
            "Triage urgency. P0=blocks all progress, P1=blocks this role, "
            "P2=workaround exists, P3=nuisance / polish."
        ),
    )
    component: Component = Field(
        description=(
            "Where the problem lives: 'tool' (MCP tool body), 'prompt' "
            "(SYSTEM.md / role contract), 'boundary' (whitelist or write "
            "scope), 'skill' (skill file), 'mcp' (server config / "
            "registration), 'env' (CLI / config / launcher), 'workflow' "
            "(cross-role coordination), 'other'."
        ),
    )
    summary: str = Field(
        description="1-3 sentences describing what is wrong.",
        min_length=1,
    )
    steps_to_reproduce: list[str] = Field(
        default_factory=list,
        description=(
            "Ordered list of steps. Empty list is acceptable when the issue "
            "is a one-shot observation rather than a reproducible bug."
        ),
    )
    expected: str = Field(
        default="",
        description="What should have happened. Leave empty when irrelevant.",
    )
    actual: str = Field(
        default="",
        description="What actually happened. Leave empty when same as summary.",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete pointers: file paths, commit SHAs, EACN event ids, "
            "log line ranges, tool call ids."
        ),
    )
    impact: str = Field(
        default="",
        description="What is blocked or degraded by this issue.",
    )
    workaround: str | None = Field(
        default=None,
        description="If a workaround exists, describe it. Otherwise null.",
    )

    @field_validator("steps_to_reproduce", "evidence", mode="before")
    @classmethod
    def _coerce_list(cls, v: object) -> object:
        if v is None:
            return []
        return v


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _resolve_port(explicit: int | None) -> int:
    if explicit is not None:
        return int(explicit)
    raw = os.environ.get("MINIONS_PROJECT_PORT", "").strip()
    if not raw:
        raise ProjectError(
            "mos_issue_report: project port must be set in MINIONS_PROJECT_PORT "
            "(auto-set in role processes) or passed explicitly."
        )
    try:
        return int(raw)
    except ValueError as exc:
        raise ProjectError(f"MINIONS_PROJECT_PORT is not a valid int: {raw!r}") from exc


def _reporter_from_env(port: int) -> dict[str, object]:
    role = os.environ.get("MINIONS_ROLE_NAME", "").strip() or "unknown"
    phase = os.environ.get("MINIONS_PROJECT_PHASE", "").strip() or None
    return {"role": role, "project_port": port, "phase": phase}


@contextmanager
def _issues_lock(port: int) -> Iterator[None]:
    """Hold an exclusive flock so concurrent appends serialise cleanly."""
    lock_path = project_issues_lock(port)
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


def _next_issue_id(port: int, jsonl_path: Path) -> str:
    """Return the next ``ISS-<port>-<n>`` id by counting prior lines.

    Counting is cheap because the JSONL file is small (one line per
    issue) and lifecycle archival keeps it bounded per-project.
    """
    if not jsonl_path.exists():
        return f"ISS-{port}-1"
    n = 0
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return f"ISS-{port}-{n + 1}"


def report_issue(
    args: IssueReportArgs,
    *,
    port: int | None = None,
) -> dict[str, object]:
    """Append one issue record to the project-local issues.jsonl.

    Side effects: creates ``project_{port}/issues/`` if missing, takes
    the per-project issues flock, appends one JSON object as a single
    line. Returns the persisted record so the caller can confirm what
    landed (and what id it received).

    Identity comes from the role process environment — the caller does
    not pass role / phase in. This matches how
    ``mos_publish_to_shared`` resolves identity and prevents a role
    from filing under another role's name.
    """
    resolved_port = _resolve_port(port)
    issues_dir = project_issues_dir(resolved_port)
    issues_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = project_issues_jsonl(resolved_port)

    with _issues_lock(resolved_port):
        record: dict[str, object] = {
            "id": _next_issue_id(resolved_port, jsonl_path),
            "ts": _now_iso(),
            "reporter": _reporter_from_env(resolved_port),
            "title": args.title,
            "severity": args.severity,
            "component": args.component,
            "summary": args.summary,
            "steps_to_reproduce": list(args.steps_to_reproduce),
            "expected": args.expected,
            "actual": args.actual,
            "evidence": list(args.evidence),
            "impact": args.impact,
            "workaround": args.workaround,
        }
        line = json.dumps(record, ensure_ascii=False)
        with jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    logger.info(
        "mos_issue_report appended: port=%d id=%s severity=%s component=%s reporter=%s",
        resolved_port,
        record["id"],
        record["severity"],
        record["component"],
        record["reporter"],
    )
    return record


def list_issues(port: int, limit: int | None = None) -> list[dict[str, object]]:
    """Read the project's issues.jsonl in chronological (file) order.

    Returns ``[]`` when no file exists. ``limit`` truncates from the
    head; use :func:`tail_issues` for the most recent N. Skips
    malformed lines with a warning rather than aborting.
    """
    jsonl_path = project_issues_jsonl(port)
    if not jsonl_path.exists():
        return []
    out: list[dict[str, object]] = []
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("issues.jsonl: skipping malformed line: %s", exc)
                continue
            if isinstance(obj, dict):
                out.append(obj)
            if limit is not None and len(out) >= limit:
                break
    return out


def tail_issues(port: int, n: int = 10) -> list[dict[str, object]]:
    """Return the most recent *n* issues for *port*."""
    if n <= 0:
        return []
    all_issues = list_issues(port)
    return all_issues[-n:]


def archive_issues(port: int, *, closed_ts: str | None = None) -> Path | None:
    """Copy ``project_{port}/issues/issues.jsonl`` to the host archive.

    Called by ``project_close`` and ``project_dormant``. Best-effort:
    returns the destination path on success, ``None`` when there is
    nothing to archive, and logs (not raises) on copy failure so a
    transient FS error does not block project teardown.

    Destination shape: ``~/.minionsos/issues/{port}-{ts}.jsonl``. The
    timestamp is the lifecycle event time (close / dormant), not the
    last-issue time, so multiple archives from the same port stay
    distinct.
    """
    src = project_issues_jsonl(port)
    if not src.exists() or src.stat().st_size == 0:
        return None
    ts = (closed_ts or _now_iso()).replace(":", "-").replace(".", "-")
    dst_dir = host_issues_archive_dir()
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("issues archive: cannot create %s: %s", dst_dir, exc)
        return None
    dst = dst_dir / f"{port}-{ts}.jsonl"
    try:
        shutil.copy2(src, dst)
    except OSError as exc:
        logger.warning(
            "issues archive: copy failed src=%s dst=%s: %s",
            src,
            dst,
            exc,
        )
        return None
    logger.info("issues archive: port=%d -> %s", port, dst)
    return dst


__all__ = [
    "Component",
    "IssueReportArgs",
    "Severity",
    "archive_issues",
    "list_issues",
    "report_issue",
    "tail_issues",
]
