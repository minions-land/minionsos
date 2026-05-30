"""End-to-end review tool tests with a fake spawner.

These tests exercise the full ``review_run`` workflow — checklist gate, round
allocation, prompt assembly indirection, resilience pass, decision extraction,
and return shape — without spawning a real ``claude --print`` subprocess.

A ``FakeSpawner`` simulates the side effects a real review run would have on
disk: writing aspect notes, reviewer-i.md, fresh.md, consolidated.md, and the
rolling summary. Each test supplies its own scripted behaviour so we can
probe specific boundary conditions cheaply.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from minions.tools import review as review_mod
from minions.tools.review import ReviewRunArgs, review_run, set_spawner


@pytest.fixture()
def project_tree(tmp_path: Path, monkeypatch) -> tuple[int, Path]:
    """Point projects_root at a clean tmp dir with one project skeleton."""
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    import minions.paths as _p

    monkeypatch.setattr(_p, "projects_root", lambda: tmp_path)
    port = 99001
    pdir = tmp_path / f"project_{port}"
    (pdir / "branches" / "main").mkdir(parents=True)
    (pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1").mkdir(parents=True)
    return port, pdir


def _write_checklist(submission: Path, *, all_required_checked: bool = True) -> None:
    if all_required_checked:
        body = (
            "## Required (all must be checked OK)\n\n"
            "- [✓] Problem statement\n"
            "- [✓] Literature survey\n"
            "- [✓] Main experiment\n"
            "- [✓] Baseline comparison\n"
            "- [✓] Ablation study\n"
            "- [✓] Case visualization\n\n"
            "## Conditionally required\n\n"
            "- [ ] Mathematical formulation\n"
        )
    else:
        body = (
            "## Required (all must be checked OK)\n\n"
            "- [✓] Problem statement\n"
            "- [✗] Baseline comparison\n"
            "- [✓] Main experiment\n"
        )
    (submission / "submission-checklist.md").write_text(body, encoding="utf-8")


def _write_manuscript(submission: Path) -> None:
    # The manuscript deliverable is always LaTeX -> compiled PDF. Seed a
    # >1 KB build/paper.pdf so the review_run manuscript-format gate passes.
    # A real LaTeX source tree would also be present; the gate only requires
    # the compiled PDF.
    build = submission / "build"
    build.mkdir(parents=True, exist_ok=True)
    (build / "paper.pdf").write_bytes(b"%PDF-1.5\n" + b"0" * 2048 + b"\n%%EOF\n")
    (submission / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}Tiny Study\\end{document}\n",
        encoding="utf-8",
    )


class FakeSpawner:
    """Records calls and runs scripted side effects."""

    def __init__(self, scripts: list[Callable[[Path, str, int], tuple[bool, str | None]]]):
        self.scripts = scripts
        self.calls: list[tuple[Path, str]] = []
        self.timeouts: list[int] = []
        self.lock_labels: list[str | None] = []

    def __call__(
        self,
        *,
        workspace: Path,
        prompt: str,
        timeout: int = 0,
        lock_label: str | None = None,
    ) -> tuple[bool, str | None]:
        idx = len(self.calls)
        self.calls.append((workspace, prompt))
        self.timeouts.append(timeout)
        self.lock_labels.append(lock_label)
        if idx >= len(self.scripts):
            return False, f"FakeSpawner: no script for call {idx}"
        return self.scripts[idx](workspace, prompt, idx)


@pytest.fixture()
def install_spawner() -> Iterator[Callable[[FakeSpawner], None]]:
    previous = review_mod.get_spawner()

    def _install(spawner: FakeSpawner) -> None:
        set_spawner(spawner)

    try:
        yield _install
    finally:
        set_spawner(previous)


def _round_dir(workspace: Path, round_num: int = 1) -> Path:
    project_root = workspace.parent.parent
    d = project_root / "branches" / "shared" / "reviews" / f"round-{round_num}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "aspect-notes").mkdir(exist_ok=True)
    return d


def _summary_path(workspace: Path, round_num: int = 1) -> Path:
    project_root = workspace.parent.parent
    p = project_root / "branches" / "shared" / "reviews" / "summaries" / f"round-{round_num}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def full_round_script(
    decision: str = "Accept",
    n_reviewers: int = 3,
    write_consolidated: bool = True,
    write_summary: bool = True,
    write_fresh: bool = True,
    write_reviewer_md: bool = True,
    write_aspect_notes: bool = True,
) -> Callable[[Path, str, int], tuple[bool, str | None]]:
    """LEGACY one-shot script: writes everything in a single spawn call.

    Useful for tests that never reach a spawn (gate / path-safety), or for
    "fallback" tests where we want any single spawn to fully populate the
    round directory. The staged pipeline calls the spawner multiple times;
    most happy-path tests should use ``staged_round_scripts`` instead.
    """

    def _script(workspace: Path, prompt: str, idx: int) -> tuple[bool, str | None]:
        rd = _round_dir(workspace, 1)
        if write_aspect_notes:
            for i in range(1, n_reviewers + 1):
                for aspect in ("presentation", "experiments", "reproducibility"):
                    (rd / "aspect-notes" / f"reviewer-{i}-{aspect}.md").write_text(
                        f"# Aspect Note\nReviewer {i} / {aspect}\n", encoding="utf-8"
                    )
        if write_reviewer_md:
            for i in range(1, n_reviewers + 1):
                (rd / f"reviewer-{i}.md").write_text(
                    f"# Reviewer {i}\n\n## Decision\n\n{decision}\n",
                    encoding="utf-8",
                )
        (rd / "revision_delta.md").write_text("skipped: no prior summary\n", encoding="utf-8")
        if write_fresh:
            fresh_body = "# Fresh\n" + "".join(
                f"\n\n## Reviewer {i}\n\n## Decision\n\n{decision}\n"
                for i in range(1, n_reviewers + 1)
            )
            (rd / "fresh.md").write_text(fresh_body, encoding="utf-8")
        if write_consolidated:
            body = (
                "# Round 1 Meta-Review\n\n"
                "## Notification\n\nRound 1 complete.\n\n"
                "## Area-Chair / Editor Meta-Review\n\nThe AC synthesized 3 reviews.\n\n"
                f"## Decision\n\n{decision}\n\n"
                "## Required Revisions\n\n- (none if Accept)\n\n"
                + "".join(
                    f"\n\n### Reviewer {i}\n\n(inlined reviewer-{i}.md)\n\n"
                    f"## Decision\n\n{decision}\n"
                    for i in range(1, n_reviewers + 1)
                )
            )
            (rd / "consolidated.md").write_text(body, encoding="utf-8")
        if write_summary:
            sp = _summary_path(workspace, 1)
            sp.write_text(
                f"Round: 1\nDecision: {decision}\nUnresolved: none\n",
                encoding="utf-8",
            )
        return True, None

    return _script


def reviewer_script(
    reviewer_index: int,
    decision: str = "Accept",
    aspects: tuple[str, ...] = ("presentation", "experiments", "reproducibility"),
    fail: bool = False,
    write_nothing: bool = False,
    round_num: int = 1,
) -> Callable[[Path, str, int], tuple[bool, str | None]]:
    """Stage 1 script: write ONE reviewer-i.md plus its aspect notes."""

    def _script(workspace: Path, prompt: str, idx: int) -> tuple[bool, str | None]:
        if fail:
            return False, f"reviewer {reviewer_index} timed out (simulated)"
        if write_nothing:
            return True, None
        rd = _round_dir(workspace, round_num)
        for aspect in aspects:
            (rd / "aspect-notes" / f"reviewer-{reviewer_index}-{aspect}.md").write_text(
                f"# Aspect Note\nReviewer {reviewer_index} / {aspect}\n",
                encoding="utf-8",
            )
        (rd / f"reviewer-{reviewer_index}.md").write_text(
            f"# Reviewer {reviewer_index}\n\n## Decision\n\n{decision}\n",
            encoding="utf-8",
        )
        return True, None

    return _script


def consolidation_script(
    decision: str = "Accept",
    n_reviewers: int = 3,
    fail: bool = False,
    write_consolidated: bool = True,
    write_summary: bool = True,
    round_num: int = 1,
) -> Callable[[Path, str, int], tuple[bool, str | None]]:
    """Stage 4 script: write consolidated.md and the rolling summary."""

    def _script(workspace: Path, prompt: str, idx: int) -> tuple[bool, str | None]:
        if fail:
            return False, "consolidation pass timed out (simulated)"
        rd = _round_dir(workspace, round_num)
        if write_consolidated:
            body = (
                f"# Round {round_num} Meta-Review\n\n"
                f"## Notification\n\nRound {round_num} complete.\n\n"
                "## Area-Chair / Editor Meta-Review\n\nAC synthesized reviews.\n\n"
                f"## Decision\n\n{decision}\n\n"
                "## Required Revisions\n\n- (none if Accept)\n\n"
                + "".join(
                    f"\n\n### Reviewer {i}\n\n(inlined)\n\n## Decision\n\n{decision}\n"
                    for i in range(1, n_reviewers + 1)
                )
            )
            (rd / "consolidated.md").write_text(body, encoding="utf-8")
        if write_summary:
            sp = _summary_path(workspace, round_num)
            sp.write_text(
                f"Round: {round_num}\nDecision: {decision}\nUnresolved: none\n",
                encoding="utf-8",
            )
        return True, None

    return _script


def revision_delta_script(
    fail: bool = False,
    round_num: int = 1,
) -> Callable[[Path, str, int], tuple[bool, str | None]]:
    """Stage 3 script: write revision_delta.md from prior summary."""

    def _script(workspace: Path, prompt: str, idx: int) -> tuple[bool, str | None]:
        if fail:
            return False, "revision-delta spawn timed out (simulated)"
        rd = _round_dir(workspace, round_num)
        (rd / "revision_delta.md").write_text(
            "# Revision Delta\n\nResolved: foo\nUnresolved: bar\n", encoding="utf-8"
        )
        return True, None

    return _script


def staged_round_scripts(
    decision: str = "Accept",
    n_reviewers: int = 3,
    round_num: int = 1,
    with_prior_summary: bool = False,
) -> list[Callable[[Path, str, int], tuple[bool, str | None]]]:
    """Build the full stage-script sequence for one review round.

    Order: N x reviewer_script, then (revision_delta_script if a prior summary
    is in play, else Python writes the skip placeholder and no spawn happens),
    then consolidation_script.
    """
    scripts: list[Callable[[Path, str, int], tuple[bool, str | None]]] = [
        reviewer_script(i, decision=decision, round_num=round_num)
        for i in range(1, n_reviewers + 1)
    ]
    if with_prior_summary:
        scripts.append(revision_delta_script(round_num=round_num))
    scripts.append(
        consolidation_script(decision=decision, n_reviewers=n_reviewers, round_num=round_num)
    )
    return scripts


class TestChecklistGate:
    """The gate must reject before spawning anything."""

    def test_missing_checklist_rejects_without_spawn(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        _write_manuscript(pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1")
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "rejected"
        assert "checklist" in result["reason"].lower()
        assert spawner.calls == [], "must not spawn claude when checklist is missing"

    def test_failed_required_rejects_without_spawn(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub, all_required_checked=False)
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "rejected"
        assert any("Baseline" in m for m in result["missing_required"])
        assert spawner.calls == []

    def test_markdown_only_manuscript_rejects_without_spawn(
        self, project_tree, install_spawner
    ) -> None:
        """A passing checklist + .md-only package (no compiled PDF) must reject."""
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        # Markdown manuscript only — the exact failure this gate prevents.
        (sub / "manuscript.md").write_text("# Tiny Study\n\nResults.\n", encoding="utf-8")
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "rejected"
        assert "pdf" in result["reason"].lower()
        assert spawner.calls == [], "must not spawn claude when manuscript is not a compiled PDF"

    def test_placeholder_pdf_under_1kb_rejects(self, project_tree, install_spawner) -> None:
        """A zero/placeholder PDF (<= 1 KB) does not satisfy the format gate."""
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        (sub / "build").mkdir(parents=True, exist_ok=True)
        (sub / "build" / "paper.pdf").write_bytes(b"%PDF-1.5\n")  # tiny placeholder
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "rejected"
        assert "pdf" in result["reason"].lower()
        assert spawner.calls == []


class TestHappyPath:
    @pytest.mark.parametrize(
        "decision",
        [
            "Strong Accept",
            "Accept",
            "Weak Accept",
            "Borderline",
            "Weak Reject",
            "Reject",
            "Strong Reject",
        ],
    )
    def test_full_round_returns_decision(self, project_tree, install_spawner, decision) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=staged_round_scripts(decision=decision))
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed"
        assert result["decision"] == decision
        assert result["round"] == 1
        assert Path(str(result["consolidated_path"])).exists()
        assert Path(str(result["summary_path"])).exists()
        # Stage 1 (3 reviewer spawns) + Stage 4 (1 consolidation spawn).
        # Stage 2 (fresh.md concat) is pure Python; Stage 3 (revision-delta)
        # writes the skip placeholder without spawning.
        assert len(spawner.calls) == 4, "staged pipeline runs 3 reviewer + 1 consolidation"

    def test_fresh_md_is_python_concat_not_a_spawn(self, project_tree, install_spawner) -> None:
        """Stage 2 must produce fresh.md without invoking the spawner."""
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=staged_round_scripts(decision="Accept"))
        install_spawner(spawner)
        review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        fresh = pdir / "branches" / "shared" / "reviews" / "round-1" / "fresh.md"
        assert fresh.exists()
        body = fresh.read_text(encoding="utf-8")
        # Concat must include each reviewer report's content.
        for i in range(1, 4):
            assert f"Reviewer {i}" in body
        # The total spawn count is still exactly 4 — fresh.md required no spawn.
        assert len(spawner.calls) == 4

    def test_per_stage_timeouts_passed_to_spawner(self, project_tree, install_spawner) -> None:
        """Each stage must pass a bounded timeout to the spawner."""
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=staged_round_scripts(decision="Accept"))
        install_spawner(spawner)
        review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        # All 4 spawns must have a positive bounded timeout (the stage caps).
        assert all(t > 0 for t in spawner.timeouts)
        # Reviewer-stage timeout (first 3 calls) and consolidation timeout (last)
        # come from different constants; both should be < 1 hour by default.
        from minions.tools.review import (
            _CONSOLIDATE_STAGE_TIMEOUT_SECONDS,
            _REVIEWER_STAGE_TIMEOUT_SECONDS,
        )

        for t in spawner.timeouts[:3]:
            assert t == _REVIEWER_STAGE_TIMEOUT_SECONDS
        assert spawner.timeouts[3] == _CONSOLIDATE_STAGE_TIMEOUT_SECONDS


class TestResiliencePass:
    def test_recovers_when_first_pass_truncates_after_fresh(
        self, project_tree, install_spawner
    ) -> None:
        """The staged pipeline is naturally idempotent: re-running with Pass A
        artifacts on disk skips Pass A and goes straight to consolidation.
        """
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        # Pre-populate Pass A artifacts (simulates a prior crash mid-round).
        r1 = pdir / "branches" / "shared" / "reviews" / "round-1"
        (r1 / "aspect-notes").mkdir(parents=True)
        for i in range(1, 4):
            (r1 / f"reviewer-{i}.md").write_text(
                f"# Reviewer {i}\n\n## Decision\n\nWeak Accept\n", encoding="utf-8"
            )
        (r1 / "fresh.md").write_text("# Fresh\n", encoding="utf-8")
        (r1 / "revision_delta.md").write_text("skipped: no prior summary\n", encoding="utf-8")

        spawner = FakeSpawner(scripts=[consolidation_script(decision="Weak Accept")])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed", result
        assert result["decision"] == "Weak Accept"
        assert len(spawner.calls) == 1, "only consolidation spawn should fire"

    def test_no_resilience_when_fresh_md_missing(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)

        def _empty(workspace: Path, prompt: str, idx: int) -> tuple[bool, str | None]:
            return True, None

        spawner = FakeSpawner(scripts=[_empty])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "error"
        # The staged pipeline rejects at stage 1 because reviewer-1.md was
        # not written, before any later stage can run.
        assert "reviewer 1" in result["reason"].lower()
        assert len(spawner.calls) == 1, "must stop at the failed stage"


class TestSpawnerFailures:
    def test_first_pass_subprocess_failure_returns_error(
        self, project_tree, install_spawner
    ) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)

        def _fail(workspace: Path, prompt: str, idx: int) -> tuple[bool, str | None]:
            return False, "claude review process exited non-zero: 137"

        spawner = FakeSpawner(scripts=[_fail])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "error"
        assert "137" in result["reason"]
        assert result["round"] == 1

    def test_consolidation_pass_failure_returns_error(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        # 3 reviewer spawns succeed; consolidation spawn fails.
        scripts = [
            reviewer_script(1, decision="Reject"),
            reviewer_script(2, decision="Reject"),
            reviewer_script(3, decision="Reject"),
            consolidation_script(fail=True),
        ]
        spawner = FakeSpawner(scripts=scripts)
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "error"
        assert "consolidation stage failed" in result["reason"]
        assert len(spawner.calls) == 4

    def test_reviewer_stage_failure_returns_error(self, project_tree, install_spawner) -> None:
        """If a reviewer-instance spawn fails, stop at that stage."""
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        # Reviewer 2 fails; reviewer 3 + consolidation should not be called.
        scripts = [
            reviewer_script(1, decision="Accept"),
            reviewer_script(2, fail=True),
            reviewer_script(3, decision="Accept"),
            consolidation_script(),
        ]
        spawner = FakeSpawner(scripts=scripts)
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "error"
        assert "reviewer 2 stage failed" in result["reason"]
        assert len(spawner.calls) == 2, "must not call later stages after a failure"


class TestRoundAllocation:
    def test_second_run_allocates_round_2(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        # Pre-create a *complete* round-1 so allocation moves on to round-2.
        r1 = pdir / "branches" / "shared" / "reviews" / "round-1"
        r1.mkdir(parents=True)
        (r1 / "consolidated.md").write_text(
            "# Round 1\n\n## Decision\n\nWeak Accept\n", encoding="utf-8"
        )
        # Pre-existing round-1 summary so the next run goes through Pass B/C.
        (pdir / "branches" / "shared" / "reviews" / "summaries").mkdir(parents=True, exist_ok=True)

        spawner = FakeSpawner(scripts=staged_round_scripts(decision="Accept", round_num=2))
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed", result
        assert result["round"] == 2

    def test_prompt_includes_prior_summary_for_round_2(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        # Complete round-1 (with consolidated.md) so allocation hits round-2.
        r1 = pdir / "branches" / "shared" / "reviews" / "round-1"
        r1.mkdir(parents=True)
        (r1 / "consolidated.md").write_text(
            "# Round 1\n\n## Decision\n\nWeak Accept\n", encoding="utf-8"
        )
        prior = pdir / "branches" / "shared" / "reviews" / "summaries" / "round-1.md"
        prior.parent.mkdir(parents=True, exist_ok=True)
        prior.write_text(
            "Round: 1\nDecision: Weak Accept\nUnresolved: thin baselines\n",
            encoding="utf-8",
        )

        # Round 2 with prior summary: 3 reviewer + 1 revision-delta + 1 consolidation.
        scripts = staged_round_scripts(decision="Accept", round_num=2, with_prior_summary=True)
        spawner = FakeSpawner(scripts=scripts)
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(
                port=port,
                submission_path="../shared/handoffs/submissions/round-1",
                prior_summary_path=str(prior),
            )
        )
        assert result["status"] == "completed", result
        # The 4th call should be the revision-delta prompt (after 3 reviewer spawns).
        assert len(spawner.calls) == 5  # 3 reviewers + revision-delta + consolidation
        _, delta_prompt = spawner.calls[3]
        assert "revision-delta" in delta_prompt or "revision_delta" in delta_prompt
        assert str(prior) in delta_prompt

    def test_resumes_incomplete_round_instead_of_allocating_new(
        self, project_tree, install_spawner
    ) -> None:
        """If the most recent round has no consolidated.md, reuse its number.

        With the staged pipeline + per-stage idempotency, the resume path is
        automatic: stages whose output already exists are skipped. So if Pass A
        artifacts are on disk from a prior crash, the next run only spawns the
        consolidation stage.
        """
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        # Pre-populate round-1 with reviewer reports + fresh.md but NO
        # consolidated.md (simulates a prior crash after Pass A).
        r1 = pdir / "branches" / "shared" / "reviews" / "round-1"
        (r1 / "aspect-notes").mkdir(parents=True)
        for i in range(1, 4):
            (r1 / f"reviewer-{i}.md").write_text(
                f"# Reviewer {i}\n\n## Decision\n\nReject\n", encoding="utf-8"
            )
        (r1 / "fresh.md").write_text("# Fresh\n", encoding="utf-8")
        (r1 / "revision_delta.md").write_text("skipped: no prior summary\n", encoding="utf-8")

        # Only the consolidation spawn should fire — all earlier stages are
        # idempotent and see their output already on disk.
        spawner = FakeSpawner(scripts=[consolidation_script(decision="Reject")])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed", result
        assert result["round"] == 1, "must reuse round-1, not allocate round-2"
        assert result["decision"] == "Reject"
        assert len(spawner.calls) == 1, (
            "resume must skip Pass A and only run the consolidation spawn"
        )
        assert not (pdir / "branches" / "shared" / "reviews" / "round-2").exists()

    def test_complete_round_does_not_trigger_resume(self, project_tree, install_spawner) -> None:
        """When round-1 has consolidated.md, the next run allocates round-2."""
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        r1 = pdir / "branches" / "shared" / "reviews" / "round-1"
        r1.mkdir(parents=True)
        (r1 / "consolidated.md").write_text(
            "# Round 1\n\n## Decision\n\nWeak Accept\n", encoding="utf-8"
        )
        (r1 / "fresh.md").write_text("# Fresh\n", encoding="utf-8")

        spawner = FakeSpawner(scripts=staged_round_scripts(decision="Accept", round_num=2))
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed", result
        assert result["round"] == 2, "complete round-1 should not trigger resume"


class TestDecisionExtractionInPipeline:
    """The AC decision in consolidated.md must win over inlined reviewer decisions."""

    def test_ac_decision_wins_over_reviewer_decisions(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)

        def _script(workspace: Path, prompt: str, idx: int) -> tuple[bool, str | None]:
            rd = _round_dir(workspace, 1)
            for i in range(1, 4):
                (rd / f"reviewer-{i}.md").write_text(
                    f"# Reviewer {i}\n\n## Decision\n\nReject\n", encoding="utf-8"
                )
            (rd / "fresh.md").write_text("# Fresh\n", encoding="utf-8")
            (rd / "revision_delta.md").write_text("skipped: no prior summary\n", encoding="utf-8")
            body = (
                "# Round 1 Meta-Review\n\n"
                "## Notification\n\nRound 1 complete.\n\n"
                "## Area-Chair / Editor Meta-Review\n\n"
                "The AC weighs three Reject votes and decides Borderline.\n\n"
                "## Decision\n\nBorderline\n\n"
                "## Required Revisions\n\n- foo\n\n"
                + "".join(
                    f"\n\n### Reviewer {i}\n\n(inlined)\n\n## Decision\n\nReject\n"
                    for i in range(1, 4)
                )
            )
            (rd / "consolidated.md").write_text(body, encoding="utf-8")
            sp = _summary_path(workspace, 1)
            sp.write_text("Round: 1\nDecision: Borderline\n", encoding="utf-8")
            return True, None

        spawner = FakeSpawner(scripts=[_script])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed"
        assert result["decision"] == "Borderline", (
            "AC's Borderline must win over the three inlined Rejects"
        )


class TestPathSafety:
    def test_rejects_submission_path_outside_project(self, project_tree, install_spawner) -> None:
        port, _pdir = project_tree
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        with pytest.raises(ValueError, match="outside project"):
            review_run(ReviewRunArgs(port=port, submission_path="../../../../../etc"))
        assert spawner.calls == []

    def test_accepts_submission_path_inside_project(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=staged_round_scripts())
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed", result

    def test_rejects_nonexistent_submission_dir(self, project_tree, install_spawner) -> None:
        port, _pdir = project_tree
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(
                port=port,
                submission_path="../shared/handoffs/submissions/never-existed",
            )
        )
        assert result["status"] == "error"
        assert "not found" in result["reason"].lower()


class TestPromptShape:
    def test_reviewer_prompt_is_focused(self, project_tree, install_spawner) -> None:
        """The per-reviewer prompt must scope the spawn to exactly one reviewer."""
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=staged_round_scripts())
        install_spawner(spawner)
        review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        # First 3 calls are per-reviewer prompts.
        for i, (_, prompt) in enumerate(spawner.calls[:3], start=1):
            assert f"reviewer {i}" in prompt.lower(), f"call {i} not scoped to reviewer {i}"
            assert "simulate-reviewer-instance" in prompt
            # Per-reviewer must NOT instruct claude to write fresh.md /
            # consolidated.md / summary — those are owned by later stages.
            assert "Do NOT write" in prompt
            assert "fresh.md" in prompt  # mentioned in the negative list
            assert "consolidated.md" in prompt

    def test_consolidation_prompt_names_outputs(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "shared" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=staged_round_scripts())
        install_spawner(spawner)
        review_run(
            ReviewRunArgs(port=port, submission_path="../shared/handoffs/submissions/round-1")
        )
        # Last call is the consolidation prompt.
        _, prompt = spawner.calls[-1]
        assert "consolidated.md" in prompt
        assert "Decision" in prompt
        # Must mention the seven canonical labels.
        for label in ("Strong Accept", "Borderline", "Strong Reject"):
            assert label in prompt
