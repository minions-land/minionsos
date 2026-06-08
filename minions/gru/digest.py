"""Gru periodic digest — health/Draft-growth/EACN-flow snapshot.

Runs every ``gru_digest_interval_seconds`` (default 270 s = 4 min 30 s).
For each active project, summarizes:

- Per-role: event counts in the recent window, Draft node growth in
  the same window, ratio (Draft writes per real event).
- Aggregate: queue depth, per-role staleness, anomalies.

Persists the digest as a markdown file under
``branches/main/governance/gru-digest/<iso>.md`` (so historical digests
are git-tracked alongside other governance artifacts) and emits health
events for genuine anomalies (e.g. a role received ≥3 events in the
window but produced zero Draft nodes — the symptom this whole pipeline
is designed to catch).

Why not in-thread with the wedge watchdog: the wedge watchdog is a
hard-kill safety net keyed on the role pane log; the digest is a
softer reporting layer keyed on Draft / EACN data. Mixing them confuses
both responsibilities and the cadences differ — wedge runs every 5 min
because the kill is consequential; digest runs slightly faster (4m30s)
to align with cache-keepalive cadence so digests land between
keepalives and don't perturb cached prompt prefixes.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from minions.paths import (
    project_events_dir,
    project_shared_subdir,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoleDigestRow:
    role: str
    real_events: int
    keepalive_events: int
    draft_growth: int
    ratio: float | None  # draft_growth / real_events (None if real_events == 0)


@dataclass(frozen=True)
class ProjectDigest:
    port: int
    window_start_iso: str
    window_end_iso: str
    rows: list[RoleDigestRow]
    anomalies: list[str]


# ---------------------------------------------------------------------------
# Pure data collection — easy to unit-test
# ---------------------------------------------------------------------------


def _count_events_in_window(events_path: Path, window_start: datetime) -> tuple[int, int]:
    """Return (real_events, keepalive_events) appended at >= window_start.

    Reads the per-agent JSONL and parses ``ingested_at``. Lines that fail
    to parse or have no usable timestamp are skipped silently.
    """
    if not events_path.is_file():
        return 0, 0
    real = keep = 0
    try:
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_raw = rec.get("ingested_at", "")
            if not ts_raw:
                continue
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts < window_start:
                continue
            etype = (rec.get("event") or {}).get("type", "")
            if etype == "cache_keepalive":
                keep += 1
            else:
                real += 1
    except OSError as exc:
        logger.debug("digest: failed to read events log %s: %s", events_path, exc)
    return real, keep


def _count_draft_growth(draft_path: Path, window_start: datetime) -> dict[str, int]:
    """Return per-role count of Draft nodes whose created_at >= window_start."""
    if not draft_path.is_file():
        return {}
    try:
        d = json.loads(draft_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("digest: failed to read draft %s: %s", draft_path, exc)
        return {}
    counter: Counter[str] = Counter()
    for node in d.get("nodes", []):
        ts_raw = node.get("created_at", "")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts < window_start:
            continue
        author = node.get("author_role") or "?"
        counter[author] += 1
    return dict(counter)


def collect_project_digest(
    port: int,
    role_names: list[str],
    *,
    window_seconds: int,
    now: datetime | None = None,
    anomaly_min_events: int = 3,
) -> ProjectDigest:
    """Build a digest snapshot for *port* covering the last *window_seconds*.

    Pure: depends only on disk state under ``project_<port>/``. Does not
    write anywhere. Callers compose the digest with publishing + issue
    reporting.
    """
    end = now or datetime.now(tz=UTC)
    start = end - timedelta(seconds=window_seconds)

    events_dir = project_events_dir(port)
    draft_path = project_shared_subdir(port, "draft") / "draft.json"
    draft_growth = _count_draft_growth(draft_path, start)

    rows: list[RoleDigestRow] = []
    anomalies: list[str] = []
    for role in role_names:
        evt_path = events_dir / f"{role}.jsonl"
        real, keep = _count_events_in_window(evt_path, start)
        grew = int(draft_growth.get(role, 0))
        ratio = (grew / real) if real > 0 else None
        rows.append(
            RoleDigestRow(
                role=role,
                real_events=real,
                keepalive_events=keep,
                draft_growth=grew,
                ratio=ratio,
            )
        )
        if real >= anomaly_min_events and grew == 0:
            anomalies.append(
                f"role={role!r}: received {real} real events but wrote 0 Draft "
                f"nodes in the last {window_seconds}s window"
            )

    return ProjectDigest(
        port=port,
        window_start_iso=start.isoformat(timespec="seconds"),
        window_end_iso=end.isoformat(timespec="seconds"),
        rows=rows,
        anomalies=anomalies,
    )


def render_digest_markdown(digest: ProjectDigest) -> str:
    """Render a project digest as a compact markdown report."""
    lines: list[str] = []
    lines.append(f"# Gru digest — port {digest.port}")
    lines.append("")
    lines.append(f"- window: `{digest.window_start_iso}` → `{digest.window_end_iso}`")
    lines.append(f"- roles surveyed: {len(digest.rows)}")
    lines.append(f"- anomalies: {len(digest.anomalies)}")
    lines.append("")
    lines.append("## Per-role activity")
    lines.append("")
    lines.append("| role | real events | keepalive | Draft nodes | ratio |")
    lines.append("|---|---:|---:|---:|---:|")
    for row in digest.rows:
        ratio_s = f"{row.ratio:.2f}" if row.ratio is not None else "—"
        lines.append(
            f"| {row.role} | {row.real_events} | {row.keepalive_events} "
            f"| {row.draft_growth} | {ratio_s} |"
        )
    if digest.anomalies:
        lines.append("")
        lines.append("## Anomalies")
        lines.append("")
        for a in digest.anomalies:
            lines.append(f"- {a}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Side-effecting publish + issue-report (called from gru/loop.py)
# ---------------------------------------------------------------------------


def publish_digest(
    digest: ProjectDigest,
    *,
    notify_anomalies: bool = True,
) -> dict[str, Any]:
    """Persist *digest* to ``branches/main/governance/gru-digest/`` and
    optionally emit health events for any anomalies.

    Returns a small status dict: ``{"path": str, "anomalies": int}``.

    Failures are logged and swallowed — the digest is observability, and
    its absence must never break the surrounding monitor tick.
    """
    text = render_digest_markdown(digest)
    out_dir = project_shared_subdir(digest.port, "governance") / "gru-digest"
    safe_iso = digest.window_end_iso.replace(":", "-")
    out_path = out_dir / f"{safe_iso}.md"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        logger.warning("digest: failed to write %s: %s", out_path, exc)
        return {"path": "", "anomalies": len(digest.anomalies)}

    if notify_anomalies and digest.anomalies:
        _emit_anomaly_health_events(digest)

    return {"path": str(out_path), "anomalies": len(digest.anomalies)}


def _emit_anomaly_health_events(digest: ProjectDigest) -> None:
    """Append a health event per anomaly so they show up in `mos status`.

    We use the existing health-event channel (same one the wedge watchdog
    writes to) rather than `mos_issue_report` directly: the digest fires
    every 4m30s and would otherwise spam the issues feed on a quiet
    project where the same anomaly persists across many ticks. Health
    events are append-only and naturally deduplicate-via-time.
    """
    try:
        from minions.lifecycle.health import append_health_event
    except Exception as exc:
        logger.debug("digest: health event import failed: %s", exc)
        return
    for msg in digest.anomalies:
        try:
            append_health_event(
                port=digest.port,
                kind="draft_lag",
                severity="warning",
                message=msg,
                metadata={"window_end": digest.window_end_iso},
            )
        except Exception as exc:
            logger.debug("digest: append_health_event failed: %s", exc)
