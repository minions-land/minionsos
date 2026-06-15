#!/usr/bin/env python3
"""Validate Skill exposure semantics for MinionsOS-on-Claude-Code."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
NATIVE_SKILL_CALL_RE = re.compile(r"\bSkill\(([^)]+)\)")
HOST_SKILL_ROOT_RE = re.compile(r"(~|/Users/[^/\s]+|/home/[^/\s]+|/root)/\.claude/skills")

ROLE_FACING_MARKDOWN = [
    ROOT / "minions" / "CLAUDE.md",
    ROOT / "minions" / "roles" / "SYSTEM.md",
    ROOT / "minions" / "roles" / "gru" / "SYSTEM.md",
    ROOT / "minions" / "roles" / "ethics" / "SYSTEM.md",
    ROOT / "minions" / "roles" / "expert" / "SYSTEM.md",
    *sorted((ROOT / "minions" / "roles" / "common" / "skills").glob("*.md")),
    *sorted((ROOT / "minions" / "roles" / "gru" / "skills").glob("*.md")),
    *sorted((ROOT / "minions" / "roles" / "ethics" / "skills").glob("*.md")),
    *sorted((ROOT / "minions" / "roles" / "expert" / "skills").glob("*.md")),
]

ROLE_SKILL_DIRS = [
    ROOT / "minions" / "roles" / "common" / "skills",
    ROOT / "minions" / "roles" / "gru" / "skills",
    ROOT / "minions" / "roles" / "ethics" / "skills",
    ROOT / "minions" / "roles" / "expert" / "skills",
]

ROLE_SKILL_ALLOWED_STATUS = {"active", "deprecated", "merged"}
ROLE_SKILL_NON_DELIVERY_KEYS = {"name", "description", "allowed-tools"}


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    fields: dict[str, str] = {}
    for raw in match.group(1).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip("'\"")
    return fields, text[match.end() :]


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def check_role_docs_do_not_call_native_skill(errors: list[str]) -> None:
    for path in ROLE_FACING_MARKDOWN:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for match in NATIVE_SKILL_CALL_RE.finditer(text):
            rel = path.relative_to(ROOT)
            errors.append(
                f"{rel} uses {match.group(0)!r}. Role-facing docs must tell Roles "
                "to read MinionsOS skill markdown from minions/roles/**/skills."
            )
        host_match = HOST_SKILL_ROOT_RE.search(text)
        if host_match:
            rel = path.relative_to(ROOT)
            errors.append(
                f"{rel} references host-level {host_match.group(0)!r}; "
                "Role-facing docs must not depend on user personal Claude configuration."
            )


def iter_direct_role_skill_files() -> list[Path]:
    out: list[Path] = []
    for skills_dir in ROLE_SKILL_DIRS:
        if skills_dir.is_dir():
            out.extend(sorted(skills_dir.glob("*.md")))
    return sorted(out)


def check_direct_role_skill_metadata(errors: list[str]) -> None:
    for path in iter_direct_role_skill_files():
        rel = path.relative_to(ROOT)
        fields, _body = parse_frontmatter(path.read_text(encoding="utf-8"))
        if not fields:
            errors.append(f"{rel} is directly discoverable but has no Role-skill frontmatter")
            continue
        expected_slug = path.stem
        if fields.get("slug") != expected_slug:
            errors.append(f"{rel} must declare slug: {expected_slug!r}")
        summary = fields.get("summary", "")
        if not summary:
            errors.append(f"{rel} must declare summary: for the wake-up [Domain Reference] block")
        status = fields.get("status")
        if status not in ROLE_SKILL_ALLOWED_STATUS:
            errors.append(
                f"{rel} status={status!r}; expected one of {sorted(ROLE_SKILL_ALLOWED_STATUS)}"
            )
        non_delivery_keys = sorted(ROLE_SKILL_NON_DELIVERY_KEYS.intersection(fields))
        if non_delivery_keys:
            errors.append(
                f"{rel} has non-delivery key(s) {non_delivery_keys}; direct Role skills "
                "use slug/summary/tools metadata"
            )


def check_workflow_plugin_skill_rendering(errors: list[str]) -> None:
    from minions.lifecycle.workflow_plugins import _render_claude_skill_bundle

    for source in sorted((ROOT / "workflow-plugins").glob("*/skills/*.md")):
        plugin_slug = source.parents[1].name
        expected_name = f"workflow-plugin-{plugin_slug}-{source.stem}"
        rendered = _render_claude_skill_bundle(expected_name, source.read_text(encoding="utf-8"))
        fields, _body = parse_frontmatter(rendered)
        if fields.get("name") != expected_name:
            errors.append(
                f"{source.relative_to(ROOT)} renders without project-local name: {expected_name}"
            )
        if not fields.get("description"):
            errors.append(f"{source.relative_to(ROOT)} renders without project-local description")
        if "slug" in fields or "tools" in fields:
            errors.append(
                f"{source.relative_to(ROOT)} leaks Role-skill metadata into "
                "project-local bundle frontmatter"
            )


def check_prompt_exposes_role_skills(errors: list[str]) -> None:
    from minions.lifecycle.agent_host import build_forever_loop_prompt

    prompt = build_forever_loop_prompt(role_name="expert", port=1)
    for fragment in (
        "## [Domain Reference]",
        "Optional domain-specific guidance",
        "Read the matching markdown file",
    ):
        if fragment not in prompt:
            errors.append(f"expert forever-loop prompt missing Domain Reference fragment: {fragment!r}")


def check_manual_fragments(errors: list[str]) -> None:
    skills_doc = (ROOT / "minions" / "roles" / "common" / "SKILLS.md").read_text(encoding="utf-8")
    workflow_doc = (ROOT / "workflow-plugins" / "README.md").read_text(encoding="utf-8")
    manual = (ROOT / "MANUAL" / "MANUAL.md").read_text(encoding="utf-8")
    domain = (ROOT / "MANUAL" / "domains" / "skills.md").read_text(encoding="utf-8")

    for fragment in (
        "Repository delivery contract",
        "`slug:`",
        "`summary:`",
        "Host-level personal Claude configuration is outside",
    ):
        if fragment not in skills_doc:
            errors.append(f"minions/roles/common/SKILLS.md missing fragment: {fragment!r}")

    for fragment in (
        "MinionsOS Role skills",
        "project-local",
        "Host-level personal Claude configuration is outside",
    ):
        if fragment not in domain:
            errors.append(f"MANUAL/domains/skills.md missing fragment: {fragment!r}")

    if "`skills`" not in manual:
        errors.append("MANUAL/MANUAL.md does not list the skills domain")
    if ".claude/skills/workflow-plugin-{slug}-{skill}/SKILL.md" not in workflow_doc:
        errors.append("workflow-plugins/README.md does not document rendered Skill bundles")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print("# SKILL OPERABILITY — errors:")
        print("  - validate_skill_operability.py validates only repository-delivered Role skills")
        return 1
    errors: list[str] = []
    check_direct_role_skill_metadata(errors)
    check_role_docs_do_not_call_native_skill(errors)
    check_workflow_plugin_skill_rendering(errors)
    check_prompt_exposes_role_skills(errors)
    check_manual_fragments(errors)
    if errors:
        print("# SKILL OPERABILITY — errors:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("OK — Skill exposure matches MinionsOS repository Role-skill semantics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
