#!/usr/bin/env python3
"""Extract EACN3 tools from mcp-servers/eacn3/plugin/index.ts and scaffold stubs.

Reads the api.registerTool({ name: ..., description: ... }) blocks and creates
MANUAL/tools/<name>.md if missing. Existing pages are preserved.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANUAL_TOOLS = ROOT / "MANUAL" / "tools"
TS_FILE = ROOT / "mcp-servers" / "eacn3" / "plugin" / "index.ts"

# Match registerTool blocks. We capture the line of `name:` for the source ref.
NAME_RE = re.compile(r'name:\s*"(eacn3_[a-z0-9_]+)"')
DESC_RE = re.compile(r'description:\s*"([^"]+)"', re.DOTALL)

DEFAULT_AUTH_BY_NAME = {
    # Lifecycle / connection — Gru-only
    "eacn3_connect": ["gru"],
    "eacn3_disconnect": ["gru"],
    "eacn3_register_agent": ["gru"],
    "eacn3_unregister_agent": ["gru"],
    "eacn3_claim_agent": ["gru"],
    "eacn3_update_agent": ["gru"],
    "eacn3_a2a_server": ["gru"],
    "eacn3_invite_agent": ["gru"],
    "eacn3_report_event": ["gru"],
    # Reverse control / federation
    "eacn3_reverse_control_status": ["gru"],
    "eacn3_cluster_status": ["gru"],
    # Heartbeat is auto
    "eacn3_heartbeat": ["*"],
    # Everything else — every EACN-registered role
}

STUB = """---
id: {name}
kind: tool
domain: eacn3
auth: [{auth}]
source: mcp-servers/eacn3/plugin/index.ts:{line}
since: stable
keywords: [{keywords}]
related: []
status: stable
---

# {name}

**One line:** {one_line}

## Full description (from EACN3 plugin)

{description}

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
"""


def derive_keywords(name: str, desc: str) -> list[str]:
    base = name.removeprefix("eacn3_").split("_")
    extras = []
    for kw in ["task", "agent", "message", "bid", "event", "domain", "reputation",
              "balance", "deposit", "escrow", "subtask", "broadcast", "directed"]:
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
                    auth_list = DEFAULT_AUTH_BY_NAME.get(name, ["gru", "ethics", "expert"])
                    auth = ", ".join(auth_list)
                    one_line = (desc.split(".")[0] if desc else "TODO").strip()[:160]
                    keywords = ", ".join(derive_keywords(name, desc))
                    page.write_text(STUB.format(
                        name=name,
                        auth=auth,
                        line=name_line,
                        keywords=keywords,
                        one_line=one_line,
                        description=desc,
                    ), encoding="utf-8")
                    written += 1
                    print(f"OK  wrote MANUAL/tools/{name}.md  (src:{name_line})")
            i = j + 1
        else:
            i += 1

    print(f"---\n{written} EACN3 stubs written, {skipped} pages already existed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
