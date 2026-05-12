# MinionsOS Repository Guidelines

> **Repository naming standard:** the project title is **MinionsOS**. Do not add
> release suffixes to product names, repository names, headings, or checkout
> paths in new documentation. The historical local folder may still have a
> version-suffixed name during this migration, but that name is temporary and
> must be removed after this revision lands.

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
- `cd minions-viz && npm install && npm run build` builds the dashboard; `npm run dev` starts live reload.

## Coding Style & Naming Conventions

Use Ruff settings from `ruff.toml`: Python 3.11 target, 100-character lines, import sorting, pyupgrade, bugbear, simplify, and Ruff rules. Add `from __future__ import annotations` to Python modules, type public functions, use `pathlib.Path` for paths, and prefer `logging` over `print`. Invoke subprocesses with list arguments; do not use `os.system`. Name tests `test_*.py`, role skills `lowercase-hyphen.md`, and domain packs `lowercase-hyphen.md`.

Role prompts and skills are markdown but still part of the runtime surface. Keep skill files short and procedural, with a title and one-line summary that `minions.lifecycle.skills` can discover. Reviewer workflow changes must keep `SYSTEM.md`, `skills/`, `templates/`, `personas/`, and `tests/unit/test_reviewer_system_invariants.py` aligned.

## Testing Guidelines

Place fast behavior tests in `tests/unit/` and end-to-end/manual wiring checks in `tests/smoke/`. Use `MINIONS_FAKE_CLAUDE=1` when tests exercise Claude subprocess orchestration; use fake Codex launcher patterns when testing `agent_host: codex`. Add focused tests for new lifecycle, state, role, tool, role prompt, reviewer template, agent-host, MCP authorization, or skill-discovery behavior. Keep runtime state isolated; do not rely on existing `minions/state/projects.json` contents.

## Repository Management Procedures

Use this repository as the single canonical MinionsOS checkout. Version identity
belongs in commit messages, tags, release notes, and changelogs, not in the
project title, GitHub repository name, or local directory name. The GitHub
repository should be `Minions-Land/MinionsOS`, with `main` as the integration
branch unless a temporary release or repair branch is explicitly needed.

Before repository-level operations, run `git status --short --branch` and
`git remote -v`. Do not rename remotes, rewrite history, delete branches, or
move checkout directories while there are unknown local changes unless those
changes have been committed, stashed, or explicitly preserved. If a mirror or
proxy is needed because direct GitHub access is unreliable, record the mirror
remote as a separate remote name such as `mirror`; keep `origin` pointed at the
canonical GitHub repository.

## Commit & Pull Request Guidelines

Every new MinionsOS management commit must include the version in the subject,
for example `Version 5 Commit: standardize repository naming` or
`Version 5.1 Commit: update role wake protocol`. Keep commits scoped,
imperative, and reviewable. Use Conventional Commit verbs after the version
prefix when useful, for example `Version 5 Commit: fix(runtime): preserve wake
inbox`.

Submission protocol:

1. Inspect state with `git status --short --branch`, `git diff --stat`, and
   focused `git diff` for the files being submitted.
2. Run the narrowest meaningful verification first, then the broader gates when
   the change touches runtime contracts. Typical gates are `uv run pytest
   tests/unit -q`, `uv run ty check minions`, `uv run ruff check .`, and `uv run
   ruff format --check .`.
3. Stage only the intended files or hunks. Do not include generated project
   worktrees, local runtime state, logs, credentials, screenshots, or unrelated
   dashboard artifacts.
4. Commit with the required versioned subject and include verification notes in
   the commit body when the change is non-trivial.
5. Push to the corresponding GitHub repository. If direct GitHub access fails,
   push to the configured mirror remote and document the mirror URL and reason
   in the handoff.

Pull requests should include a short summary, linked issue or motivation,
commands run, and screenshots or GIFs for `minions-viz` UI changes. Call out
configuration, migration, repository rename, or runtime-state impacts
explicitly.

## Local Modification Workflow

For local changes, work from a clean branch or a clearly named temporary
worktree when the main checkout already has unrelated edits. Prefer
`git worktree add -b <branch> <path> HEAD` for isolated repository-management
work. Keep generated output out of commits unless the generated artifact is the
explicit deliverable.

When editing, preserve user or agent changes that predate your task. If a file
already contains unrelated edits, either stage only your hunks or move the work
to a clean worktree and re-apply the minimal patch. Before finishing, run
`rg -n "MinionsOS[ _-]?V[0-9]+"` to catch accidental product-name regressions;
ignore only incidental binary hashes or historical external data with a clear
note.

## Security & Configuration Tips

Do not commit secrets, experiment credentials, generated project worktrees, or local runtime state. Base local config on `minions/config/*.yaml.example`. Preserve project isolation: cross-project communication should use Gru relay paths only, and dashboard endpoints must remain read-only.
