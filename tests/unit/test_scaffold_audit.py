"""Unit tests for the scaffold + audit surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minions.scaffold import audit as audit_module
from minions.scaffold import contracts, generators

# ---------------------------------------------------------------------------
# Fixture: a fully-isolated fake repo wired into contracts.* paths.
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "fake-repo"
    package = repo / "minions"
    for sub in ("roles", "review/templates", "review/skills", "domains", "tools"):
        (package / sub).mkdir(parents=True, exist_ok=True)
    (repo / "mcp-servers").mkdir()

    monkeypatch.setattr(contracts, "REPO_ROOT", repo)
    monkeypatch.setattr(contracts, "PACKAGE_ROOT", package)
    monkeypatch.setattr(contracts, "ROLES_DIR", package / "roles")
    monkeypatch.setattr(contracts, "REVIEW_DIR", package / "review")
    monkeypatch.setattr(contracts, "DOMAINS_DIR", package / "domains")
    monkeypatch.setattr(contracts, "TOOLS_DIR", package / "tools")
    monkeypatch.setattr(contracts, "MCP_SERVERS_DIR", repo / "mcp-servers")
    monkeypatch.setattr(contracts, "MCP_JSON", repo / ".mcp.json")
    monkeypatch.setattr(contracts, "ROOT_CLAUDE_MD", repo / "CLAUDE.md")
    monkeypatch.setattr(contracts, "PACKAGE_CLAUDE_MD", package / "CLAUDE.md")

    monkeypatch.setattr(generators, "ROLES_DIR", package / "roles")
    monkeypatch.setattr(generators, "REVIEW_DIR", package / "review")
    monkeypatch.setattr(generators, "DOMAINS_DIR", package / "domains")
    monkeypatch.setattr(generators, "TOOLS_DIR", package / "tools")
    return repo


def _seed_role(repo: Path, name: str, *, system_md: bool = True) -> None:
    role_dir = repo / "minions" / "roles" / name
    role_dir.mkdir(parents=True, exist_ok=True)
    if system_md:
        (role_dir / "SYSTEM.md").write_text(f"# {name}\n", encoding="utf-8")


def _seed_minimal_repo(repo: Path) -> None:
    """Seed CLAUDE.md, .mcp.json, README so structural checks have a baseline."""
    (repo / "CLAUDE.md").write_text(
        "| Gru main | a | b | c | d | e | f |\n"
        "| Coder main | a | b | c | d | e | f |\n"
        "| Writer main | a | b | c | d | e | f |\n"
        "| Ethics main | a | b | c | d | e | f |\n"
        "| Expert main | a | b | c | d | e | f |\n",
        encoding="utf-8",
    )
    (repo / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "minionsos": {"type": "stdio", "command": "uv", "args": []},
                }
            }
        ),
        encoding="utf-8",
    )
    (repo / "mcp-servers" / "README.md").write_text("# MCP Servers\n", encoding="utf-8")
    for role in ("gru", "ethics", "expert"):
        _seed_role(repo, role)


# ---------------------------------------------------------------------------
# Generator tests
# ---------------------------------------------------------------------------


def test_generate_role_writes_system_md_and_skills_dir(fake_repo: Path) -> None:
    result = generators.generate_role("librarian", title="Librarian")
    sys_md = fake_repo / "minions" / "roles" / "librarian" / "SYSTEM.md"
    assert sys_md.is_file()
    assert "# Librarian — System Prompt" in sys_md.read_text(encoding="utf-8")
    assert (fake_repo / "minions" / "roles" / "librarian" / "skills").is_dir()
    assert "FIXED_ROLES" in " ".join(result.manual_followups)


def test_generate_role_skill_requires_existing_role(fake_repo: Path) -> None:
    with pytest.raises(generators.ScaffoldError):
        generators.generate_role_skill("ghost", "evidence-audit")


def test_generate_role_skill_writes_frontmatter_and_summary(fake_repo: Path) -> None:
    _seed_role(fake_repo, "coder")
    result = generators.generate_role_skill(
        "coder", "evidence-audit", summary="Audit evidence chain"
    )
    body = result.paths_written[0].read_text(encoding="utf-8")
    assert body.startswith("---\nslug: evidence-audit\n")
    assert "summary: Audit evidence chain" in body


def test_generate_review_template(fake_repo: Path) -> None:
    result = generators.generate_review_template("rebuttal-note", title="Rebuttal Note")
    body = result.paths_written[0].read_text(encoding="utf-8")
    assert body.startswith("# Rebuttal Note")


def test_generate_domain(fake_repo: Path) -> None:
    result = generators.generate_domain("rl-theory", title="RL Theory")
    body = result.paths_written[0].read_text(encoding="utf-8")
    assert "Domain Pack: RL Theory (rl-theory)" in body


def test_generate_mcp_tool_rejects_non_mos_prefix(fake_repo: Path) -> None:
    with pytest.raises(generators.ScaffoldError):
        generators.generate_mcp_tool("frob_widget")


def test_generate_mcp_tool_emits_args_class(fake_repo: Path) -> None:
    result = generators.generate_mcp_tool("mos_widget_kick")
    body = result.paths_written[0].read_text(encoding="utf-8")
    assert "class MosWidgetKickArgs(BaseModel):" in body


def test_generate_refuses_to_overwrite_without_force(fake_repo: Path) -> None:
    generators.generate_domain("rl-theory")
    with pytest.raises(generators.ScaffoldError):
        generators.generate_domain("rl-theory")
    generators.generate_domain("rl-theory", force=True)


# ---------------------------------------------------------------------------
# Audit tests
# ---------------------------------------------------------------------------


def test_audit_clean_baseline_has_no_errors(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_minimal_repo(fake_repo)
    monkeypatch.setattr(contracts, "fixed_roles", lambda: {"ethics"})
    issues = audit_module.audit()
    errors = [i for i in issues if i.severity == "error"]
    assert errors == [], errors


def test_audit_flags_role_dir_missing_system_md(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_minimal_repo(fake_repo)
    monkeypatch.setattr(contracts, "fixed_roles", lambda: set())
    _seed_role(fake_repo, "broken", system_md=False)
    surfaces = {i.surface for i in audit_module.check_role_dirs_have_system_md()}
    assert "roles" in surfaces


def test_audit_flags_fixed_role_without_dir(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_minimal_repo(fake_repo)
    monkeypatch.setattr(contracts, "fixed_roles", lambda: {"phantom"})
    issues = audit_module.check_fixed_roles_have_dir()
    assert any("phantom" in i.message for i in issues)


def test_audit_flags_unregistered_mcp_server_dir(fake_repo: Path) -> None:
    _seed_minimal_repo(fake_repo)
    (fake_repo / "mcp-servers" / "drifting").mkdir()
    issues = audit_module.check_mcp_servers_registered()
    assert any("drifting" in i.message for i in issues)


def test_audit_flags_orphan_mcp_tool(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = fake_repo / "minions" / "tools" / "mcp_server.py"
    server.write_text(
        "@mcp.tool()\ndef mos_orphan_tool(args):\n    return {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {("coder", "main"): ["Read"]},
    )
    issues = audit_module.check_mcp_tools_whitelisted()
    assert any("mos_orphan_tool" in i.message for i in issues)


def test_list_registered_mcp_tools_finds_both_sync_and_async(fake_repo: Path) -> None:
    """Regression: ``async def`` tools must be picked up by the parser.

    Bug observed 2026-05-19: the @mcp.tool() regex required a bare ``def``
    and silently missed every ``async def`` tool, causing audit to report
    them as dead whitelist entries even though they were properly
    registered.
    """
    server = fake_repo / "minions" / "tools" / "mcp_server.py"
    server.write_text(
        "@mcp.tool()\n"
        "def mos_sync_tool(args):\n"
        "    return {}\n"
        "\n"
        "@mcp.tool()\n"
        "async def mos_async_tool(text: str) -> dict:\n"
        "    return {}\n"
        "\n"
        "@mcp.tool()\n"
        "async  def  mos_async_loose_spacing(x: int) -> dict:\n"
        "    return {}\n",
        encoding="utf-8",
    )
    found = set(contracts.list_registered_mcp_tools())
    assert "mos_sync_tool" in found
    assert "mos_async_tool" in found
    assert "mos_async_loose_spacing" in found


def test_audit_wildcard_match_passes(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = fake_repo / "minions" / "tools" / "mcp_server.py"
    server.write_text(
        "@mcp.tool()\ndef mos_draft_append(args):\n    return {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {("noter", "main"): ["mos_draft_*"]},
    )
    issues = audit_module.check_mcp_tools_whitelisted()
    assert issues == []


# ---------------------------------------------------------------------------
# New audit checks (S2, S3, S5, P1, P2 from red-team review)
# ---------------------------------------------------------------------------


def test_check_whitelist_entries_resolve_flags_dead_entry(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = fake_repo / "minions" / "tools" / "mcp_server.py"
    server.write_text("@mcp.tool()\ndef mos_real_tool(args):\n    return {}\n", encoding="utf-8")
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {("coder", "main"): ["mos_real_tool", "mos_quantum_teleport"]},
    )
    issues = audit_module.check_whitelist_entries_resolve()
    assert any("mos_quantum_teleport" in i.message for i in issues)
    assert not any("mos_real_tool" in i.message for i in issues)


def test_check_whitelist_entries_resolve_accepts_wildcard(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = fake_repo / "minions" / "tools" / "mcp_server.py"
    server.write_text("@mcp.tool()\ndef mos_draft_append(args):\n    return {}\n", encoding="utf-8")
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {("noter", "main"): ["mos_draft_*"]},
    )
    assert audit_module.check_whitelist_entries_resolve() == []


def test_check_publish_policy_matches_boundaries_flags_extra_subdir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        contracts,
        "role_publish_policy",
        lambda: {"noter": {"notes", "exploration", "handoffs", "exp"}},
    )
    monkeypatch.setattr(
        contracts,
        "role_write_boundaries",
        lambda: {
            "noter": [
                "branches/noter/",
                "branches/shared/notes/",
                "branches/shared/draft/",
                "branches/shared/handoffs/",
            ]
        },
    )
    issues = audit_module.check_publish_policy_matches_boundaries()
    assert any(
        "exp" in i.message and "ROLE_WRITE_BOUNDARIES does not list" in i.message for i in issues
    )


def test_check_subagent_not_broader_than_main_flags_drift(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {
            ("librarian", "main"): ["Read"],
            ("librarian", "subagent"): ["Read", "Write", "Edit"],
        },
    )
    monkeypatch.setattr(contracts, "list_registered_mcp_tools", lambda: [])
    issues = audit_module.check_subagent_not_broader_than_main()
    assert any(
        "librarian" in i.message and "Write" in i.message and "Edit" in i.message for i in issues
    )


def test_check_subagent_not_broader_when_aligned(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {
            ("coder", "main"): ["Bash", "Read", "Write"],
            ("coder", "subagent"): ["Read", "Write"],
        },
    )
    monkeypatch.setattr(contracts, "list_registered_mcp_tools", lambda: [])
    assert audit_module.check_subagent_not_broader_than_main() == []


def test_check_wildcard_baseline_drift(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = fake_repo / "minions" / "scaffold" / "_wildcard_baseline.txt"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text("mos_draft_*=2\n", encoding="utf-8")
    monkeypatch.setattr(audit_module, "_KNOWN_WILDCARD_TOOL_COUNTS_PATH", baseline)
    server = fake_repo / "minions" / "tools" / "mcp_server.py"
    server.write_text(
        "@mcp.tool()\ndef mos_draft_append(args):\n    return {}\n"
        "@mcp.tool()\ndef mos_draft_query(args):\n    return {}\n"
        "@mcp.tool()\ndef mos_draft_nuke_all(args):\n    return {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {("gru", "main"): ["mos_draft_*"]},
    )
    issues = audit_module.check_wildcard_tool_set_unchanged()
    assert any("baseline 2" in i.message and "matches 3" in i.message for i in issues)


# ---------------------------------------------------------------------------
# Server-side identity + cross-project checks
# ---------------------------------------------------------------------------


def test_enforce_caller_identity_rejects_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    from minions.tools import mcp_server

    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
    monkeypatch.delenv("MINIONS_DISABLE_MCP_AUTHZ", raising=False)
    with pytest.raises(PermissionError, match="role identity mismatch"):
        mcp_server._enforce_caller_identity("gru")


def test_enforce_caller_identity_accepts_match(monkeypatch: pytest.MonkeyPatch) -> None:
    from minions.tools import mcp_server

    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
    monkeypatch.delenv("MINIONS_DISABLE_MCP_AUTHZ", raising=False)
    mcp_server._enforce_caller_identity("coder")


def test_enforce_caller_identity_normalises_expert(monkeypatch: pytest.MonkeyPatch) -> None:
    from minions.tools import mcp_server

    monkeypatch.setenv("MINIONS_ROLE_NAME", "expert-rl-theory")
    monkeypatch.delenv("MINIONS_DISABLE_MCP_AUTHZ", raising=False)
    mcp_server._enforce_caller_identity("expert")
    mcp_server._enforce_caller_identity("expert-rl-theory")


def test_enforce_caller_project_rejects_cross_port(monkeypatch: pytest.MonkeyPatch) -> None:
    from minions.tools import mcp_server

    monkeypatch.setenv("MINIONS_PROJECT_PORT", "37596")
    monkeypatch.delenv("MINIONS_DISABLE_MCP_AUTHZ", raising=False)
    with pytest.raises(PermissionError, match="cross-project publish blocked"):
        mcp_server._enforce_caller_project(99999)


def test_enforce_caller_project_accepts_same(monkeypatch: pytest.MonkeyPatch) -> None:
    from minions.tools import mcp_server

    monkeypatch.setenv("MINIONS_PROJECT_PORT", "37596")
    monkeypatch.delenv("MINIONS_DISABLE_MCP_AUTHZ", raising=False)
    mcp_server._enforce_caller_project(37596)


def test_expert_normalisation_no_longer_matches_expertise() -> None:
    from minions.config import resolve_whitelist

    # 'expertise' must NOT inherit expert's full whitelist anymore.
    assert resolve_whitelist("expertise", "main") == []
    # 'expert-rl-theory' continues to inherit the expert whitelist.
    assert resolve_whitelist("expert-rl-theory", "main") == resolve_whitelist("expert", "main")


# --------------------------------------------------------------------------
# check_dispatch_posture
# --------------------------------------------------------------------------


def _build_role_jsonl(slug_dir: Path, *, cwd: str, tool_uses: list[str]) -> Path:
    """Write a minimal Role-main session jsonl into *slug_dir*.

    The first entry carries the cwd (so cwd-existence filtering sees it).
    Each ``tool_uses`` entry becomes one assistant turn with one tool_use.
    """
    slug_dir.mkdir(parents=True, exist_ok=True)
    path = slug_dir / "session.jsonl"
    entries = [
        {"type": "user", "cwd": cwd, "message": {"content": "boot"}},
    ]
    for i, name in enumerate(tool_uses):
        entries.append(
            {
                "type": "assistant",
                "timestamp": f"2026-05-19T00:00:{i:02d}Z",
                "message": {
                    "usage": {"cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                    "content": [{"type": "tool_use", "name": name}],
                },
            }
        )
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


def test_dispatch_posture_silent_when_no_live_data(tmp_path: Path) -> None:
    """Empty / nonexistent claude_root must not warn — fresh repos are clean."""
    from minions.scaffold.audit import check_dispatch_posture

    issues = check_dispatch_posture(claude_root=tmp_path / "missing")
    assert issues == []


def test_dispatch_posture_warns_above_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """heavy_self ratio above the threshold raises a single info-level Issue."""
    from minions.scaffold.audit import check_dispatch_posture

    # Create a "live" branches/<role>/ directory that the audit sees as real
    role_cwd = tmp_path / "project_38000" / "branches" / "coder"
    role_cwd.mkdir(parents=True)

    claude_root = tmp_path / "claude" / "projects"
    # 80% Bash + 20% Task → heavy_self_pct = 80% > 15% threshold
    _build_role_jsonl(
        claude_root / "slug",
        cwd=str(role_cwd),
        tool_uses=["Bash"] * 80 + ["Task"] * 20,
    )

    monkeypatch.delenv("MINIONS_AUDIT_DISPATCH_HEAVY_SELF_THRESHOLD", raising=False)
    issues = check_dispatch_posture(claude_root=claude_root)
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == "info"
    assert issue.surface == "dispatch-posture"
    assert "heavy_self=80.0%" in issue.message
    assert "dispatcher-discipline" in issue.hint


def test_dispatch_posture_silent_below_threshold(tmp_path: Path) -> None:
    """heavy_self under the threshold must produce no issue."""
    from minions.scaffold.audit import check_dispatch_posture

    role_cwd = tmp_path / "project_38000" / "branches" / "coder"
    role_cwd.mkdir(parents=True)
    claude_root = tmp_path / "claude" / "projects"
    # 5% Bash + 95% Task → well under threshold
    _build_role_jsonl(
        claude_root / "slug",
        cwd=str(role_cwd),
        tool_uses=["Bash"] * 5 + ["Task"] * 95,
    )

    issues = check_dispatch_posture(claude_root=claude_root)
    assert issues == []


def test_dispatch_posture_excludes_archived_projects(tmp_path: Path) -> None:
    """Sessions whose cwd has been deleted (closed project) are skipped."""
    from minions.scaffold.audit import check_dispatch_posture

    # Note: do NOT create role_cwd → it does not exist
    nonexistent_cwd = str(tmp_path / "project_99999" / "branches" / "coder")
    claude_root = tmp_path / "claude" / "projects"
    _build_role_jsonl(
        claude_root / "slug",
        cwd=nonexistent_cwd,
        tool_uses=["Bash"] * 100,  # would warn if it counted
    )

    assert check_dispatch_posture(claude_root=claude_root) == []


def test_dispatch_posture_threshold_overridable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MINIONS_AUDIT_DISPATCH_HEAVY_SELF_THRESHOLD env var raises the bar."""
    from minions.scaffold.audit import check_dispatch_posture

    role_cwd = tmp_path / "project_38000" / "branches" / "coder"
    role_cwd.mkdir(parents=True)
    claude_root = tmp_path / "claude" / "projects"
    _build_role_jsonl(
        claude_root / "slug",
        cwd=str(role_cwd),
        tool_uses=["Bash"] * 50 + ["Task"] * 50,  # 50% heavy_self
    )

    # Default threshold (15%) → warns
    monkeypatch.setenv("MINIONS_AUDIT_DISPATCH_HEAVY_SELF_THRESHOLD", "0.15")
    assert len(check_dispatch_posture(claude_root=claude_root)) == 1

    # Bump threshold above observed → silent
    monkeypatch.setenv("MINIONS_AUDIT_DISPATCH_HEAVY_SELF_THRESHOLD", "0.75")
    assert check_dispatch_posture(claude_root=claude_root) == []


def test_dispatch_posture_silent_when_sample_too_small(tmp_path: Path) -> None:
    """Below MIN_TURNS, heavy_self ratio is statistically meaningless → no warn."""
    from minions.scaffold.audit import check_dispatch_posture

    role_cwd = tmp_path / "project_38000" / "branches" / "coder"
    role_cwd.mkdir(parents=True)
    claude_root = tmp_path / "claude" / "projects"
    # Fewer than _DISPATCH_POSTURE_MIN_TURNS (=20), all heavy
    _build_role_jsonl(
        claude_root / "slug",
        cwd=str(role_cwd),
        tool_uses=["Bash"] * 5,
    )
    assert check_dispatch_posture(claude_root=claude_root) == []
