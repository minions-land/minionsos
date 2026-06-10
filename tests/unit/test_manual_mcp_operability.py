"""Regression tests for MCP MANUAL hot-path operability."""

from __future__ import annotations

import subprocess
import sys
from importlib import util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_validator() -> ModuleType:
    path = ROOT / "MANUAL" / "scripts" / "validate_mcp_operability.py"
    spec = util.spec_from_file_location("validate_mcp_operability_under_test", path)
    assert spec is not None
    module = util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_mcp_operability_validator_passes() -> None:
    result = subprocess.run(
        [sys.executable, "MANUAL/scripts/validate_mcp_operability.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MCP tool pages have aligned metadata" in result.stdout
    assert "critical pages are operational" in result.stdout


def test_lookup_surfaces_curated_gru_event_pages() -> None:
    for page_id in ("mos_unread_summary", "mos_get_events"):
        result = subprocess.run(
            [sys.executable, "MANUAL/scripts/lookup.py", "--id", page_id],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "No curated MANUAL page yet" not in result.stdout
        assert "## Signature" in result.stdout
        assert "Gru" in result.stdout


def test_operability_gate_rejects_stub_critical_page(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = _load_validator()
    fake_path = ROOT / "MANUAL" / "tools" / "mos_get_events.md"
    monkeypatch.setattr(
        validator,
        "CRITICAL_TOOLS",
        {"mos_get_events": {"domain": "runtime", "must_contain": ["## Signature"]}},
    )
    monkeypatch.setattr(
        validator,
        "page",
        lambda _tool_name: (
            {"domain": "runtime", "auth": ["gru"], "status": "stub", "since": "stub"},
            "No curated MANUAL page yet.",
            fake_path,
        ),
    )

    errors: list[str] = []
    validator.check_tool_pages(errors)

    assert any("generated stub" in error for error in errors)
    assert any("## Signature" in error for error in errors)


def test_operability_gate_rejects_auth_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = _load_validator()
    fake_path = ROOT / "MANUAL" / "tools" / "mos_get_events.md"
    monkeypatch.setattr(
        validator,
        "iter_tool_pages",
        lambda: [
            (
                "mos_get_events",
                {"auth": ["expert"], "status": "stable", "since": "stable"},
                "## Signature\n",
                fake_path,
            )
        ],
    )

    errors: list[str] = []
    validator.check_all_tool_metadata(errors)

    assert any("expected server authz ['gru']" in error for error in errors)


def test_operability_gate_rejects_stable_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = _load_validator()
    fake_path = ROOT / "MANUAL" / "tools" / "eacn3_get_events.md"
    monkeypatch.setattr(
        validator,
        "iter_tool_pages",
        lambda: [
            (
                "eacn3_get_events",
                {"auth": ["gru", "expert", "ethics"], "status": "stable", "since": "stable"},
                "No curated MANUAL page yet.",
                fake_path,
            )
        ],
    )

    errors: list[str] = []
    validator.check_all_tool_metadata(errors)

    assert any("placeholder body but status is not stub" in error for error in errors)
    assert any("placeholder body but since is not stub" in error for error in errors)
