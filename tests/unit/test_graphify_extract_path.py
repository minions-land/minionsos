"""Tests for ``mcp-servers/graphify/extract.py`` workspace resolution.

GitHub Issue #31: ``extract.py`` resolved the project workspace via
``_REPO_ROOT / f"project_{port}"`` where ``_REPO_ROOT`` is the MinionsOS
checkout. That only works when projects live INSIDE MinionsOS; on the
documented sibling-of-MinionsOS layout (`MinionsOS/` and `project_<port>/`
sharing a parent) it crashed with FileNotFoundError and Noter silently
failed the Shelf rebuild for hours.

The fix delegates workspace resolution to
``minions.paths.project_workspace`` so extract.py honors the same
``MINIONS_AUTHOR_REPO`` / ``MINIONS_PROJECTS_ROOT`` resolution as the
rest of MinionsOS.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACT_PY = REPO_ROOT / "mcp-servers" / "graphify" / "extract.py"


def _load_extract():
    """Import extract.py as a module without invoking its CLI."""
    spec = importlib.util.spec_from_file_location("graphify_extract", EXTRACT_PY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {EXTRACT_PY}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestProjectWorkspaceResolution:
    def test_resolves_via_minions_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With MINIONS_PROJECTS_ROOT set to a sibling directory, the
        resolver must find project_<port>/ there rather than crashing on
        the legacy MinionsOS/project_<port>/ path."""
        sibling = tmp_path / "sibling-projects"
        ws = sibling / "project_31337"
        ws.mkdir(parents=True)
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(sibling))

        mod = _load_extract()
        resolved = mod._project_workspace(31337)
        assert resolved == ws

    def test_missing_workspace_raises_filenotfound(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the configured projects root has no project_<port>/, the
        helper raises FileNotFoundError (not ImportError or AttributeError)
        so Noter's subprocess wrapper sees a clean exit-1 it can log."""
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
        mod = _load_extract()
        with pytest.raises(FileNotFoundError, match="Project workspace not found"):
            mod._project_workspace(99999)

    def test_adds_minions_root_to_syspath(self) -> None:
        """Importing the module side-effects sys.path so the
        minions.paths import works when extract.py is run as a script
        from any cwd. Regression check that the side-effect persists."""
        # Drop any cached graphify_extract first so the module re-runs.
        sys.modules.pop("graphify_extract", None)
        _load_extract()
        assert str(REPO_ROOT) in sys.path
