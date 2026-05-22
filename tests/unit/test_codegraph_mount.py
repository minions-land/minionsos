"""Tests for the codegraph (Coder L3) MCP mount.

Covers:
- Whitelist (CLI surface) parity: every EACN role main session sees the full
  codegraph tool surface byte-identically (KV cache invariant).
- Server-side authz: heavy tools (context/explore) gated to coder + expert;
  light tools accessible to coder, expert, ethics, gru, noter.
- Subagent surface: codegraph tools NOT exposed to subagents (matches graphify policy).
- Writer is excluded entirely (does not consume code).
- _gen_mcp_json registers codegraph; doctor probe sets include codegraph.
- Launcher script exists, is executable, and references the upstream binary path.
"""

from __future__ import annotations

import stat
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────

_LIGHT = {
    "mcp__codegraph__codegraph_search",
    "mcp__codegraph__codegraph_callers",
    "mcp__codegraph__codegraph_callees",
    "mcp__codegraph__codegraph_impact",
    "mcp__codegraph__codegraph_node",
    "mcp__codegraph__codegraph_files",
    "mcp__codegraph__codegraph_status",
}
_HEAVY = {
    "mcp__codegraph__codegraph_context",
    "mcp__codegraph__codegraph_explore",
}
_ALL = _LIGHT | _HEAVY


# ── CLI whitelist parity (KV cache invariant) ─────────────────────────────


def test_cli_whitelist_parity_across_eacn_roles() -> None:
    """All EACN-visible main roles share the unified _EACN_ROLE_MAIN_TOOLS list,
    so their codegraph surface must be byte-identical (LIGHT + HEAVY both)."""
    from minions.config import resolve_whitelist

    for role in ("gru", "coder", "writer", "ethics", "expert"):
        allowed = set(resolve_whitelist(role, "main"))
        missing = _ALL - allowed
        assert not missing, f"{role} main is missing codegraph tools: {missing}"


def test_cli_whitelist_noter_has_codegraph_light_at_minimum() -> None:
    """Noter is on its own (Sonnet) cache namespace and uses the bespoke
    main whitelist; it gets LIGHT codegraph for stat/file probes."""
    from minions.config import resolve_whitelist

    allowed = set(resolve_whitelist("noter", "main"))
    missing = _LIGHT - allowed
    assert not missing, f"noter main is missing codegraph LIGHT tools: {missing}"


# ── Server-side authz (real enforcement boundary) ─────────────────────────


def test_server_authz_coder_main_has_full_surface() -> None:
    from minions.config import resolve_server_authz

    allowed = set(resolve_server_authz("coder", "main"))
    missing = _ALL - allowed
    assert not missing, f"coder main authz is missing: {missing}"


def test_server_authz_expert_main_has_full_surface() -> None:
    from minions.config import resolve_server_authz

    allowed = set(resolve_server_authz("expert", "main"))
    missing = _ALL - allowed
    assert not missing, f"expert main authz is missing: {missing}"


def test_server_authz_ethics_main_has_light_only() -> None:
    from minions.config import resolve_server_authz

    allowed = set(resolve_server_authz("ethics", "main"))
    missing_light = _LIGHT - allowed
    leaked_heavy = _HEAVY & allowed
    assert not missing_light, f"ethics main authz missing LIGHT: {missing_light}"
    assert not leaked_heavy, f"ethics main authz unexpectedly has HEAVY: {leaked_heavy}"


def test_server_authz_writer_has_no_codegraph() -> None:
    """Writer does not consume code; codegraph would be dead surface."""
    from minions.config import resolve_server_authz

    allowed = set(resolve_server_authz("writer", "main"))
    leaked = _ALL & allowed
    assert not leaked, f"writer main authz unexpectedly has codegraph: {leaked}"


def test_server_authz_noter_main_has_light_only() -> None:
    from minions.config import resolve_server_authz

    allowed = set(resolve_server_authz("noter", "main"))
    missing_light = _LIGHT - allowed
    leaked_heavy = _HEAVY & allowed
    assert not missing_light, f"noter main authz missing LIGHT: {missing_light}"
    assert not leaked_heavy, f"noter main authz unexpectedly has HEAVY: {leaked_heavy}"


def test_server_authz_gru_main_has_light_only() -> None:
    from minions.config import resolve_server_authz

    allowed = set(resolve_server_authz("gru", "main"))
    missing_light = _LIGHT - allowed
    leaked_heavy = _HEAVY & allowed
    assert not missing_light, f"gru main authz missing LIGHT: {missing_light}"
    assert not leaked_heavy, f"gru main authz unexpectedly has HEAVY: {leaked_heavy}"


def test_server_authz_subagents_have_no_codegraph() -> None:
    """Subagents never see codegraph — same policy as graphify."""
    from minions.config import resolve_server_authz

    for role in ("coder", "writer", "ethics", "expert", "gru", "noter"):
        try:
            allowed = set(resolve_server_authz(role, "subagent"))
        except Exception:
            continue
        leaked = _ALL & allowed
        assert not leaked, f"{role} subagent authz unexpectedly has codegraph: {leaked}"


# ── _gen_mcp_json registration ────────────────────────────────────────────


def test_gen_mcp_json_registers_codegraph(tmp_path: Path) -> None:
    """Running _gen_mcp_json against a fake project root must produce a
    .mcp.json with the codegraph server entry."""
    import json
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parent.parent.parent
    gen = repo_root / "minions" / "tools" / "_gen_mcp_json.py"
    assert gen.exists(), "generator script missing"

    subprocess.run(
        [sys.executable, str(gen), str(tmp_path)],
        check=True,
        capture_output=True,
    )
    cfg = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    servers = cfg.get("mcpServers", {})
    assert "codegraph" in servers, f"codegraph missing from generated .mcp.json: {sorted(servers)}"
    cg = servers["codegraph"]
    assert cg["command"] == "bash"
    assert cg["args"] == ["mcp-servers/codegraph/launcher.sh"]


# ── Doctor probe: codegraph in core mount sets ────────────────────────────


def test_doctor_probe_includes_codegraph() -> None:
    """The mcp-config-mounts-core probe enforces that codegraph is present
    in both .mcp.json and .codex/config.toml."""
    cli = Path(__file__).resolve().parent.parent.parent / "minions" / "cli.py"
    text = cli.read_text(encoding="utf-8")
    # Both probe sites (Claude Code mcp.json + Codex toml) must include codegraph.
    assert text.count('"codegraph"') >= 2, (
        "codegraph must appear in both core-mount probe sets in minions/cli.py"
    )


# ── Launcher script invariants ────────────────────────────────────────────


def test_launcher_script_exists_and_is_executable() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    launcher = repo_root / "mcp-servers" / "codegraph" / "launcher.sh"
    assert launcher.exists(), "codegraph launcher missing"
    mode = launcher.stat().st_mode
    assert mode & stat.S_IXUSR, "launcher.sh must be executable"


def test_launcher_resolves_repo_scope_when_port_unset() -> None:
    """Static check: when MINIONS_PROJECT_PORT is unset, launcher SCOPE should
    fall back to REPO_ROOT (not exit with an error like graphify does)."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    launcher = repo_root / "mcp-servers" / "codegraph" / "launcher.sh"
    text = launcher.read_text(encoding="utf-8")
    # Repo-scope fallback branch must exist (the `else SCOPE="$REPO_ROOT"` arm).
    assert 'SCOPE="$REPO_ROOT"' in text, "launcher must support repo-scope fallback"
    # No graphify-style hard fail on missing port.
    assert "MINIONS_PROJECT_PORT must be set" not in text, (
        "codegraph launcher must NOT hard-fail on missing port (unlike graphify)"
    )


def test_launcher_fails_fast_on_missing_index() -> None:
    """Launcher must NOT silently retry init at MCP-connect time.

    `codegraph init -i` does an initial tree-sitter pass that on a large repo
    can take tens of seconds; running it inside the MCP handshake would time
    out the connection. The launcher therefore exits 1 with a bootstrap
    instruction; install.sh warms repo scope; project scope is bootstrapped
    out-of-band.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    launcher = repo_root / "mcp-servers" / "codegraph" / "launcher.sh"
    text = launcher.read_text(encoding="utf-8")
    assert "init -i" in text, "launcher must point operators at `init -i` for bootstrap"
    assert "exit 1" in text, "launcher must fail-fast (exit 1) when index missing"
    assert "serve --mcp" in text, "launcher must exec `serve --mcp`"
    assert "init --quiet" not in text, (
        "`codegraph init` does not support --quiet upstream; using it would error"
    )


# ── Package metadata ──────────────────────────────────────────────────────


def test_package_json_pins_upstream() -> None:
    import json

    repo_root = Path(__file__).resolve().parent.parent.parent
    pkg = repo_root / "mcp-servers" / "codegraph" / "package.json"
    assert pkg.exists()
    data = json.loads(pkg.read_text(encoding="utf-8"))
    deps = data.get("dependencies", {})
    assert "@colbymchenry/codegraph" in deps, "must depend on upstream npm package"


# ── Project lifecycle bootstrap ───────────────────────────────────────────


def test_bootstrap_coder_graph_skips_when_index_exists(tmp_path: Path) -> None:
    """If `.codegraph/` already exists, bootstrap is a no-op (idempotent)."""
    from minions.lifecycle.project import _bootstrap_coder_graph

    workspace = tmp_path / "branches" / "coder"
    (workspace / ".codegraph").mkdir(parents=True)
    # Should not raise, should not log a warning, should not call subprocess.
    _bootstrap_coder_graph(workspace)
    assert (workspace / ".codegraph").is_dir()


def test_bootstrap_coder_graph_warns_when_binary_missing(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    """If the npm install hasn't run yet, bootstrap warns and returns gracefully."""
    import logging

    from minions.lifecycle import project as project_mod

    # Point MINIONS_ROOT at an empty tree so node_modules/.bin/codegraph is missing.
    monkeypatch.setattr(project_mod, "MINIONS_ROOT", tmp_path)
    workspace = tmp_path / "branches" / "coder"
    workspace.mkdir(parents=True)

    with caplog.at_level(logging.WARNING):
        project_mod._bootstrap_coder_graph(workspace)

    assert any("codegraph binary missing" in r.message for r in caplog.records)
    # Bootstrap is non-fatal — workspace is left untouched.
    assert not (workspace / ".codegraph").exists()


def test_ensure_role_workspace_invokes_bootstrap_only_for_coder(
    tmp_path: Path, monkeypatch
) -> None:
    """Lifecycle dispatch: only role_name=='coder' should trigger codegraph bootstrap."""
    from minions.lifecycle import project as project_mod

    calls: list[Path] = []

    def fake_create(port, role_name, base_branch=None):
        ws = tmp_path / role_name
        ws.mkdir(parents=True, exist_ok=True)
        return ("branch", ws)

    monkeypatch.setattr(project_mod, "_create_role_worktree", fake_create)
    monkeypatch.setattr(project_mod, "_seed_claude_settings", lambda ws: None)
    monkeypatch.setattr(project_mod, "_bootstrap_coder_graph", lambda ws: calls.append(ws))

    project_mod.ensure_role_workspace(99999, "writer")
    assert calls == [], "writer role must not trigger codegraph bootstrap"

    project_mod.ensure_role_workspace(99999, "coder")
    assert len(calls) == 1, "coder role must trigger exactly one bootstrap call"
