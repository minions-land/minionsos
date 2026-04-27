# Repository Guidelines

## Project Structure & Module Organization

MinionsOS is a Python 3.11 package with a companion Vite/React dashboard. Core Python code lives in `minions/`: `cli.py` provides the `mos` entrypoint, `lifecycle/` manages projects and roles, `tools/` exposes MCP/experiment utilities, `state/` holds runtime state helpers, `roles/` contains role templates and skills, `domains/` contains expert packs, and `config/*.yaml.example` documents local configuration. Tests live in `tests/unit/` and `tests/smoke/`. `minions-viz/` is the read-only web dashboard, and `EACN3/` is the local editable dependency. Treat caches, logs, and `graphify-out/` as generated output.

## Build, Test, and Development Commands

- `./install.sh` bootstraps `uv`, syncs Python dependencies, prepares EACN3, and copies example configs.
- `./mos doctor` checks local prerequisites and project wiring.
- `./gru` or `./mos` launches the Gru CLI via `minions/bin/gru`.
- `uv sync` installs Python dependencies from `pyproject.toml` and `uv.lock`.
- `uv run pytest tests/unit -q` runs the unit suite used by CI.
- `MINIONS_FAKE_CLAUDE=1 uv run pytest tests/smoke/` runs smoke coverage without a live Claude CLI.
- `uv run ruff check .` and `uv run ruff format --check .` verify linting and formatting.
- `cd minions-viz && npm install && npm run build` builds the dashboard; `npm run dev` starts live reload.

## Coding Style & Naming Conventions

Use Ruff settings from `ruff.toml`: Python 3.11 target, 100-character lines, import sorting, pyupgrade, bugbear, simplify, and Ruff rules. Add `from __future__ import annotations` to Python modules, type public functions, use `pathlib.Path` for paths, and prefer `logging` over `print`. Invoke subprocesses with list arguments; do not use `os.system`. Name tests `test_*.py`, role skills `lowercase-hyphen.md`, and domain packs `lowercase-hyphen.md`.

## Testing Guidelines

Place fast behavior tests in `tests/unit/` and end-to-end/manual wiring checks in `tests/smoke/`. Use `MINIONS_FAKE_CLAUDE=1` when tests exercise Claude subprocess orchestration. Add focused tests for new lifecycle, state, role, tool, or skill-discovery behavior. Keep runtime state isolated; do not rely on existing `minions/state/projects.json` contents.

## Commit & Pull Request Guidelines

Git history follows Conventional Commit-style subjects such as `feat(state): ...`, `fix: ...`, and `style: ...`. Keep commits scoped and imperative. Pull requests should include a short summary, linked issue or motivation, commands run, and screenshots or GIFs for `minions-viz` UI changes. Call out configuration, migration, or runtime-state impacts explicitly.

## Security & Configuration Tips

Do not commit secrets, experiment credentials, generated project worktrees, or local runtime state. Base local config on `minions/config/*.yaml.example`. Preserve project isolation: cross-project communication should use Gru relay paths only, and dashboard endpoints must remain read-only.
