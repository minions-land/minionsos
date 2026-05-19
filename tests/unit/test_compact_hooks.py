"""Tests for the PreCompact / PostCompact hook scripts.

These hooks are run by Claude Code as standalone subprocesses
(``python3 minions/hooks/<name>.py``), so the tests treat them as black
boxes: feed JSON on stdin, assert on stdout / stderr / side-effect files.
We do not import the modules — the hooks must work without the package
being importable in the runner.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRE_HOOK = REPO_ROOT / "minions" / "hooks" / "pre_compact_science.py"
POST_HOOK = REPO_ROOT / "minions" / "hooks" / "post_compact_dag.py"


def _run(
    hook: Path,
    stdin: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a hook script with the given stdin and env overrides."""
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    return subprocess.run(
        [sys.executable, str(hook)],
        input=stdin,
        capture_output=True,
        text=True,
        env=proc_env,
        check=False,
    )


# ---------------------------------------------------------------------------
# PreCompact
# ---------------------------------------------------------------------------


class TestPreCompact:
    def test_empty_stdin_still_emits_brief(self) -> None:
        result = _run(PRE_HOOK, stdin="")
        assert result.returncode == 0, result.stderr
        assert "## Working_on" in result.stdout
        assert "## Pending_plans" in result.stdout
        assert "L1 — Exploration DAG" in result.stdout
        assert "L2 — Wiki" in result.stdout
        assert "L3 — Structural index" in result.stdout

    def test_existing_instructions_are_prepended(self) -> None:
        payload = json.dumps({"trigger": "manual", "custom_instructions": "PRIOR-MARKER"})
        result = _run(PRE_HOOK, stdin=payload)
        assert result.returncode == 0
        assert result.stdout.startswith("PRIOR-MARKER\n\n")
        assert "## Working_on" in result.stdout

    def test_no_placeholder_leaks(self) -> None:
        result = _run(PRE_HOOK, stdin="{}")
        # Authoring-time placeholders must never reach the compact model.
        for marker in ("BODY_PART", "REPLACE_ME", "PLACEHOLDER"):
            assert marker not in result.stdout, f"placeholder {marker!r} leaked"

    def test_hard_cap_rule_present(self) -> None:
        # The hard cap is the explicit lever that keeps summaries cheap.
        result = _run(PRE_HOOK, stdin="{}")
        assert "hard cap 2000 tokens" in result.stdout
        assert "Cite IDs and paths" in result.stdout

    def test_malformed_json_does_not_block(self) -> None:
        # Hook must never block /compact with a non-zero exit, even on garbage.
        result = _run(PRE_HOOK, stdin="this is not json")
        assert result.returncode == 0
        assert "## Working_on" in result.stdout


# ---------------------------------------------------------------------------
# PostCompact
# ---------------------------------------------------------------------------


SAMPLE_SUMMARY = """\
## Working_on
- E-002 driving tokenizer ablation

## Next_action
- mos_dag_summary() then mos_await_events()

## New_or_changed_nodes
- E-002 — tokenizer ablation (verified)
- R-003 — sweep result (tentative)

## Pending_plans
- Q-007 — Writer asked for plot

## Open_questions
- Q-008 — does HF tokenizer match SentencePiece?

## Blocked_on
- waiting on coder@2026-05-19T12:00Z to land PR

## Dead_ends
- DEAD-004 — abandoned: distillation underperformed

## Notes
- mid-flight: writer wants Figure 3 redone before submission
"""


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Create a project_<port>/branches/shared/exploration/ tree mirroring
    the layout that lives under ``MINIONS_ROOT.parent``.

    The hook resolves the project dir relative to ``MINIONS_ROOT.parent``,
    so we set ``MINIONS_ROOT=tmp_path/MinionsOS`` and create the project
    under ``tmp_path/project_<port>``.
    """
    port = 99001
    fake_minions_root = tmp_path / "MinionsOS"
    fake_minions_root.mkdir()
    (tmp_path / f"project_{port}" / "branches" / "shared" / "exploration").mkdir(parents=True)
    return tmp_path


def _seed_dag(project_root: Path, port: int, ids: list[str]) -> None:
    dag_path = project_root / f"project_{port}" / "branches" / "shared" / "exploration" / "dag.json"
    dag_path.write_text(
        json.dumps({"nodes": [{"id": i, "type": "x", "text": ""} for i in ids], "edges": []}),
        encoding="utf-8",
    )


def _read_journal(project_root: Path, port: int) -> list[dict]:
    journal = (
        project_root
        / f"project_{port}"
        / "branches"
        / "shared"
        / "exploration"
        / "journal.jsonl"
    )
    if not journal.exists():
        return []
    return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line]


class TestPostCompact:
    def test_empty_stdin_no_op(self, project_dir: Path) -> None:
        result = _run(
            POST_HOOK,
            stdin="",
            env={
                "MINIONS_PROJECT_PORT": "99001",
                "MINIONS_ROOT": str(project_dir / "MinionsOS"),
            },
        )
        assert result.returncode == 0
        assert _read_journal(project_dir, 99001) == []

    def test_writes_to_correct_journal_path(self, project_dir: Path) -> None:
        port = 99001
        _seed_dag(project_dir, port, ["E-002"])
        payload = json.dumps({"trigger": "auto", "compact_summary": SAMPLE_SUMMARY})
        result = _run(
            POST_HOOK,
            stdin=payload,
            env={
                "MINIONS_PROJECT_PORT": str(port),
                "MINIONS_ROLE_NAME": "coder",
                "MINIONS_ROOT": str(project_dir / "MinionsOS"),
            },
        )
        assert result.returncode == 0, result.stderr
        entries = _read_journal(project_dir, port)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["op"] == "post_compact_extract"
        assert entry["role"] == "coder"
        assert entry["trigger"] == "auto"
        assert entry["summary_chars"] == len(SAMPLE_SUMMARY)

    def test_extracts_pointer_shaped_fields(self, project_dir: Path) -> None:
        port = 99001
        _seed_dag(project_dir, port, ["E-002"])
        payload = json.dumps({"trigger": "auto", "compact_summary": SAMPLE_SUMMARY})
        _run(
            POST_HOOK,
            stdin=payload,
            env={
                "MINIONS_PROJECT_PORT": str(port),
                "MINIONS_ROOT": str(project_dir / "MinionsOS"),
            },
        )
        extract = _read_journal(project_dir, port)[0]["extract"]
        assert extract["new_or_changed_node_ids"] == ["E-002", "R-003"]
        assert extract["pending_plan_node_ids"] == ["Q-007"]
        assert extract["dead_end_node_ids"] == ["DEAD-004"]
        assert "E-002" in extract["known_node_refs"]
        # R-003 was cited but isn't in the seeded dag.json — must show up as unknown.
        assert "R-003" in extract["unknown_node_refs"]

    def test_no_journal_write_when_project_missing(self, tmp_path: Path) -> None:
        # MINIONS_PROJECT_PORT set but the project dir doesn't exist.
        # Hook must not crash and must not create a stray journal.
        fake_root = tmp_path / "MinionsOS"
        fake_root.mkdir()
        payload = json.dumps({"trigger": "auto", "compact_summary": SAMPLE_SUMMARY})
        result = _run(
            POST_HOOK,
            stdin=payload,
            env={
                "MINIONS_PROJECT_PORT": "65535",
                "MINIONS_ROOT": str(fake_root),
            },
        )
        assert result.returncode == 0
        # Nothing should have been created under tmp_path.
        leaked = list(tmp_path.glob("project_*/branches/shared/exploration/journal.jsonl"))
        assert leaked == []

    def test_malformed_json_does_not_crash(self, project_dir: Path) -> None:
        result = _run(
            POST_HOOK,
            stdin="not json at all",
            env={
                "MINIONS_PROJECT_PORT": "99001",
                "MINIONS_ROOT": str(project_dir / "MinionsOS"),
            },
        )
        assert result.returncode == 0
        assert _read_journal(project_dir, 99001) == []
