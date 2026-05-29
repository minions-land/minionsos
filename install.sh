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

# ── Incremental install: stamp-based freshness ────────────────────────────────
# Each heavy step hashes its input files (lockfile, package.json, etc.) and
# stores the result in .install_stamps/<step>. On re-run, if the hash matches,
# the step is skipped entirely. This turns a 60-90s full install into a <5s
# no-op when nothing changed — the "incremental upgrade" path customers need.
# Force full rebuild: MINIONS_FORCE_INSTALL=1 ./install.sh
STAMP_DIR="$ROOT/.install_stamps"
mkdir -p "$STAMP_DIR"

_stamp_hash() {
    # Hash one or more files; output a single sha256. Missing files → "missing".
    local h=""
    for f in "$@"; do
        if [ -f "$f" ]; then
            h="${h}$(shasum -a 256 "$f" | cut -d' ' -f1)"
        else
            h="${h}missing"
        fi
    done
    printf '%s' "$h" | shasum -a 256 | cut -d' ' -f1
}

_stamp_fresh() {
    # Usage: _stamp_fresh <step_name> <file1> [file2 ...]
    # Returns 0 (true) if the stamp matches current inputs → skip the step.
    local step="$1"; shift
    [ -z "${MINIONS_FORCE_INSTALL:-}" ] || return 1
    local current; current=$(_stamp_hash "$@")
    local stamp_file="$STAMP_DIR/$step"
    [ -f "$stamp_file" ] && [ "$(cat "$stamp_file")" = "$current" ]
}

_stamp_save() {
    # Usage: _stamp_save <step_name> <file1> [file2 ...]
    local step="$1"; shift
    _stamp_hash "$@" > "$STAMP_DIR/$step"
}

_src_tree_hash() {
    # Usage: _src_tree_hash <dir> [<pathspec> ...]
    # Emit a single sha256 over the *content* of the source files in <dir>.
    #
    # Why this exists: the Node components (eacn3 plugin, codex-subagent,
    # minions-viz) are compiled from TypeScript that lives directly in this
    # repo. The old freshness checks keyed only on package.json (or a
    # dist-newer-than-package.json mtime test), so a commit that changed ONLY
    # *.ts/*.tsx left the stamp "fresh" and `mos upgrade` shipped a stale
    # build. Hashing the tracked source tree closes that hole.
    #
    # Primary path: `git ls-files` enumerates tracked source, and we hash the
    # working-tree content of each so an uncommitted local edit also rebuilds.
    # Fallback (no git / detached source export): a sorted find+shasum over the
    # same extensions. Either way the output is a stable single digest.
    local dir="$1"; shift
    local pathspec=("$@")
    [ ${#pathspec[@]} -gt 0 ] || pathspec=('*.ts' '*.tsx' '*.json' 'tsconfig*.json')
    if [ ! -d "$dir" ]; then
        printf '%s' "absent" | shasum -a 256 | cut -d' ' -f1
        return
    fi
    local files=""
    if git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        files="$(git -C "$dir" ls-files -- "${pathspec[@]}" 2>/dev/null | sort)"
    fi
    if [ -z "$files" ]; then
        # Non-git fallback: recursive find, excluding build/dep output.
        files="$(cd "$dir" && find . \
            \( -name node_modules -o -name dist -o -name .git \) -prune -o \
            \( -name '*.ts' -o -name '*.tsx' -o -name '*.json' \) -print 2>/dev/null \
            | sed 's|^\./||' | sort)"
    fi
    if [ -z "$files" ]; then
        printf '%s' "empty" | shasum -a 256 | cut -d' ' -f1
        return
    fi
    # Hash each file's content (path-prefixed so renames register), then fold
    # into one digest. Read the relative list from stdin to tolerate spaces.
    printf '%s\n' "$files" | while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        if [ -f "$dir/$rel" ]; then
            printf '%s:%s\n' "$rel" "$(shasum -a 256 "$dir/$rel" | cut -d' ' -f1)"
        else
            printf '%s:missing\n' "$rel"
        fi
    done | shasum -a 256 | cut -d' ' -f1
}

_node_build_fresh() {
    # Usage: _node_build_fresh <step_name> <dir> <dist_artifact>
    # Returns 0 (skip build) only when ALL hold:
    #   - MINIONS_FORCE_INSTALL is unset (force always rebuilds), AND
    #   - the built dist artifact exists, AND
    #   - the saved stamp equals a fresh content hash of the source tree.
    # The stamp value is the source-tree digest, so a source-only commit
    # (no package.json change) correctly invalidates and forces a rebuild.
    local step="$1" dir="$2" artifact="$3"
    [ -z "${MINIONS_FORCE_INSTALL:-}" ] || return 1
    [ -f "$artifact" ] || return 1
    local stamp_file="$STAMP_DIR/$step"
    [ -f "$stamp_file" ] || return 1
    local current; current="$(_src_tree_hash "$dir")"
    [ "$(cat "$stamp_file")" = "$current" ]
}

_node_build_save() {
    # Usage: _node_build_save <step_name> <dir>
    local step="$1" dir="$2"
    _src_tree_hash "$dir" > "$STAMP_DIR/$step"
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
# Two-phase install:
#   Phase A (this step) — core deps only, fast. After this, ./gru is usable.
#   Phase B (later)     — heavy visual extras (opencv/pdf2image/numpy/pillow,
#                         ~160MB) installed in the background so the user does
#                         not wait. Visual tools (mos_visual_*) report a clear
#                         "not installed yet" error if invoked before B finishes.
#
# PyPI mirror auto-detection (sibling-session forensic finding 2026-05-26):
#   On a CN server, curl HEAD pypi.org → 8.13s; mirrors.cloud.aliyuncs.com →
#   0.018s (~450x slower). uv does NOT read /etc/pip.conf or ~/.pip/pip.conf;
#   it has its own config at ~/.config/uv/uv.toml or honors $UV_INDEX_URL.
#   Many users have pip-on-mirror but uv-on-pypi.org and don't know it — uv
#   silently spends minutes on what should be seconds.
#
# Strategy here:
#   1. If $UV_INDEX_URL already set, respect it (user knows what they want).
#   2. Else probe pypi.org reachability with a 4s connect timeout. If slow or
#      unreachable, probe two well-known CN mirrors and pick the fastest.
#   3. Print the chosen mirror, and the one-liner the user can paste into
#      ~/.config/uv/uv.toml to make it permanent for this machine.
#   Set MINIONS_NO_MIRROR_PROBE=1 to skip the probe (e.g. inside CI / dev).
probe_pypi_latency() {
    # Returns 0/1 on stdout: connect time in seconds (float), or "timeout".
    local url="$1"
    local timeout="${2:-4}"
    local t
    t=$(curl -sS -o /dev/null -m "$timeout" --connect-timeout "$timeout" \
        -w '%{time_total}' -I "$url" 2>/dev/null) || { echo timeout; return 1; }
    echo "$t"
}

select_mirror() {
    # Echo a chosen mirror URL on stdout, or empty if pypi.org is fine.
    local pypi_t aliyun_t tuna_t
    pypi_t=$(probe_pypi_latency "https://pypi.org/simple/" 4)
    # awk handles "timeout" → falsey via 0; numeric strings compare normally.
    if [ "$pypi_t" != "timeout" ] && \
       awk -v t="$pypi_t" 'BEGIN{exit !(t<2.0)}'; then
        return 0   # pypi.org is fast enough; keep default
    fi
    aliyun_t=$(probe_pypi_latency "https://mirrors.aliyun.com/pypi/simple/" 4)
    tuna_t=$(probe_pypi_latency "https://pypi.tuna.tsinghua.edu.cn/simple/" 4)
    local best="" best_t="99"
    if [ "$aliyun_t" != "timeout" ] && awk -v t="$aliyun_t" -v b="$best_t" 'BEGIN{exit !(t<b)}'; then
        best="https://mirrors.aliyun.com/pypi/simple/"; best_t="$aliyun_t"
    fi
    if [ "$tuna_t" != "timeout" ] && awk -v t="$tuna_t" -v b="$best_t" 'BEGIN{exit !(t<b)}'; then
        best="https://pypi.tuna.tsinghua.edu.cn/simple/"; best_t="$tuna_t"
    fi
    if [ -n "$best" ]; then
        echo "$best"
    fi
}

if [ -n "${UV_INDEX_URL:-}" ]; then
    info "PyPI mirror: $UV_INDEX_URL  (from \$UV_INDEX_URL)"
elif [ -n "${MINIONS_NO_MIRROR_PROBE:-}" ]; then
    info "PyPI mirror probe skipped (MINIONS_NO_MIRROR_PROBE=1)"
else
    info "Probing PyPI reachability (4s timeout each)..."
    PICKED_MIRROR="$(select_mirror)"
    if [ -n "$PICKED_MIRROR" ]; then
        export UV_INDEX_URL="$PICKED_MIRROR"
        warn "pypi.org is slow/unreachable from this host."
        ok "  Auto-selected fastest mirror: $UV_INDEX_URL"
        info "  To make this permanent (uv ignores pip.conf — this matters):"
        info "    mkdir -p ~/.config/uv && cat > ~/.config/uv/uv.toml <<EOF"
        info "    [[index]]"
        info "    url = \"$UV_INDEX_URL\""
        info "    default = true"
        info "    EOF"
    else
        ok "pypi.org reachable; using default index."
    fi
fi

info "Running uv sync (core dependencies)..."
if _stamp_fresh uv_sync "$ROOT/pyproject.toml" "$ROOT/uv.lock"; then
    ok "uv sync (core) — up to date, skipped"
else
    uv_project sync
    _stamp_save uv_sync "$ROOT/pyproject.toml" "$ROOT/uv.lock"
    ok "uv sync complete (core)"
fi
PROJECT_PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PROJECT_PYTHON" ]; then
    die "uv sync completed, but project Python was not found at $PROJECT_PYTHON"
fi

# ── 4. Install EACN3 editable ─────────────────────────────────────────────────
EACN3_INPUTS="$ROOT/mcp-servers/eacn3/pyproject.toml"
if _stamp_fresh eacn3_editable "$EACN3_INPUTS"; then
    ok "EACN3 editable — up to date, skipped"
else
    info "Installing EACN3 (editable)..."
    uv_project pip install --python "$PROJECT_PYTHON" -e ./mcp-servers/eacn3
    _stamp_save eacn3_editable "$EACN3_INPUTS"
    ok "EACN3 installed"
fi

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

    EACN3_PLUGIN_DIR="$ROOT/mcp-servers/eacn3/plugin"
    PLUGIN_DIST="$EACN3_PLUGIN_DIR/dist/server.js"
    if _node_build_fresh eacn3_plugin "$EACN3_PLUGIN_DIR" "$PLUGIN_DIST"; then
        ok "EACN3 MCP plugin — up to date, skipped"
    else
        info "Building EACN3 MCP plugin (npm dependency install + build)..."
        if ! (npm_project_install "$EACN3_PLUGIN_DIR" && cd "$EACN3_PLUGIN_DIR" && npm run build); then
            die "EACN3 plugin build failed.\n       Inspect the output above; fix the error, then re-run ./install.sh."
        fi
        if [ ! -f "$PLUGIN_DIST" ]; then
            die "EACN3 plugin build reported success but $PLUGIN_DIST is missing.\n       This indicates a broken build script in mcp-servers/eacn3/plugin/."
        fi
        _node_build_save eacn3_plugin "$EACN3_PLUGIN_DIR"
        ok "EACN3 MCP plugin built: $PLUGIN_DIST"
    fi

    # ── 5a-codex-subagent. Build Codex GPT-5.5 bridge MCP ─────────────────
    # `mcp-servers/codex-subagent/` is the Node TypeScript bridge that
    # exposes Codex GPT-5.5 to every Role process as the `codex` MCP tool.
    # Without `dist/server.js` built, `_gen_mcp_json.py` silently skips
    # registration and tier-2 subagent dispatch silently degrades to
    # Sonnet-only — operators wouldn't notice until cost spikes. Soft-fail
    # (warn, not die) so a working Sonnet-fallback path is preserved if
    # the build environment is broken.
    CSA_DIR="$ROOT/mcp-servers/codex-subagent"
    CSA_MARKER="$CSA_DIR/dist/server.js"
    if [ -d "$CSA_DIR" ]; then
        need_csa_build=1
        # Skip only when the built artifact exists AND the tracked source
        # tree is unchanged since the last build. Honors MINIONS_FORCE_INSTALL
        # (via _node_build_fresh) and the explicit MINIONS_CSA_REBUILD knob.
        if [ -z "${MINIONS_CSA_REBUILD:-}" ] \
            && _node_build_fresh codex_subagent "$CSA_DIR" "$CSA_MARKER"; then
            need_csa_build=0
        fi
        if [ "$need_csa_build" = "1" ]; then
            info "Building codex-subagent MCP (npm install + build)..."
            if npm_project_install "$CSA_DIR" \
                && (cd "$CSA_DIR" && npm run build); then
                if [ -f "$CSA_MARKER" ]; then
                    _node_build_save codex_subagent "$CSA_DIR"
                    ok "codex-subagent built: $CSA_MARKER"
                else
                    warn "codex-subagent npm build reported success but $CSA_MARKER is missing."
                    warn "Roles will fall back to Sonnet for tier-2 subagent dispatch."
                fi
            else
                warn "codex-subagent build failed — Sonnet fallback will be used for subagent dispatch."
                warn "To retry: cd $CSA_DIR && npm install && npm run build"
            fi
        else
            ok "codex-subagent already built (set MINIONS_CSA_REBUILD=1 to force)"
        fi
    else
        warn "mcp-servers/codex-subagent/ directory missing — codex MCP will not be registered."
    fi

    # ── 5b. Build minions-viz Observatory ───────────────────────────────
    VIZ_DIR="$ROOT/minions-viz"
    VIZ_MARKER="$VIZ_DIR/dist/web/index.html"
    if [ -d "$VIZ_DIR" ]; then
        need_build=1
        if [ -z "${MINIONS_VIZ_REBUILD:-}" ] \
            && _node_build_fresh minions_viz "$VIZ_DIR" "$VIZ_MARKER"; then
            need_build=0
        fi
        if [ "$need_build" = "1" ]; then
            info "Building minions-viz Observatory (npm dependency install + build)..."
            npm_project_install "$VIZ_DIR"
            (cd "$VIZ_DIR" && npm run build)
            if [ -f "$VIZ_MARKER" ]; then
                _node_build_save minions_viz "$VIZ_DIR"
            fi
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

# ── 6b-auth. Detect existing Codex auth (no login attempt) ───────────────────
# We do NOT run `codex login` from install.sh — it's an interactive flow that
# would block CI and overwrite an operator's existing auth. Instead, surface
# whichever of these the user already has so they know the codex-subagent
# MCP will work the moment a Role tries it. Priority order matches what the
# Codex CLI itself checks:
#   1. ~/.codex/auth.json            (codex login output)
#   2. $OPENAI_API_KEY env var       (machine-wide)
#   3. ~/.codex/config.toml          (alt provider via env_key)
# Pure detection — no writes, no prompts. Operators who already authed via
# any of these get a green check; everyone else gets actionable next steps.
CODEX_AUTH_DETECTED=""
CODEX_AUTH_SOURCE=""
if [ -s "$HOME/.codex/auth.json" ]; then
    CODEX_AUTH_DETECTED="1"
    CODEX_AUTH_SOURCE="~/.codex/auth.json"
elif [ -n "${OPENAI_API_KEY:-}" ]; then
    CODEX_AUTH_DETECTED="1"
    CODEX_AUTH_SOURCE="\$OPENAI_API_KEY env"
elif [ -f "$HOME/.codex/config.toml" ] \
    && grep -qE '^\s*env_key\s*=' "$HOME/.codex/config.toml" 2>/dev/null; then
    CODEX_AUTH_DETECTED="1"
    CODEX_AUTH_SOURCE="~/.codex/config.toml (env_key provider)"
fi
if [ -n "$CODEX_AUTH_DETECTED" ]; then
    ok "Codex auth detected: $CODEX_AUTH_SOURCE"
else
    warn "No Codex auth found (~/.codex/auth.json absent, OPENAI_API_KEY unset)."
    warn "Roles will fall back to Sonnet for tier-2 subagent dispatch until auth is configured."
    warn "Tier-2 default is Codex GPT-5.5; configure auth at your convenience using your"
    warn "preferred method (existing OPENAI_API_KEY env var, or ~/.codex/auth.json)."
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

# ── 11. Phase B: background install of visual extras ─────────────────────────
# opencv-python-headless + pdf2image + pillow + numpy total ~160MB. These are
# only needed by mos_visual_* MCP tools (PDF layout / figure inspection).
# Installing them in the background means ./gru can launch immediately while
# the heavy wheels download and unpack.
#
# Override: MINIONS_SKIP_VISUAL=1 skips entirely (CI / headless runners that
# never inspect PDFs). MINIONS_VISUAL_FOREGROUND=1 installs synchronously
# (debugging / scripted setups that need a known-complete state on return).
VISUAL_LOG="$ROOT/.install_visual.log"
VISUAL_PID_FILE="$ROOT/.install_visual.pid"
VISUAL_INSTALLED=0
if [ -n "${MINIONS_SKIP_VISUAL:-}" ]; then
    warn "MINIONS_SKIP_VISUAL=1 — visual extras NOT installed."
    warn "mos_visual_* tools will refuse to run until you do:"
    warn "  uv sync --extra visual"
elif "$PROJECT_PYTHON" -c 'import cv2, pdf2image, numpy, PIL' >/dev/null 2>&1; then
    ok "Visual extras already installed (opencv/pdf2image/numpy/pillow)"
    VISUAL_INSTALLED=1
elif [ -n "${MINIONS_VISUAL_FOREGROUND:-}" ]; then
    info "Installing visual extras (foreground, ~160MB)..."
    if uv_project sync --extra visual; then
        ok "Visual extras installed"
        VISUAL_INSTALLED=1
    else
        warn "Visual extras install failed. mos_visual_* tools will be unavailable."
        warn "Re-run: uv sync --extra visual"
    fi
else
    info "Launching visual extras install in background (~160MB)..."
    info "  Log:  $VISUAL_LOG"
    info "  Check status later with: ./mos doctor   (or tail -f .install_visual.log)"
    # nohup + disown so the child survives this shell exit; uv reads no stdin.
    (
        cd "$ROOT"
        nohup bash -c "uv sync --extra visual" \
            > "$VISUAL_LOG" 2>&1 &
        echo $! > "$VISUAL_PID_FILE"
    )
    if [ -f "$VISUAL_PID_FILE" ]; then
        ok "Visual extras installing in background (pid $(cat "$VISUAL_PID_FILE"))"
    else
        warn "Could not background visual install; run manually: uv sync --extra visual"
    fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
# Check that claude CLI is reachable — Role processes spawn 'claude' and fail
# silently if it is not on PATH (seen on servers where claude is installed via
# nvm or VS Code extension but PATH is not set in non-interactive shells).
if command -v claude >/dev/null 2>&1; then
    CLAUDE_PATH=$(command -v claude)
    ok "claude CLI found: ${CLAUDE_PATH}"
else
    # Check common non-PATH install locations
    FOUND_CLAUDE=""
    for candidate in \
        "$HOME/.nvm/versions/node/"*/bin/claude \
        "$HOME/.local/bin/claude" \
        "$HOME/.vscode-server/extensions/anthropic.claude-code-"*/resources/native-binary/claude \
        "/usr/local/bin/claude"; do
        # shellcheck disable=SC2086
        if [ -x "$candidate" ] 2>/dev/null; then
            FOUND_CLAUDE="$candidate"
            break
        fi
    done
    if [ -n "$FOUND_CLAUDE" ]; then
        warn "claude CLI found at ${FOUND_CLAUDE} but NOT on PATH."
        warn "Role processes will fail with 'Failed to spawn: claude' on revive."
        warn "Fix: add the directory to PATH in ~/.bashrc or ~/.profile:"
        warn "  export PATH=\"$(dirname "$FOUND_CLAUDE"):\$PATH\""
    else
        warn "claude CLI NOT found. Role processes cannot start without it."
        warn "Install Claude Code CLI: https://docs.anthropic.com/en/docs/claude-code"
    fi
fi
echo ""
echo ""
echo -e "${BOLD}${GREEN}MinionsOS core installation complete — ./gru is ready to launch.${RESET}"
if [ "$VISUAL_INSTALLED" = "0" ] && [ -z "${MINIONS_SKIP_VISUAL:-}" ] && [ -z "${MINIONS_VISUAL_FOREGROUND:-}" ]; then
    echo -e "${YELLOW}  (visual extras still installing in background — see .install_visual.log)${RESET}"
fi
echo ""
echo -e "  ${BOLD}Next steps:${RESET}"
echo -e "  1. Edit ${CYAN}minions/config/gru.yaml${RESET} to adjust heartbeat interval, log level, etc."
echo -e "  2. Edit ${CYAN}minions/config/experiment_targets.yaml${RESET} to add SSH compute targets."
echo -e "  3. Launch Gru:  ${BOLD}./gru${RESET}"
echo -e "     Watch one project: ${BOLD}./noter <port>${RESET}"
echo -e "     Or use the CLI:  ${BOLD}./mos status${RESET}"
echo ""
