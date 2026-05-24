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

# ── 0b. tmux (hard runtime dependency) ────────────────────────────────────────
# Every Role process is launched inside a named tmux session by
# minions/lifecycle/role_launcher.py (sessions named mos-{port}-{role}). Without
# tmux, mos_spawn_role / mos_spawn_expert silently no-op (session_alive() short-
# circuits on _have_tmux() == False) and the entire MinionsOS bus is dark even
# though Gru looks healthy. So this is FATAL: try to install once, surface the
# package-manager output if it fails, and stop here.
#
# Platform notes:
# - macOS (Darwin): brew
# - Linux (incl. WSL2 — `uname -s` returns "Linux"): apt-get / dnf / pacman
# - MSYS2 / Git-Bash on Windows: pacman against the MSYS repo
# - Cygwin on Windows: apt-cyg if installed; otherwise point to setup-x86_64.exe
# - Native Windows shells (cmd, PowerShell) cannot run this script at all and
#   should use WSL2 — that path is covered by the Linux branch automatically.
ensure_tmux() {
    if command -v tmux &>/dev/null; then
        ok "tmux already present: $(tmux -V)"
        return 0
    fi

    info "tmux not found — Roles cannot launch without it. Attempting to install..."
    case "$(uname -s)" in
        Darwin)
            if ! command -v brew &>/dev/null; then
                die "tmux is missing and Homebrew is not installed.\n       Install Homebrew (https://brew.sh) and re-run ./install.sh,\n       or install tmux manually: brew install tmux"
            fi
            if ! brew install tmux; then
                die "brew install tmux failed. Inspect the output above and install tmux manually,\n       then re-run ./install.sh."
            fi
            ;;
        Linux)
            if command -v apt-get &>/dev/null; then
                sudo apt-get update -y || die "apt-get update failed."
                if ! sudo apt-get install -y tmux; then
                    die "apt-get install tmux failed. Install tmux manually,\n       then re-run ./install.sh."
                fi
            elif command -v dnf &>/dev/null; then
                if ! sudo dnf install -y tmux; then
                    die "dnf install tmux failed. Install tmux manually, then re-run ./install.sh."
                fi
            elif command -v pacman &>/dev/null; then
                if ! sudo pacman -S --noconfirm tmux; then
                    die "pacman -S tmux failed. Install tmux manually, then re-run ./install.sh."
                fi
            else
                die "tmux is missing and no supported package manager (apt-get/dnf/pacman) found.\n       Install tmux manually, then re-run ./install.sh."
            fi
            ;;
        MINGW*|MSYS*)
            # MSYS2 / Git-Bash on Windows. tmux ships in the MSYS repo
            # (`pacman -S tmux`); MinGW shells share that pacman binary.
            # Note: MinionsOS as a whole is best-supported on WSL2 — running
            # under raw MSYS2 may surface other issues (path translation,
            # subprocess semantics). We install tmux here so install.sh can
            # finish, but flag the platform.
            warn "Detected MSYS2 / Git-Bash on Windows."
            warn "MinionsOS is best-supported on WSL2; raw MSYS2 may have rough edges."
            warn "Consider: wsl --install -d Ubuntu, then re-run ./install.sh inside WSL2."
            if ! command -v pacman &>/dev/null; then
                die "tmux is missing and pacman is not on PATH inside this MSYS2/MinGW shell.\n       Install via the MSYS2 installer (https://www.msys2.org), then re-run ./install.sh,\n       or switch to WSL2 (recommended)."
            fi
            if ! pacman -S --noconfirm tmux; then
                die "pacman -S tmux failed under MSYS2.\n       Open MSYS2 MSYS shell (not MinGW64), run: pacman -Syu && pacman -S tmux\n       Then re-run ./install.sh, or switch to WSL2 (recommended)."
            fi
            ;;
        CYGWIN*)
            warn "Detected Cygwin on Windows."
            warn "MinionsOS is best-supported on WSL2; Cygwin is untested for the full stack."
            warn "Consider: wsl --install -d Ubuntu, then re-run ./install.sh inside WSL2."
            if command -v apt-cyg &>/dev/null; then
                if ! apt-cyg install tmux; then
                    die "apt-cyg install tmux failed.\n       Re-run Cygwin's setup-x86_64.exe and select the 'tmux' package manually,\n       or switch to WSL2 (recommended)."
                fi
            else
                die "tmux is missing under Cygwin and apt-cyg is not installed.\n       Re-run setup-x86_64.exe (https://www.cygwin.com/install.html) and select 'tmux',\n       or switch to WSL2 (recommended): wsl --install -d Ubuntu"
            fi
            ;;
        *)
            die "tmux is missing and this OS ($(uname -s)) has no automatic install path.\n       Install tmux manually (it is a hard runtime dependency), then re-run ./install.sh.\n       On Windows, the supported path is WSL2: wsl --install -d Ubuntu"
            ;;
    esac

    if ! command -v tmux &>/dev/null; then
        die "tmux installation reported success but tmux is still not on PATH.\n       Open a new shell so the installer's PATH change takes effect, then re-run ./install.sh."
    fi
    ok "tmux installed: $(tmux -V)"
}
ensure_tmux

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

    # ── 5a-codegraph. Install codegraph MCP dependencies ────────────────
    # The codegraph MCP wraps `@colbymchenry/codegraph` (npm). It is a
    # prebuilt package — no `npm run build` needed; `npm install` populates
    # node_modules/.bin/codegraph which the launcher exec's.
    CG_DIR="$ROOT/mcp-servers/codegraph"
    if [ -d "$CG_DIR" ] && [ -f "$CG_DIR/package.json" ]; then
        info "Installing codegraph MCP dependencies (npm)..."
        if ! npm_project_install "$CG_DIR"; then
            die "codegraph npm install failed.\n       Inspect the output above; fix the error, then re-run ./install.sh."
        fi
        CG_BIN="$CG_DIR/node_modules/.bin/codegraph"
        if [ ! -x "$CG_BIN" ]; then
            die "codegraph npm install reported success but $CG_BIN is missing or not executable."
        fi
        ok "codegraph MCP installed: $CG_BIN"

        # Warm up the repo-scope codegraph index so the launcher does not
        # block on a multi-second tree-sitter extraction during the first
        # MCP handshake (system-maintenance work runs without
        # MINIONS_PROJECT_PORT, hitting repo scope). `init -i` runs both
        # init and the initial index pass; without `-i`, init only writes
        # the .codegraph/ scaffolding and serve --mcp would expose an
        # empty graph. Project-scope first-run is bootstrapped by the
        # operator (or a future project_create lifecycle hook) — those
        # scopes are tiny so the latency is acceptable on first connect.
        if [ ! -d "$ROOT/.codegraph" ]; then
            info "Warming repo-scope codegraph index (one-time, ~30s on this repo)..."
            if (cd "$ROOT" && "$CG_BIN" init -i); then
                ok "Repo-scope codegraph index built: $ROOT/.codegraph"
            else
                warn "codegraph init failed at repo scope; the MCP launcher will refuse to start until you bootstrap manually:"
                warn "  cd $ROOT && $CG_BIN init -i"
            fi
        else
            ok "Repo-scope codegraph index already present: $ROOT/.codegraph"
        fi
    fi

    # ── 5a-graphify. Install graphify (L3 Shelf extractor) Python deps ───
    # graphify provides extract.py, the script Noter shells out to during
    # its periodic wake to rebuild branches/shared/shelf/shelf.json. Without
    # the local venv, _maybe_rebuild_shelf_graph silently bails with
    # "graphify venv not installed", the L3 Shelf never auto-populates,
    # and mos_shelf_register reports "no graph" forever (GitHub Issue #11).
    GR_DIR="$ROOT/mcp-servers/graphify"
    if [ -d "$GR_DIR" ] && [ -f "$GR_DIR/pyproject.toml" ]; then
        GR_VENV_PY="$GR_DIR/.venv/bin/python"
        if [ ! -x "$GR_VENV_PY" ]; then
            info "Setting up graphify L3 extractor venv..."
            # Bound the install with a wall-clock timeout. GitHub Issue #16:
            # on PyPI-restricted hosts (corporate firewall, throttled net,
            # air-gapped clusters) `uv pip install -e .` blocks for tens
            # of minutes with no output, leaving installers staring at a
            # dead terminal. 180s is generous for a healthy network and
            # long enough that a slow-but-progressing install completes.
            GR_INSTALL_TIMEOUT="${GRAPHIFY_INSTALL_TIMEOUT:-180}"
            gr_rc=0
            (
                cd "$GR_DIR"
                # Create a project-local venv and install graphify into it.
                # Using `uv venv` + `uv pip install` keeps the install
                # consistent with the rest of MinionsOS.
                uv_project venv .venv
                if command -v timeout >/dev/null 2>&1; then
                    timeout "$GR_INSTALL_TIMEOUT" \
                        env VIRTUAL_ENV="$GR_DIR/.venv" uv_project pip install -e .
                else
                    VIRTUAL_ENV="$GR_DIR/.venv" uv_project pip install -e .
                fi
            ) || gr_rc=$?
            if [ "$gr_rc" -ne 0 ] || [ ! -x "$GR_VENV_PY" ]; then
                warn "graphify venv setup failed or timed out after ${GR_INSTALL_TIMEOUT}s (rc=$gr_rc)."
                warn "This usually means PyPI is unreachable or rate-limited from this host."
                warn "L3 Shelf auto-rebuild will be DISABLED until you finish the install:"
                warn "  cd $GR_DIR && uv venv .venv && VIRTUAL_ENV=\$PWD/.venv uv pip install -e ."
                warn "MinionsOS will continue to start; only cross-role structural search"
                warn "degrades. Re-run install.sh (or the command above) once PyPI is reachable."
            else
                ok "graphify venv ready: $GR_VENV_PY"
            fi
        else
            ok "graphify venv already present: $GR_VENV_PY"
        fi
    fi

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

# ── 6b. Generate Codex project MCP config ────────────────────────────────────
# Issue #27: regenerate every install so absolute paths refresh when the repo
# moves between machines. The generator emits paths relative to $ROOT.
CODEX_CONFIG_DIR="$ROOT/.codex"
CODEX_CONFIG="$CODEX_CONFIG_DIR/config.toml"
mkdir -p "$CODEX_CONFIG_DIR"
"$PROJECT_PYTHON" "$ROOT/minions/tools/_gen_codex_config.py" "$CODEX_CONFIG" "$ROOT"
ok "Generated Codex MCP config: .codex/config.toml"

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
# This catches the "system python3 is 3.9 but hooks need 3.11+" failure mode,
# and that PostToolUse hooks survive MCP-shaped tool_response payloads
# (which arrive as a list of content blocks, not a dict).
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
# PostToolUse smoke test: MCP tools (e.g. mcp__codex-subagent__codex) deliver
# tool_response as a list of content blocks, not a dict. Hooks that read
# tool_response.get(...) without a type guard crash with AttributeError on
# every codex call. Verify the affected hooks survive the list shape.
MCP_PAYLOAD='{"tool_name":"mcp__codex-subagent__codex","tool_input":{},"tool_response":[{"type":"text","text":"x"}]}'
for hookname in bg_keepalive_nudge.py reel_capture.py; do
    hook="$HOOKS_DIR/$hookname"
    [ -f "$hook" ] || continue
    err=$(printf '%s' "$MCP_PAYLOAD" | "$PROJECT_PYTHON" "$hook" 2>&1 >/dev/null) || true
    if printf '%s' "$err" | grep -q "Traceback"; then
        warn "Hook $hookname crashes on MCP-shaped tool_response (list, not dict)."
        warn "First lines of traceback:"
        printf '%s\n' "$err" | head -3 | sed 's/^/         /'
        HOOK_VERIFY_FAILED=1
    fi
done
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
