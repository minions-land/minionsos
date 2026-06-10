# MinionsOS Rust CLI

High-performance Rust implementation of the MinionsOS command-line interface.

## Why Rust CLI?

The Rust CLI provides **instant startup** for frequent query commands while maintaining full compatibility with the Python backend.

### Performance Comparison

| Command | Python CLI | Rust CLI | Speedup |
|---------|-----------|----------|---------|
| `mos status` | ~238ms | ~5-10ms | **~24×** |
| `mos project list` | ~238ms | ~5-10ms | **~24×** |
| `mos role list PORT` | ~238ms | ~5-10ms | **~24×** |

The speedup comes from eliminating Python interpreter startup and import overhead. For query commands you run dozens of times per day, this adds up to a noticeably smoother experience.

## Architecture

```
┌─────────────────────────────────────┐
│  minions-cli (Rust binary)          │
│  • Fast startup (<10ms)              │
│  • Read-only queries                 │
│  • Direct JSON/file access           │
└──────────┬──────────────────────────┘
           │
           ├─ reads → minions/state/projects.json
           └─ reads → projects/project_{port}/meta.json
```

The Rust CLI currently implements **read-only query commands**:
- `mos status` — dashboard of all projects
- `mos project list` — list projects
- `mos project show PORT` — show project details
- `mos role list PORT` — list roles in a project

For write operations (create/close/revive), it currently delegates to the Python CLI. This is the **Phase 1 implementation** as outlined in the Rust migration plan.

## Structure

- **`minions-core/`** — Shared Rust library for state management
  - `state.rs` — Project/Role data structures (matches Python's schema)
  - `paths.rs` — Path resolution (MINIONS_ROOT, projects.json location)
  - Fully compatible with Python's JSON format
  
- **`minions-cli/`** — CLI binary
  - Uses `clap` for argument parsing
  - Uses `tabled` for formatted output
  - Reads directly from state files (no Python subprocess for queries)

- **`minions-tui/`** — Existing Rust TUI (3.2K LOC, already in use)

## Installation

```bash
# Build and install
./install-rust-cli.sh

# Or manually
cargo build --package minions-cli --release
cp target/release/mos ~/.local/bin/mos-rust

# Replace Python CLI (optional)
ln -sf ~/.local/bin/mos-rust ~/.local/bin/mos
```

## Usage

Identical to Python CLI for implemented commands:

```bash
# View all projects
mos status

# List projects
mos project list

# Show project details
mos project show 37680

# List roles
mos role list 37680

# Help
mos --help
```

## Testing

```bash
# Unit tests (tests state parsing with real projects.json)
cargo test --package minions-core

# Integration test (compare with Python output)
diff <(target/release/mos status) <(uv run python -m minions.cli status)
```

## Compatibility

✅ **Reads the same state files as Python**
- `minions/state/projects.json`
- `projects/project_{port}/meta.json`

✅ **Respects environment variables**
- `MINIONS_ROOT` — override repo root detection
- `MINIONS_PROJECTS_ROOT` — override projects directory

✅ **Works side-by-side with Python**
- No conflicts, both can run simultaneously
- Rust reads, Python writes (current phase)

## Roadmap

### ✅ Phase 1: Read-only query commands (DONE)
- [x] `mos status`
- [x] `mos project list`
- [x] `mos project show`
- [x] `mos role list`
- [x] State file parsing (`minions-core`)
- [x] Install script

### 🚧 Phase 2: Write operations (future)
- [ ] `mos project close PORT`
- [ ] `mos project revive PORT`
- [ ] `mos role dismiss PORT ROLE`
- [ ] EACN3 HTTP client (already proven in `minions-tui`)

### 🚧 Phase 3: Daemon integration (future, optional)
- [ ] Rust daemon supervisor (Gru loop + watchdogs)
- [ ] See full migration plan in docs

## Performance Notes

**Why is startup so fast?**

1. **Static binary** — No Python interpreter initialization
2. **No imports** — No module loading overhead
3. **Direct file I/O** — Read JSON directly, no subprocess
4. **Release build** — Full compiler optimizations

**What's the tradeoff?**

- Faster for queries, but requires Rust compilation for changes
- Python CLI remains the source of truth for write operations (Phase 1)
- Development iteration is slower (compile vs edit-and-run)

## Development

```bash
# Check compilation
cargo check --workspace

# Run tests
cargo test --workspace

# Build release binary
cargo build --package minions-cli --release

# Format code
cargo fmt --all

# Lint
cargo clippy --all
```

## Binary Size

Release binary: **~1.5MB** (includes all dependencies, statically linked)

Compare to Python:
- Python + uv + dependencies: ~100MB
- Rust single binary: 1.5MB

For deployment, you copy one file.
