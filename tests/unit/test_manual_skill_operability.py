"""Regression tests for Skill exposure operability."""

from __future__ import annotations

import subprocess
import sys
from importlib import util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _load_validator() -> ModuleType:
    path = ROOT / "MANUAL" / "scripts" / "validate_skill_operability.py"
    spec = util.spec_from_file_location("validate_skill_operability_under_test", path)
    assert spec is not None
    module = util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_skill_operability_validator_passes() -> None:
    result = subprocess.run(
        [sys.executable, "MANUAL/scripts/validate_skill_operability.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MinionsOS repository Role-skill semantics" in result.stdout


def test_role_facing_docs_cannot_use_native_skill_call(tmp_path: Path, monkeypatch) -> None:
    validator = _load_validator()
    doc = tmp_path / "SYSTEM.md"
    doc.write_text("Escalate via `Skill(think-in-parallel)`.\n", encoding="utf-8")
    monkeypatch.setattr(validator, "ROLE_FACING_MARKDOWN", [doc])
    monkeypatch.setattr(validator, "ROOT", tmp_path)

    errors: list[str] = []
    validator.check_role_docs_do_not_call_native_skill(errors)

    assert any("Skill(think-in-parallel)" in error for error in errors)


def test_role_facing_docs_cannot_depend_on_host_skill_root(tmp_path: Path, monkeypatch) -> None:
    validator = _load_validator()
    doc = tmp_path / "SYSTEM.md"
    doc.write_text("Read `~/.claude/skills/think-then-act/SKILL.md`.\n", encoding="utf-8")
    monkeypatch.setattr(validator, "ROLE_FACING_MARKDOWN", [doc])
    monkeypatch.setattr(validator, "ROOT", tmp_path)

    errors: list[str] = []
    validator.check_role_docs_do_not_call_native_skill(errors)

    assert any("host-level" in error for error in errors)


def test_direct_role_skill_rejects_native_only_frontmatter(tmp_path: Path, monkeypatch) -> None:
    validator = _load_validator()
    skills = tmp_path / "minions" / "roles" / "common" / "skills"
    skills.mkdir(parents=True)
    (skills / "bad.md").write_text(
        "---\nname: bad\ndescription: Native-only metadata.\nstatus: active\n---\n\n# Bad\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    monkeypatch.setattr(validator, "ROLE_SKILL_DIRS", [skills])

    errors: list[str] = []
    validator.check_direct_role_skill_metadata(errors)

    assert any("must declare slug" in error for error in errors)
    assert any("must declare summary" in error for error in errors)
    assert any("non-delivery key" in error for error in errors)
