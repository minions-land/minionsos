#!/usr/bin/env python3
"""Scaffold tool stubs from @mcp.tool() decorators in minions/tools/mcp/*.

For every @mcp.tool() decorator without a corresponding tools/<name>.md page,
write a stub page with frontmatter + skeleton body. Existing pages are NEVER
overwritten — this is a scaffold-only tool. Hand-curated pages are sacred.

Usage:
    python3 MANUAL/scripts/gen_tool_stubs.py             # write missing stubs
    python3 MANUAL/scripts/gen_tool_stubs.py --dry-run   # report only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANUAL_TOOLS = ROOT / "MANUAL" / "tools"
MCP_DIR = ROOT / "minions" / "tools" / "mcp"

DECORATOR_RE = re.compile(r"^\s*@mcp\.tool\(\)\s*$")
DEFLINE_RE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(")

DOMAIN_BY_FILE = {
    "project_tools.py": "lifecycle",
    "spawn_tools.py": "lifecycle",
    "signboard_tools.py": "lifecycle",
    "memory_tools.py": "memory",
    "reel_tools.py": "memory",
    "experiment_tools.py": "experiments",
    "publish_tools.py": "publish",
    "paper_tools.py": "papers",
    "evaluator_tools.py": "deliverables",
    "visual_tools.py": "visual",
    "runtime_tools.py": "runtime",
    "role_evolution_tools.py": "evolution",
}

# Default auth — overridden per-tool when known. Placeholder, refined later.
DEFAULT_AUTH = {
    "lifecycle": ["gru"],
    "memory": ["*"],
    "experiments": ["expert"],
    "publish": ["*"],
    "papers": ["expert"],
    "deliverables": ["gru"],
    "visual": ["ethics", "expert", "gru"],
    "runtime": ["*"],
    "evolution": ["gru"],
}


def find_tools(mcp_dir: Path):
    """Yield (tool_name, source_path:line, domain) for every @mcp.tool() decorator."""
    for py in sorted(mcp_dir.glob("*.py")):
        if py.name.startswith("_") or py.name == "__init__.py":
            continue
        domain = DOMAIN_BY_FILE.get(py.name, "")
        lines = py.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            if DECORATOR_RE.match(lines[i]):
                # next non-empty line should be the def
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                m = DEFLINE_RE.match(lines[j]) if j < len(lines) else None
                if m:
                    name = m.group(1)
                    src = f"minions/tools/mcp/{py.name}:{i + 1}"
                    yield name, src, domain
                    i = j + 1
                    continue
            i += 1


STUB_TEMPLATE = """---
id: {name}
kind: tool
domain: {domain}
auth: [{auth}]
source: {source}
since: stub
keywords: []
related: []
status: stub
---

# {name}

**One line:** STUB — fill in.

## Signature
See source: `{source}`.

## Args
TODO.

## Pitfalls
None recorded yet.

## See also
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    MANUAL_TOOLS.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped_existing = 0
    for name, source, domain in find_tools(MCP_DIR):
        path = MANUAL_TOOLS / f"{name}.md"
        if path.exists():
            skipped_existing += 1
            continue
        auth = ", ".join(DEFAULT_AUTH.get(domain, ["*"]))
        content = STUB_TEMPLATE.format(name=name, domain=domain, auth=auth, source=source)
        if args.dry_run:
            print(f"DRY: would write {path.relative_to(ROOT)}")
        else:
            path.write_text(content, encoding="utf-8")
            print(f"OK  wrote {path.relative_to(ROOT)}")
        written += 1
    print(
        f"---\n{written} stubs {'planned' if args.dry_run else 'written'}, "
        f"{skipped_existing} pages already exist"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
