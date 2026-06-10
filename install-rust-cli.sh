#!/usr/bin/env bash
# Install Rust CLI binary to user path

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${HOME}/.local/bin"

echo "Building Rust CLI in release mode..."
cd "$SCRIPT_DIR"
cargo build --package minions-cli --release

echo "Installing mos binary to ${INSTALL_DIR}..."
mkdir -p "$INSTALL_DIR"
cp target/release/mos "$INSTALL_DIR/mos-rust"

echo ""
echo "✓ Rust CLI installed as: mos-rust"
echo ""
echo "To use the Rust CLI instead of Python:"
echo "  1. Add to your PATH: export PATH=\"${INSTALL_DIR}:\$PATH\""
echo "  2. Run: mos-rust status"
echo ""
echo "To replace Python mos entirely:"
echo "  ln -sf ${INSTALL_DIR}/mos-rust ${INSTALL_DIR}/mos"
echo ""
echo "Binary size: $(du -h target/release/mos | cut -f1)"
echo "Location: ${INSTALL_DIR}/mos-rust"
