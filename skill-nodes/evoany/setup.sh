#!/usr/bin/env bash
# Setup script for the EvoAny skill node.
# Clones the EvoAny repo and builds its MCP server so the manifest can
# reference dist/plugin/server.js.
#
# Usage: ./setup.sh
# Idempotent — safe to re-run.

set -euo pipefail
cd "$(dirname "$0")"

REPO_URL="https://github.com/DataLab-atom/EvoAny.git"
REPO_DIR="repo"

if [ ! -d "$REPO_DIR" ]; then
    echo "Cloning EvoAny..."
    git clone --depth=1 "$REPO_URL" "$REPO_DIR"
else
    echo "EvoAny repo already present; pulling latest..."
    git -C "$REPO_DIR" pull --ff-only || true
fi

echo "Installing dependencies..."
cd "$REPO_DIR"
npm install

echo "Building MCP server..."
npm run build || npx tsc

echo "Done. EvoAny skill node is ready."
echo "Manifest expects server at: skill-nodes/evoany/repo/dist/plugin/server.js"
