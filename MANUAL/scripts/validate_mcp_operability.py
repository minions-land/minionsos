#!/usr/bin/env python3
"""Validate that hot-path MCP MANUAL pages are operational, not just present."""

from __future__ import annotations

import re
import sys
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MANUAL_ROOT = ROOT / "MANUAL"
TOOLS_DIR = MANUAL_ROOT / "tools"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
EACN3_NAME_RE = re.compile(r'name:\s*"(eacn3_[a-z0-9_]+)"')
PY_TOOL_RE = re.compile(r"^\s*@mcp\.tool\(\)\s*$", re.MULTILINE)

MAIN_ROLES = ("gru", "expert", "ethics")

CRITICAL_TOOLS = {
    "mos_await_events": {
        "domain": "runtime",
        "must_contain": ["## Signature", '"count"', '"events"', "cache_keepalive"],
    },
    "mos_get_events": {
        "domain": "runtime",
        "must_contain": ["## Signature", "project_{port}/events/gru.jsonl", "unread_remaining"],
    },
    "mos_unread_summary": {
        "domain": "runtime",
        "must_contain": ["## Signature", "total_unread", "Pure read"],
    },
    "mos_review_run": {
        "domain": "deliverables",
        "must_contain": ["## Signature", "submission-checklist.md", "build/paper.pdf"],
    },
    "mos_list_workflow_plugins": {
        "domain": "lifecycle",
        "must_contain": ["## Signature", "workflow-plugins/*/manifest.yaml", "per-instance MCP"],
    },
    "eacn3_get_events": {
        "domain": "eacn3",
        "must_contain": ["## Signature", "mos_await_events", "mos_get_events", "drain"],
    },
    "eacn3_await_events": {
        "domain": "eacn3",
        "must_contain": ["## Signature", "mos_await_events", "mos_get_events", "timeout"],
    },
    "eacn3_send_message": {
        "domain": "eacn3",
        "must_contain": ["## Signature", "direct EACN3 message", "mos_publish_to_shared"],
    },
    "eacn3_create_task": {
        "domain": "eacn3",
        "must_contain": ["## Signature", "Role-level", "Gru manages projects"],
    },
    "eacn3_submit_bid": {
        "domain": "eacn3",
        "must_contain": ["## Signature", "confidence", "Gru observes"],
    },
    "eacn3_submit_result": {
        "domain": "eacn3",
        "must_contain": ["## Signature", "awaiting_retrieval", "Gru does not submit"],
    },
}

WRAPPER_GUIDANCE_TOOLS = {"eacn3_get_events", "eacn3_await_events"}


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    frontmatter = match.group(1)
    body = text[match.end() :]
    parsed: dict[str, object] = {}
    for raw in frontmatter.splitlines():
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            parsed[key] = [part.strip().strip("'\"") for part in inner.split(",") if part.strip()]
        else:
            parsed[key] = value.strip("'\"")
    return parsed, body


def page(tool_name: str) -> tuple[dict[str, object], str, Path]:
    path = TOOLS_DIR / f"{tool_name}.md"
    text = path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(text)
    return frontmatter, body, path


def iter_tool_pages() -> list[tuple[str, dict[str, object], str, Path]]:
    pages: list[tuple[str, dict[str, object], str, Path]] = []
    for path in sorted(TOOLS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(text)
        tool_name = str(frontmatter.get("id") or path.stem)
        if tool_name.startswith(("mos_", "eacn3_")):
            pages.append((tool_name, frontmatter, body, path))
    return pages


def advertised_authz(tool_name: str) -> list[str]:
    from minions.config import resolve_server_authz

    allowed: list[str] = []
    for role in MAIN_ROLES:
        patterns = resolve_server_authz(role, "main")
        if any(fnmatchcase(tool_name, pattern) for pattern in patterns):
            allowed.append(role)
    return allowed


def minions_tool_count() -> int:
    from minions.tools.mcp import _MINIONS_MCP_TOOL_NAMES

    return len(_MINIONS_MCP_TOOL_NAMES)


def eacn3_tool_count() -> int:
    text = (ROOT / "mcp-servers" / "eacn3" / "plugin" / "index.ts").read_text(encoding="utf-8")
    return len(set(EACN3_NAME_RE.findall(text)))


def keepalive_tools() -> set[str]:
    text = (ROOT / "mcp-servers" / "keepalive" / "server.py").read_text(encoding="utf-8")
    names = set()
    lines = text.splitlines()
    for i, line in enumerate(lines[:-1]):
        if line.strip() == "@mcp.tool()":
            match = re.match(r"\s*(?:async\s+)?def\s+(\w+)\s*\(", lines[i + 1])
            if match:
                names.add(match.group(1))
    return names


def check_manual_mcp_map(errors: list[str]) -> None:
    manual = (MANUAL_ROOT / "MANUAL.md").read_text(encoding="utf-8")
    runtime = (MANUAL_ROOT / "domains" / "runtime.md").read_text(encoding="utf-8")
    eacn3 = (MANUAL_ROOT / "domains" / "eacn3.md").read_text(encoding="utf-8")

    expected_fragments = [
        f"{minions_tool_count()} `mos_*`",
        f"{eacn3_tool_count()} `eacn3_*`",
        "`wait_bg` and `keepalive_now`",
        "Workflow plugins",
        "mos_unread_summary",
        "mos_get_events",
    ]
    for fragment in expected_fragments:
        if fragment not in manual:
            errors.append(f"MANUAL.md missing MCP map fragment: {fragment!r}")

    for fragment in ("MCP layers", "`minionsos`", "`eacn3`", "`keepalive`"):
        if fragment not in runtime:
            errors.append(f"runtime domain missing MCP layer fragment: {fragment!r}")

    for fragment in ("Expert / Ethics", "Gru", "mos_unread_summary", "mos_get_events"):
        if fragment not in eacn3:
            errors.append(f"eacn3 domain missing event-intake fragment: {fragment!r}")

    if keepalive_tools() != {"wait_bg", "keepalive_now"}:
        errors.append(f"keepalive MCP tool set changed: {sorted(keepalive_tools())}")


def check_tool_pages(errors: list[str]) -> None:
    for tool_name, expected in CRITICAL_TOOLS.items():
        frontmatter, body, path = page(tool_name)
        rel = path.relative_to(ROOT)

        if "No curated MANUAL page yet" in body:
            errors.append(f"{rel} is still a generated stub")
        if frontmatter.get("status") == "stub" or frontmatter.get("since") == "stub":
            errors.append(f"{rel} still has stub frontmatter")

        expected_domain = expected["domain"]
        if frontmatter.get("domain") != expected_domain:
            errors.append(
                f"{rel} domain={frontmatter.get('domain')!r}, expected {expected_domain!r}"
            )

        expected_auth = advertised_authz(tool_name)
        actual_auth = frontmatter.get("auth")
        if actual_auth != expected_auth:
            errors.append(f"{rel} auth={actual_auth!r}, expected server authz {expected_auth!r}")

        for fragment in expected["must_contain"]:
            if fragment not in body:
                errors.append(f"{rel} missing required operational fragment: {fragment!r}")

        if tool_name in WRAPPER_GUIDANCE_TOOLS:
            for wrapper in ("mos_await_events", "mos_get_events", "mos_unread_summary"):
                if wrapper not in body:
                    errors.append(f"{rel} must point to wrapper {wrapper}")


def check_all_tool_metadata(errors: list[str]) -> None:
    for tool_name, frontmatter, body, path in iter_tool_pages():
        rel = path.relative_to(ROOT)
        expected_auth = advertised_authz(tool_name)
        if expected_auth and frontmatter.get("auth") != expected_auth:
            errors.append(
                f"{rel} auth={frontmatter.get('auth')!r}, expected server authz {expected_auth!r}"
            )

        placeholder = "No curated MANUAL page yet" in body
        if placeholder and frontmatter.get("status") != "stub":
            errors.append(f"{rel} has placeholder body but status is not stub")
        if placeholder and frontmatter.get("since") != "stub":
            errors.append(f"{rel} has placeholder body but since is not stub")
        if not placeholder and frontmatter.get("status") == "stub":
            errors.append(f"{rel} is curated but still has status stub")


def main() -> int:
    errors: list[str] = []
    check_manual_mcp_map(errors)
    check_all_tool_metadata(errors)
    check_tool_pages(errors)
    if errors:
        print("# MCP MANUAL OPERABILITY — errors:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        f"OK — {len(iter_tool_pages())} MCP tool pages have aligned metadata; "
        f"{len(CRITICAL_TOOLS)} critical pages are operational"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
