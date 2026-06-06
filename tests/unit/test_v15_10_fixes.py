"""Tests for v15.10 — GitHub Issues #13 + #14.

- Issue #13: book ingest/lint commit amplification.
- Issue #14: steady-state turn unbounded reads.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from minions.lifecycle import project as project_mod
from minions.paths import (
    project_dir,
    project_shared_workspace,
    project_state_dir,
    project_workspace_root,
)


def _git(args: list[str], cwd: Path) -> str:
    res = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)
    return res.stdout


def _shared_log_count(workspace: Path) -> int:
    return sum(1 for line in _git(["log", "--oneline"], workspace).splitlines() if line.strip())


@pytest.fixture
def shared_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    author = tmp_path / "author"
    projects_root = tmp_path / "projects-root"
    author.mkdir()
    projects_root.mkdir()
    _git(["init", "-q"], author)
    _git(["config", "user.email", "t@e.com"], author)
    _git(["config", "user.name", "test"], author)
    (author / "README.md").write_text("init\n", encoding="utf-8")
    _git(["add", "."], author)
    _git(["commit", "-qm", "init"], author)

    monkeypatch.setenv("MINIONS_AUTHOR_REPO", str(author))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(projects_root))

    port = 39911
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))

    project_dir(port).mkdir(parents=True, exist_ok=True)
    project_workspace_root(port).mkdir(parents=True, exist_ok=True)
    project_state_dir(port).mkdir(parents=True, exist_ok=True)

    project_mod._seed_per_project_repo(port)
    project_mod._create_worktree(port, "HEAD")
    project_mod._create_shared_worktree(port)

    shared = project_shared_workspace(port)
    notes_dir = shared / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    return {"port": port, "shared": shared, "notes_dir": notes_dir}


# --- Issue #13 ---------------------------------------------------------


def test_publish_files_to_shared_one_commit(shared_project: dict[str, object]) -> None:
    """Multi-file batch publish lands as exactly one commit on shared."""
    from minions.tools.publish import mos_publish_files_to_shared

    port: int = int(shared_project["port"])  # type: ignore[arg-type]
    shared: Path = shared_project["shared"]  # type: ignore[assignment]

    src_dir = Path(shared_project["notes_dir"]) / "_stage"  # not used; we stage outside
    stage = Path(shared) / "_stage_outside"
    stage.mkdir(parents=True, exist_ok=True)
    src_dir = stage  # alias
    a = src_dir / "a.md"
    b = src_dir / "b.md"
    c = src_dir / "c.md"
    a.write_text("A1\n", encoding="utf-8")
    b.write_text("B1\n", encoding="utf-8")
    c.write_text("C1\n", encoding="utf-8")

    before = _shared_log_count(shared)
    result = mos_publish_files_to_shared(
        role="ethics",
        files=[
            {"src_path": str(a.resolve()), "dst_subpath": "notes/a.md"},
            {"src_path": str(b.resolve()), "dst_subpath": "notes/b.md"},
            {"src_path": str(c.resolve()), "dst_subpath": "notes/c.md"},
        ],
        commit_message="ethics: batch publish",
        port=port,
    )
    after = _shared_log_count(shared)
    assert after - before == 1
    assert result["commit_sha"] is not None
    assert (shared / "notes/a.md").read_text() == "A1\n"
    assert (shared / "notes/b.md").read_text() == "B1\n"
    assert (shared / "notes/c.md").read_text() == "C1\n"


def test_book_ingest_yields_single_commit(shared_project: dict[str, object]) -> None:
    """mos_book_ingest writes 3-4 files but produces exactly 1 commit."""
    from minions.tools.book import mos_book_ingest

    port: int = int(shared_project["port"])  # type: ignore[arg-type]
    shared: Path = shared_project["shared"]  # type: ignore[assignment]

    handoffs = shared / "handoffs"
    handoffs.mkdir(parents=True, exist_ok=True)
    src = handoffs / "expert-tokenizer.md"
    src.write_text("# tokenizer note\nThe BPE merger keeps frequent pairs.\n", encoding="utf-8")

    before = _shared_log_count(shared)
    mos_book_ingest(
        src_path="handoffs/expert-tokenizer.md",
        source_role="expert",
        source_slug="tokenizer",
        title="BPE tokenizer",
        port=port,
    )
    after = _shared_log_count(shared)
    assert after - before == 1, f"expected exactly 1 ingest commit, got {after - before}"
    assert (shared / "book/sources/expert-tokenizer.md").exists()
    assert (shared / "book/index.md").exists()
    assert (shared / "book/log.md").exists()


def test_book_lint_yields_single_commit(shared_project: dict[str, object]) -> None:
    from minions.tools.book import mos_book_ingest, mos_book_lint

    port: int = int(shared_project["port"])  # type: ignore[arg-type]
    shared: Path = shared_project["shared"]  # type: ignore[assignment]

    handoffs = shared / "handoffs"
    handoffs.mkdir(parents=True, exist_ok=True)
    src = handoffs / "coder-x.md"
    src.write_text("# x\nclaim.\n", encoding="utf-8")
    mos_book_ingest(
        src_path="handoffs/coder-x.md",
        source_role="coder",
        source_slug="x",
        port=port,
    )
    before = _shared_log_count(shared)
    mos_book_lint(port=port)
    after = _shared_log_count(shared)
    assert after - before <= 1, f"expected at most 1 lint commit, got {after - before}"


def test_book_ingest_batch_single_commit_for_all_sources(
    shared_project: dict[str, object],
) -> None:
    from minions.tools.book import mos_book_ingest_batch

    port: int = int(shared_project["port"])  # type: ignore[arg-type]
    shared: Path = shared_project["shared"]  # type: ignore[assignment]

    handoffs = shared / "handoffs"
    handoffs.mkdir(parents=True, exist_ok=True)
    for slug in ("alpha", "beta", "gamma"):
        (handoffs / f"coder-{slug}.md").write_text(f"# {slug}\nbody.\n", encoding="utf-8")

    before = _shared_log_count(shared)
    mos_book_ingest_batch(
        sources=[
            {
                "src_path": f"handoffs/coder-{slug}.md",
                "source_role": "coder",
                "source_slug": slug,
            }
            for slug in ("alpha", "beta", "gamma")
        ],
        port=port,
    )
    after = _shared_log_count(shared)
    assert after - before == 1, f"batch of 3 should be 1 commit, got {after - before}"


# --- Issue #14 ---------------------------------------------------------
