"""Review MCP tool: synchronous Area-Chair review run.

Reviewer is no longer a long-lived Role. The review workflow is invoked as a
single MCP tool call by Gru when Writer submits a manuscript. This module:

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

# Per-stage timeouts. Each stage is bounded so a single slow / runaway
# claude call cannot stall the whole tool. Defaults err on the generous
# side; override via env vars when debugging.
_REVIEWER_STAGE_TIMEOUT_SECONDS = int(os.environ.get("MOS_REVIEW_REVIEWER_TIMEOUT", str(15 * 60)))
_CONSOLIDATE_STAGE_TIMEOUT_SECONDS = int(
    os.environ.get("MOS_REVIEW_CONSOLIDATE_TIMEOUT", str(10 * 60))
)
_FALLBACK_STAGE_TIMEOUT_SECONDS = int(os.environ.get("MOS_REVIEW_FALLBACK_TIMEOUT", str(60 * 60)))

_DEFAULT_REVIEWER_COUNT = 3
_MAX_REVIEWER_COUNT = 5


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
    ``branches/writer/paper/submissions/`` or ``branches/shared/handoffs/``).
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

    If the most recent round directory is missing ``consolidated.md`` (the
    final artifact), reuse that round number — `review_run` will resume the
    incomplete round rather than start a new one and waste the partial work.
    Only allocate a fresh round number when the previous round has its
    consolidated.md on disk.
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
    if not (reviews_dir / f"round-{last}" / "consolidated.md").exists():
        return last
    return last + 1


def _build_reviewer_prompt(
    *,
    port: int,
    submission_dir: Path,
    round_num: int,
    reviewer_index: int,
    round_dir: Path,
    earlier_reviewers: list[Path],
) -> str:
    """Prompt for a single reviewer-instance spawn (Pass A, one reviewer).

    Each reviewer instance is a separate ``claude --print`` call so the model
    cannot decide "I'm done" mid-round. The prompt is tightly scoped: produce
    exactly one ``reviewer-<i>.md`` plus its aspect notes. No fresh.md, no
    consolidated.md, no rolling summary — those happen later as their own
    stages.
    """
    earlier_note = (
        f"Earlier reviewer reports already exist in this round: "
        f"{', '.join(p.name for p in earlier_reviewers)}. You may peek at "
        "them only to decide whether your independent perspective adds new "
        "weaknesses; do not copy from them, do not converge prematurely."
        if earlier_reviewers
        else "You are the first reviewer in this round; no peer reports exist yet."
    )
    return (
        f"You are reviewer {reviewer_index} for review round {round_num} on "
        f"project port {port}.\n"
        f"Submission package (read-only): `{submission_dir}`.\n"
        f"Round output dir: `{round_dir}`.\n"
        f"\n"
        f"{earlier_note}\n"
        "\n"
        "Drive the `simulate-reviewer-instance` skill to produce ONE "
        f"reviewer instance — `reviewer-{reviewer_index}.md` plus its aspect "
        f"notes under `aspect-notes/reviewer-{reviewer_index}-<aspect>.md`. "
        "Spawn aspect subagents per the skill (mixed stances). Use Codex via "
        "the `codex` MCP tool when an aspect needs to read volume.\n"
        "\n"
        f"Your single deliverable for this run is `{round_dir}/reviewer-"
        f"{reviewer_index}.md` ending in a `## Decision` line with one of: "
        "`Strong Accept | Accept | Weak Accept | Borderline | Weak Reject | "
        "Reject | Strong Reject`. Do NOT write fresh.md, consolidated.md, "
        "revision_delta.md, or any rolling summary — those are owned by "
        "later stages of `mos_review_run`. Exit when reviewer-"
        f"{reviewer_index}.md and its aspect notes are on disk."
    )


def _build_revision_delta_prompt(
    *,
    port: int,
    submission_dir: Path,
    round_num: int,
    round_dir: Path,
    prior_summary_path: Path,
) -> str:
    """Prompt for the dedicated revision-delta subagent (Pass B / Pass C)."""
    return (
        f"You are the revision-delta agent for review round {round_num} on "
        f"project port {port}.\n"
        f"Submission package (Pass C input): `{submission_dir}`.\n"
        f"Prior rolling summary (Pass B input, ONLY allowed historical input): "
        f"`{prior_summary_path}`.\n"
        f"Round output dir: `{round_dir}`.\n"
        "\n"
        "Drive the `revision-delta` skill: Pass B reads the prior summary "
        "ONLY; Pass C then reads the current submission and any author "
        "rebuttal/changelog. Produce "
        f"`{round_dir}/revision_delta.md` per `templates/revision_delta.md`.\n"
        "\n"
        "Do NOT read current-round reviewer-i.md, fresh.md, or "
        "consolidated.md — those would contaminate independence. Do NOT "
        "write anything except revision_delta.md."
    )


def _build_consolidation_prompt(
    *,
    port: int,
    submission_dir: Path,
    round_num: int,
    round_dir: Path,
    summary_path: Path,
) -> str:
    """Prompt for a consolidation-only pass when the first run left it incomplete."""
    return (
        f"You are finishing review round {round_num} for project on port {port}.\n"
        f"Pass A reviewer reports already exist under `{round_dir}`:\n"
        f"  - `fresh.md` (concatenation of all reviewer-i.md)\n"
        "  - `reviewer-1.md`, `reviewer-2.md`, `reviewer-3.md`, etc.\n"
        f"  - `revision_delta.md`\n"
        f"  - aspect notes under `aspect-notes/`\n"
        f"\n"
        f"Submission package (read-only context if you need to disambiguate a "
        f"reviewer claim): `{submission_dir}`.\n"
        f"\n"
        "Your only job in this pass is to produce two missing artifacts:\n"
        f"\n"
        f"1. `{round_dir / 'consolidated.md'}` — the Area-Chair / Editor "
        "meta-review packet, following `templates/consolidated.md`. It must "
        "contain: a short notification, the meta-review synthesis, "
        "`## Decision` on its own line with exactly one of "
        "`Strong Accept | Accept | Weak Accept | Borderline | Weak Reject | "
        "Reject | Strong Reject`, required revisions, revision-delta highlights "
        "if applicable, and the full text of every reviewer-i.md inlined.\n"
        f"\n"
        f"2. `{summary_path}` — the compressed rolling summary following "
        "`templates/summary.md`. Unresolved issues, newly raised issues, "
        "resolved-since-last-round items, long-standing unanswered questions, "
        "and the final decision. No raw quotations, no notification prose.\n"
        "\n"
        "Read `fresh.md` and the individual `reviewer-i.md` files first, then "
        "write both outputs. You may use `codex.ask_codex` to help synthesize a "
        "long packet — it is faster and cheaper than composing turn-by-turn.\n"
        "\n"
        "Do not re-run reviewer instances. Do not modify aspect notes or "
        "reviewer-i.md. Exit when both files exist on disk; end with the "
        "absolute path to consolidated.md and the decision label on its own "
        "line."
    )


def _spawn_claude_review(
    *,
    workspace: Path,
    prompt: str,
    timeout: int = _FALLBACK_STAGE_TIMEOUT_SECONDS,
    lock_label: str | None = None,
) -> tuple[bool, str | None]:
    """Run a single ``claude --print`` review pass. Returns (ok, error_reason).

    Reads ``MOS_REVIEW_MODEL`` from the environment to pick the model. Defaults
    to whatever the user's claude session would pick; set ``MOS_REVIEW_MODEL=haiku``
    for fast / cheap runs where review-quality details are not the goal.

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
        "Read,Write,Edit,Bash,Task,codex",
        "--permission-mode",
        "bypassPermissions",
    ]
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


def _stage_pass_a_reviewer(
    *,
    spawner: Spawner,
    workspace: Path,
    port: int,
    submission_dir: Path,
    round_num: int,
    round_dir: Path,
    reviewer_index: int,
) -> tuple[bool, str | None]:
    """Run one reviewer-instance spawn (Stage 1, idempotent per index)."""
    target = round_dir / f"reviewer-{reviewer_index}.md"
    if target.exists():
        logger.info(
            "review_run stage1 reviewer %d already exists; skipping spawn",
            reviewer_index,
        )
        return True, None
    earlier = _existing_reviewer_reports(round_dir)
    prompt = _build_reviewer_prompt(
        port=port,
        submission_dir=submission_dir,
        round_num=round_num,
        reviewer_index=reviewer_index,
        round_dir=round_dir,
        earlier_reviewers=earlier,
    )
    logger.info(
        "review_run stage1 spawning reviewer %d for round %d (timeout=%ds)",
        reviewer_index,
        round_num,
        _REVIEWER_STAGE_TIMEOUT_SECONDS,
    )
    ok, err = spawner(
        workspace=workspace,
        prompt=prompt,
        timeout=_REVIEWER_STAGE_TIMEOUT_SECONDS,
        lock_label=f"mos-review-p{port}-r{round_num}-rev{reviewer_index}",
    )
    if not ok:
        return False, err
    if not target.exists():
        return False, (
            f"reviewer {reviewer_index} spawn returned ok but {target.name} was not written"
        )
    return True, None


def _stage_revision_delta(
    *,
    spawner: Spawner,
    workspace: Path,
    port: int,
    submission_dir: Path,
    round_num: int,
    round_dir: Path,
    prior_summary: Path | None,
) -> tuple[bool, str | None]:
    """Run Pass B / Pass C as one bounded spawn, or write the skip placeholder."""
    target = round_dir / "revision_delta.md"
    if target.exists():
        return True, None
    if prior_summary is None:
        target.write_text("skipped: no prior summary\n", encoding="utf-8")
        return True, None
    prompt = _build_revision_delta_prompt(
        port=port,
        submission_dir=submission_dir,
        round_num=round_num,
        round_dir=round_dir,
        prior_summary_path=prior_summary,
    )
    logger.info(
        "review_run stage2 spawning revision-delta for round %d (timeout=%ds)",
        round_num,
        _REVIEWER_STAGE_TIMEOUT_SECONDS,
    )
    ok, err = spawner(
        workspace=workspace,
        prompt=prompt,
        timeout=_REVIEWER_STAGE_TIMEOUT_SECONDS,
        lock_label=f"mos-review-p{port}-r{round_num}-delta",
    )
    if not ok:
        return False, err
    if not target.exists():
        return False, "revision-delta spawn returned ok but revision_delta.md was not written"
    return True, None


def _stage_consolidation(
    *,
    spawner: Spawner,
    workspace: Path,
    port: int,
    submission_dir: Path,
    round_num: int,
    round_dir: Path,
    summary_path: Path,
) -> tuple[bool, str | None]:
    """Produce consolidated.md + rolling summary as one bounded spawn."""
    consolidated = round_dir / "consolidated.md"
    if consolidated.exists() and summary_path.exists():
        return True, None
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = _build_consolidation_prompt(
        port=port,
        submission_dir=submission_dir,
        round_num=round_num,
        round_dir=round_dir,
        summary_path=summary_path,
    )
    logger.info(
        "review_run stage4 spawning consolidation for round %d (timeout=%ds)",
        round_num,
        _CONSOLIDATE_STAGE_TIMEOUT_SECONDS,
    )
    ok, err = spawner(
        workspace=workspace,
        prompt=prompt,
        timeout=_CONSOLIDATE_STAGE_TIMEOUT_SECONDS,
        lock_label=f"mos-review-p{port}-r{round_num}-consolidate",
    )
    if not ok:
        return False, err
    if not consolidated.exists():
        return False, "consolidation spawn returned ok but consolidated.md was not written"
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

    The round is decomposed into bounded stages, each its own ``claude --print``
    call (when a spawn is required) or pure Python (when the work is just file
    concatenation). Every stage is idempotent: if its output already exists,
    the stage is skipped. This makes ``review_run`` safely re-runnable after
    any partial failure.

    Stages:
      1. Pass A — N independent reviewer-instance spawns (default 3).
      2. fresh.md — Python concatenation of reviewer-i.md files.
      3. revision-delta — one spawn (Pass B / Pass C) when a prior summary
         exists; otherwise Python writes a "skipped" placeholder.
      4. consolidation — one spawn that produces consolidated.md + the
         rolling summary.

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
        "review_run round=%d port=%d submission=%s (staged pipeline)",
        round_num,
        args.port,
        submission_dir,
    )

    # Stage 1: Pass A — N reviewer instances, one spawn each.
    for i in range(1, _DEFAULT_REVIEWER_COUNT + 1):
        ok, err = _stage_pass_a_reviewer(
            spawner=spawner,
            workspace=workspace,
            port=args.port,
            submission_dir=submission_dir,
            round_num=round_num,
            round_dir=round_dir,
            reviewer_index=i,
        )
        if not ok:
            return {
                "status": "error",
                "reason": f"reviewer {i} stage failed: {err}",
                "round": round_num,
            }

    # Stage 2: fresh.md — pure-Python concat. No spawn.
    reports = _existing_reviewer_reports(round_dir)
    if not reports:
        return {
            "status": "error",
            "reason": "stage1 produced no reviewer reports",
            "round": round_num,
        }
    fresh_md = round_dir / "fresh.md"
    if not fresh_md.exists():
        _concat_fresh_md(round_dir, reports)

    # Stage 3: revision-delta. Spawn only when there is a prior summary.
    ok, err = _stage_revision_delta(
        spawner=spawner,
        workspace=workspace,
        port=args.port,
        submission_dir=submission_dir,
        round_num=round_num,
        round_dir=round_dir,
        prior_summary=prior_summary,
    )
    if not ok:
        return {
            "status": "error",
            "reason": f"revision-delta stage failed: {err}",
            "round": round_num,
        }

    # Stage 4: consolidation — produce consolidated.md and rolling summary.
    ok, err = _stage_consolidation(
        spawner=spawner,
        workspace=workspace,
        port=args.port,
        submission_dir=submission_dir,
        round_num=round_num,
        round_dir=round_dir,
        summary_path=summary_path,
    )
    if not ok:
        return {
            "status": "error",
            "reason": f"consolidation stage failed: {err}",
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
