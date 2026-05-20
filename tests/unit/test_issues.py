"""Tests for the runtime issue tracker (``mos_issue_report``).

The tracker is a pure file-backed surface — no git, no EACN, no
project lifecycle plumbing — so the tests use a per-test
``MINIONS_PROJECTS_ROOT`` to redirect ``project_{port}/issues/`` into
``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from minions.errors import ProjectError
from minions.tools import issues as _issues
from minions.tools.issues import (
    IssueReportArgs,
    archive_issues,
    list_issues,
    report_issue,
    tail_issues,
)


@pytest.fixture
def issue_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    projects_root = tmp_path / "projects-root"
    projects_root.mkdir()
    archive_root = tmp_path / "host-archive"
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(projects_root))
    monkeypatch.setenv("MINIONS_PROJECT_PORT", "9001")
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
    monkeypatch.setenv("MINIONS_PROJECT_PHASE", "execute")
    # Redirect the host-level archive away from the user's real home dir.
    monkeypatch.setattr(
        _issues,
        "host_issues_archive_dir",
        lambda: archive_root,
        raising=True,
    )
    return {
        "port": 9001,
        "projects_root": projects_root,
        "archive_root": archive_root,
    }


def _make_args(**overrides: object) -> IssueReportArgs:
    base = {
        "title": "mos_scratchpad_append rejects valid edges",
        "severity": "P1",
        "component": "tool",
        "summary": (
            "Calling mos_scratchpad_append with a hypothesis->experiment edge raises ValidationError."
        ),
        "steps_to_reproduce": ["call mos_scratchpad_append with edges=[{...}]"],
        "expected": "edge appended",
        "actual": "ValidationError raised",
        "evidence": ["project_9001/logs/role-coder.log:142"],
        "impact": "blocks recording experiment outcomes",
        "workaround": "manually patch dag.json",
    }
    base.update(overrides)
    return IssueReportArgs(**base)  # type: ignore[arg-type]


def test_report_appends_record(issue_env: dict) -> None:
    record = report_issue(_make_args())
    assert record["id"] == "ISS-9001-1"
    assert record["reporter"] == {
        "role": "coder",
        "project_port": 9001,
        "phase": "execute",
    }
    assert record["severity"] == "P1"
    assert record["component"] == "tool"
    issues = list_issues(9001)
    assert len(issues) == 1
    assert issues[0]["id"] == "ISS-9001-1"
    assert issues[0]["title"] == record["title"]


def test_id_sequencing_across_multiple_reports(issue_env: dict) -> None:
    report_issue(_make_args(title="first"))
    report_issue(_make_args(title="second"))
    report_issue(_make_args(title="third"))
    issues = list_issues(9001)
    assert [r["id"] for r in issues] == [
        "ISS-9001-1",
        "ISS-9001-2",
        "ISS-9001-3",
    ]
    assert [r["title"] for r in issues] == ["first", "second", "third"]


def test_reporter_uses_env_identity(issue_env: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")
    record = report_issue(_make_args())
    assert record["reporter"]["role"] == "ethics"
    assert record["reporter"]["project_port"] == 9001


def test_phase_optional(issue_env: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINIONS_PROJECT_PHASE", raising=False)
    record = report_issue(_make_args())
    assert record["reporter"]["phase"] is None


def test_missing_port_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MINIONS_PROJECT_PORT", raising=False)
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    with pytest.raises(ProjectError):
        report_issue(_make_args())


def test_explicit_port_overrides_env(issue_env: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    record = report_issue(_make_args(), port=9002)
    assert record["reporter"]["project_port"] == 9002
    assert record["id"] == "ISS-9002-1"
    assert list_issues(9002)
    assert list_issues(9001) == []


def test_severity_must_be_valid() -> None:
    with pytest.raises(ValidationError):
        IssueReportArgs(  # type: ignore[arg-type]
            title="x",
            severity="P5",
            component="tool",
            summary="x",
        )


def test_component_must_be_valid() -> None:
    with pytest.raises(ValidationError):
        IssueReportArgs(  # type: ignore[arg-type]
            title="x",
            severity="P2",
            component="frontend",
            summary="x",
        )


def test_minimal_args_accepted() -> None:
    args = IssueReportArgs(  # type: ignore[arg-type]
        title="t",
        severity="P3",
        component="other",
        summary="s",
    )
    assert args.steps_to_reproduce == []
    assert args.evidence == []
    assert args.workaround is None


def test_tail_returns_recent(issue_env: dict) -> None:
    for i in range(5):
        report_issue(_make_args(title=f"issue-{i}"))
    last_two = tail_issues(9001, 2)
    assert [r["title"] for r in last_two] == ["issue-3", "issue-4"]
    assert tail_issues(9001, 0) == []


def test_list_skips_malformed_lines(issue_env: dict) -> None:
    report_issue(_make_args(title="ok"))
    from minions.paths import project_issues_jsonl

    path = project_issues_jsonl(9001)
    with path.open("a", encoding="utf-8") as fh:
        fh.write("not json\n")
        fh.write("\n")
    report_issue(_make_args(title="ok2"))
    issues = list_issues(9001)
    assert len(issues) == 2
    assert {r["title"] for r in issues} == {"ok", "ok2"}


def test_archive_copies_jsonl(issue_env: dict) -> None:
    report_issue(_make_args(title="a"))
    report_issue(_make_args(title="b"))
    dst = archive_issues(9001, closed_ts="2026-05-19T00:00:00+00:00")
    assert dst is not None
    assert dst.exists()
    assert dst.parent == issue_env["archive_root"]
    assert dst.name.startswith("9001-")
    lines = [line for line in dst.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert [r["title"] for r in parsed] == ["a", "b"]


def test_archive_noop_without_issues(issue_env: dict) -> None:
    assert archive_issues(9001) is None


def test_archive_noop_for_empty_file(issue_env: dict) -> None:
    from minions.paths import project_issues_dir, project_issues_jsonl

    project_issues_dir(9001).mkdir(parents=True, exist_ok=True)
    project_issues_jsonl(9001).write_text("", encoding="utf-8")
    assert archive_issues(9001) is None


def test_jsonl_is_valid_per_line(issue_env: dict) -> None:
    """Every appended line must be a standalone JSON object — required so a
    downstream triage agent can stream-parse without buffering the whole file."""
    for i in range(3):
        report_issue(_make_args(title=f"t{i}"))
    from minions.paths import project_issues_jsonl

    path = project_issues_jsonl(9001)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        assert set(obj.keys()) >= {
            "id",
            "ts",
            "reporter",
            "title",
            "severity",
            "component",
            "summary",
        }
