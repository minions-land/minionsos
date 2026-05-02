# MinionsOS V5 Repository Guidelines

## Project Structure & Module Organization

MinionsOS is a Python 3.11 package with a companion Vite/React dashboard. Core Python code lives in `minions/`: `cli.py` provides the `mos` entrypoint, `lifecycle/` manages projects, roles, wakeups, skills, and EACN identity, `tools/` exposes MCP/experiment utilities, `state/` holds runtime state helpers, `roles/` contains the shared Role contract plus role prompts, skills, and reviewer templates/personas, `domains/` contains expert packs, and `config/*.yaml.example` documents local configuration. Tests live in `tests/unit/` and `tests/smoke/`. `minions-viz/` is the read-only web dashboard, and `EACN3/` is the local editable dependency. Treat caches, logs, `project_{port}/`, and `graphify-out/` as generated output.

## Build, Test, and Development Commands

- `./install.sh` bootstraps `uv`, syncs Python dependencies, prepares EACN3, and copies example configs.
- `./mos doctor` checks local prerequisites and project wiring.
- `./gru` or `./mos` launches the Gru CLI via `minions/bin/gru`.
- `uv sync` installs Python dependencies from `pyproject.toml` and `uv.lock`.
- `uv run pytest tests/unit -q` runs the unit suite used by CI.
- `MINIONS_FAKE_CLAUDE=1 uv run pytest tests/smoke/` runs smoke coverage without a live Claude CLI.
- `MINIONS_AGENT_HOST=codex ./gru` launches the same MinionsOS control plane through Codex when `.codex/config.toml` is present.
- `uv run ty check minions` runs the typed runtime-contract gate for the Python runtime core.
- `uv run ruff check .` and `uv run ruff format --check .` verify linting and formatting.
- `cargo test --workspace` runs the Rust runtime-contract tests.
- `cargo fmt --all --check` verifies Rust formatting.
- `cd minions-viz && npm install && npm run build` builds the dashboard; `npm run dev` starts live reload.

## Coding Style & Naming Conventions

Use Ruff settings from `ruff.toml`: Python 3.11 target, 100-character lines, import sorting, pyupgrade, bugbear, simplify, and Ruff rules. Add `from __future__ import annotations` to Python modules, type public functions, use `pathlib.Path` for paths, and prefer `logging` over `print`. Invoke subprocesses with list arguments; do not use `os.system`. Name tests `test_*.py`, role skills `lowercase-hyphen.md`, and domain packs `lowercase-hyphen.md`.

Role prompts and skills are markdown but still part of the runtime surface. Keep skill files short and procedural, with a title and one-line summary that `minions.lifecycle.skills` can discover. Reviewer workflow changes must keep `SYSTEM.md`, `skills/`, `templates/`, `personas/`, and `tests/unit/test_reviewer_system_invariants.py` aligned.

## Testing Guidelines

Place fast behavior tests in `tests/unit/` and end-to-end/manual wiring checks in `tests/smoke/`. Use `MINIONS_FAKE_CLAUDE=1` when tests exercise Claude subprocess orchestration; use fake Codex launcher patterns when testing `agent_host: codex`. Add focused tests for new lifecycle, state, role, tool, role prompt, reviewer template, agent-host, MCP authorization, or skill-discovery behavior. Keep runtime state isolated; do not rely on existing `minions/state/projects.json` contents.

## Commit & Pull Request Guidelines

Git history follows Conventional Commit-style subjects such as `feat(state): ...`, `fix: ...`, and `style: ...`. Keep commits scoped and imperative. Pull requests should include a short summary, linked issue or motivation, commands run, and screenshots or GIFs for `minions-viz` UI changes. Call out configuration, migration, or runtime-state impacts explicitly.

## Security & Configuration Tips

Do not commit secrets, experiment credentials, generated project worktrees, or local runtime state. Base local config on `minions/config/*.yaml.example`. Preserve project isolation: cross-project communication should use Gru relay paths only, and dashboard endpoints must remain read-only.
