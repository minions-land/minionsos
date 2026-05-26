"""Resident-Role process launcher.

Each MinionsOS Role runs as a long-lived ``claude`` process inside its own
``tmux`` session. This module is the only place that knows how to start
that session, detect whether it is still alive, attach to it, or kill it.

Why tmux:

- Long-lived ``claude`` is interactive and wants a TTY.
- The author needs an emergency hatch to drop into a Role's session and see
  exactly what the model sees ("hop in over its shoulder").
- A named tmux session is trivial to ``has-session`` / ``attach`` / ``kill``
  from outside, and survives a closed terminal.

Naming: each session is named ``mos-{port}-{role}`` so any operator can
``tmux ls`` to see all live Roles or ``tmux attach -t mos-37596-coder`` to
inspect one.

The launcher does NOT manage role state in ``projects.json`` — that is the
caller's job. The launcher only owns the tmux session and the ``claude``
argv it dispatches.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from minions.config import GruConfig, load_gru_config, whitelist_csv
from minions.errors import RoleError
from minions.lifecycle.agent_host import build_role_invocation
from minions.lifecycle.eacn_identity import (
    plugin_state_dir,
    resolve_agent_id,
)
from minions.paths import (
    MINIONS_ROOT,
    common_role_system_md,
    project_role_log,
    project_role_workspace,
    project_session_name,
    project_workspace,
    project_workspace_root,
    role_system_md,
)
from minions.state.store import RoleEntry

logger = logging.getLogger(__name__)


def session_name(project_port: int, role_name: str) -> str:
    """Return the tmux session name for *(port, role)*."""
    return f"mos-{project_port}-{role_name}"


def session_alive(project_port: int, role_name: str) -> bool:
    """Return True if a tmux session for this Role is currently alive."""
    if not _have_tmux():
        return False
    name = session_name(project_port, role_name)
    return _tmux_has_session(name)


def kill_session(project_port: int, role_name: str) -> bool:
    """Kill the tmux session for this Role. Returns True if a session was killed."""
    if not _have_tmux():
        return False
    name = session_name(project_port, role_name)
    if not _tmux_has_session(name):
        return False
    try:
        subprocess.run(
            ["tmux", "kill-session", "-t", name],
            check=True,
            capture_output=True,
        )
        logger.info("kill_session: tmux session=%s killed", name)
        return True
    except subprocess.CalledProcessError as exc:
        logger.warning("kill_session: tmux kill-session failed for %s: %s", name, exc)
        return False


def attach_command(project_port: int, role_name: str) -> list[str]:
    """Return the argv the operator can run to attach to a Role session.

    The launcher itself never attaches; it only reports the command so the
    user can ``tmux attach -t ...`` from their own terminal.
    """
    return ["tmux", "attach", "-t", session_name(project_port, role_name)]


def list_project_sessions(project_port: int) -> list[str]:
    """Return tmux session names matching the ``mos-{port}-*`` prefix.

    Used by lifecycle cleanup to find orphan Role sessions whose names
    were never recorded in ``meta.json`` — for example because the
    record was set to ``state="dismissed"`` while the tmux session was
    still alive (a kill/revive ordering bug).
    """
    if not _have_tmux():
        return []
    prefix = f"mos-{project_port}-"
    try:
        proc = subprocess.run(
            ["tmux", "ls", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip().startswith(prefix)]


def kill_project_sessions(project_port: int) -> list[str]:
    """Kill every ``mos-{port}-*`` tmux session. Returns the names killed.

    Defensive sweep used by ``project_kill`` and ``project_revive`` to
    eliminate orphan Role tmux sessions regardless of what
    ``meta.json`` thinks. Idempotent: calling it twice is safe.
    """
    killed: list[str] = []
    for name in list_project_sessions(project_port):
        try:
            subprocess.run(
                ["tmux", "kill-session", "-t", name],
                check=True,
                capture_output=True,
            )
            killed.append(name)
            logger.info("kill_project_sessions: tmux session=%s killed", name)
        except subprocess.CalledProcessError as exc:
            logger.warning(
                "kill_project_sessions: tmux kill-session failed for %s: %s",
                name,
                exc,
            )
    return killed


def launch_role_process(
    role_entry: RoleEntry,
    project_port: int,
    *,
    cfg: GruConfig | None = None,
    resume: bool = False,
) -> dict[str, object]:
    """Start a long-lived ``claude`` process for *role_entry* in tmux.

    Idempotent in the "session already alive" sense: if the named tmux
    session is already running, the function returns without launching a
    second one. Callers wanting to force-restart should ``kill_session``
    first.

    When ``resume=True``, the launched ``claude`` is invoked with
    ``--resume <session_name>`` so Claude Code reattaches to the prior
    conversation persisted under the role's cwd in
    ``~/.claude/projects/<cwd-slug>/``. **This resets the prompt cache** —
    Claude Code rebuilds the cache from scratch and replays the prior
    history as fresh uncached input, which for a long-running Role
    typically costs hundreds of thousands of tokens. Pass ``resume=True``
    only for explicit operator debugging; ``project_revive`` and the
    crash-watchdog respawn path both pass ``resume=False`` so Roles cold-
    start and rebuild context from the Draft (L1) instead.

    Returns a small status dict with ``session_name``, ``cwd``,
    ``log_path``, ``attach_cmd``, ``started`` (True if a fresh session was
    launched, False if an existing session was found), and ``resumed``
    (mirrors the *resume* argument when a fresh session was launched).
    """
    if not _have_tmux():
        raise RoleError("tmux is not installed; resident-Role launcher requires tmux on PATH.")

    role_name = role_entry.name
    name = session_name(project_port, role_name)

    if _tmux_has_session(name):
        logger.info(
            "launch_role_process: tmux session=%s already alive; skipping launch",
            name,
        )
        return {
            "session_name": name,
            "started": False,
            "resumed": False,
            "attach_cmd": attach_command(project_port, role_name),
        }

    cfg = cfg or load_gru_config()
    workspace = (
        Path(role_entry.workspace_path)
        if role_entry.workspace_path
        else project_role_workspace(project_port, role_name)
    )
    if not workspace.exists() and project_workspace(project_port).exists():
        workspace = project_workspace(project_port)

    log_path = project_role_log(project_port, role_name)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Pre-allocate a Claude Code session UUID so we can lock its registry
    # entry BEFORE claude starts. This prevents any host-side auto-rename
    # hook from overwriting the deliberate ``mos-{port}-{role}`` label
    # under /resume. See minions/lifecycle/sidecar_lock.py.
    from minions.lifecycle.sidecar_lock import allocate_session_id

    claude_session_id = allocate_session_id()

    # Workflow-plugin injection: if this role has an associated workflow plugin,
    # generate a per-instance MCP config, resolve extra tools, and inject
    # skills into the workspace.
    mcp_config_path: Path | None = None
    extra_allowed: str = ""
    extra_domain_md: Path | None = None

    if role_entry.workflow_plugin_slug:
        from minions.lifecycle.workflow_plugins import (
            generate_instance_mcp_config,
            inject_skills_to_workspace,
            load_manifest,
            resolve_extra_allowed_tools,
        )

        manifest = load_manifest(role_entry.workflow_plugin_slug)
        session = session_name(project_port, role_name)
        mcp_config_path = generate_instance_mcp_config(
            MINIONS_ROOT / ".mcp.json", manifest, session
        )
        extra_tools = resolve_extra_allowed_tools(manifest)
        if extra_tools:
            extra_allowed = "," + ",".join(extra_tools)
        inject_skills_to_workspace(manifest, workspace)
        extra_domain_md = manifest.domain_pack_path

    invocation = build_role_invocation(
        cfg=cfg,
        role_name=role_name,
        project_port=project_port,
        project_agent_id=role_entry.eacn_agent_id or role_name,
        system_path=_combined_system_prompt(role_name, extra_domain_md=extra_domain_md),
        allowed_tools=whitelist_csv(role_name, "main") + extra_allowed,
        workspace=workspace,
        session_name=role_entry.session_name or project_session_name(project_port, role_name),
        resume=resume,
        model=_role_model(cfg, role_name),
        mcp_config_path=mcp_config_path,
        role_system_paths=_role_system_paths(role_name, extra_domain_md=extra_domain_md),
        claude_session_id=claude_session_id,
    )

    # Lock the registry entry BEFORE the claude process starts so the
    # auto_title hooks (if installed) see locked=true on their first
    # SessionStart and never overwrite the title.
    from minions.lifecycle.sidecar_lock import lock_session_title

    lock_session_title(claude_session_id, name)

    env = _role_env(
        role_name=role_name,
        project_port=project_port,
        role_entry=role_entry,
        workspace=workspace,
    )
    _spawn_tmux(
        session_name=name,
        cwd=invocation.cwd,
        env=env,
        argv=invocation.command,
        initial_prompt=invocation.initial_prompt,
        log_path=log_path,
    )
    logger.info(
        "launch_role_process: tmux session=%s launched role=%s port=%d resume=%s",
        name,
        role_name,
        project_port,
        resume,
    )
    return {
        "session_name": name,
        "started": True,
        "resumed": bool(resume),
        "cwd": str(invocation.cwd),
        "log_path": str(log_path),
        "attach_cmd": attach_command(project_port, role_name),
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _have_tmux() -> bool:
    return shutil.which("tmux") is not None


def _tmux_has_session(name: str) -> bool:
    try:
        proc = subprocess.run(
            ["tmux", "has-session", "-t", name],
            capture_output=True,
        )
        return proc.returncode == 0
    except FileNotFoundError:
        return False


def _spawn_tmux(
    *,
    session_name: str,
    cwd: Path,
    env: dict[str, str],
    argv: list[str],
    initial_prompt: str,
    log_path: Path,
) -> None:
    """Start a detached tmux session running *argv*, then send *initial_prompt*.

    The session is created with ``tmux new-session -d`` so it never
    daemonizes inside the caller's TTY. Logging is captured via
    ``tmux pipe-pane`` (NOT a shell ``| tee`` pipe) — Claude Code 2.1+
    detects a non-TTY stdout when piped through ``tee`` and silently
    switches to ``--print`` mode, then errors with "Input must be
    provided through stdin" because the launcher feeds its initial
    prompt via send-keys, not stdin. ``pipe-pane`` taps the pty after
    Claude already attached, so the TTY check passes.

    After session is up we ``send-keys`` the initial prompt followed by
    ``Enter``. Claude Code's REPL treats a multiline pasted block as a
    single buffered submission requiring an explicit Enter to commit, so
    we send a second Enter after a short delay to ensure the prompt
    actually fires.
    """
    cmd_str = " ".join(_quote(a) for a in argv)
    new_session_cmd = [
        "tmux",
        "new-session",
        "-d",
        "-s",
        session_name,
        "-c",
        str(cwd),
    ]
    for key, value in env.items():
        new_session_cmd += ["-e", f"{key}={value}"]
    new_session_cmd.append(cmd_str)

    try:
        subprocess.run(new_session_cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
        raise RoleError(
            f"tmux new-session failed for {session_name}: {stderr.strip() or exc}"
        ) from exc

    # Capture pane output to log via tmux's own pipe-pane (preserves TTY).
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "tmux",
                "pipe-pane",
                "-t",
                session_name,
                f"cat >> {_quote(str(log_path))}",
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        # Logging is optional — never fail the spawn over a missing log.
        logger.warning(
            "_spawn_tmux: pipe-pane failed for %s; role will run without log: %s",
            session_name,
            exc,
        )

    # Give claude a moment to come up, then deliver the initial prompt.
    # The delivery (poll-until-REPL-ready up to 30s + paste + commit + retry
    # up to 3 attempts x 5s activity check) costs up to ~47s of wall-clock
    # per role. With Gru spawning ~7 roles at project bootstrap, that's
    # ~5 min of pure synchronization. Move the whole delivery to a daemon
    # thread so the launcher returns as soon as the tmux session is alive
    # and the prompt is *queued*, rather than after it's been delivered.
    #
    # Roles already tolerate slow first-prompt delivery — they wake up
    # when the prompt actually lands, not when launch_role_process
    # returns. The Claude Code REPL itself buffers keystrokes safely.
    #
    # Tests that need to assert delivery completed can opt in by setting
    # ``MINIONS_ROLE_LAUNCHER_SYNC=1`` (the default-off env switch
    # preserves the test_role_register_invoke / test_bootstrap_seed
    # contracts that previously assumed sync delivery).
    sync = os.environ.get("MINIONS_ROLE_LAUNCHER_SYNC") == "1"
    if sync:
        _tmux_send_initial_prompt(session_name, initial_prompt)
    else:
        import threading

        def _deliver() -> None:
            try:
                _tmux_send_initial_prompt(session_name, initial_prompt)
            except Exception as exc:  # daemon thread — never propagate
                logger.warning(
                    "_spawn_tmux: background prompt delivery failed for %s: %s",
                    session_name,
                    exc,
                )

        threading.Thread(
            target=_deliver,
            name=f"role-launcher-deliver-{session_name}",
            daemon=True,
        ).start()


# U+276F HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT — this is the
# literal glyph the Claude Code TUI prints as its input prompt. The character
# is intentional; ruff's "ambiguous" rule is suppressed because it looks
# nothing like a plain '>' to our pane probe.
_CLAUDE_PROMPT_GLYPH = chr(0x276F)


def _capture_pane(session_name: str) -> str:
    """Return the current visible content of *session_name*'s pane, or '' on failure."""
    try:
        proc = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout or ""


def _wait_for_repl_ready(
    session_name: str, *, timeout: float = 30.0, poll_interval: float = 0.25
) -> bool:
    """Block until Claude Code's REPL prompt appears, or *timeout* elapses.

    Markers we accept (any one is enough):
    - the Claude Code TUI prompt glyph (U+276F);
    - ``"> "`` AND a ``"claude"`` welcome line — fallback for a degraded
      glyph-stripped pane;
    - ``"Welcome to"`` plus at least 200 chars of pane content — Claude
      finished its splash and is showing prompts.

    Returns True if the marker was seen, False on timeout. False is not
    fatal — the caller proceeds best-effort to send-keys, matching pre-v15.7
    behavior on hosts where the marker probe somehow fails.

    Why this exists: the previous fixed ``time.sleep(3)`` was a TOCTOU race
    on loaded hosts. If MCP server startup or git worktree creation slowed
    Claude past the 3 s window, send-keys ran against a TTY whose paste
    buffer wasn't open yet and the keystrokes were silently dropped — the
    role process came up with an empty prompt and parked. See GitHub
    Issue #2.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pane = _capture_pane(session_name)
        if _CLAUDE_PROMPT_GLYPH in pane:
            return True
        if "> " in pane and "claude" in pane.lower():
            return True
        if "Welcome to" in pane and len(pane) > 200:
            return True
        time.sleep(poll_interval)
    logger.warning(
        "_wait_for_repl_ready: timeout (%.1fs) waiting for Claude REPL prompt in %s; "
        "proceeding with send-keys best-effort",
        timeout,
        session_name,
    )
    return False


def _tmux_paste_prompt(session_name: str, prompt: str) -> None:
    """Inject *prompt* into the tmux session via a temp-file paste buffer.

    Why not ``send-keys -l``: tmux's argv length limit (~32 KB on Linux)
    rejects large prompts with ``command too long``. Role init prompts
    routinely exceed 32 KB once role SYSTEM.md, all skill files, and
    book/hot.md are concatenated (78 KB observed for ``ethics``). See
    GitHub Issue #22.

    The load-buffer + paste-buffer path reads the prompt from a file,
    avoiding the argv limit entirely. ``paste-buffer -d`` deletes the
    buffer after paste so it does not leak into other sessions.
    """
    import os
    import tempfile
    from contextlib import suppress

    fd, buf_path = tempfile.mkstemp(prefix="minionsos_init_", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(prompt)
        buf_name = f"minionsos_init_{session_name}_{os.getpid()}"
        subprocess.run(
            ["tmux", "load-buffer", "-b", buf_name, buf_path],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["tmux", "paste-buffer", "-d", "-b", buf_name, "-t", session_name],
            check=True,
            capture_output=True,
        )
    finally:
        with suppress(OSError):
            os.unlink(buf_path)


def _tmux_send_initial_prompt(session_name: str, prompt: str) -> None:
    """Inject *prompt* into the tmux session as if the operator typed it.

    Two waits + two Enters are deliberate. Claude Code 2.1 needs the REPL
    to be attached before keystrokes register, and its multiline paste mode
    treats a freshly pasted block as buffered input that requires an
    explicit Enter to commit. The sequence:

    1. Poll-until-ready: capture-pane in a 30 s loop until the Claude REPL
       prompt marker appears (replaces the legacy fixed 3 s sleep, which
       was racy on loaded hosts — see GitHub Issue #2).
    2. load-buffer + paste-buffer: pastes the prompt verbatim via a
       file-backed tmux buffer, sidestepping the ~32 KB argv limit on
       ``send-keys -l`` (GitHub Issue #22). Role init prompts routinely
       exceed 32 KB once skills + hot-cache are stitched in.
    3. send-keys Enter: turns the paste into a committed multiline block.
    4. Brief sleep so the REPL processes the commit.
    5. send-keys Enter: actually submits the prompt to the model.
    6. Activity check: wait up to 5 s for the pane to change (model begins
       processing). If no change is seen, retry steps 2-5 up to 2 more
       times. This guards against the case where "Welcome back!" sessions
       (with long prior history) falsely satisfy the ready-check while
       still replaying history — the keystrokes land in the input field
       but are never committed (GitHub Issue #21).
    """
    import time

    # 1. Wait for Claude's REPL to be ready (replaces fixed sleep).
    _wait_for_repl_ready(session_name)

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            pane_before = _capture_pane(session_name)
            # 2. Paste the prompt via a file-backed buffer.
            _tmux_paste_prompt(session_name, prompt)
            # 3. Commit the paste.
            subprocess.run(
                ["tmux", "send-keys", "-t", session_name, "Enter"],
                check=True,
                capture_output=True,
            )
            # 4. Brief settle.
            time.sleep(0.5)
            # 5. Actually submit.
            subprocess.run(
                ["tmux", "send-keys", "-t", session_name, "Enter"],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
            logger.warning(
                "_tmux_send_initial_prompt: tmux call failed for %s: %s; stderr=%r",
                session_name,
                exc,
                stderr,
            )
            return
        # 6. Activity check: wait up to 5 s for the pane to change.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            time.sleep(0.25)
            pane_after = _capture_pane(session_name)
            if pane_after != pane_before:
                logger.info(
                    "_tmux_send_initial_prompt: activity detected for %s (attempt %d/%d)",
                    session_name,
                    attempt,
                    max_attempts,
                )
                return
        # No change detected — session may still be loading prior history.
        # Re-wait for the REPL to be ready, then retry.
        logger.warning(
            "_tmux_send_initial_prompt: no activity after 5s for %s (attempt %d/%d); retrying",
            session_name,
            attempt,
            max_attempts,
        )
        _wait_for_repl_ready(session_name)


def _role_env(
    *,
    role_name: str,
    project_port: int,
    role_entry: RoleEntry,
    workspace: Path,
) -> dict[str, str]:
    """Build the environment passed to the Role's claude process.

    Only includes the variables ``mos_await_events`` and the role contract
    actually need: project port, agent id, workspace path, role name,
    EACN3 plugin state dir.
    """
    eacn_agent_id = role_entry.eacn_agent_id or resolve_agent_id(project_port, role_name)
    # Generate a unique session ID for this role process. Used by the Reel
    # (L0) layer to organize captured transcripts under a stable session
    # directory. Session IDs are timestamped at launch and remain constant
    # for the lifetime of the tmux session.
    from datetime import UTC, datetime

    session_id = f"sess-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    return {
        "MINIONS_AGENT_HOST": "claude",
        "MINIONS_ROLE_NAME": role_name,
        "MINIONS_AGENT_TYPE": "main",
        "MINIONS_PROJECT_PORT": str(project_port),
        "MINIONS_AGENT_ID": eacn_agent_id,
        "MINIONS_SESSION_ID": session_id,
        "MINIONS_WORKSPACE": str(workspace),
        "MINIONS_WORKSPACE_ROOT": str(project_workspace_root(project_port)),
        "MINIONS_WORKSPACE_MAIN": str(project_workspace(project_port)),
        "MINIONS_ROLE_WORKSPACE": str(workspace),
        "MINIONS_ROLE_WORKSPACE_BRANCH": role_entry.workspace_branch or "",
        "EACN3_NETWORK_URL": f"http://127.0.0.1:{project_port}",
        "EACN3_STATE_DIR": str(plugin_state_dir(project_port, eacn_agent_id).resolve()),
        "MINIONS_GITHUB_PUSH_TARGET": role_entry.github_push_target or "",
        # Anchor for hook-command resolution. Role workspaces are git
        # worktrees whose `git rev-parse --show-toplevel` is the worktree
        # path, NOT MinionsOS root — so hook commands that fall back to
        # `--show-toplevel` resolve to a path that has no `.venv` and no
        # `minions/hooks/`. Exporting MINIONS_ROOT lets the hook gate in
        # `.claude/settings.json` resolve to the real install instead.
        # Also consumed directly by minions/hooks/post_compact_draft.py.
        "MINIONS_ROOT": str(MINIONS_ROOT),
        # Long-horizon cache hit-rate optimization: opt the Role's claude
        # process into 1-hour prompt cache TTL on backends that honor it
        # (direct Anthropic API key, Bedrock, Vertex, Foundry — see
        # claude-code CHANGELOG 2.1.108). NOTE: a *stock* Claude Code CLI
        # binary does NOT actually send the ttl:"1h" cache_control field
        # even when this env var is set; only a patched binary (see
        # ~/Tools/claude-1h-cache-patch/) emits the header. On stock binaries
        # this var is a silent no-op and the cliff stays at 5 min, so we
        # keep cache_keepalive_seconds (default 240s) as the load-bearing
        # cliff guard. The env var is harmless to set unconditionally —
        # when ignored it does nothing; when honored it lifts the cliff.
        # Requires claude CLI ≥ 2.1.131 (earlier versions silently
        # downgraded 1h to 5 min). DISABLE_TELEMETRY would force a 5-min
        # fallback for subscription auth, so we deliberately do not set it.
        "ENABLE_PROMPT_CACHING_1H": "1",
        # 5-minute cache-cliff guard: when ENABLE_PROMPT_CACHING_1H is
        # silently ignored by the upstream gateway, we still want long-
        # running Bash subagent calls to slot under the default 5-min TTL
        # rather than splitting cache blocks across cliff boundaries.
        # BASH_DEFAULT_TIMEOUT_MS=120000 (2 min) keeps individual Bash
        # turns short enough that the model's reply lands well before the
        # cache window closes; BASH_MAX_TIMEOUT_MS=240000 (4 min) caps the
        # absolute upper bound at < 5 min so user-supplied `timeout:` args
        # cannot push a turn past the cliff. CLAUDE_AUTO_BACKGROUND_TASKS=1
        # makes the harness auto-promote any Bash that's still running near
        # its timeout into a background task (BashOutput) instead of
        # blocking the conversation, which is the single biggest source of
        # cache-window overruns in long-lived Role loops. These three are
        # mirrored in MinionsOS/.claude/settings.json for the dev-host
        # session and in minions/bin/gru for Gru, so all three agent
        # surfaces (dev / Gru / Role) inherit the same cliff-guard config
        # without depending on ~/.claude/settings.json.
        "BASH_DEFAULT_TIMEOUT_MS": "120000",
        "BASH_MAX_TIMEOUT_MS": "240000",
        "CLAUDE_AUTO_BACKGROUND_TASKS": "1",
        # Root-uid sandbox attestation. Many SSH boxes run as root, and Claude
        # Code refuses to honor --permission-mode=bypassPermissions (and
        # --dangerously-skip-permissions) under euid 0 unless IS_SANDBOX=1 is
        # set as the operator's self-attestation that the host is sandboxed.
        # Gru gets this for free via minions/bin/gru's GRU_SANDBOX=1 default,
        # but Role tmux sessions launch with this clean env dict (no inherit),
        # so without an explicit entry every Role wakeup would crash on a
        # root-uid host. The default here is "1" because every Role MinionsOS
        # spawns is permission-bypassed by design — the boundary is enforced
        # by --allowed-tools + server-side authz, not by the OS prompt.
        "IS_SANDBOX": "1",
        # Tiered Tool Search for Role processes. Background:
        # - 2026-05-19: ENABLE_TOOL_SEARCH=false was forced because the
        #   dispatch-eval e2e showed Coder thrashing 6+ min on deferred
        #   eacn3_* tools — the forever-loop prompt didn't teach the
        #   ToolSearch dance, so the agent gave up.
        # - 2026-05-25: MANUAL/ shipped (155 atomic pages, 12 domain
        #   cards, lookup.py CLI, pitfall-deferred-schema page). MANUAL.md
        #   is now always-loaded L0 and explicitly tells the agent how
        #   to recover from "tool not found":
        #     ToolSearch(query="select:<exact_name>")
        # Re-enabling deferred loading became safe and saves ~25k tokens
        # per Role wake-up (project_37596 evidence: 134/153 MCP tools were
        # never called; eager-loading them was pure tax).
        # Valid Claude Code values: "true" / "false" / "auto" / "auto:N".
        # `auto:30` keeps the top-30 most-used tools eagerly loaded
        # (data-driven from project_37596 logs: covers ≥99% of real call
        # volume) and defers the long tail. The MANUAL/ pitfall page tells
        # the agent how to load deferred schemas on demand.
        # An invalid value (e.g. "0") is silently ignored on non-first-party
        # hosts like tok.fan, leaving the default in place.
        "ENABLE_TOOL_SEARCH": "auto:30",
        "PATH": os.environ.get("PATH", ""),
    }


def _role_model(cfg: GruConfig, role_name: str) -> str | None:
    """Return the model override for a role, or None for the default."""
    if role_name == "noter":
        return cfg.noter_model
    return cfg.claude_model or None


def _combined_system_prompt(role_name: str, *, extra_domain_md: Path | None = None) -> Path | None:
    """Return the path to the common SYSTEM.md only (cache-optimized).

    Cache optimization: all roles share the same ``--append-system-prompt``
    content (the common contract at ``minions/roles/SYSTEM.md``). Role-specific
    instructions and domain packs are injected into the first user message by
    ``build_forever_loop_prompt`` via ``role_system_paths``, so the system-prompt
    prefix stays byte-identical across roles and maximizes cross-role KV cache
    sharing at the API level.
    """
    del role_name, extra_domain_md  # no longer used; role-specific goes to user msg
    common_path = common_role_system_md()
    if common_path.exists():
        return common_path
    return None


def _role_system_paths(role_name: str, *, extra_domain_md: Path | None = None) -> list[Path]:
    """Return the list of role-specific SYSTEM.md paths for user-message injection."""
    from minions.config import normalise_role_name

    role_path = role_system_md(normalise_role_name(role_name))
    paths: list[Path] = []
    if role_path.exists():
        paths.append(role_path)
    if extra_domain_md and extra_domain_md.exists():
        paths.append(extra_domain_md)
    return paths


def _quote(value: str) -> str:
    """Minimal shell quoting for tmux command-string concatenation."""
    if not value:
        return "''"
    safe = all(c.isalnum() or c in "@%+=:,./-_" for c in value)
    if safe:
        return value
    return "'" + value.replace("'", "'\\''") + "'"


# Surface MINIONS_ROOT for tests / callers that need it relative to this module.
__all__ = [
    "MINIONS_ROOT",
    "attach_command",
    "kill_project_sessions",
    "kill_session",
    "launch_role_process",
    "list_project_sessions",
    "session_alive",
    "session_name",
]
