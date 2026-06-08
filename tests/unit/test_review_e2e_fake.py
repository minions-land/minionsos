"""End-to-end review tool tests with a fake spawner.

These tests exercise the full ``review_run`` flow — checklist gate, round
allocation, the single Area-Chair spawn, structural validation of the round
on disk, decision extraction, and return shape — without spawning a real
``claude --print`` subprocess.

The review round is driven by ONE Area-Chair ``claude --print`` process that
runs all three passes and fans reviewer instances out as concurrent foreground
``Task`` subagents. ``review_run`` does not slice the round into separate
subprocesses; it spawns once and then validates the artifacts the Area-Chair
left on disk. A ``FakeSpawner`` simulates that single process's disk side
effects (reviewer-i.md, fresh.md, revision_delta.md, consolidated.md, the
rolling summary). Each test scripts the behaviour to probe one boundary.
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
    (pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1").mkdir(parents=True)
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
    build = submission / "build"
    build.mkdir(parents=True, exist_ok=True)
    (build / "paper.pdf").write_bytes(b"%PDF-1.5\n" + b"0" * 2048 + b"\n%%EOF\n")
    (submission / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}Tiny Study\\end{document}\n",
        encoding="utf-8",
    )


class FakeSpawner:
    """Records calls and runs scripted side effects.

    The signature matches the production ``Spawner`` protocol. ``review_run``
    now calls the spawner exactly once per round (the Area-Chair), so most
    tests script a single behaviour.
    """

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
    d = project_root / "branches" / "main" / "reviews" / f"round-{round_num}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "aspect-notes").mkdir(exist_ok=True)
    return d


def _summary_path(workspace: Path, round_num: int = 1) -> Path:
    project_root = workspace.parent.parent
    p = project_root / "branches" / "main" / "reviews" / "summaries" / f"round-{round_num}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def full_round_script(
    decision: str = "Accept",
    n_reviewers: int = 3,
    write_consolidated: bool = True,
    write_summary: bool = True,
    write_fresh: bool = True,
    write_reviewer_md: bool = True,
    write_revision_delta: bool = True,
    write_aspect_notes: bool = True,
    round_num: int = 1,
) -> Callable[[Path, str, int], tuple[bool, str | None]]:
    """Simulate the single Area-Chair process writing the whole round.

    This mirrors what one ``claude --print`` Area-Chair leaves on disk after
    driving all three passes: per-reviewer reports + aspect notes, fresh.md,
    revision_delta.md, consolidated.md (AC decision first), and the rolling
    summary. Flags let a test omit one artifact to probe structural
    validation.
    """

    def _script(workspace: Path, prompt: str, idx: int) -> tuple[bool, str | None]:
        rd = _round_dir(workspace, round_num)
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
        if write_revision_delta:
            (rd / "revision_delta.md").write_text("skipped: no prior summary\n", encoding="utf-8")
        if write_fresh:
            fresh_body = "# Fresh\n" + "".join(
                f"\n\n## Reviewer {i}\n\n## Decision\n\n{decision}\n"
                for i in range(1, n_reviewers + 1)
            )
            (rd / "fresh.md").write_text(fresh_body, encoding="utf-8")
        if write_consolidated:
            body = (
                f"# Round {round_num} Meta-Review\n\n"
                "## Notification\n\nRound complete.\n\n"
                "## Area-Chair / Editor Meta-Review\n\nThe AC synthesized the reviews.\n\n"
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
            sp = _summary_path(workspace, round_num)
            sp.write_text(
                f"Round: {round_num}\nDecision: {decision}\nUnresolved: none\n",
                encoding="utf-8",
            )
        return True, None

    return _script


class TestChecklistGate:
    """The gate must reject before spawning anything."""

    def test_missing_checklist_rejects_without_spawn(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        _write_manuscript(pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1")
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "rejected"
        assert "checklist" in result["reason"].lower()
        assert spawner.calls == [], "must not spawn claude when checklist is missing"

    def test_failed_required_rejects_without_spawn(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub, all_required_checked=False)
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "rejected"
        assert any("Baseline" in m for m in result["missing_required"])
        assert spawner.calls == []

    def test_markdown_only_manuscript_rejects_without_spawn(
        self, project_tree, install_spawner
    ) -> None:
        """A passing checklist + .md-only package (no compiled PDF) must reject."""
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        (sub / "manuscript.md").write_text("# Tiny Study\n\nResults.\n", encoding="utf-8")
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "rejected"
        assert "pdf" in result["reason"].lower()
        assert spawner.calls == [], "must not spawn claude when manuscript is not a compiled PDF"

    def test_placeholder_pdf_under_1kb_rejects(self, project_tree, install_spawner) -> None:
        """A zero/placeholder PDF (<= 1 KB) does not satisfy the format gate."""
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        (sub / "build").mkdir(parents=True, exist_ok=True)
        (sub / "build" / "paper.pdf").write_bytes(b"%PDF-1.5\n")  # tiny placeholder
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
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
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=[full_round_script(decision=decision)])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed"
        assert result["decision"] == decision
        assert result["round"] == 1
        assert Path(str(result["consolidated_path"])).exists()
        assert Path(str(result["summary_path"])).exists()
        # The round is driven by a SINGLE Area-Chair spawn.
        assert len(spawner.calls) == 1, "one Area-Chair spawn drives the whole round"

    def test_fresh_md_repaired_when_area_chair_skips_it(
        self, project_tree, install_spawner
    ) -> None:
        """fresh.md is a deterministic concat; review_run repairs it if absent."""
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        # Area-Chair writes everything EXCEPT fresh.md.
        spawner = FakeSpawner(scripts=[full_round_script(decision="Accept", write_fresh=False)])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed", result
        fresh = pdir / "branches" / "main" / "reviews" / "round-1" / "fresh.md"
        assert fresh.exists(), "review_run must repair a missing fresh.md by concat"
        body = fresh.read_text(encoding="utf-8")
        for i in range(1, 4):
            assert f"reviewer-{i}" in body or f"Reviewer {i}" in body
        assert len(spawner.calls) == 1

    def test_round_spawn_gets_bounded_timeout(self, project_tree, install_spawner) -> None:
        """The single round spawn must carry the configured wall."""
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=[full_round_script(decision="Accept")])
        install_spawner(spawner)
        review_run(ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1"))
        from minions.tools.review import _review_timeout_seconds

        assert len(spawner.timeouts) == 1
        assert spawner.timeouts[0] == _review_timeout_seconds()
        assert spawner.timeouts[0] > 0

    def test_round_timeout_env_override(self, project_tree, install_spawner, monkeypatch) -> None:
        """MOS_REVIEW_TIMEOUT overrides the round wall."""
        monkeypatch.setenv("MOS_REVIEW_TIMEOUT", "4242")
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=[full_round_script(decision="Accept")])
        install_spawner(spawner)
        review_run(ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1"))
        assert spawner.timeouts[0] == 4242


class TestStructuralValidation:
    """review_run validates artifacts on disk, not the exit code."""

    def test_too_few_reviewers_is_error(self, project_tree, install_spawner) -> None:
        """A round with fewer than the minimum reviewer reports is an error."""
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        # Only 2 reviewer reports — below the default floor of 3.
        spawner = FakeSpawner(scripts=[full_round_script(decision="Accept", n_reviewers=2)])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "error"
        assert "reviewer" in result["reason"].lower()
        assert "at least" in result["reason"].lower()

    def test_missing_consolidated_is_error(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(
            scripts=[full_round_script(decision="Accept", write_consolidated=False)]
        )
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "error"
        assert "consolidated.md" in result["reason"]

    def test_missing_summary_is_error(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=[full_round_script(decision="Accept", write_summary=False)])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "error"
        assert "summary" in result["reason"].lower()

    def test_missing_revision_delta_no_prior_summary_is_repaired(
        self, project_tree, install_spawner
    ) -> None:
        """No-prior-summary round: a missing revision_delta.md is filled in.

        The skip placeholder is as deterministic as fresh.md, so review_run
        writes it rather than hard-failing on a forgotten one-liner.
        """
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(
            scripts=[full_round_script(decision="Accept", write_revision_delta=False)]
        )
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed", result
        rd = pdir / "branches" / "main" / "reviews" / "round-1" / "revision_delta.md"
        assert rd.exists()
        assert "skipped: no prior summary" in rd.read_text(encoding="utf-8")

    def test_missing_revision_delta_with_prior_summary_is_error(
        self, project_tree, install_spawner
    ) -> None:
        """Revision round: a missing revision_delta.md (real model output) errors."""
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        # Complete round-1 + its rolling summary so allocation reaches round-2
        # and a prior_summary is in play (revision-delta becomes mandatory).
        r1 = pdir / "branches" / "main" / "reviews" / "round-1"
        r1.mkdir(parents=True)
        (r1 / "consolidated.md").write_text(
            "# Round 1\n\n## Decision\n\nWeak Accept\n", encoding="utf-8"
        )
        prior = pdir / "branches" / "main" / "reviews" / "summaries" / "round-1.md"
        prior.parent.mkdir(parents=True, exist_ok=True)
        prior.write_text("Round: 1\nDecision: Weak Accept\n", encoding="utf-8")

        spawner = FakeSpawner(
            scripts=[full_round_script(decision="Accept", round_num=2, write_revision_delta=False)]
        )
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(
                port=port,
                submission_path="../main/handoffs/submissions/round-1",
                prior_summary_path=str(prior),
            )
        )
        assert result["status"] == "error"
        assert "revision_delta.md" in result["reason"]

    def test_dynamic_reviewer_count_five_accepted(self, project_tree, install_spawner) -> None:
        """A round may produce up to 5 reviewer instances; that is valid."""
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=[full_round_script(decision="Borderline", n_reviewers=5)])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed", result
        assert result["decision"] == "Borderline"


class TestResilience:
    def test_complete_round_is_validated_not_respawned(self, project_tree, install_spawner) -> None:
        """_run_review_round skips the spawn when the round is already complete.

        This is the idempotency guard: if consolidated.md + the rolling summary
        already exist for the round (a prior run finished it), no new spawn is
        issued — the round is only structurally validated. Tested at the helper
        boundary, since ``review_run``'s round allocator never hands a complete
        round back to ``_run_review_round`` (it would allocate the next round).
        """
        from minions.tools.review import _run_review_round

        port, pdir = project_tree
        workspace = pdir / "branches" / "main"
        # Pre-populate a fully complete round-1 (consolidated + summary).
        full_round_script(decision="Weak Accept")(workspace, "", 0)
        round_dir = pdir / "branches" / "main" / "reviews" / "round-1"
        summary_path = pdir / "branches" / "main" / "reviews" / "summaries" / "round-1.md"

        # No scripts: if the helper tried to spawn, FakeSpawner would fail.
        spawner = FakeSpawner(scripts=[])
        ok, err = _run_review_round(
            spawner=spawner,
            workspace=workspace,
            port=port,
            submission_dir=pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1",
            round_num=1,
            round_dir=round_dir,
            summary_path=summary_path,
            prior_summary=None,
        )
        assert ok, err
        assert len(spawner.calls) == 0, "a complete round must not be re-spawned"

    def test_spawn_failure_returns_error(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)

        def _fail(workspace: Path, prompt: str, idx: int) -> tuple[bool, str | None]:
            return False, "claude review process exited non-zero: 137"

        spawner = FakeSpawner(scripts=[_fail])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "error"
        assert "137" in result["reason"]
        assert result["round"] == 1

    def test_spawn_ok_but_empty_round_is_error(self, project_tree, install_spawner) -> None:
        """Process returns ok but writes nothing -> structural validation fails."""
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)

        def _empty(workspace: Path, prompt: str, idx: int) -> tuple[bool, str | None]:
            return True, None

        spawner = FakeSpawner(scripts=[_empty])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "error"
        assert len(spawner.calls) == 1


class TestRoundAllocation:
    def test_second_run_allocates_round_2(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        # Pre-create a *complete* round-1 (consolidated.md + rolling summary)
        # so allocation moves on to round-2.
        r1 = pdir / "branches" / "main" / "reviews" / "round-1"
        r1.mkdir(parents=True)
        (r1 / "consolidated.md").write_text(
            "# Round 1\n\n## Decision\n\nWeak Accept\n", encoding="utf-8"
        )
        summaries = pdir / "branches" / "main" / "reviews" / "summaries"
        summaries.mkdir(parents=True, exist_ok=True)
        (summaries / "round-1.md").write_text("Round: 1\nDecision: Weak Accept\n", encoding="utf-8")

        spawner = FakeSpawner(scripts=[full_round_script(decision="Accept", round_num=2)])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed", result
        assert result["round"] == 2

    def test_prompt_includes_prior_summary_for_round_2(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        r1 = pdir / "branches" / "main" / "reviews" / "round-1"
        r1.mkdir(parents=True)
        (r1 / "consolidated.md").write_text(
            "# Round 1\n\n## Decision\n\nWeak Accept\n", encoding="utf-8"
        )
        prior = pdir / "branches" / "main" / "reviews" / "summaries" / "round-1.md"
        prior.parent.mkdir(parents=True, exist_ok=True)
        prior.write_text(
            "Round: 1\nDecision: Weak Accept\nUnresolved: thin baselines\n",
            encoding="utf-8",
        )

        spawner = FakeSpawner(scripts=[full_round_script(decision="Accept", round_num=2)])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(
                port=port,
                submission_path="../main/handoffs/submissions/round-1",
                prior_summary_path=str(prior),
            )
        )
        assert result["status"] == "completed", result
        # The single round prompt must reference the prior summary so the
        # Area-Chair runs Pass B / Pass C against it.
        _, prompt = spawner.calls[0]
        assert str(prior) in prompt
        assert "revision" in prompt.lower()

    def test_resumes_incomplete_round_instead_of_allocating_new(
        self, project_tree, install_spawner
    ) -> None:
        """If the most recent round has no consolidated.md, reuse its number.

        Pass A artifacts on disk from a prior crash are not re-spawned blindly;
        the round number is reused. Since consolidated.md/summary are missing,
        the Area-Chair is re-spawned to finish round-1 (not allocate round-2).
        """
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        # Pre-populate round-1 with reviewer reports but NO consolidated.md.
        r1 = pdir / "branches" / "main" / "reviews" / "round-1"
        (r1 / "aspect-notes").mkdir(parents=True)
        for i in range(1, 4):
            (r1 / f"reviewer-{i}.md").write_text(
                f"# Reviewer {i}\n\n## Decision\n\nReject\n", encoding="utf-8"
            )
        (r1 / "fresh.md").write_text("# Fresh\n", encoding="utf-8")
        (r1 / "revision_delta.md").write_text("skipped: no prior summary\n", encoding="utf-8")

        # The re-spawn finishes round-1 (writes consolidated.md + summary).
        spawner = FakeSpawner(scripts=[full_round_script(decision="Reject")])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed", result
        assert result["round"] == 1, "must reuse round-1, not allocate round-2"
        assert result["decision"] == "Reject"
        assert not (pdir / "branches" / "main" / "reviews" / "round-2").exists()

    def test_complete_round_does_not_trigger_resume(self, project_tree, install_spawner) -> None:
        """When round-1 has consolidated.md + summary, the next run allocates round-2."""
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        r1 = pdir / "branches" / "main" / "reviews" / "round-1"
        r1.mkdir(parents=True)
        (r1 / "consolidated.md").write_text(
            "# Round 1\n\n## Decision\n\nWeak Accept\n", encoding="utf-8"
        )
        (r1 / "fresh.md").write_text("# Fresh\n", encoding="utf-8")
        summaries = pdir / "branches" / "main" / "reviews" / "summaries"
        summaries.mkdir(parents=True, exist_ok=True)
        (summaries / "round-1.md").write_text("Round: 1\nDecision: Weak Accept\n", encoding="utf-8")

        spawner = FakeSpawner(scripts=[full_round_script(decision="Accept", round_num=2)])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed", result
        assert result["round"] == 2, "complete round-1 should not trigger resume"

    def test_consolidated_without_summary_resumes_same_round(
        self, project_tree, install_spawner
    ) -> None:
        """A round with consolidated.md but no rolling summary is incomplete.

        Crash window: consolidated.md landed but the summary write didn't. The
        round must be REUSED (resumed) and finished, not abandoned for a fresh
        round-2 — round-number completeness == consolidated.md AND summary.
        """
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        # round-1 has consolidated.md + reviewers + delta, but NO summary.
        r1 = pdir / "branches" / "main" / "reviews" / "round-1"
        (r1 / "aspect-notes").mkdir(parents=True)
        for i in range(1, 4):
            (r1 / f"reviewer-{i}.md").write_text(
                f"# Reviewer {i}\n\n## Decision\n\nReject\n", encoding="utf-8"
            )
        (r1 / "fresh.md").write_text("# Fresh\n", encoding="utf-8")
        (r1 / "revision_delta.md").write_text("skipped: no prior summary\n", encoding="utf-8")
        (r1 / "consolidated.md").write_text(
            "# Round 1\n\n## Decision\n\nReject\n", encoding="utf-8"
        )
        # The resume spawn finishes round-1 by writing the missing summary.
        spawner = FakeSpawner(scripts=[full_round_script(decision="Reject")])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed", result
        assert result["round"] == 1, "must resume round-1, not allocate round-2"
        assert not (pdir / "branches" / "main" / "reviews" / "round-2").exists()


class TestDecisionExtractionInPipeline:
    """The AC decision in consolidated.md must win over inlined reviewer decisions."""

    def test_ac_decision_wins_over_reviewer_decisions(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
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
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
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
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1")
        )
        assert result["status"] == "completed", result

    def test_rejects_nonexistent_submission_dir(self, project_tree, install_spawner) -> None:
        port, _pdir = project_tree
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        result = review_run(
            ReviewRunArgs(
                port=port,
                submission_path="../main/handoffs/submissions/never-existed",
            )
        )
        assert result["status"] == "error"
        assert "not found" in result["reason"].lower()


class TestPromptShape:
    def test_round_prompt_sets_concurrency_contract(self, project_tree, install_spawner) -> None:
        """The single round prompt must pin the band + the no-background rule."""
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        review_run(ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1"))
        _, prompt = spawner.calls[0]
        low = prompt.lower()
        # Reviewer band.
        assert "at least 3" in low and "at most 5" in low
        # Concurrency primitive + the explicit no-background guardrail.
        assert "concurrent" in low
        assert "task" in low
        assert "background" in low
        assert "workflow" in low

    def test_round_prompt_names_outputs(self, project_tree, install_spawner) -> None:
        port, pdir = project_tree
        sub = pdir / "branches" / "main" / "handoffs" / "submissions" / "round-1"
        _write_manuscript(sub)
        _write_checklist(sub)
        spawner = FakeSpawner(scripts=[full_round_script()])
        install_spawner(spawner)
        review_run(ReviewRunArgs(port=port, submission_path="../main/handoffs/submissions/round-1"))
        _, prompt = spawner.calls[0]
        assert "consolidated.md" in prompt
        assert "fresh.md" in prompt
        assert "revision_delta.md" in prompt
        for label in ("Strong Accept", "Borderline", "Strong Reject"):
            assert label in prompt
