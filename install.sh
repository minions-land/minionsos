#!/usr/bin/env bash
# MinionsOS V2 — idempotent installer.
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

# ── 0. Submodule guard ────────────────────────────────────────────────────────
if [ ! -f "$ROOT/EACN3/pyproject.toml" ] && [ ! -f "$ROOT/EACN3/setup.py" ]; then
    die "EACN3 submodule is missing or empty.\n       Run: git submodule update --init --recursive\n       Then re-run ./install.sh"
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
uv sync
ok "uv sync complete"

# ── 4. Install EACN3 editable ─────────────────────────────────────────────────
info "Installing EACN3 (editable)..."
uv pip install -e ./EACN3
ok "EACN3 installed"

# ── 5. Build EACN3 MCP plugin ─────────────────────────────────────────────────
if ! command -v node &>/dev/null; then
    warn "node not found — skipping EACN3 plugin build.\n       Install Node ≥ 16 and re-run ./install.sh to complete setup."
elif ! command -v npm &>/dev/null; then
    warn "npm not found — skipping EACN3 plugin build.\n       Install npm and re-run ./install.sh to complete setup."
else
    NODE_VER=$(node --version | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VER" | cut -d. -f1)
    if [ "$NODE_MAJOR" -lt 16 ]; then
        warn "Node $(node --version) is below the required ≥16 — skipping plugin build."
    else
        info "Building EACN3 MCP plugin (npm install + build)..."
        (cd "$ROOT/EACN3/plugin" && npm install && npm run build)
        ok "EACN3 MCP plugin built"
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

# ── 7. Ensure launcher is executable ─────────────────────────────────────────
if [ -f "$ROOT/minions/bin/gru" ]; then
    chmod +x "$ROOT/minions/bin/gru"
    ok "minions/bin/gru is executable"
fi

# ── 8. Parent-directory git preflight (non-fatal) ────────────────────────────
# MinionsOS creates per-project git worktrees branched off the directory that
# CONTAINS MinionsOS_V2. If that parent is not a git repo, project_create will
# fail with an actionable error at runtime. We warn here so users can fix it
# before the first ./gru run instead of hitting it mid-flow.
PARENT="$(cd "$ROOT/.." && pwd)"
if ! git -C "$PARENT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    warn "Parent directory is NOT a git repository: $PARENT"
    warn "MinionsOS needs the parent to be git-initialised so it can create"
    warn "per-project worktrees. Before running ./gru, do:"
    warn "    cd $PARENT && git init && git add -A && git commit -m 'init'"
    warn "Also make sure MinionsOS_V2/.git is absent (or added as a submodule)"
    warn "so the parent does not treat it as an embedded repo."
else
    # Parent is a git repo — check the embedded-.git trap too.
    if [ -d "$ROOT/.git" ]; then
        # Is MinionsOS_V2 registered as a submodule of the parent? If yes, .git
        # is normally a file (gitlink), not a directory — so a literal .git/
        # directory inside a parent repo is the footgun case.
        if ! git -C "$PARENT" ls-files --error-unmatch "MinionsOS_V2" >/dev/null 2>&1; then
            warn "MinionsOS_V2/.git exists inside a parent git repo, and"
            warn "MinionsOS_V2 is not registered as a submodule. The parent"
            warn "repo will treat it as an embedded repo and 'git add' there"
            warn "will misbehave. Either register as a submodule, or remove"
            warn "MinionsOS_V2/.git before the parent's first commit."
        fi
    fi
    ok "Parent directory git state looks sane: $PARENT"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}MinionsOS V2 installation complete.${RESET}"
echo ""
echo -e "  ${BOLD}Next steps:${RESET}"
echo -e "  1. Edit ${CYAN}minions/config/gru.yaml${RESET} to adjust heartbeat interval, log level, etc."
echo -e "  2. Edit ${CYAN}minions/config/experiment_targets.yaml${RESET} to add SSH compute targets."
echo -e "  3. Launch Gru:  ${BOLD}./gru${RESET}"
echo -e "     Or use the CLI:  ${BOLD}./mos status${RESET}"
echo ""
