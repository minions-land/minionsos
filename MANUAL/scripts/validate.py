#!/usr/bin/env python3
"""Drift detector — keeps the manual honest as MinionsOS evolves.

Runs three checks:
  1. Every @mcp.tool() in minions/tools/mcp/ has a tools/<name>.md page.
  2. Every tools/<name>.md page either matches a real @mcp.tool() OR is
     explicitly marked status: deprecated.
  3. Every page's `source: <file>:<line>` resolves to a real @mcp.tool() decorator.

Exit code 0 = clean. Non-zero = drift; report goes to stdout. Suitable for CI.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANUAL_ROOT = ROOT / "MANUAL"
TOOLS_DIR = MANUAL_ROOT / "tools"
MCP_DIR = ROOT / "minions" / "tools" / "mcp"

DECORATOR_RE = re.compile(r"^\s*@mcp\.tool\(\)\s*$")
DEFLINE_RE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
SOURCE_RE = re.compile(r"^source:\s*(.+?):(\d+)\s*$", re.MULTILINE)
ID_RE = re.compile(r"^id:\s*(.+?)\s*$", re.MULTILINE)
STATUS_RE = re.compile(r"^status:\s*(.+?)\s*$", re.MULTILINE)


EACN3_TS = ROOT / "mcp-servers" / "eacn3" / "plugin" / "index.ts"
EACN3_NAME_RE = re.compile(r'name:\s*"(eacn3_[a-z0-9_]+)"')


def collect_tool_decorators() -> dict[str, str]:
    """Return {tool_name: '<source>:<line>'} for both Python @mcp.tool() AND
    EACN3 TS plugin api.registerTool({...}) entries."""
    found: dict[str, str] = {}
    for py in sorted(MCP_DIR.glob("*.py")):
        if py.name.startswith("_") or py.name == "__init__.py":
            continue
        lines = py.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            if DECORATOR_RE.match(lines[i]):
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                m = DEFLINE_RE.match(lines[j]) if j < len(lines) else None
                if m:
                    name = m.group(1)
                    found[name] = f"minions/tools/mcp/{py.name}:{i+1}"
                    i = j + 1
                    continue
            i += 1
    if EACN3_TS.exists():
        for idx, ln in enumerate(EACN3_TS.read_text(encoding="utf-8").splitlines(), start=1):
            m = EACN3_NAME_RE.search(ln)
            if m:
                found[m.group(1)] = f"mcp-servers/eacn3/plugin/index.ts:{idx}"
    return found


def collect_pages() -> list[tuple[str, dict, Path]]:
    out = []
    for p in sorted(TOOLS_DIR.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        m = FRONTMATTER_RE.match(text)
        if not m:
            continue
        fm_text = m.group(1)
        fm = {
            "id": (ID_RE.search(fm_text).group(1) if ID_RE.search(fm_text) else ""),
            "status": (STATUS_RE.search(fm_text).group(1) if STATUS_RE.search(fm_text) else ""),
            "source": "",
            "source_line": 0,
        }
        sm = SOURCE_RE.search(fm_text)
        if sm:
            fm["source"] = sm.group(1)
            fm["source_line"] = int(sm.group(2))
        out.append((fm["id"], fm, p))
    return out


def main() -> int:
    decorators = collect_tool_decorators()
    pages = collect_pages()
    pages_by_id = {pid: (fm, p) for pid, fm, p in pages}

    errors: list[str] = []
    warnings: list[str] = []

    # 1. tools without pages
    for name, src in decorators.items():
        if name not in pages_by_id:
            errors.append(f"MISSING_PAGE: tool {name} ({src}) has no MANUAL/tools/{name}.md")

    # 2. pages without tools (allow deprecated / domain stub)
    for pid, fm, p in pages:
        if pid not in decorators and fm["status"] not in ("deprecated", "alias"):
            warnings.append(
                f"ORPHAN_PAGE: {p.relative_to(ROOT)} (id={pid!r}) has no matching @mcp.tool(); "
                f"mark status: deprecated or remove"
            )

    # 3. source line drift
    mcp_files: dict[str, list[str]] = {}
    for py in MCP_DIR.glob("*.py"):
        rel = f"minions/tools/mcp/{py.name}"
        mcp_files[rel] = py.read_text(encoding="utf-8").splitlines()
    if EACN3_TS.exists():
        mcp_files["mcp-servers/eacn3/plugin/index.ts"] = EACN3_TS.read_text(encoding="utf-8").splitlines()

    for pid, fm, p in pages:
        if not fm["source"]:
            continue
        if pid not in decorators:
            continue  # already covered by ORPHAN_PAGE
        # check the page's claimed source line is a @mcp.tool() decorator OR an EACN3 name
        rel = fm["source"]
        line = fm["source_line"]
        lines = mcp_files.get(rel)
        if not lines:
            errors.append(f"BAD_SOURCE: {p.relative_to(ROOT)} → {rel} (file does not exist)")
            continue
        if line < 1 or line > len(lines):
            errors.append(f"BAD_SOURCE: {p.relative_to(ROOT)} → {rel}:{line} (line out of range)")
            continue
        actual = lines[line - 1]
        is_python = rel.endswith(".py")
        is_ts = rel.endswith(".ts")
        ok = False
        if is_python and DECORATOR_RE.match(actual):
            ok = True
        if is_ts and (f'"{pid}"' in actual or EACN3_NAME_RE.search(actual)):
            ok = True
        if not ok:
            actual_src = decorators[pid]
            errors.append(
                f"DRIFT: {p.relative_to(ROOT)} claims source={rel}:{line} but that line is "
                f"{actual!r}. Actual location: {actual_src}. Update the page's `source:` field."
            )

    # 4. verbatim-description regression (v15.28)
    # The V1 transform replaced every auto-gen body with a 1-line source
    # pointer to break the silent-drift class confirmed in the v15.28
    # post-compact survival probe. Any new page that re-ingests a verbatim
    # plugin description re-introduces the bug. Block at CI.
    for pid, fm, p in pages:
        body = p.read_text(encoding="utf-8")
        # The marker the gen_eacn3_stubs.py scaffolder used historically.
        # Curated pages don't need this header — they restate discipline,
        # they don't copy descriptions.
        if "## Full description (from EACN3 plugin)" in body:
            errors.append(
                f"VERBATIM_DESCRIPTION: {p.relative_to(ROOT)} contains the "
                "'## Full description (from EACN3 plugin)' header. Per v15.28 "
                "(see /tmp/lookup-experiment-results.md), no page may re-ingest a "
                "verbatim plugin description — that creates silent drift the live "
                "drift detector cannot catch. Replace the body with a 1-line "
                "source pointer or curated discipline notes."
            )

    # Report
    if errors:
        print("# DRIFT — errors:")
        for e in errors:
            print(f"  ✗ {e}")
    if warnings:
        print("# DRIFT — warnings:")
        for w in warnings:
            print(f"  ⚠ {w}")
    if not errors and not warnings:
        print(f"OK — {len(decorators)} tools, {len(pages)} pages, no drift")
        return 0
    print(f"---\n{len(errors)} errors, {len(warnings)} warnings, "
          f"{len(decorators)} tools, {len(pages)} pages")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
