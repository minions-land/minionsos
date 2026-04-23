# MinionsOS V2

> Towards Fully Autonomous Scientific Discovery: A Multi-Agent Workflow on the EACN Protocol.

MinionsOS V2 is a multi-agent operating system for running autonomous research projects. One author, one checkout, one persistent Gru — supervising as many papers as you want, each isolated on its own EACN3 coordination bus.

## 60-second install

```bash
git clone --recursive https://github.com/your-org/MinionsOS_V2
cd MinionsOS_V2
./install.sh
./gru
```

`install.sh` bootstraps `uv`, installs Python 3.11, syncs the package, builds the EACN3 plugin, and copies example configs. After that, `./gru` is all you need.

Requirements: Python 3.11+, Node 16+, Git 2.x.

## Architecture

```
Author
  |
  v
Gru (global supervisor, human window)
  |
  +-- project_37596/  (one paper = one project = one EACN3 backend)
  |     |
  |     +-- EACN3 bus (port 37596)
  |           |
  |           +-- Noter       (silent observer; artifacts/notes/)
  |           +-- Coder       (workspace/src/)
  |           +-- Expert-dl   (workspace/ scratch)
  |           +-- Experimenter (workspace/experiments/ + remote GPUs)
  |           +-- Writer      (workspace/paper/)
  |           +-- Reviewer    (artifacts/reviews/)
  |
  +-- project_37601/  (another paper, fully isolated)
        |
        +-- EACN3 bus (port 37601)
              ...

Cross-project relay: Gru only, via gru_relay()
```

## Role matrix

| Role | Instances | Default spawn | Writable scope |
|---|---|---|---|
| Gru | 1 global | n/a | everything |
| Noter | 1 per project | yes | `artifacts/notes/` only |
| Coder | 1 per project | yes | full `workspace/` |
| Expert | 1-8, domain-flavored | 1: `expert-dl-arch` | `workspace/` (soft: read mostly) |
| Experimenter | 1 per project | on demand | full `workspace/` |
| Writer | 1 per project | on demand | full `workspace/` |
| Reviewer | 1 per project | on demand | `artifacts/reviews/` only |

## Why EACN3 is pluggable

EACN3 lives in `EACN3/` as a git submodule. MinionsOS never edits its internals. To upgrade, replace the submodule. Each project gets its own EACN3 backend instance on a dedicated port, so projects are physically isolated — no shared state, no cross-contamination. The only cross-project path is `gru_relay`, which Gru controls.

## Common commands

```bash
./mos status                  # project dashboard
./mos logs --project 37596    # project logs
./mos doctor                  # environment health check
./mos project revive 37596    # wake a dormant project
./mos role list 37596         # list roles on a project
```

## Full documentation

See `CLAUDE.md` at the repo root for the complete constitution: hard rules, tool whitelists, debug entry points, and reader navigation for every agent type.
