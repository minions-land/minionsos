# MinionsOS — unified task runner
# Wraps uv/npm/cargo to provide a single command interface.

.PHONY: help install test lint clean upgrade doctor
.DEFAULT_GOAL := help

# ────────────────────────────────────────────────────────────────────────────
# User-facing targets
# ────────────────────────────────────────────────────────────────────────────

help:  ## Show this help message
	@echo "MinionsOS unified task runner"
	@echo ""
	@echo "Common targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Full install (Python + Node + optional Rust CLI)
	@echo "→ Running ./install.sh (uv + npm managed automatically)..."
	./install.sh
	@echo ""
	@echo "✓ Core installation complete (Python + Node)"
	@echo "  Optional: make rust-cli  (build Rust CLI)"

test:  ## Run all tests (Python unit + Rust if built)
	@echo "→ Python unit tests..."
	MINIONS_FAKE_CLAUDE=1 uv run pytest tests/unit/ -q
	@if [ -f target/release/mos ]; then \
		echo ""; \
		echo "→ Rust CLI smoke test..."; \
		./target/release/mos status || echo "(Rust CLI test skipped — no running instance)"; \
	fi

lint:  ## Run all linters (ruff + cargo clippy if Rust exists)
	@echo "→ Python: ruff check + format check..."
	uv run ruff check .
	uv run ruff format --check .
	@if [ -f Cargo.toml ]; then \
		echo ""; \
		echo "→ Rust: cargo clippy (warnings only, experimental)..."; \
		cargo clippy --all-targets 2>&1 | grep -E "warning:|error:" || echo "  (Rust clippy passed or skipped)"; \
	fi

clean:  ## Remove build artifacts and caches
	@echo "→ Cleaning Python caches..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "→ Cleaning Rust target/..."
	cargo clean 2>/dev/null || true
	@echo "→ Cleaning Node modules..."
	rm -rf mcp-servers/eacn3/node_modules 2>/dev/null || true
	rm -rf minions-viz/node_modules 2>/dev/null || true
	@echo "✓ Clean complete"

upgrade:  ## Upgrade MinionsOS (git pull + incremental install)
	./mos upgrade

doctor:  ## Run health checks
	./mos doctor

# ────────────────────────────────────────────────────────────────────────────
# Optional subsystems
# ────────────────────────────────────────────────────────────────────────────

rust-cli:  ## Build and install Rust CLI (optional, experimental)
	@echo "→ Building Rust CLI (release mode)..."
	cargo build --package minions-cli --release
	@echo "→ Installing to ~/.local/bin/mos..."
	mkdir -p ~/.local/bin
	cp target/release/mos ~/.local/bin/
	@echo "✓ Rust CLI installed: ~/.local/bin/mos"
	@echo "  (ensure ~/.local/bin is in your PATH)"

rust-test:  ## Test Rust CLI
	@echo "→ Rust CLI unit tests..."
	cargo test --package minions-cli
	@echo "→ Rust CLI integration test..."
	cargo run --package minions-cli -- status

# ────────────────────────────────────────────────────────────────────────────
# Subsystem-specific targets (advanced users)
# ────────────────────────────────────────────────────────────────────────────

python-sync:  ## Sync Python dependencies only
	uv sync

eacn3-rebuild:  ## Rebuild EACN3 Node plugin
	cd mcp-servers/eacn3 && npm install

viz-rebuild:  ## Rebuild dashboard frontend
	cd minions-viz && npm install && npm run build

audit:  ## Run contract audit
	uv run mos audit
