"""Review MCP tool: synchronous Area-Chair review run.

Reviewer is no longer a long-lived Role. The review workflow is invoked as a
single MCP tool call by Gru when an Expert submits a manuscript (Book→Paper,
Gru-driven). This module:

1. Parses the accompanying submission checklist and short-circuits with a
   rejection if any Required item is unchecked.
2. Spawns a one-shot ``claude --print`` process with the Reviewer prompt assets
   appended as the system prompt. That process drives the 3-pass review
   procedure documented in ``minions/review/SYSTEM.md`` and the review skills.
3. Reads the produced ``consolidated.md`` and returns the round number,
   decision label, and artifact paths.

The spawner is exposed as a module-level ``Spawner`` callable so tests can
substitute a fake without subclassing or monkeypatching subprocess internals.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from minions.paths import (
    MINIONS_ROOT,
    REVIEW_DIR,
    project_dir,
    project_main_workspace,
    project_reviews_dir,
    project_shared_workspace,
)

logger = logging.getLogger(__name__)

DECISION_LABELS: frozenset[str] = frozenset(
    {
        "Strong Accept",
        "Accept",
        "Weak Accept",
        "Borderline",
        "Weak Reject",
        "Reject",
        "Strong Reject",
    }
)

REQUIRED_HEADER = "## Required"
CONDITIONAL_HEADER = "## Conditionally required"
CHECKLIST_BLOCK_OPEN = "[SUBMISSION CHECKLIST]"
CHECKLIST_BLOCK_CLOSE = "[/SUBMISSION CHECKLIST]"

# Single review-round wall. The Area-Chair drives the WHOLE round inside one
# `claude --print` subprocess, fanning reviewer instances out as concurrent
# foreground `Task` subagents (not N serial subprocesses, and never background
# tasks — a backgrounded task / `Workflow` is abandoned when a `--print` turn
# ends). The wall therefore bounds the entire round, whose wall-clock is
# ~the slowest reviewer plus consolidation rather than the sum of N reviewers
# run in series. Generous by default; override via env or GruConfig.
_DEFAULT_REVIEW_TIMEOUT_SECONDS = 60 * 60
_DEFAULT_MIN_REVIEWERS = 3
_DEFAULT_MAX_REVIEWERS = 5


def _review_timeout_seconds() -> int:
    """Wall for one review round. Env ``MOS_REVIEW_TIMEOUT`` > GruConfig > 1h."""
    env = os.environ.get("MOS_REVIEW_TIMEOUT", "").strip()
    if env:
        try:
            return max(60, int(env))
        except ValueError:
            pass
    try:
        from minions.config import load_gru_config

        return max(60, int(load_gru_config().review_timeout_seconds))
    except Exception:  # pragma: no cover — config load failure is non-fatal
        return _DEFAULT_REVIEW_TIMEOUT_SECONDS


def _review_ultracode_enabled() -> bool:
    """Whether to launch the Area-Chair with ultracode. Env > GruConfig > True."""
    env = os.environ.get("MOS_REVIEW_ULTRACODE", "").strip().lower()
    if env:
        return env not in ("0", "false", "no", "off")
    try:
        from minions.config import load_gru_config

        return bool(load_gru_config().review_ultracode)
    except Exception:  # pragma: no cover — config load failure is non-fatal
        return True


def _reviewer_band() -> tuple[int, int]:
    """(min, max) reviewer instances. Env ``MOS_REVIEW_{MIN,MAX}_REVIEWERS``."""

    def _int_env(name: str, default: int) -> int:
        raw = os.environ.get(name, "").strip()
        if raw:
            try:
                return int(raw)
            except ValueError:
                pass
        return default

    lo = max(1, _int_env("MOS_REVIEW_MIN_REVIEWERS", _DEFAULT_MIN_REVIEWERS))
    hi = max(lo, _int_env("MOS_REVIEW_MAX_REVIEWERS", _DEFAULT_MAX_REVIEWERS))
    return lo, hi


class ReviewRunArgs(BaseModel):
    port: int = Field(description="Project port whose workspace holds the submission.")
    submission_path: str = Field(
        description=(
            "Path (absolute, or relative to the project main workspace) to the submission "
            "package directory. Must contain `submission-checklist.md` and the manuscript."
        )
    )
    prior_summary_path: str | None = Field(
        default=None,
        description=(
            "Optional path to the previous round's rolling summary "
            "(``branches/shared/reviews/summaries/round-<n-1>.md``). Required for Pass B / Pass C."
        ),
    )


class ChecklistGateResult(BaseModel):
    passed: bool
    missing_required: list[str]
    raw_block: str | None = None


def parse_checklist(text: str) -> ChecklistGateResult:
    """Parse a submission-checklist markdown body and report Required-section gaps.

    A Required item is "missing" if its checkbox is empty (``[ ]``) or unchecked
    with ``✗`` / ``x``. ``✓`` / ``X``-marked items pass. Lines outside the
    ``## Required`` section are ignored by the gate.
    """
    lines = text.splitlines()
    in_required = False
    missing: list[str] = []
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("## "):
            in_required = stripped.startswith(REQUIRED_HEADER) and not stripped.startswith(
                CONDITIONAL_HEADER
            )
            continue
        if not in_required:
            continue
        m = re.match(r"-\s*\[(.)\]\s*(.+)", stripped)
        if not m:
            continue
        mark, item = m.group(1), m.group(2).strip()
        if mark in {"✓", "x", "X"}:
            continue
        missing.append(item)
    return ChecklistGateResult(passed=not missing, missing_required=missing)


def _resolve_submission_dir(port: int, submission_path: str) -> Path:
    """Resolve *submission_path* to an absolute Path under the project tree.

    Rejects paths that resolve outside the project's directory — submissions
    must live within ``project_{port}/`` (typically under
    ``branches/<expert>/paper/submissions/`` or ``branches/shared/handoffs/``).
    """
    p = Path(submission_path)
    if not p.is_absolute():
        p = project_main_workspace(port) / p
    resolved = p.resolve()
    project_root = project_dir(port).resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"submission_path resolves outside project_{port}/: {resolved}") from exc
    return resolved


def _current_round_number(reviews_dir: Path) -> int:
    """Return the round number to use for the next ``review_run``.

    A round counts as *complete* only when both its ``consolidated.md`` and its
    rolling summary (``summaries/round-<n>.md``) are on disk — the same pair
    ``_run_review_round`` uses as its skip-spawn guard. If the most recent round
    is missing either, reuse that round number so ``review_run`` resumes and
    finishes it rather than abandoning the partial work and starting fresh. Only
    allocate a new number when the previous round has both final artifacts.
    """
    if not reviews_dir.exists():
        return 1
    existing = sorted(
        int(m.group(1))
        for m in (re.match(r"round-(\d+)$", child.name) for child in reviews_dir.iterdir())
        if m
    )
    if not existing:
        return 1
    last = existing[-1]
    consolidated = reviews_dir / f"round-{last}" / "consolidated.md"
    summary = reviews_dir / "summaries" / f"round-{last}.md"
    if not (consolidated.exists() and summary.exists()):
        return last
    return last + 1


def _build_review_round_prompt(
    *,
    port: int,
    submission_dir: Path,
    round_num: int,
    round_dir: Path,
    summary_path: Path,
    prior_summary: Path | None,
    min_reviewers: int,
    max_reviewers: int,
) -> str:
    """Prompt for the single Area-Chair spawn that drives the WHOLE round.

    One ``claude --print`` process runs all three passes per the review
    SYSTEM.md, fanning reviewer instances out as concurrent foreground
    ``Task`` subagents. The detailed procedure lives in SYSTEM.md and the
    review skills; this prompt only pins the round-specific paths, the
    reviewer-count band, and the concurrency / no-background contract.
    """
    pass_bc = (
        "A prior rolling summary EXISTS for this submission:\n"
        f"  `{prior_summary}`\n"
        "Run Pass B / Pass C: spawn exactly ONE dedicated revision-delta\n"
        "subagent that reads ONLY that prior summary first, then the current\n"
        "submission + any author rebuttal/changelog, and writes\n"
        f"`{round_dir}/revision_delta.md`. It does NOT count toward the\n"
        "reviewer band and must NOT see current-round reviewer reports."
        if prior_summary is not None
        else (
            "No prior rolling summary exists — this is the first round for\n"
            "this submission. SKIP Pass B / Pass C: write\n"
            f"`{round_dir}/revision_delta.md` containing only the single line\n"
            "`skipped: no prior summary`."
        )
    )
    return (
        f"You are the Area Chair / Editor for review round {round_num} on "
        f"project port {port}. Drive the COMPLETE round per your SYSTEM.md "
        "and the `run-review-round` skill — all passes, in one process.\n"
        "\n"
        f"Submission package (read-only): `{submission_dir}`.\n"
        f"Round output dir (already created): `{round_dir}`.\n"
        f"Aspect notes go under: `{round_dir}/aspect-notes/`.\n"
        f"Rolling summary path to write: `{summary_path}`.\n"
        "\n"
        "## Reviewer band\n"
        f"Convene at least {min_reviewers} and at most {max_reviewers} "
        "independent reviewer instances (Pass A). Start at "
        f"{min_reviewers}; add a 4th/5th only when the submission is complex "
        "or reviewers materially disagree; stop when the marginal reviewer is "
        "redundant. Each reviewer instance is a composite of aspect subagents "
        "with mixed stances, per `simulate-reviewer-instance`.\n"
        "\n"
        "## Concurrency contract (this is what makes the round finish in time)\n"
        "Spawn the reviewer instances' aspect subagents as CONCURRENT "
        "foreground `Task` subagents — issue multiple `Task` calls in a "
        "single turn so they run in parallel, then read their notes once they "
        "return. Do NOT run reviewers one fully-finished-before-the-next in "
        "series. Do NOT use `run_in_background` or the `Workflow` tool: this "
        "is a `--print` process and a backgrounded task is abandoned when the "
        "turn ends. Delegate volume reading (long PDF, code tracing, citation "
        "sweeps) to `Task` subagents.\n"
        "\n"
        "## Passes\n"
        "1. Pass A — independent reviewer instances, history-isolated. Merge "
        "each instance's aspect notes into "
        f"`{round_dir}/reviewer-<i>.md` (each ending in a `## Decision` "
        "line), then concatenate them verbatim into "
        f"`{round_dir}/fresh.md` (raw concat, no synthesis).\n"
        f"2. {pass_bc}\n"
        "3. Consolidation — synthesize the meta-review into "
        f"`{round_dir}/consolidated.md` per `templates/consolidated.md`: "
        "notification, AC/Editor meta-review, `## Decision` on its own line "
        "with exactly one of `Strong Accept | Accept | Weak Accept | "
        "Borderline | Weak Reject | Reject | Strong Reject`, required "
        "revisions, revision-delta highlights if any, and the full text of "
        f"every reviewer-<i>.md inlined. Then write `{summary_path}` per "
        "`templates/summary.md` (compressed; safe as the next round's only "
        "historical input).\n"
        "\n"
        "End your final turn with the absolute path to consolidated.md and "
        "the decision label on its own last line. `mos_review_run` parses the "
        "decision from consolidated.md; do not stay resident or poll."
    )


def _spawn_claude_review(
    *,
    workspace: Path,
    prompt: str,
    timeout: int = _DEFAULT_REVIEW_TIMEOUT_SECONDS,
    lock_label: str | None = None,
) -> tuple[bool, str | None]:
    """Run the Area-Chair ``claude --print`` review process. Returns (ok, error).

    One process drives the whole round and fans reviewer instances out as
    concurrent foreground ``Task`` subagents. ``Workflow`` is intentionally
    absent from ``--allowed-tools``: a ``--print`` turn ends before a
    backgrounded workflow completes, so the reliable parallelism primitive
    here is concurrent foreground ``Task`` calls, not the background-only
    ``Workflow`` tool.

    Reads ``MOS_REVIEW_MODEL`` from the environment to pick the model. Defaults
    to whatever the user's claude session would pick; set ``MOS_REVIEW_MODEL=haiku``
    for fast / cheap runs where review-quality details are not the goal.

    When ``review_ultracode`` is on (GruConfig, default; env override
    ``MOS_REVIEW_ULTRACODE=0/1``), the process launches with the Claude Code
    ``ultracode`` session setting (xhigh effort), mirroring how long-lived
    Roles are launched in ``agent_host``.

    When *lock_label* is set, allocates a Claude Code ``--session-id`` UUID
    and pre-locks its title in the global sidecar registry so any host-side
    auto-rename hook leaves the run alone. The lock is best-effort; failure
    never blocks the spawn.
    """
    from minions.lifecycle.sidecar_lock import allocate_session_id, lock_session_title

    system_path = REVIEW_DIR / "SYSTEM.md"
    cmd = [
        "uv",
        "run",
        "--project",
        str(MINIONS_ROOT),
        "claude",
        "--print",
        "--append-system-prompt",
        f"@{system_path}",
        "--mcp-config",
        str(MINIONS_ROOT / ".mcp.json"),
        "--allowed-tools",
        "Read,Write,Edit,Bash,Task",
        "--permission-mode",
        "bypassPermissions",
    ]
    if _review_ultracode_enabled():
        # ultracode == xhigh reasoning effort + standing orchestration posture,
        # passed as a session setting (NOT --effort, which rejects the value).
        # See agent_host.build_role_invocation for the canonical rationale.
        cmd += ["--settings", '{"ultracode": true}']
    if lock_label:
        sid = allocate_session_id()
        cmd += ["--session-id", sid]
        lock_session_title(sid, lock_label)
    model = os.environ.get("MOS_REVIEW_MODEL", "").strip()
    if model:
        cmd += ["--model", model]
    # Auto-fallback on 404 (overload / model rotation). Honored by --print
    # mode (see Claude Code 2.1.152 --help). Read MOS_REVIEW_FALLBACK_MODEL
    # first, then GruConfig.fallback_model. Empty/missing means no fallback.
    fallback_model = os.environ.get("MOS_REVIEW_FALLBACK_MODEL", "").strip()
    if not fallback_model:
        try:
            from minions.config import load_gru_config

            fallback_model = (load_gru_config().fallback_model or "").strip()
        except Exception:  # pragma: no cover — config load failure is non-fatal here
            fallback_model = ""
    if fallback_model:
        cmd += ["--fallback-model", fallback_model]
    try:
        subprocess.run(
            cmd,
            cwd=str(workspace if workspace.exists() else MINIONS_ROOT),
            input=prompt,
            text=True,
            timeout=timeout,
            check=True,
        )
        return True, None
    except subprocess.CalledProcessError as exc:
        return False, f"claude review process exited non-zero: {exc.returncode}"
    except subprocess.TimeoutExpired:
        return False, f"claude review process exceeded {timeout}s timeout"


# Module-level spawner indirection so tests can inject a fake without
# patching ``subprocess`` internals. Production code reads this attribute
# at call time, so test code can replace it for the duration of one test.
class Spawner(Protocol):
    def __call__(
        self,
        *,
        workspace: Path,
        prompt: str,
        timeout: int = ...,
        lock_label: str | None = ...,
    ) -> tuple[bool, str | None]: ...


_spawner: Spawner = _spawn_claude_review


def set_spawner(spawner: Spawner | None) -> Spawner:
    """Override the spawner used by ``review_run``. Returns the previous one.

    Pass ``None`` to restore the default. Test code should always restore
    after the test (use a try/finally or a fixture).
    """
    global _spawner
    previous = _spawner
    _spawner = spawner if spawner is not None else _spawn_claude_review
    return previous


def get_spawner() -> Spawner:
    return _spawner


def _extract_decision(consolidated_path: Path) -> str | None:
    """Extract the AC / Editor decision label from ``consolidated.md``.

    ``consolidated.md`` inlines every individual reviewer-i.md, each of which
    carries its own ``## Decision`` line. The AC / Editor meta-review's
    ``## Decision`` is the authoritative one and conventionally appears
    *before* the inlined reviewer reports in our template. We therefore take
    the **first** ``## Decision`` block, but only after stripping out
    anything that looks like a per-reviewer report header.

    If the first match falls inside a sub-section explicitly labelled as a
    reviewer report (e.g. ``### Reviewer 1`` / ``# Reviewer 1`` / a
    "Round N Reviewer i" heading), we keep scanning.
    """
    if not consolidated_path.exists():
        return None
    text = consolidated_path.read_text(encoding="utf-8")
    canonical_sorted = sorted(DECISION_LABELS, key=lambda s: -len(s))

    reviewer_section = re.compile(
        r"^#+\s*(?:Round\s*\d+\s+)?Reviewer\s*\d+\b", re.IGNORECASE | re.MULTILINE
    )

    def _label_at(pos_in_text: str) -> str | None:
        label = pos_in_text.strip().strip("*_`").splitlines()[0].strip().strip("*_`")
        for canonical in canonical_sorted:
            if re.fullmatch(rf"\s*{re.escape(canonical)}\s*\.?\s*", label, flags=re.IGNORECASE):
                return canonical
        return None

    # Find all `## Decision` blocks with their offsets.
    for m in re.finditer(r"^##\s*Decision\s*\n+\s*(.+)$", text, flags=re.MULTILINE):
        body_before = text[: m.start()]
        # Walk back: the nearest preceding heading determines the section.
        prev_headings = list(re.finditer(r"^#+\s+.+$", body_before, flags=re.MULTILINE))
        if prev_headings and reviewer_section.match(prev_headings[-1].group(0)):
            # This `## Decision` sits inside an inlined reviewer report. Skip.
            continue
        return _label_at(m.group(1))
    return None


def _existing_reviewer_reports(round_dir: Path) -> list[Path]:
    """Return reviewer-i.md files in *round_dir* sorted by index."""
    pattern = re.compile(r"reviewer-(\d+)\.md$")
    items: list[tuple[int, Path]] = []
    for child in round_dir.iterdir():
        m = pattern.match(child.name)
        if m and child.is_file():
            items.append((int(m.group(1)), child))
    items.sort(key=lambda t: t[0])
    return [p for _, p in items]


def _concat_fresh_md(round_dir: Path, reviewer_reports: list[Path]) -> Path:
    """Pure-Python concat of reviewer-i.md files into fresh.md.

    fresh.md is a direct concatenation, not a synthesis. Concat is
    deterministic and trivially correct, so it does not need a spawn.
    """
    fresh = round_dir / "fresh.md"
    parts: list[str] = ["# Fresh — Round Reviewer Reports\n\n"]
    for path in reviewer_reports:
        parts.append(f"\n\n---\n\n## {path.stem}\n\n")
        parts.append(path.read_text(encoding="utf-8"))
        if not parts[-1].endswith("\n"):
            parts.append("\n")
    fresh.write_text("".join(parts), encoding="utf-8")
    return fresh


def _run_review_round(
    *,
    spawner: Spawner,
    workspace: Path,
    port: int,
    submission_dir: Path,
    round_num: int,
    round_dir: Path,
    summary_path: Path,
    prior_summary: Path | None,
) -> tuple[bool, str | None]:
    """Drive a complete review round in ONE Area-Chair spawn, then validate.

    The single ``claude --print`` Area-Chair process runs all three passes and
    fans reviewer instances out as concurrent foreground ``Task`` subagents
    (see ``_build_review_round_prompt`` and the review SYSTEM.md). This replaces
    the old N-serial-subprocess pipeline whose per-reviewer 900 s wall blew up
    on multi-aspect Opus 4.8 reviews.

    Idempotent: if ``consolidated.md`` and the rolling summary already exist on
    disk (a prior run completed the round), the spawn is skipped — the
    structural check below still runs so a resumed round is validated.

    After the spawn we structurally verify the round on disk rather than
    trusting the process exit code: at least ``min_reviewers`` reviewer reports,
    a ``revision_delta.md``, ``consolidated.md``, and the rolling summary.
    ``fresh.md`` is repaired by deterministic Python concat if the Area-Chair
    skipped it (it is a raw concatenation, not a synthesis).
    """
    consolidated = round_dir / "consolidated.md"
    min_reviewers, max_reviewers = _reviewer_band()
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    already_complete = consolidated.exists() and summary_path.exists()
    if not already_complete:
        prompt = _build_review_round_prompt(
            port=port,
            submission_dir=submission_dir,
            round_num=round_num,
            round_dir=round_dir,
            summary_path=summary_path,
            prior_summary=prior_summary,
            min_reviewers=min_reviewers,
            max_reviewers=max_reviewers,
        )
        timeout = _review_timeout_seconds()
        logger.info(
            "review_run spawning Area-Chair for round %d port %d "
            "(timeout=%ds, ultracode=%s, band=%d-%d)",
            round_num,
            port,
            timeout,
            _review_ultracode_enabled(),
            min_reviewers,
            max_reviewers,
        )
        ok, err = spawner(
            workspace=workspace,
            prompt=prompt,
            timeout=timeout,
            lock_label=f"mos-review-p{port}-r{round_num}",
        )
        if not ok:
            return False, f"Area-Chair review process failed: {err}"

    # Structural validation — trust disk artifacts, not the exit code.
    reports = _existing_reviewer_reports(round_dir)
    if len(reports) < min_reviewers:
        return False, (
            f"review round produced {len(reports)} reviewer report(s); "
            f"at least {min_reviewers} are required"
        )
    revision_delta = round_dir / "revision_delta.md"
    if not revision_delta.exists():
        if prior_summary is None:
            # No-prior-summary skip placeholder is as deterministic as fresh.md —
            # write it ourselves rather than hard-failing on a forgotten one-liner.
            revision_delta.write_text("skipped: no prior summary\n", encoding="utf-8")
        else:
            # A revision round's delta carries real model judgment; we cannot
            # synthesize it, so a missing one is a genuine failure.
            return False, "review round did not produce revision_delta.md"
    # fresh.md is a deterministic concat — repair it rather than failing.
    fresh_md = round_dir / "fresh.md"
    if not fresh_md.exists():
        _concat_fresh_md(round_dir, reports)
    if not consolidated.exists():
        return False, "review round did not produce consolidated.md"
    if not summary_path.exists():
        return False, "review round did not produce the rolling summary"
    return True, None


def _find_manuscript_pdf(submission_dir: Path) -> Path | None:
    """Return a compiled manuscript PDF inside *submission_dir*, or None.

    The manuscript deliverable is always LaTeX → compiled PDF. We accept the
    canonical ``build/paper.pdf`` first, then any non-trivial ``*.pdf`` in the
    package root or ``build/``. A PDF must be > 1 KB to count — a zero-byte or
    placeholder file does not satisfy the format gate. This is the mechanical
    backstop behind the checklist's "Manuscript format" Required item, so a
    package whose only manuscript is a ``.md`` cannot pass by gaming the
    checkbox.
    """
    candidates = [submission_dir / "build" / "paper.pdf", submission_dir / "paper.pdf"]
    candidates += sorted(submission_dir.glob("*.pdf"))
    candidates += sorted(submission_dir.glob("build/*.pdf"))
    for pdf in candidates:
        if pdf.exists() and pdf.is_file() and pdf.stat().st_size > 1024:
            return pdf
    return None


def review_run(args: ReviewRunArgs) -> dict[str, object]:
    """Run one review round for *args.submission_path* under project *args.port*.

    After the upstream gates (submission dir, checklist, compiled-PDF format),
    the round is driven by a SINGLE Area-Chair ``claude --print`` process that
    runs all three passes and fans reviewer instances out as concurrent
    foreground ``Task`` subagents (see ``_run_review_round`` and the review
    SYSTEM.md). The whole round is bounded by one wall (``review_timeout_seconds``,
    default 1 h) rather than the old per-reviewer 900 s wall x N serial spawns
    that timed out on multi-aspect Opus 4.8 reviews.

    The round is idempotent: a completed round on disk (consolidated.md +
    rolling summary) is not re-spawned, and the round is always structurally
    validated on disk (≥ min reviewers, revision_delta.md, consolidated.md,
    rolling summary) rather than trusting the process exit code.

    Returns one of three shapes::

        {"status": "rejected", "reason": ..., "missing_required": [...]}
        {"status": "error", "reason": ..., "round": int, ...}
        {"status": "completed", "round": int, "decision": str,
         "consolidated_path": str, "summary_path": str}
    """
    submission_dir = _resolve_submission_dir(args.port, args.submission_path)
    if not submission_dir.exists() or not submission_dir.is_dir():
        return {
            "status": "error",
            "reason": f"submission_path not found or not a directory: {submission_dir}",
        }

    checklist_file = submission_dir / "submission-checklist.md"
    if not checklist_file.exists():
        return {
            "status": "rejected",
            "reason": "submission-checklist.md is missing from the submission package",
            "missing_required": [],
        }

    gate = parse_checklist(checklist_file.read_text(encoding="utf-8"))
    if not gate.passed:
        logger.info(
            "review_run gate rejected: port=%d missing=%s", args.port, gate.missing_required
        )
        return {
            "status": "rejected",
            "reason": "Required checklist items unchecked; submission not reviewable.",
            "missing_required": gate.missing_required,
        }

    # Manuscript-format gate: the deliverable is always LaTeX → compiled PDF.
    # Reject a package whose manuscript is not a real PDF even if the checklist
    # claims otherwise — markdown is never an acceptable manuscript.
    if _find_manuscript_pdf(submission_dir) is None:
        logger.info("review_run gate rejected: port=%d no compiled manuscript PDF", args.port)
        return {
            "status": "rejected",
            "reason": (
                "No compiled manuscript PDF found in the submission package. "
                "The manuscript must be LaTeX compiled to build/paper.pdf; a "
                "Markdown file is not an acceptable manuscript."
            ),
            "missing_required": ["Manuscript format: compiled LaTeX -> PDF"],
        }

    reviews_dir = project_reviews_dir(args.port)
    round_num = _current_round_number(reviews_dir)
    round_dir = reviews_dir / f"round-{round_num}"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "aspect-notes").mkdir(exist_ok=True)

    prior_summary: Path | None = None
    if args.prior_summary_path:
        prior = Path(args.prior_summary_path)
        if not prior.is_absolute():
            prior = project_main_workspace(args.port) / prior
        if prior.exists():
            prior_summary = prior.resolve()

    workspace = project_main_workspace(args.port)
    consolidated_path = round_dir / "consolidated.md"
    summary_path = reviews_dir / "summaries" / f"round-{round_num}.md"
    spawner = get_spawner()

    logger.info(
        "review_run round=%d port=%d submission=%s (single Area-Chair)",
        round_num,
        args.port,
        submission_dir,
    )

    ok, err = _run_review_round(
        spawner=spawner,
        workspace=workspace,
        port=args.port,
        submission_dir=submission_dir,
        round_num=round_num,
        round_dir=round_dir,
        summary_path=summary_path,
        prior_summary=prior_summary,
    )
    if not ok:
        return {
            "status": "error",
            "reason": err,
            "round": round_num,
        }

    decision = _extract_decision(consolidated_path)
    if decision is None:
        return {
            "status": "error",
            "reason": "review run completed but no valid Decision found in consolidated.md",
            "round": round_num,
            "consolidated_path": str(consolidated_path),
        }

    commit_sha = _commit_review_round_to_shared(
        port=args.port,
        round_num=round_num,
        decision=decision,
    )

    return {
        "status": "completed",
        "round": round_num,
        "decision": decision,
        "consolidated_path": str(consolidated_path),
        "summary_path": str(summary_path),
        "shared_commit_sha": commit_sha,
    }


def _commit_review_round_to_shared(*, port: int, round_num: int, decision: str) -> str | None:
    """Commit the round's outputs on the shared branch.

    ``mos_review_run`` owns ``branches/shared/reviews/`` directly rather
    than going through ``mos_publish_to_shared``, since it produced the
    files in-place under that tree. We still acquire the per-project
    flock so concurrent ``mos_publish_to_shared`` calls from any role
    serialise cleanly with this commit.
    """
    from minions.tools.publish import _shared_lock  # local import to avoid cycle

    workspace = project_shared_workspace(port)
    if not workspace.exists():
        logger.warning("review_run: shared worktree missing for port=%d; skipping commit", port)
        return None

    msg = f"review: round-{round_num} consolidated ({decision})"
    with _shared_lock(port):
        add = subprocess.run(
            ["git", "add", "-A", "reviews"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
        )
        if add.returncode != 0:
            logger.warning(
                "review_run: git add failed for shared port=%d: %s",
                port,
                add.stderr.strip(),
            )
            return None
        commit = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=str(workspace),
            capture_output=True,
            text=True,
        )
        if commit.returncode != 0:
            output = f"{commit.stdout}\n{commit.stderr}".lower()
            if "nothing to commit" in output or "nothing added to commit" in output:
                return None
            logger.warning(
                "review_run: git commit failed for shared port=%d: %s",
                port,
                commit.stderr.strip(),
            )
            return None
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
        )
        if head.returncode != 0:
            return None
        return head.stdout.strip() or None
