"""Consistency audit for MinionsOS extension contracts.

Each check returns a list of :class:`Issue` records. ``audit()`` aggregates
the full set so the CLI can print or JSON-dump them. Severity levels mirror
the contract surface they protect:

* ``error`` — a contract claim in ``CLAUDE.md`` is provably wrong (e.g. a
  role mentioned in the boundary table has no whitelist entry).
* ``warning`` — a likely drift (e.g. a tool defined in the MCP server is in
  no role whitelist) that *may* be intentional but deserves review.
* ``info`` — a registry pointer that humans should keep an eye on (e.g. a
  new ``mcp-servers/`` directory with no doc card).

The audit is intentionally read-only: it never mutates the tree, and it never
edits ``CLAUDE.md`` to "match" code or vice versa. Drift is reported, not
silently smoothed over.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from minions.scaffold import contracts

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Issue:
    severity: Severity
    surface: str
    message: str
    hint: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Individual checks. Each returns a list[Issue].
# ---------------------------------------------------------------------------


def check_role_dirs_have_system_md() -> list[Issue]:
    issues: list[Issue] = []
    for role in contracts.list_role_dirs():
        if not contracts.role_has_system_md(role):
            issues.append(
                Issue(
                    "error",
                    "roles",
                    f"minions/roles/{role}/ has no SYSTEM.md.",
                    hint="Every role directory must ship a SYSTEM.md or be removed.",
                )
            )
    return issues


def check_whitelist_role_coverage() -> list[Issue]:
    """Whitelist must define both 'main' and 'subagent' for every known role."""
    issues: list[Issue] = []
    wl = contracts.whitelist_table()
    classified = {key[0] for key in wl}
    for role in contracts.list_role_dirs():
        if role == "common":
            continue
        if role not in classified:
            issues.append(
                Issue(
                    "error",
                    "whitelist",
                    f"role {role!r} has a SYSTEM.md but no _WHITELIST entries.",
                    hint=(
                        f"Add ({role!r}, 'main') and ({role!r}, 'subagent')"
                        " in minions/config/__init__.py:_WHITELIST."
                    ),
                )
            )
            continue
        for agent_type in ("main", "subagent"):
            if (role, agent_type) not in wl:
                issues.append(
                    Issue(
                        "warning",
                        "whitelist",
                        f"role {role!r} is missing the '{agent_type}' whitelist profile.",
                    )
                )
    return issues


def check_publish_policy_covers_known_roles() -> list[Issue]:
    """Every role with a write boundary should have a publish policy."""
    issues: list[Issue] = []
    policy = contracts.role_publish_policy()
    for role in contracts.role_write_boundaries():
        if role not in policy:
            issues.append(
                Issue(
                    "error",
                    "publish",
                    f"role {role!r} has a write boundary but no entry in "
                    "_ROLE_ALLOWED_SHARED_SUBDIRS (minions/tools/publish.py).",
                )
            )
    for role in policy:
        if role == "expert":
            continue  # expert-* roles normalise onto 'expert'.
        if role not in contracts.role_write_boundaries():
            issues.append(
                Issue(
                    "warning",
                    "publish",
                    f"role {role!r} appears in _ROLE_ALLOWED_SHARED_SUBDIRS but has no "
                    "ROLE_WRITE_BOUNDARIES entry (minions/config/__init__.py).",
                )
            )
    return issues


def check_fixed_roles_have_dir() -> list[Issue]:
    """Every name in FIXED_ROLES must have a roles/ directory + SYSTEM.md."""
    issues: list[Issue] = []
    role_dirs = set(contracts.list_role_dirs())
    for role in contracts.fixed_roles():
        if role not in role_dirs:
            issues.append(
                Issue(
                    "error",
                    "roles",
                    f"FIXED_ROLES references {role!r} but minions/roles/{role}/ does not exist.",
                )
            )
        elif not contracts.role_has_system_md(role):
            issues.append(
                Issue(
                    "error",
                    "roles",
                    f"FIXED_ROLES references {role!r} but"
                    f" minions/roles/{role}/SYSTEM.md is missing.",
                )
            )
    return issues


def check_mcp_servers_registered() -> list[Issue]:
    """Every mcp-servers/<dir> must be wired into .mcp.json (or have a doc card)."""
    issues: list[Issue] = []
    cfg = contracts.load_mcp_json()
    if not cfg:
        issues.append(Issue("error", "mcp", ".mcp.json missing or has no mcpServers section."))
        return issues

    referenced_paths = " ".join(" ".join(server.get("args", []) or []) for server in cfg.values())
    for sub in contracts.list_mcp_server_dirs():
        # A server folder is "registered" if .mcp.json args reference its path.
        if f"mcp-servers/{sub}/" not in referenced_paths and sub not in cfg:
            issues.append(
                Issue(
                    "warning",
                    "mcp",
                    f"mcp-servers/{sub}/ exists but is not referenced from .mcp.json.",
                    hint="Add it to .mcp.json or document it in mcp-servers/README.md.",
                )
            )
    return issues


def check_mcp_servers_have_doc_card() -> list[Issue]:
    """README.md should list every mcp-servers/<dir>; loose doc cards must point to a real impl."""
    issues: list[Issue] = []
    readme = contracts.MCP_SERVERS_DIR / "README.md"
    if not readme.is_file():
        issues.append(Issue("error", "mcp", "mcp-servers/README.md is missing."))
        return issues
    text = readme.read_text(encoding="utf-8")
    for sub in contracts.list_mcp_server_dirs():
        if sub not in text:
            issues.append(
                Issue(
                    "warning",
                    "mcp",
                    f"mcp-servers/{sub}/ is not mentioned in mcp-servers/README.md.",
                )
            )
    cfg = contracts.load_mcp_json()
    for card in contracts.list_mcp_server_doc_cards():
        # A doc card without a matching directory or .mcp.json entry usually means
        # an in-package server (e.g. minionsos -> minions/tools/mcp_server.py).
        # We accept it as long as the card's stem appears as a server name in
        # .mcp.json.
        if card not in cfg and card not in contracts.list_mcp_server_dirs():
            issues.append(
                Issue(
                    "info",
                    "mcp",
                    f"mcp-servers/{card}.md doc card has no matching directory or "
                    "`.mcp.json` server entry; check whether it still describes a live server.",
                )
            )
    return issues


def _whitelist_flat_tools() -> set[str]:
    flat: set[str] = set()
    for tools in contracts.whitelist_table().values():
        flat.update(tools)
    return flat


def _whitelist_matches(name: str) -> bool:
    flat = _whitelist_flat_tools()
    if name in flat:
        return True
    return any(entry.endswith("*") and name.startswith(entry[:-1]) for entry in flat)


def check_mcp_tools_whitelisted() -> list[Issue]:
    """Every @mcp.tool() name should be referenced by at least one whitelist entry."""
    issues: list[Issue] = []
    for name in contracts.list_registered_mcp_tools():
        if not _whitelist_matches(name):
            issues.append(
                Issue(
                    "warning",
                    "mcp",
                    f"MCP tool {name!r} is registered in mcp_server.py but no role whitelist "
                    "references it (no exact name and no matching wildcard).",
                    hint=(
                        "Add it to the appropriate role's _WHITELIST entry,"
                        " or remove the @mcp.tool()."
                    ),
                )
            )
    return issues


_TABLE_ROW_RE = re.compile(r"^\|\s*([A-Za-z][A-Za-z\- ]*?)\s+main\b", re.MULTILINE)


def check_root_claudemd_role_table() -> list[Issue]:
    """Every role in the whitelist should appear in the root CLAUDE.md role table."""
    issues: list[Issue] = []
    if not contracts.ROOT_CLAUDE_MD.is_file():
        return [Issue("error", "claudemd", "root CLAUDE.md is missing.")]
    text = contracts.ROOT_CLAUDE_MD.read_text(encoding="utf-8")
    listed = {match.group(1).strip().lower() for match in _TABLE_ROW_RE.finditer(text)}
    classified = {key[0] for key in contracts.whitelist_table()}
    for role in classified:
        if role.lower() not in listed:
            issues.append(
                Issue(
                    "warning",
                    "claudemd",
                    f"role {role!r} has a whitelist entry but no row in the root CLAUDE.md "
                    "tool/write-boundary table.",
                )
            )
    return issues


# ---------------------------------------------------------------------------
# Semantic + privilege checks (added after red-team review).
# ---------------------------------------------------------------------------


def _whitelist_entry_resolves(entry: str, registered_tools: set[str]) -> bool:
    """Return True if a whitelist entry matches a real registered tool.

    Entries that don't start with ``mos_`` are host tools (Bash, Read,
    eacn3_*, etc.) and we cannot enumerate them; treat them as resolved.
    """
    if not entry.startswith("mos_"):
        return True
    if "*" not in entry:
        return entry in registered_tools
    prefix = entry.rstrip("*")
    return any(tool.startswith(prefix) for tool in registered_tools)


def check_whitelist_entries_resolve() -> list[Issue]:
    """S2: every ``mos_*`` whitelist entry must point at a real registered tool.

    Catches dead whitelist entries left behind after a tool rename or removal.
    Host tools (Bash/Read/eacn3_*) are skipped because their registry
    lives outside this repo.
    """
    issues: list[Issue] = []
    registered = set(contracts.list_registered_mcp_tools())
    if not registered:
        return issues
    seen: set[str] = set()
    for (role, agent_type), tools in contracts.whitelist_table().items():
        for entry in tools:
            key = f"{role}:{agent_type}:{entry}"
            if key in seen:
                continue
            seen.add(key)
            if not _whitelist_entry_resolves(entry, registered):
                issues.append(
                    Issue(
                        "warning",
                        "whitelist",
                        f"({role!r}, {agent_type!r}) lists {entry!r} but no "
                        "@mcp.tool() in mcp_server.py matches.",
                        hint="Remove the dead entry or restore the tool registration.",
                    )
                )
    return issues


def _shared_subdirs_in_boundary_text(text: str) -> set[str]:
    """Extract ``branches/main/<sub>/`` roots mentioned in free-form text."""
    return set(re.findall(r"branches/main/([a-z][a-z0-9_-]*)/", text))


def check_publish_policy_matches_boundaries() -> list[Issue]:
    """S3: publish policy subdirs must align with ROLE_WRITE_BOUNDARIES text.

    Currently boundaries are encoded twice (string list in
    ROLE_WRITE_BOUNDARIES, set in _ROLE_ALLOWED_SHARED_SUBDIRS). Drift here
    means the prompt copy and the runtime check disagree.
    """
    issues: list[Issue] = []
    policy = contracts.role_publish_policy()
    boundaries = contracts.role_write_boundaries()
    for role, allowed in policy.items():
        if "*" in allowed:
            continue
        boundary_text = " ".join(boundaries.get(role, []))
        documented = _shared_subdirs_in_boundary_text(boundary_text)
        if not documented and not allowed:
            continue
        extra_in_policy = allowed - documented
        extra_in_boundary = documented - allowed
        for sub in sorted(extra_in_policy):
            issues.append(
                Issue(
                    "warning",
                    "publish",
                    f"role {role!r} can publish to branches/main/{sub}/ "
                    "but ROLE_WRITE_BOUNDARIES does not list it.",
                )
            )
        for sub in sorted(extra_in_boundary):
            issues.append(
                Issue(
                    "warning",
                    "publish",
                    f"role {role!r} ROLE_WRITE_BOUNDARIES mentions "
                    f"branches/main/{sub}/ but the publish policy rejects it.",
                )
            )
    return issues


def _expand_whitelist(entries: list[str], universe: set[str]) -> set[str]:
    """Expand wildcard whitelist entries into the matching subset of *universe*."""
    expanded: set[str] = set()
    for entry in entries:
        if not entry.endswith("*"):
            expanded.add(entry)
            continue
        prefix = entry[:-1]
        expanded.update(t for t in universe if t.startswith(prefix))
        expanded.add(entry)  # keep the literal pattern for non-mos hosts
    return expanded


# Intentional asymmetries between (role, "main") and (role, "subagent").
# Recorded here so the audit doesn't repeatedly flag known design decisions.
# Adding to this list is a privileged action — review carefully.
_SUBAGENT_BROADER_EXCEPTIONS: dict[str, frozenset[str]] = {
    # Ethics main is read-mostly; concrete writes (mock-reviews, flag files)
    # are produced by short-lived subagents that can use Write / Edit.
    "ethics": frozenset({"Write", "Edit"}),
}


def check_subagent_not_broader_than_main() -> list[Issue]:
    """S5: a subagent must not have tools that its main role lacks.

    Inheritance of tools from main is a soft contract. Intentional
    asymmetries are tracked in ``_SUBAGENT_BROADER_EXCEPTIONS`` and excluded
    from the warning set; anything else is flagged for review.
    """
    issues: list[Issue] = []
    wl = contracts.whitelist_table()
    universe = set(contracts.list_registered_mcp_tools())
    main_keys = {role for (role, agent_type) in wl if agent_type == "main"}
    for role in main_keys:
        if (role, "subagent") not in wl:
            continue
        main_tools = _expand_whitelist(wl[(role, "main")], universe)
        sub_tools = _expand_whitelist(wl[(role, "subagent")], universe)
        extra = sub_tools - main_tools - _SUBAGENT_BROADER_EXCEPTIONS.get(role, frozenset())
        if extra:
            issues.append(
                Issue(
                    "warning",
                    "whitelist",
                    f"role {role!r} subagent has tools not in main: {sorted(extra)!r}.",
                    hint=(
                        "Either add them to main, drop them from subagent,"
                        " or document the asymmetry in"
                        " minions/scaffold/audit.py:_SUBAGENT_BROADER_EXCEPTIONS."
                    ),
                )
            )
    return issues


_KNOWN_WILDCARD_TOOL_COUNTS_PATH = contracts.PACKAGE_ROOT / "scaffold" / "_wildcard_baseline.txt"


def _load_wildcard_baseline() -> dict[str, int]:
    if not _KNOWN_WILDCARD_TOOL_COUNTS_PATH.is_file():
        return {}
    out: dict[str, int] = {}
    for line in _KNOWN_WILDCARD_TOOL_COUNTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        pattern, count = line.split("=", 1)
        try:
            out[pattern.strip()] = int(count.strip())
        except ValueError:
            continue
    return out


def check_wildcard_tool_set_unchanged() -> list[Issue]:
    """P1: warn when a wildcard whitelist auto-grants a newly-added tool.

    The baseline file ``minions/scaffold/_wildcard_baseline.txt`` records the
    expected number of registered tools that match each ``mos_*_*``-style
    wildcard. When a new tool that matches a wildcard is added, the count
    grows and we surface a one-time warning so the human reviewing the PR
    can confirm the auto-grant is intentional.

    Update the baseline by re-running ``mos audit --refresh-wildcards`` after
    you have verified the new tool's access surface.
    """
    issues: list[Issue] = []
    baseline = _load_wildcard_baseline()
    if not baseline:
        return issues
    universe = set(contracts.list_registered_mcp_tools())
    seen: set[str] = set()
    for tools in contracts.whitelist_table().values():
        for entry in tools:
            if not entry.endswith("*") or not entry.startswith("mos_"):
                continue
            if entry in seen:
                continue
            seen.add(entry)
            prefix = entry[:-1]
            actual = sum(1 for t in universe if t.startswith(prefix))
            expected = baseline.get(entry)
            if expected is None:
                issues.append(
                    Issue(
                        "info",
                        "whitelist",
                        f"wildcard {entry!r} has no baseline entry; "
                        f"currently matches {actual} tool(s).",
                        hint="Append `<pattern>=<count>` to "
                        "minions/scaffold/_wildcard_baseline.txt after review.",
                    )
                )
            elif actual != expected:
                issues.append(
                    Issue(
                        "warning",
                        "whitelist",
                        f"wildcard {entry!r} now matches {actual} tools "
                        f"(baseline {expected}). A new tool was auto-granted.",
                        hint=(
                            "Confirm the auto-grant is intentional, then update"
                            " minions/scaffold/_wildcard_baseline.txt."
                        ),
                    )
                )
    return issues


_DISPATCH_POSTURE_THRESHOLD_DEFAULT = 0.15
_DISPATCH_POSTURE_THRESHOLD_ENV = "MINIONS_AUDIT_DISPATCH_HEAVY_SELF_THRESHOLD"
_DISPATCH_POSTURE_MIN_TURNS = 20  # below this, sample is too small to draw a conclusion


def _dispatch_posture_threshold() -> float:
    """Resolve the heavy_self threshold, allowing CI / test override."""
    raw = os.environ.get(_DISPATCH_POSTURE_THRESHOLD_ENV)
    if raw is None or raw == "":
        return _DISPATCH_POSTURE_THRESHOLD_DEFAULT
    try:
        return float(raw)
    except ValueError:
        return _DISPATCH_POSTURE_THRESHOLD_DEFAULT


def _live_role_session_paths(claude_root: Path) -> list[Path]:
    """Find session jsonls whose recorded cwd still exists today.

    A session whose cwd has been deleted (closed project, removed worktree)
    reflects a contract version that is no longer running. Excluding those
    keeps the audit focused on live posture, not archeology.
    """
    import json

    paths: list[Path] = []
    if not claude_root.exists():
        return paths
    for slug_dir in claude_root.iterdir():
        if not slug_dir.is_dir():
            continue
        for jsonl in slug_dir.glob("*.jsonl"):
            try:
                with jsonl.open(encoding="utf-8") as fh:
                    cwd: str | None = None
                    for line in fh:
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        c = obj.get("cwd")
                        if isinstance(c, str) and c:
                            cwd = c
                            break
            except OSError:
                continue
            if cwd is None:
                continue
            if "/branches/" not in cwd:
                continue  # not a Role main session
            if not Path(cwd).exists():
                continue  # archived / closed project
            paths.append(jsonl)
    return paths


def check_dispatch_posture(
    *,
    claude_root: Path | None = None,
) -> list[Issue]:
    """Warn when live Role main sessions self-execute past the threshold.

    The ``dispatcher-discipline`` skill (now advisory cache discipline) says
    the main role process should keep its working set small and let heavy
    work land inside Workflow agents (common §4), not Bash / Edit / Write
    itself. This check counts ``tool_use`` records across live (cwd
    still exists) Role main session jsonls. If ``heavy_self`` exceeds
    ``MINIONS_AUDIT_DISPATCH_HEAVY_SELF_THRESHOLD`` (default 15%) it
    raises an info-level Issue.

    Silent pass when no live data exists yet — a freshly cloned repo
    should not warn.
    """
    from minions.tools.cache_stats import compute_dispatch_posture

    root = claude_root if claude_root is not None else Path.home() / ".claude" / "projects"
    paths = _live_role_session_paths(root)
    if not paths:
        return []
    posture = compute_dispatch_posture(paths)
    if posture.total() < _DISPATCH_POSTURE_MIN_TURNS:
        return []
    threshold = _dispatch_posture_threshold()
    pct = posture.heavy_self_pct()
    if pct <= threshold:
        return []
    bucket_summary = ", ".join(
        f"{b}={getattr(posture, b)}"
        for b in ("dispatch", "coord", "heavy_self", "read_self", "misc")
    )
    return [
        Issue(
            "info",
            "dispatch-posture",
            (
                f"Role main heavy_self={pct:.1%} > {threshold:.1%} threshold "
                f"across {posture.total()} live tool_uses ({bucket_summary})."
            ),
            hint=(
                "Main role is self-executing instead of dispatching to a "
                "Workflow. Open minions/roles/common/skills/dispatcher-discipline.md "
                "and move heavy Bash / Edit / Write work into a Workflow agent "
                "(common §4)."
            ),
        )
    ]


_ALL_CHECKS = (
    check_role_dirs_have_system_md,
    check_fixed_roles_have_dir,
    check_whitelist_role_coverage,
    check_publish_policy_covers_known_roles,
    check_mcp_servers_registered,
    check_mcp_servers_have_doc_card,
    check_mcp_tools_whitelisted,
    check_root_claudemd_role_table,
    check_whitelist_entries_resolve,
    check_publish_policy_matches_boundaries,
    check_subagent_not_broader_than_main,
    check_wildcard_tool_set_unchanged,
    check_dispatch_posture,
)


def audit() -> list[Issue]:
    """Run every consistency check and return the aggregated issue list."""
    issues: list[Issue] = []
    for check in _ALL_CHECKS:
        issues.extend(check())
    return issues


__all__ = [
    "Issue",
    "Severity",
    "audit",
    "check_dispatch_posture",
    "check_fixed_roles_have_dir",
    "check_mcp_servers_have_doc_card",
    "check_mcp_servers_registered",
    "check_mcp_tools_whitelisted",
    "check_publish_policy_covers_known_roles",
    "check_publish_policy_matches_boundaries",
    "check_role_dirs_have_system_md",
    "check_root_claudemd_role_table",
    "check_subagent_not_broader_than_main",
    "check_whitelist_entries_resolve",
    "check_whitelist_role_coverage",
    "check_wildcard_tool_set_unchanged",
]
