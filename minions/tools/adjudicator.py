"""Adjudication tool — fine-grained answer review for benchmark submissions.

Provides ``mos_adjudicate``, a two-layer evaluation flow:

1. **Adjudication layer** (this module) — runs before the grader. Spawns 1-3
   independent adjudicator instances (depending on profile depth) that audit
   the submitted answer's reasoning chain, search counterexamples, check
   self-consistency, and ground external claims. Returns {decision: accept |
   reject | revise, confidence, evidence_refs, critique_path}.

2. **Grader layer** (``evaluator.py``) — runs after adjudication if decision
   is accept. Compares the bare answer to the reference via exact_match /
   numeric_close / test_runner.

Adjudication reuses the Reviewer's Pass A/B/C multi-reviewer-instance
structure but with answer-shape templates (``minions/review/templates/answer/``
and ``minions/review/skills/answer/``).

Depth tiers (controlled by ``profile.evaluation.adjudication.depth``):
- ``none`` — skip adjudication, go straight to grader (default for
  scientific-paper).
- ``single`` — one adjudicator instance (fast, cheap, lower confidence).
- ``panel`` — three adjudicator instances + chair synthesis (default for
  hle-answer).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Literal, Protocol, cast, get_args

from pydantic import BaseModel, Field

from minions.paths import (
    MINIONS_ROOT,
    REVIEW_DIR,
    project_shared_subdir,
    project_shared_workspace,
)

logger = logging.getLogger(__name__)

# Decision labels for adjudication (simpler than paper review).
AdjudicationDecision = Literal["Accept", "Revise", "Reject"]
ADJUDICATION_DECISIONS: frozenset[str] = frozenset(get_args(AdjudicationDecision))

# Per-stage timeouts (same as review.py).
_ADJUDICATOR_STAGE_TIMEOUT_SECONDS = int(os.environ.get("MOS_ADJUDICATE_TIMEOUT", str(15 * 60)))
_CONSOLIDATE_STAGE_TIMEOUT_SECONDS = int(
    os.environ.get("MOS_ADJUDICATE_CONSOLIDATE_TIMEOUT", str(10 * 60))
)


class AdjudicateArgs(BaseModel):
    port: int = Field(description="Project port.")
    depth: Literal["none", "single", "panel"] = Field(
        default="panel",
        description="Adjudication depth: none (skip), single (1 instance), panel (3 instances).",
    )


def mos_adjudicate(args: AdjudicateArgs) -> dict[str, object]:
    """Run adjudication on the submitted answer at branches/shared/submissions/answer.json.

    Returns one of three shapes::

        {"status": "skipped", "reason": "depth=none"}
        {"status": "error", "reason": ..., "round": int}
        {"status": "completed", "round": int, "decision": str, "confidence": float,
         "evidence_refs": [...], "consolidated_path": str, "summary_path": str}
    """
    if args.depth == "none":
        return {"status": "skipped", "reason": "depth=none"}

    submission_path = project_shared_subdir(args.port, "submissions") / "answer.json"
    if not submission_path.exists():
        return {
            "status": "error",
            "reason": f"Submission answer.json not found at {submission_path}",
        }

    reviews_dir = project_shared_subdir(args.port, "governance") / "adjudication"
    round_num = _current_round_number(reviews_dir)
    round_dir = reviews_dir / f"round-{round_num}"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "aspect-notes").mkdir(exist_ok=True)

    workspace = project_shared_workspace(args.port)
    consolidated_path = round_dir / "consolidated.md"
    summary_path = reviews_dir / "summaries" / f"round-{round_num}.md"

    logger.info(
        "mos_adjudicate round=%d port=%d depth=%s submission=%s",
        round_num,
        args.port,
        args.depth,
        submission_path,
    )

    # Stage 1: spawn adjudicator instances (1 or 3 depending on depth).
    instance_count = 1 if args.depth == "single" else 3
    for i in range(1, instance_count + 1):
        ok, err = _stage_adjudicator_instance(
            workspace=workspace,
            port=args.port,
            submission_path=submission_path,
            round_num=round_num,
            round_dir=round_dir,
            adjudicator_index=i,
        )
        if not ok:
            return {
                "status": "error",
                "reason": f"adjudicator {i} stage failed: {err}",
                "round": round_num,
            }

    # Stage 2: fresh.md — pure-Python concat (same as review.py).
    reports = _existing_adjudicator_reports(round_dir)
    if not reports:
        return {
            "status": "error",
            "reason": "stage1 produced no adjudicator reports",
            "round": round_num,
        }
    fresh_md = round_dir / "fresh.md"
    if not fresh_md.exists():
        _concat_fresh_md(round_dir, reports)

    # Stage 3: consolidation — produce consolidated.md + adjudication-summary.md.
    ok, err = _stage_consolidation(
        workspace=workspace,
        port=args.port,
        submission_path=submission_path,
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
            "reason": "adjudication completed but no valid Decision found in consolidated.md",
            "round": round_num,
            "consolidated_path": str(consolidated_path),
        }

    confidence = _extract_confidence(consolidated_path)
    evidence_refs = _extract_evidence_refs(consolidated_path)

    commit_sha = _commit_adjudication_round_to_shared(
        port=args.port,
        round_num=round_num,
        decision=decision,
    )

    return {
        "status": "completed",
        "round": round_num,
        "decision": decision,
        "confidence": confidence,
        "evidence_refs": evidence_refs,
        "consolidated_path": str(consolidated_path),
        "summary_path": str(summary_path),
        "shared_commit_sha": commit_sha,
    }


def _current_round_number(reviews_dir: Path) -> int:
    """Return the round number to use for the next adjudication run."""
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


def _build_adjudicator_prompt(
    *,
    port: int,
    submission_path: Path,
    round_num: int,
    adjudicator_index: int,
    round_dir: Path,
    earlier_adjudicators: list[Path],
) -> str:
    """Prompt for a single adjudicator-instance spawn."""
    earlier_note = (
        f"Earlier adjudicator reports already exist in this round: "
        f"{', '.join(p.name for p in earlier_adjudicators)}. You may peek at "
        "them only to decide whether your independent perspective adds new "
        "weaknesses; do not copy from them, do not converge prematurely."
        if earlier_adjudicators
        else "You are the first adjudicator in this round; no peer reports exist yet."
    )
    return (
        f"You are adjudicator {adjudicator_index} for adjudication round {round_num} on "
        f"project port {port}.\n"
        f"Submission (read-only): `{submission_path}`.\n"
        f"Round output dir: `{round_dir}`.\n"
        f"\n"
        f"{earlier_note}\n"
        "\n"
        "Drive the answer-shape adjudication workflow to produce ONE "
        f"adjudicator instance — `reviewer-{adjudicator_index}.md` plus its aspect "
        f"notes under `aspect-notes/reviewer-{adjudicator_index}-<aspect>.md`. "
        "Spawn aspect subagents per the answer-shape skills "
        "(query-reasoning-chain, search-counterexamples, check-self-consistency, "
        "evidence-grounding). Use Codex via the `codex` MCP tool when an aspect "
        "needs to read volume or run code.\n"
        "\n"
        f"Your single deliverable for this run is `{round_dir}/reviewer-"
        f"{adjudicator_index}.md` ending in a `## Decision` line with one of: "
        "`Accept | Revise | Reject`. Do NOT write fresh.md, consolidated.md, "
        "or any rolling summary — those are owned by later stages. Exit when "
        f"reviewer-{adjudicator_index}.md and its aspect notes are on disk."
    )


def _build_consolidation_prompt(
    *,
    port: int,
    submission_path: Path,
    round_num: int,
    round_dir: Path,
    summary_path: Path,
) -> str:
    """Prompt for the consolidation-only pass."""
    return (
        f"You are finishing adjudication round {round_num} for project on port {port}.\n"
        f"Adjudicator reports already exist under `{round_dir}`:\n"
        f"  - `fresh.md` (concatenation of all reviewer-i.md)\n"
        "  - `reviewer-1.md`, `reviewer-2.md`, `reviewer-3.md`, etc.\n"
        f"  - aspect notes under `aspect-notes/`\n"
        f"\n"
        f"Submission (read-only context if you need to disambiguate a "
        f"reviewer claim): `{submission_path}`.\n"
        f"\n"
        "Your only job in this pass is to produce two missing artifacts:\n"
        f"\n"
        f"1. `{round_dir / 'consolidated.md'}` — the chair synthesis packet, "
        "following `minions/review/templates/answer/consolidated.md`. It must "
        "contain: a short notification, the chair synthesis, "
        "`## Decision` on its own line with exactly one of "
        "`Accept | Revise | Reject`, confidence (0.0-1.0), required revisions "
        "if applicable, evidence refs, and the full text of every reviewer-i.md inlined.\n"
        f"\n"
        f"2. `{summary_path}` — the compressed adjudication summary following "
        "`minions/review/templates/answer/adjudication-summary.md`. Include the "
        "final verdict, confidence, bare answer (only if Decision=Accept), decisive "
        "evidence, and pointers. No raw quotations, no notification prose.\n"
        "\n"
        "Read `fresh.md` and the individual `reviewer-i.md` files first, then "
        "write both outputs. You may use `codex.ask_codex` to help synthesize a "
        "long packet — it is faster and cheaper than composing turn-by-turn.\n"
        "\n"
        "Do not re-run adjudicator instances. Do not modify aspect notes or "
        "reviewer-i.md. Exit when both files exist on disk; end with the "
        "absolute path to consolidated.md and the decision label on its own "
        "line."
    )


def _spawn_claude_adjudicate(
    *,
    workspace: Path,
    prompt: str,
    timeout: int = _ADJUDICATOR_STAGE_TIMEOUT_SECONDS,
    lock_label: str | None = None,
) -> tuple[bool, str | None]:
    """Run a single ``claude --print`` adjudication pass.

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
    model = os.environ.get("MOS_ADJUDICATE_MODEL", "").strip()
    if model:
        cmd += ["--model", model]
    # Auto-fallback on 404 (overload / model rotation). Honored by --print
    # mode (see Claude Code 2.1.152 --help). Read MOS_ADJUDICATE_FALLBACK_MODEL
    # first, then GruConfig.fallback_model. Empty/missing means no fallback.
    fallback_model = os.environ.get("MOS_ADJUDICATE_FALLBACK_MODEL", "").strip()
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
        return False, f"claude adjudicate process exited non-zero: {exc.returncode}"
    except subprocess.TimeoutExpired:
        return False, f"claude adjudicate process exceeded {timeout}s timeout"


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


_spawner: Spawner = _spawn_claude_adjudicate


def set_spawner(spawner: Spawner | None) -> Spawner:
    """Override the spawner used by ``mos_adjudicate``. Returns the previous one.

    Pass ``None`` to restore the default. Test code should always restore
    after the test (use a try/finally or a fixture).
    """
    global _spawner
    previous = _spawner
    _spawner = spawner if spawner is not None else _spawn_claude_adjudicate
    return previous


def get_spawner() -> Spawner:
    return _spawner


def _stage_adjudicator_instance(
    *,
    workspace: Path,
    port: int,
    submission_path: Path,
    round_num: int,
    round_dir: Path,
    adjudicator_index: int,
) -> tuple[bool, str | None]:
    """Run one adjudicator-instance spawn (idempotent per index)."""
    target = round_dir / f"reviewer-{adjudicator_index}.md"
    if target.exists():
        logger.info(
            "mos_adjudicate stage1 adjudicator %d already exists; skipping spawn",
            adjudicator_index,
        )
        return True, None
    earlier = _existing_adjudicator_reports(round_dir)
    prompt = _build_adjudicator_prompt(
        port=port,
        submission_path=submission_path,
        round_num=round_num,
        adjudicator_index=adjudicator_index,
        round_dir=round_dir,
        earlier_adjudicators=earlier,
    )
    logger.info(
        "mos_adjudicate stage1 spawning adjudicator %d for round %d (timeout=%ds)",
        adjudicator_index,
        round_num,
        _ADJUDICATOR_STAGE_TIMEOUT_SECONDS,
    )
    spawner = get_spawner()
    ok, err = spawner(
        workspace=workspace,
        prompt=prompt,
        timeout=_ADJUDICATOR_STAGE_TIMEOUT_SECONDS,
        lock_label=f"mos-adjudicate-p{port}-r{round_num}-adj{adjudicator_index}",
    )
    if not ok:
        return False, err
    if not target.exists():
        return False, (
            f"adjudicator {adjudicator_index} spawn returned ok but {target.name} was not written"
        )
    return True, None


def _stage_consolidation(
    *,
    workspace: Path,
    port: int,
    submission_path: Path,
    round_num: int,
    round_dir: Path,
    summary_path: Path,
) -> tuple[bool, str | None]:
    """Produce consolidated.md + adjudication-summary.md as one bounded spawn."""
    consolidated = round_dir / "consolidated.md"
    if consolidated.exists() and summary_path.exists():
        return True, None
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = _build_consolidation_prompt(
        port=port,
        submission_path=submission_path,
        round_num=round_num,
        round_dir=round_dir,
        summary_path=summary_path,
    )
    logger.info(
        "mos_adjudicate stage2 spawning consolidation for round %d (timeout=%ds)",
        round_num,
        _CONSOLIDATE_STAGE_TIMEOUT_SECONDS,
    )
    spawner = get_spawner()
    ok, err = spawner(
        workspace=workspace,
        prompt=prompt,
        timeout=_CONSOLIDATE_STAGE_TIMEOUT_SECONDS,
        lock_label=f"mos-adjudicate-p{port}-r{round_num}-consolidate",
    )
    if not ok:
        return False, err
    if not consolidated.exists():
        return False, "consolidation spawn returned ok but consolidated.md was not written"
    return True, None


def _existing_adjudicator_reports(round_dir: Path) -> list[Path]:
    """Return reviewer-i.md files in *round_dir* sorted by index."""
    pattern = re.compile(r"reviewer-(\d+)\.md$")
    items: list[tuple[int, Path]] = []
    for child in round_dir.iterdir():
        m = pattern.match(child.name)
        if m and child.is_file():
            items.append((int(m.group(1)), child))
    items.sort(key=lambda t: t[0])
    return [p for _, p in items]


def _concat_fresh_md(round_dir: Path, adjudicator_reports: list[Path]) -> Path:
    """Pure-Python concat of reviewer-i.md files into fresh.md."""
    fresh = round_dir / "fresh.md"
    parts: list[str] = ["# Fresh — Round Adjudicator Reports\n\n"]
    for path in adjudicator_reports:
        parts.append(f"\n\n---\n\n## {path.stem}\n\n")
        parts.append(path.read_text(encoding="utf-8"))
        if not parts[-1].endswith("\n"):
            parts.append("\n")
    fresh.write_text("".join(parts), encoding="utf-8")
    return fresh


def _extract_decision(consolidated_path: Path) -> AdjudicationDecision | None:
    """Extract the chair decision label from consolidated.md."""
    if not consolidated_path.exists():
        return None
    text = consolidated_path.read_text(encoding="utf-8")
    canonical_sorted = sorted(ADJUDICATION_DECISIONS, key=lambda s: -len(s))

    def _label_at(pos_in_text: str) -> AdjudicationDecision | None:
        label = pos_in_text.strip().strip("*_`").splitlines()[0].strip().strip("*_`")
        for canonical in canonical_sorted:
            if re.fullmatch(rf"\s*{re.escape(canonical)}\s*\.?\s*", label, flags=re.IGNORECASE):
                # Cast: re-derive narrow type after lookup against canonical set.
                return cast(AdjudicationDecision, canonical)
        return None

    # Find the first `## Decision` block.
    for m in re.finditer(r"^##\s*Decision\s*\n+\s*(.+)$", text, flags=re.MULTILINE):
        return _label_at(m.group(1))
    return None


def _extract_confidence(consolidated_path: Path) -> float:
    """Extract confidence from consolidated.md (default 0.5 if not found)."""
    if not consolidated_path.exists():
        return 0.5
    text = consolidated_path.read_text(encoding="utf-8")
    m = re.search(r"Confidence:\s*(0?\.\d+|1\.0|0|1)\b", text, flags=re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return 0.5


def _extract_evidence_refs(consolidated_path: Path) -> list[str]:
    """Extract evidence refs from consolidated.md."""
    if not consolidated_path.exists():
        return []
    text = consolidated_path.read_text(encoding="utf-8")
    refs: list[str] = []
    in_evidence = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^##\s*Evidence\s+Refs?\b", stripped, flags=re.IGNORECASE):
            in_evidence = True
            continue
        if in_evidence:
            if stripped.startswith("##"):
                break
            if stripped.startswith("-"):
                refs.append(stripped.lstrip("- ").strip())
    return refs


def _commit_adjudication_round_to_shared(
    *, port: int, round_num: int, decision: AdjudicationDecision
) -> str | None:
    """Commit the round's outputs on the shared branch."""
    from minions.tools.publish import _shared_lock

    workspace = project_shared_workspace(port)
    if not workspace.exists():
        logger.warning("mos_adjudicate: shared worktree missing for port=%d; skipping commit", port)
        return None

    msg = f"adjudicate: round-{round_num} consolidated ({decision})"
    with _shared_lock(port):
        add = subprocess.run(
            ["git", "add", "-A", "governance/adjudication"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
        )
        if add.returncode != 0:
            logger.warning(
                "mos_adjudicate: git add failed for shared port=%d: %s",
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
                "mos_adjudicate: git commit failed for shared port=%d: %s",
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


__all__ = [
    "AdjudicateArgs",
    "AdjudicationDecision",
    "get_spawner",
    "mos_adjudicate",
    "set_spawner",
]
