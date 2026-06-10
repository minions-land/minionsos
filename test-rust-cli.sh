#!/bin/bash
# Quick test script for Rust CLI

set -e

cd "$(dirname "$0")"

echo "=== MinionsOS Rust CLI Quick Test ==="
echo ""

echo "1. Building Rust CLI..."
cargo build --package minions-cli --release

echo ""
echo "2. Testing commands..."
echo ""

echo "→ mos status:"
./target/release/mos status
echo ""

echo "→ mos project list:"
./target/release/mos project list
echo ""

if [ -n "$1" ]; then
    PORT="$1"
else
    # Try to find a project port
    PORT=$(./target/release/mos status 2>/dev/null | grep -E "^\| [0-9]+" | head -1 | awk '{print $2}' || echo "")
fi

if [ -n "$PORT" ]; then
    echo "→ mos project show $PORT:"
    ./target/release/mos project show "$PORT"
    echo ""

    echo "→ mos role list $PORT:"
    ./target/release/mos role list "$PORT"
    echo ""
fi

echo "=== All tests passed! ==="
echo ""
echo "To install:"
echo "  ./install-rust-cli.sh"
echo ""
echo "Binary location:"
echo "  $(pwd)/target/release/mos"
echo "  Size: $(du -h target/release/mos | cut -f1)"
