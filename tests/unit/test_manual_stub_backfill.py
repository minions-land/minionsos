"""Regression tests for lookup.py stub→source docstring backfill.

The role contract tells agents to look a tool up in the MANUAL. 76% of tool
pages were bare stubs ("No curated page yet"), so the lookup returned nothing
actionable and the agent had to guess — the live failure that motivated this.
``backfill_from_source`` resolves the real contract from the code at read time
so a stub still yields the docstring. These tests pin that behavior, including
the two parser edge cases that initially misfired (``async def`` and
multi-line signatures).
"""

from __future__ import annotations

import subprocess
import sys
from importlib import util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _load_lookup() -> ModuleType:
    path = ROOT / "MANUAL" / "scripts" / "lookup.py"
    spec = util.spec_from_file_location("lookup_under_test", path)
    assert spec is not None
    module = util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_curated_page_is_untouched() -> None:
    lookup = _load_lookup()
    curated = "---\nstatus: curated\n---\n\n# x\n\nReal body.\n"
    assert lookup.backfill_from_source(curated) == curated


def test_simple_def_docstring_backfilled() -> None:
    lookup = _load_lookup()
    doc = lookup._extract_py_docstring("minions/tools/mcp/spawn_tools.py", 102)
    assert doc is not None
    assert "Terminate a resident role" in doc
    assert "tmux" in doc


def test_async_def_with_multiline_signature_backfilled() -> None:
    """mos_book_ingest_batch is `async def` with a multi-line signature."""
    out = subprocess.run(
        [sys.executable, "MANUAL/scripts/lookup.py", "--id", "mos_book_ingest_batch"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0
    assert "Contract (from source docstring)" in out.stdout
    assert "Ingest multiple shared artifacts" in out.stdout


def test_ts_description_backfilled() -> None:
    lookup = _load_lookup()
    desc = lookup._extract_ts_description(
        "mcp-servers/eacn3/plugin/index.ts", 531
    )
    assert desc is not None
    assert "agent" in desc.lower()


def test_stub_without_resolvable_source_is_left_as_is() -> None:
    lookup = _load_lookup()
    stub = (
        "---\nstatus: stub\nsource: minions/does/not/exist.py:1\n---\n\n"
        "No curated MANUAL page yet.\n"
    )
    # no crash, no spurious Contract section
    assert "Contract (from source docstring)" not in lookup.backfill_from_source(stub)
