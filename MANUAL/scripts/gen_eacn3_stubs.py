#!/usr/bin/env python3
"""Extract EACN3 tools from mcp-servers/eacn3/plugin/index.ts and scaffold stubs.

Reads the api.registerTool({ name: ..., description: ... }) blocks and creates
MANUAL/tools/<name>.md if missing. Existing pages are preserved.
"""

from __future__ import annotations

import re
import sys
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MANUAL_TOOLS = ROOT / "MANUAL" / "tools"
TS_FILE = ROOT / "mcp-servers" / "eacn3" / "plugin" / "index.ts"

# Match registerTool blocks. We capture the line of `name:` for the source ref.
NAME_RE = re.compile(r'name:\s*"(eacn3_[a-z0-9_]+)"')
DESC_RE = re.compile(r'description:\s*"([^"]+)"', re.DOTALL)

MAIN_ROLES = ("gru", "expert", "ethics")


def auth_for_tool(tool_name: str) -> list[str]:
    """Return MANUAL auth frontmatter from server-side MCP authorization."""
    from minions.config import resolve_server_authz

    return [
        role
        for role in MAIN_ROLES
        if any(fnmatchcase(tool_name, pattern) for pattern in resolve_server_authz(role, "main"))
    ]


STUB = """---
id: {name}
kind: tool
domain: eacn3
auth: [{auth}]
source: mcp-servers/eacn3/plugin/index.ts:{line}
since: stub
keywords: [{keywords}]
related: []
status: stub
---

# {name}

No curated MANUAL page yet. The MCP description is in your Role system prompt.
Source: mcp-servers/eacn3/plugin/index.ts:{line}

For event intake, start from `mos_await_events` for Expert/Ethics or
`mos_unread_summary` / `mos_get_events` for Gru before using raw EACN3 tools.
"""


def derive_keywords(name: str, desc: str) -> list[str]:
    base = name.removeprefix("eacn3_").split("_")
    extras = []
    for kw in [
        "task",
        "agent",
        "message",
        "bid",
        "event",
        "domain",
        "reputation",
        "balance",
        "deposit",
        "escrow",
        "subtask",
        "broadcast",
        "directed",
    ]:
        if kw in desc.lower():
            extras.append(kw)
    return list(dict.fromkeys(base + extras))[:10]


def main() -> int:
    text = TS_FILE.read_text(encoding="utf-8")
    lines = text.splitlines()
    written = 0
    skipped = 0

    # Walk line-by-line, find `api.registerTool({` blocks
    i = 0
    while i < len(lines):
        if "api.registerTool({" in lines[i]:
            block_start = i + 1
            depth = 1
            j = i + 1
            while j < len(lines) and depth > 0:
                depth += lines[j].count("{") - lines[j].count("}")
                if depth <= 0:
                    break
                j += 1
            block_text = "\n".join(lines[block_start:j])
            nm = NAME_RE.search(block_text)
            dm = DESC_RE.search(block_text)
            if nm:
                name = nm.group(1)
                desc = (dm.group(1) if dm else "").replace('\\"', '"')
                # find the line number of `name:` in the file
                name_line = block_start
                for offset, ln in enumerate(lines[block_start:j]):
                    if f'"{name}"' in ln:
                        name_line = block_start + offset + 1
                        break
                page = MANUAL_TOOLS / f"{name}.md"
                if page.exists():
                    skipped += 1
                else:
                    auth = ", ".join(auth_for_tool(name) or MAIN_ROLES)
                    one_line = (desc.split(".")[0] if desc else "TODO").strip()[:160]
                    keywords = ", ".join(derive_keywords(name, desc))
                    page.write_text(
                        STUB.format(
                            name=name,
                            auth=auth,
                            line=name_line,
                            keywords=keywords,
                            one_line=one_line,
                            description=desc,
                        ),
                        encoding="utf-8",
                    )
                    written += 1
                    print(f"OK  wrote MANUAL/tools/{name}.md  (src:{name_line})")
            i = j + 1
        else:
            i += 1

    print(f"---\n{written} EACN3 stubs written, {skipped} pages already existed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
