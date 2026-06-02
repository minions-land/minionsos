"""Context-pressure detection for MinionsOS Roles.

Reads the current Role's Claude Code session jsonl and computes a
``context_pressure`` signal based on recent ``cache_read_input_tokens``
per turn. Used by ``mos_await_events`` to advise the Role when its
accumulated conversation history has bloated past the threshold where
``mos_compact_context`` is the cheaper option.

Background (from issue #38 analysis 2026-05-27):

  - Floor cost per turn ≈ 46-50K tokens (SYSTEM.md + tool schema +
    skill listing + cold-start brief). This is the irreducible structural
    cost — every wake re-reads it.
  - Each turn beyond cold-start adds the previous turn's input + output
    to the cached prefix. By turn 200+ the prefix can reach 150K-200K.
  - Of that 100K+ history tail, ~75% is recoverable from Draft (L1) +
    Book (L2) + EACN ``since_iso`` increments. ~25% is in-flight plan
    state that needs a 5-10K compact summary to preserve.
  - ``mos_compact_context`` already wires that compression: pre-compact
    hook makes the summary pointer-shaped, post-compact hook extracts
    audit trail. The mechanism is sound — what's missing is the
    *trigger*: the Role currently only compacts on subjective "context
    feels large" which doesn't fire at the cost-optimal point.

Threshold rationale:

  These thresholds gate a compaction *advisory*, not a hard auto-compact.
  They are expressed in cache_read tokens-per-turn averaged over the
  recent window, which tracks the size of the accumulated prefix.

  Original calibration (issue #38) optimized pure cache COST: at
  $1.5/M cache_read, ~100K cr/turn was the break-even where a compact
  pays for itself. But cost-break-even is the wrong target on a 1M
  window — it fired "medium" at 77K cr/turn while a role was mid-task,
  proposing to discard a warm 1M-capable prefix to save cents.

  Revised default (2026-05-30): keep the full 1M window and only advise
  compaction once the transcript is genuinely large — MEDIUM (soft hint)
  at 150K cr/turn, HIGH ("compact now") at 200K. Operators tune via
  gru.yaml ``context_pressure_{high,medium}_tokens`` or the
  ``MINIONS_CTX_PRESSURE_{HIGH,MEDIUM}_TOKENS`` env vars (see
  ``_load_thresholds``). The 1M window is unchanged; this only moves the
  point at which the advisory fires.

Cooldown:

  ``mos_compact_context`` writes to ``branches/main/draft/journal.jsonl``
  with ``op: "compact"``. We refuse to fire a high-pressure annotation
  if the most recent compact event for this role is less than
  ``cooldown_seconds`` (default 300s) ago. This prevents oscillation
  while the post-compact prefix is still rebuilding.

Cost of the check itself:

  This module reads the **tail** of one jsonl file (~1-2 MB at the high
  end), parses ~10 lines, and exits. Its own cost is bounded (≤50ms
  wall-clock) and it does NOT load all turns. Its result is cached for
  ``CACHE_TTL_SECONDS`` (default 30s) to avoid re-reading on every
  ``mos_await_events`` return.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 30
# Context-pressure thresholds, in cache_read tokens-per-turn averaged over the
# recent window. These gate the compaction ADVISORY surfaced via
# mos_await_events — NOT a hard auto-compact.
#
# Calibration (revised 2026-05-30): the original 70K/100K defaults were tuned
# for pure cache-COST optimization (issue #38: "above ~100K cr/turn a compact
# pays for itself"). But on the 1M-context model that is far too eager — a role
# was observed self-assessing "medium" pressure at only 77K cr/turn while
# mid-task, i.e. proposing to throw away a warm 1M-capable prefix to save a few
# cents. The window is 1M; we want roles to USE it and only consider compaction
# once the transcript is genuinely large. New floor: do not even hint until
# ~150K, do not say "compact now" until ~200K. Operators can override via
# gru.yaml (context_pressure_*_tokens) or the MINIONS_CTX_PRESSURE_*_TOKENS env
# vars; the 1M window itself is preserved — this only moves the advisory point.
DEFAULT_THRESHOLD_HIGH = 200_000
DEFAULT_THRESHOLD_MEDIUM = 150_000
DEFAULT_WINDOW_TURNS = 10
DEFAULT_COOLDOWN_SECONDS = 300


def _load_thresholds() -> tuple[int, int]:
    """Resolve (high, medium) cr/turn thresholds: env > gru.yaml > defaults.

    Read lazily (not at import) so a Role process stays decoupled from
    gru.yaml availability — a malformed config never breaks the event
    loop, it just falls back to the built-in defaults. Env vars
    ``MINIONS_CTX_PRESSURE_HIGH_TOKENS`` / ``..._MEDIUM_TOKENS`` win so an
    operator can tune a single revive without editing gru.yaml.
    """
    high = DEFAULT_THRESHOLD_HIGH
    medium = DEFAULT_THRESHOLD_MEDIUM
    try:
        from minions.config import load_gru_config

        cfg = load_gru_config()
        high = int(getattr(cfg, "context_pressure_high_tokens", high) or high)
        medium = int(getattr(cfg, "context_pressure_medium_tokens", medium) or medium)
    except Exception as exc:
        logger.debug("context_pressure threshold config load failed; using defaults: %s", exc)
    for env_key, which in (
        ("MINIONS_CTX_PRESSURE_HIGH_TOKENS", "high"),
        ("MINIONS_CTX_PRESSURE_MEDIUM_TOKENS", "medium"),
    ):
        raw = os.environ.get(env_key, "").strip()
        if raw:
            try:
                val = int(raw)
                if which == "high":
                    high = val
                else:
                    medium = val
            except ValueError:
                logger.debug("context_pressure: ignoring non-int %s=%r", env_key, raw)
    # Guard against an inverted config (medium must be < high or the medium
    # band vanishes / inverts). If misconfigured, clamp medium below high.
    if medium >= high:
        medium = max(1, int(high * 0.75))
    return high, medium


# Per-process memo: (workspace_path, mtime) -> result
_memo: dict[str, tuple[float, dict[str, Any]]] = {}


@dataclass
class ContextPressure:
    """Result of a context-pressure probe."""

    level: str  # "low" / "medium" / "high"
    avg_cr_recent: int  # avg cache_read across recent window
    window_turns: int  # how many turns the avg covers
    threshold_high: int
    threshold_medium: int
    on_cooldown: bool  # True if recent compact suppressed escalation
    cooldown_remaining_s: int  # >0 if on cooldown
    session_path: str | None  # which jsonl was read (None if no session)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "avg_cr_recent": self.avg_cr_recent,
            "window_turns": self.window_turns,
            "threshold_high": self.threshold_high,
            "threshold_medium": self.threshold_medium,
            "on_cooldown": self.on_cooldown,
            "cooldown_remaining_s": self.cooldown_remaining_s,
        }


def _slug_for_workspace(workspace: Path) -> str:
    """Replicate Claude Code's slug encoding: non-alphanumeric -> '-'.

    e.g. /Users/mjm/MinionsOS -> -Users-mjm-MinionsOS
    """
    s = str(workspace.resolve())
    return "".join(c if c.isalnum() else "-" for c in s)


def _claude_projects_root() -> Path:
    home = Path(os.environ.get("HOME", os.path.expanduser("~")))
    return home / ".claude" / "projects"


def _find_active_session(workspace: Path) -> Path | None:
    """Find the most-recently-modified jsonl for this workspace.

    Returns None if the slug directory doesn't exist or has no jsonl
    files (cold start, before the first assistant turn writes one).
    """
    slug_dir = _claude_projects_root() / _slug_for_workspace(workspace)
    if not slug_dir.is_dir():
        return None
    jsonls = sorted(
        slug_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return jsonls[0] if jsonls else None


def _tail_assistant_turns(jsonl: Path, n: int) -> list[int]:
    """Return ``cache_read_input_tokens`` for the last ``n`` assistant turns.

    Reads the file linearly; for typical session sizes (≤2 MB) this is
    fast. For very large sessions we could mmap+seek, but the simple
    path is fine at the scales we care about.
    """
    cr_values: list[int] = []
    try:
        with jsonl.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "assistant":
                    continue
                usage = (rec.get("message") or {}).get("usage") or {}
                cr = int(usage.get("cache_read_input_tokens") or 0)
                cr_values.append(cr)
    except OSError as exc:
        logger.debug("context_pressure: failed to read %s: %s", jsonl, exc)
        return []
    return cr_values[-n:]


def _last_compact_at(workspace: Path) -> float | None:
    """Return UNIX timestamp of the most recent compact event for this role.

    Reads ``branches/main/draft/journal.jsonl`` looking for the last
    line with ``op == "compact"`` and ``role == <our role>``. Returns
    None if no such event found.

    Falls back to scanning the role's own branch journal location too,
    in case the role-local compact tool wrote there.
    """
    role = os.environ.get("MINIONS_ROLE_NAME", "")
    # Shared journal: <workspace>/../main/draft/journal.jsonl (v23: main=Book)
    # workspace is branches/<role>/, so parent is branches/, parent.parent is project root
    candidates: list[Path] = []
    if workspace.parent.name == "branches":
        candidates.append(workspace.parent / "main" / "draft" / "journal.jsonl")
    # Role-local fallback (older shape):
    candidates.append(workspace / "draft" / "journal.jsonl")

    last_ts: float | None = None
    for journal in candidates:
        if not journal.is_file():
            continue
        try:
            with journal.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("op") != "compact":
                        continue
                    if role and rec.get("role") != role:
                        continue
                    ts_str = rec.get("timestamp", "")
                    if not ts_str:
                        continue
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                    except ValueError:
                        continue
                    if last_ts is None or ts > last_ts:
                        last_ts = ts
        except OSError:
            continue
    return last_ts


def probe(
    workspace: Path | None = None,
    *,
    threshold_high: int | None = None,
    threshold_medium: int | None = None,
    window_turns: int = DEFAULT_WINDOW_TURNS,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    now: float | None = None,
) -> ContextPressure:
    """Probe the current Role's context pressure.

    ``workspace`` defaults to ``MINIONS_WORKSPACE``. ``now`` is
    injected for tests; defaults to ``time.time()``.

    ``threshold_high`` / ``threshold_medium`` default to ``None``, in
    which case they are resolved from gru.yaml + env via
    ``_load_thresholds`` (the configurable, operator/TUI-settable path).
    Pass explicit ints to override (tests do this).

    Returns a ``ContextPressure`` with ``level`` in {low, medium, high}.
    A ``high`` reading on cooldown returns ``level == "medium"`` so we
    surface a softer signal but don't oscillate.
    """
    if threshold_high is None or threshold_medium is None:
        cfg_high, cfg_medium = _load_thresholds()
        if threshold_high is None:
            threshold_high = cfg_high
        if threshold_medium is None:
            threshold_medium = cfg_medium
    if workspace is None:
        ws_env = os.environ.get("MINIONS_WORKSPACE", "")
        workspace = Path(ws_env) if ws_env else None
    if workspace is None:
        return ContextPressure(
            level="low",
            avg_cr_recent=0,
            window_turns=0,
            threshold_high=threshold_high,
            threshold_medium=threshold_medium,
            on_cooldown=False,
            cooldown_remaining_s=0,
            session_path=None,
        )

    now = now if now is not None else time.time()

    # Memoize per session-path-mtime to avoid re-parsing on tight loops.
    session = _find_active_session(workspace)
    if session is None:
        return ContextPressure(
            level="low",
            avg_cr_recent=0,
            window_turns=0,
            threshold_high=threshold_high,
            threshold_medium=threshold_medium,
            on_cooldown=False,
            cooldown_remaining_s=0,
            session_path=None,
        )
    try:
        mtime = session.stat().st_mtime
    except OSError:
        mtime = 0.0
    cache_key = f"{session}:{mtime}:{threshold_high}:{threshold_medium}:{window_turns}"
    cached = _memo.get(cache_key)
    if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
        d = cached[1]
        return ContextPressure(
            level=d["level"],
            avg_cr_recent=d["avg_cr_recent"],
            window_turns=d["window_turns"],
            threshold_high=threshold_high,
            threshold_medium=threshold_medium,
            on_cooldown=d["on_cooldown"],
            cooldown_remaining_s=d["cooldown_remaining_s"],
            session_path=str(session),
        )

    cr_values = _tail_assistant_turns(session, window_turns)
    if not cr_values:
        result = ContextPressure(
            level="low",
            avg_cr_recent=0,
            window_turns=0,
            threshold_high=threshold_high,
            threshold_medium=threshold_medium,
            on_cooldown=False,
            cooldown_remaining_s=0,
            session_path=str(session),
        )
        _memo[cache_key] = (now, result.to_dict())
        return result

    avg_cr = sum(cr_values) // len(cr_values)
    last_compact = _last_compact_at(workspace)
    cooldown_remaining = 0
    on_cooldown = False
    if last_compact is not None:
        elapsed = now - last_compact
        if elapsed < cooldown_seconds:
            on_cooldown = True
            cooldown_remaining = int(cooldown_seconds - elapsed)

    if avg_cr >= threshold_high:
        # Suppress hard "high" while cooldown is active — surface medium so the
        # role gets context but doesn't compact-loop.
        level = "medium" if on_cooldown else "high"
    elif avg_cr >= threshold_medium:
        level = "medium"
    else:
        level = "low"

    result = ContextPressure(
        level=level,
        avg_cr_recent=avg_cr,
        window_turns=len(cr_values),
        threshold_high=threshold_high,
        threshold_medium=threshold_medium,
        on_cooldown=on_cooldown,
        cooldown_remaining_s=cooldown_remaining,
        session_path=str(session),
    )
    _memo[cache_key] = (now, result.to_dict())
    return result


def annotate_event(event: dict[str, Any], pressure: ContextPressure) -> dict[str, Any]:
    """Attach a pressure annotation + suggested-action override to an event.

    Mutates ``event`` in place and also returns it. The role contract
    teaches the LLM to read ``suggested_action``; we use that channel
    rather than inventing a new one. Original ``suggested_action`` is
    preserved as ``original_suggested_action`` so nothing is lost.

    Pressure levels:
      - low:    no annotation
      - medium: append a soft hint
      - high:   prepend an explicit "compact now" instruction
    """
    if pressure.level == "low":
        return event

    event["context_pressure"] = pressure.to_dict()
    original = event.get("suggested_action", "")

    if pressure.level == "high":
        compact_directive = (
            f"⚠ CONTEXT PRESSURE HIGH (avg cache_read {pressure.avg_cr_recent:,} "
            f"over last {pressure.window_turns} turns, threshold "
            f"{pressure.threshold_high:,}). Before continuing other work, "
            f'call `mos_compact_context(reason="context_pressure_high", '
            f"pending_plans=[...])` to compress conversation history into a "
            f"pointer-shaped summary. Persist any in-flight plans first as "
            f"`pending_plan` Draft nodes. After this completes do not "
            f"continue this turn — the compact will fire on next user input."
        )
        if original:
            event["suggested_action"] = f"{compact_directive}\n\nOriginal: {original}"
            event["original_suggested_action"] = original
        else:
            event["suggested_action"] = compact_directive
    else:  # medium
        hint = (
            f"[context advisory: avg cache_read {pressure.avg_cr_recent:,} "
            f"approaching threshold {pressure.threshold_high:,}; consider "
            f"`mos_compact_context` after current work completes]"
        )
        if original:
            event["suggested_action"] = f"{original}\n\n{hint}"
        else:
            event["suggested_action"] = hint

    return event


def reset_memo() -> None:
    """Clear the per-process memo. For tests."""
    _memo.clear()
