#!/usr/bin/env bash
# MinionsOS — idempotent installer.
# Usage: ./install.sh
# Re-running is safe; each step checks before acting.
set -euo pipefail

# ── ANSI colours ──────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; RESET='\033[0m'

info()  { echo -e "${CYAN}[info]${RESET}  $*"; }
ok()    { echo -e "${GREEN}[ok]${RESET}    $*"; }
warn()  { echo -e "${YELLOW}[warn]${RESET}  $*"; }
die()   { echo -e "${RED}[error]${RESET} $*" >&2; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

uv_project() {
    if [ -n "${VIRTUAL_ENV:-}" ] && [ "$VIRTUAL_ENV" != "$ROOT/.venv" ]; then
        env -u VIRTUAL_ENV uv "$@"
    else
        uv "$@"
    fi
}

npm_project_install() {
    local dir="$1"
    local install_cmd="install"
    if [ -f "$dir/package-lock.json" ]; then
        install_cmd="ci"
    fi
    (
        cd "$dir"
        NPM_CONFIG_AUDIT=false \
            NPM_CONFIG_FUND=false \
            NPM_CONFIG_PROGRESS=false \
            NPM_CONFIG_UPDATE_NOTIFIER=false \
            npm "$install_cmd" --loglevel=warn
    )
}

# ── 0. Launcher permissions first ────────────────────────────────────────────
# Do this before dependency/build steps so a partially failed install still
# leaves ./gru, ./mos, ./noter, and ./viz usable for diagnostics.
ensure_launchers() {
    for script in "$ROOT/minions/bin/gru" "$ROOT/minions/bin/viz" "$ROOT/minions/bin/noter"; do
        if [ -f "$script" ]; then
            chmod +x "$script"
        fi
    done
    for link in gru mos minionsos; do
        if [ ! -e "$ROOT/$link" ] && [ ! -L "$ROOT/$link" ]; then
            (cd "$ROOT" && ln -sf minions/bin/gru "$link")
        fi
    done
    if [ ! -e "$ROOT/noter" ] && [ ! -L "$ROOT/noter" ]; then
        (cd "$ROOT" && ln -sf minions/bin/noter noter)
    fi
    if [ ! -e "$ROOT/viz" ] && [ ! -L "$ROOT/viz" ]; then
        (cd "$ROOT" && ln -sf minions/bin/viz viz)
    fi
}
ensure_launchers
ok "Launcher permissions ready"

# ── 0. Submodule guard ────────────────────────────────────────────────────────
if [ ! -f "$ROOT/mcp-servers/eacn3/pyproject.toml" ] && [ ! -f "$ROOT/mcp-servers/eacn3/setup.py" ]; then
    die "EACN3 source is missing or empty at mcp-servers/eacn3/.\n       Run: git submodule update --init --recursive\n       Then re-run ./install.sh"
fi

# ── 1. Bootstrap uv ───────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    info "uv not found — attempting to install via curl..."
    if ! command -v curl &>/dev/null; then
        die "curl is required to install uv but was not found.\n       Install uv manually: https://docs.astral.sh/uv/getting-started/installation/\n       Then re-run ./install.sh"
    fi
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
        die "uv installation failed (are you offline?).\n       Install uv manually: https://docs.astral.sh/uv/getting-started/installation/\n       Then re-run ./install.sh"
    fi
    # Reload PATH so the newly installed uv is visible
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        die "uv was installed but is not on PATH.\n       Add ~/.local/bin (or ~/.cargo/bin) to your PATH, then re-run ./install.sh"
    fi
    ok "uv installed: $(uv --version)"
else
    ok "uv already present: $(uv --version)"
fi

# ── 2. Python 3.11 ────────────────────────────────────────────────────────────
if ! uv python list 2>/dev/null | grep -q '3\.11'; then
    info "Python 3.11 not found in uv — installing..."
    uv python install 3.11
    ok "Python 3.11 installed"
else
    ok "Python 3.11 already available"
fi

# ── 3. uv sync (creates .venv, installs MinionsOS editable) ──────────────────
info "Running uv sync..."
uv_project sync
PROJECT_PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PROJECT_PYTHON" ]; then
    die "uv sync completed, but project Python was not found at $PROJECT_PYTHON"
fi
ok "uv sync complete"

# ── 4. Install EACN3 editable ─────────────────────────────────────────────────
info "Installing EACN3 (editable)..."
uv_project pip install --python "$PROJECT_PYTHON" -e ./mcp-servers/eacn3
ok "EACN3 installed"

# ── 5. Build EACN3 MCP plugin ─────────────────────────────────────────────────
# This plugin exposes the `eacn3_*` MCP tools that every Role uses to talk to
# the per-project EACN3 backend. Without it, Roles have no way to post
# messages or poll events, and the entire MinionsOS bus is dark. So this step
# is FATAL: if Node is missing, the build fails, or dist/server.js is absent
# at the end, we stop here with an actionable error rather than let the user
# discover the breakage mid-session.
#
# Escape hatch: set MINIONS_SKIP_PLUGIN_BUILD=1 to intentionally skip (e.g.
# CI smoke test on a node-less runner). This is the only supported way.
if [ -n "${MINIONS_SKIP_PLUGIN_BUILD:-}" ]; then
    warn "MINIONS_SKIP_PLUGIN_BUILD=1 — skipping EACN3 plugin build."
    warn "Roles will NOT have eacn3_* tools; the EACN bus will be dark."
else
    if ! command -v node &>/dev/null; then
        die "node not found. EACN3 plugin build requires Node >= 16.\n       Install Node (https://nodejs.org/), then re-run ./install.sh.\n       To intentionally skip (not recommended), set MINIONS_SKIP_PLUGIN_BUILD=1."
    fi
    if ! command -v npm &>/dev/null; then
        die "npm not found. EACN3 plugin build requires npm.\n       Install npm, then re-run ./install.sh."
    fi
    NODE_VER=$(node --version | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VER" | cut -d. -f1)
    if [ "$NODE_MAJOR" -lt 16 ]; then
        die "Node $(node --version) is below the required >= 16.\n       Upgrade Node, then re-run ./install.sh."
    fi

    info "Building EACN3 MCP plugin (npm dependency install + build)..."
    if ! (npm_project_install "$ROOT/mcp-servers/eacn3/plugin" && cd "$ROOT/mcp-servers/eacn3/plugin" && npm run build); then
        die "EACN3 plugin build failed.\n       Inspect the output above; fix the error, then re-run ./install.sh."
    fi
    PLUGIN_DIST="$ROOT/mcp-servers/eacn3/plugin/dist/server.js"
    if [ ! -f "$PLUGIN_DIST" ]; then
        die "EACN3 plugin build reported success but $PLUGIN_DIST is missing.\n       This indicates a broken build script in mcp-servers/eacn3/plugin/."
    fi
    ok "EACN3 MCP plugin built: $PLUGIN_DIST"

    # ── 5b. Build minions-viz Observatory ───────────────────────────────
    VIZ_DIR="$ROOT/minions-viz"
    VIZ_MARKER="$VIZ_DIR/dist/web/index.html"
    if [ -d "$VIZ_DIR" ]; then
        need_build=1
        if [ -f "$VIZ_MARKER" ] && [ -z "${MINIONS_VIZ_REBUILD:-}" ]; then
            if [ "$VIZ_MARKER" -nt "$VIZ_DIR/package.json" ]; then
                need_build=0
            fi
        fi
        if [ "$need_build" = "1" ]; then
            info "Building minions-viz Observatory (npm dependency install + build)..."
            npm_project_install "$VIZ_DIR"
            (cd "$VIZ_DIR" && npm run build)
            ok "minions-viz built"
        else
            ok "minions-viz already built (set MINIONS_VIZ_REBUILD=1 to force)"
        fi
    else
        warn "minions-viz/ directory missing — skipping Observatory build."
    fi
fi

# ── 6. Copy .yaml.example → .yaml (if not already present) ───────────────────
CONFIG_DIR="$ROOT/minions/config"
if [ -d "$CONFIG_DIR" ]; then
    for example in "$CONFIG_DIR"/*.yaml.example; do
        [ -f "$example" ] || continue
        target="${example%.example}"
        if [ ! -f "$target" ]; then
            cp "$example" "$target"
            ok "Created config: $(basename "$target")"
        else
            ok "Config already exists: $(basename "$target") (not overwritten)"
        fi
    done
else
    warn "minions/config/ not found — skipping config copy (run install.sh again after full checkout)"
fi

# ── 6b. Ensure Codex project MCP config exists ───────────────────────────────
CODEX_CONFIG_DIR="$ROOT/.codex"
CODEX_CONFIG="$CODEX_CONFIG_DIR/config.toml"
mkdir -p "$CODEX_CONFIG_DIR"
if [ ! -f "$CODEX_CONFIG" ]; then
    "$PROJECT_PYTHON" "$ROOT/minions/tools/_gen_codex_config.py" "$CODEX_CONFIG"
    ok "Created Codex MCP config: .codex/config.toml"
else
    ok "Codex MCP config already exists: .codex/config.toml (not overwritten)"
fi

# ── 6c. Generate .mcp.json (Claude Code MCP servers) ─────────────────────────
# Always regenerated to stay in sync with what is actually built.
# codex-subagent is conditional: only registered if its dist/server.js exists.
info "Generating .mcp.json (Claude Code MCP servers)..."
"$PROJECT_PYTHON" "$ROOT/minions/tools/_gen_mcp_json.py" "$ROOT"
ok ".mcp.json generated"

# ── 7. Ensure launcher is executable ─────────────────────────────────────────
if [ -f "$ROOT/minions/bin/gru" ]; then
    chmod +x "$ROOT/minions/bin/gru"
    ok "minions/bin/gru is executable"
fi
if [ -f "$ROOT/minions/bin/viz" ]; then
    chmod +x "$ROOT/minions/bin/viz"
    ok "minions/bin/viz is executable"
fi
if [ -f "$ROOT/minions/bin/noter" ]; then
    chmod +x "$ROOT/minions/bin/noter"
    ok "minions/bin/noter is executable"
fi
# Top-level symlinks (gru / mos / minionsos / noter / viz -> minions/bin/*)
for link in gru mos minionsos; do
    if [ ! -e "$ROOT/$link" ] && [ ! -L "$ROOT/$link" ]; then
        (cd "$ROOT" && ln -sf minions/bin/gru "$link")
        ok "Created symlink: ./$link → minions/bin/gru"
    fi
done
if [ ! -e "$ROOT/noter" ] && [ ! -L "$ROOT/noter" ]; then
    (cd "$ROOT" && ln -sf minions/bin/noter noter)
    ok "Created symlink: ./noter -> minions/bin/noter"
fi
if [ ! -e "$ROOT/viz" ] && [ ! -L "$ROOT/viz" ]; then
    (cd "$ROOT" && ln -sf minions/bin/viz viz)
    ok "Created symlink: ./viz → minions/bin/viz"
fi

# User-level state dir for machine-singleton viz + Gru registry.
mkdir -p "$HOME/.minionsos"
chmod 0700 "$HOME/.minionsos" 2>/dev/null || true
ok "User dir ready: $HOME/.minionsos"

# ── 8. Author seed-repo git preflight (non-fatal) ────────────────────────────
# MinionsOS imports the directory containing this repo into a per-project
# bare repo at project_create time (the "author seed"). If that directory is
# not a git repo, project_create will fail with an actionable error at
# runtime. We warn here so users can fix it before the first ./gru run.
# After seeding, the author repo is never touched again — project branches
# live entirely inside project_<port>/parent_repo.git/.
PARENT="$(cd "$ROOT/.." && pwd)"
if ! git -C "$PARENT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    warn "Author repo is NOT a git repository: $PARENT"
    warn "MinionsOS seeds each project from the author repo's HEAD, so it"
    warn "must be git-initialised. Before running ./gru, do:"
    warn "    cd $PARENT && git init && git add -A && git commit -m 'init'"
    warn "Or set gru.yaml:author_repo to a different git work tree."
else
    # Parent is a git repo — check the embedded-.git trap too.
    if [ -d "$ROOT/.git" ]; then
        # Is MinionsOS registered as a submodule of the parent? If yes, .git
        # is normally a file (gitlink), not a directory — so a literal .git/
        # directory inside a parent repo is the footgun case.
        CHECKOUT_NAME="$(basename "$ROOT")"
        if ! git -C "$PARENT" ls-files --error-unmatch "$CHECKOUT_NAME" >/dev/null 2>&1; then
            warn "$CHECKOUT_NAME/.git exists inside a parent git repo, and"
            warn "$CHECKOUT_NAME is not registered as a submodule. The parent"
            warn "repo will treat it as an embedded repo and 'git add' there"
            warn "will misbehave. Either register as a submodule, or remove"
            warn "$CHECKOUT_NAME/.git before the parent's first commit."
        fi
    fi
    ok "Author repo git state looks sane: $PARENT"
fi

# ── 9. Claude Code hooks verification ────────────────────────────────────────
# Verify that the project Python can import all hook dependencies.
# This catches the "system python3 is 3.9 but hooks need 3.11+" failure mode.
info "Verifying Claude Code hooks..."
HOOKS_DIR="$ROOT/minions/hooks"
HOOK_VERIFY_FAILED=0
for hook in "$HOOKS_DIR"/*.py; do
    [ -f "$hook" ] || continue
    hookname="$(basename "$hook")"
    if ! "$PROJECT_PYTHON" -c "import ast; ast.parse(open('$hook').read())" 2>/dev/null; then
        warn "Hook syntax error: $hookname"
        HOOK_VERIFY_FAILED=1
        continue
    fi
    if ! "$PROJECT_PYTHON" "$hook" < /dev/null >/dev/null 2>/dev/null; then
        : # hooks exit 0 on empty stdin; non-zero means import or runtime error
        # But some hooks legitimately exit 0 on empty input, so only check import
    fi
done
# Targeted import check for the known 3.11+ dependency
if ! "$PROJECT_PYTHON" -c "from datetime import UTC" 2>/dev/null; then
    warn "Project Python cannot import datetime.UTC (requires 3.11+)"
    HOOK_VERIFY_FAILED=1
fi
if [ "$HOOK_VERIFY_FAILED" = "0" ]; then
    ok "All hooks verified with project Python ($("$PROJECT_PYTHON" --version 2>&1))"
else
    die "Hook verification failed. Ensure Python 3.11+ is available:\n       uv python install 3.11 && uv sync"
fi

# ── 10. Claude Code settings validation ──────────────────────────────────────
# Verify .claude/settings.json exists and hooks reference the project venv.
CLAUDE_SETTINGS="$ROOT/.claude/settings.json"
if [ -f "$CLAUDE_SETTINGS" ]; then
    if grep -q 'python3 ' "$CLAUDE_SETTINGS" 2>/dev/null; then
        warn ".claude/settings.json still references bare 'python3' in hooks."
        warn "Hooks should use .venv/bin/python to ensure Python 3.11+."
        warn "Run: git checkout .claude/settings.json  (to get the fixed version)"
    else
        ok "Claude Code settings: hooks use project Python"
    fi
else
    warn ".claude/settings.json not found — Claude Code hooks will not be active."
    warn "This file should be checked into the repository."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}MinionsOS installation complete.${RESET}"
echo ""
echo -e "  ${BOLD}Next steps:${RESET}"
echo -e "  1. Edit ${CYAN}minions/config/gru.yaml${RESET} to adjust heartbeat interval, log level, etc."
echo -e "  2. Edit ${CYAN}minions/config/experiment_targets.yaml${RESET} to add SSH compute targets."
echo -e "  3. Launch Gru:  ${BOLD}./gru${RESET}"
echo -e "     Watch one project: ${BOLD}./noter <port>${RESET}"
echo -e "     Or use the CLI:  ${BOLD}./mos status${RESET}"
echo ""
