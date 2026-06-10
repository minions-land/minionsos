<div align="center">

# MinionsOS

**Local multi-agent OS for autonomous, paper-sized research projects.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Node 16+](https://img.shields.io/badge/node-16%2B-green)](https://nodejs.org/)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange)](#)

[English](#english) · [中文](#中文)

</div>

---

## English

**MinionsOS** is a local multi-agent operating system for running isolated,
research-grade projects. A persistent **Gru** supervisor manages projects;
each project owns its own **EACN3** coordination backend; long-lived
agent-host **Roles** wake up on event arrival, process work, and stay resident
across many cycles. Claude Code is the only Role host.

**The core contribution is a team Memory mechanism for autonomous scientific
discovery.** A project's knowledge lives in one structured graph — the
**Draft** — that every Role reads and writes through a single unified lens
(`mos_draft_view`) and appends to as work lands (`mos_draft_append`, with
plan nodes replaced by their results, never left as zombies). One Role,
**Ethics**, curates that graph (drawing cross-Role edges, computing decay,
sealing dead-ends) and audits whether every claim on it has real evidence.
Verified knowledge is compiled into the **Book** — the main-branch, paper-shaped
organization of the project's output. Reel → Draft → Book carry provenance
links: Reel is a per-role pointer index over native Claude session JSONL, so
auditable claims can trace back to the execution frame that produced them.
EACN3 is the coordination substrate; the Memory graph is what makes a team of
cold-started agents accumulate, verify, and compound knowledge across cycles.

The runtime topology of each project is selected by a *Mission Profile*
(`minions/profiles/<name>.yaml`). The default `scientific-paper` profile drives
the full Autonomous Scientific Discovery pipeline: a **Gru** supervisor, an
**Ethics** memory-curator/auditor, and one or more spawnable **Expert** workers
(code, experiments, writing, figures, literature) producing peer-reviewed PDFs.

The design goal is simple: one author, one checkout, one Gru, many isolated
research projects.

### Table of Contents

- [What You Get](#what-you-get)
- [Architecture](#architecture)
- [Repository Layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Install](#install)
- [Configure](#configure)
- [Run](#run)
- [Roles](#roles)
- [Skill family and autonomous evolution](#skill-family-and-autonomous-evolution)
- [MCP Surface](#mcp-surface)
- [Runtime Project Structure](#runtime-project-structure)
- [MinionsVIZ](#minionsviz)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Security and Configuration](#security-and-configuration)
- [License](#license)

### What You Get

- **Project isolation.** Every project has its own `projects/project_{port}/` directory,
  EACN3 backend, SQLite state, per-project bare git repo, role worktrees, logs,
  artifacts, and event audit stream.
- **Mission Profiles.** Each project is parameterised by a *Mission Profile*
  (`minions/profiles/<name>.yaml`) declaring `roles_active`, `deliverable_schema`,
  `evaluation` strategy, `phase_schema`, and `on_done` behaviour. The default
  `scientific-paper` profile runs the autonomous scientific discovery pipeline
  with Gru, Ethics, Expert workers, peer review output, `mos_submit` /
  `mos_evaluate`, and benchmark support. New profiles ship as a single YAML
  file plus optional role-prompt overlays.
- **Long-lived Roles.** Gru, Ethics, and one or more Experts run as
  resident `claude` processes inside named tmux sessions
  (`mos-{port}-{role}`). EACN-registered roles drive their event loop with
  `mos_await_events()`. Experts are the spawnable general workers (code,
  experiments, writing, figures, literature); Gru adjusts the Expert roster as
  the project's needs shift.
- **Gru as the control plane.** Gru is the human-facing supervisor and the only
  component allowed to create projects, spawn roles, and bridge across
  projects.
- **Tool and write boundaries.** Claude roles receive `--allowed-tools`;
  MinionsOS additionally enforces project-lifecycle authorization inside its
  MCP server. Each Role owns `branches/<role>/`; cross-role artefacts always
  travel through `branches/main/<subdir>/` via `mos_publish_to_shared`.
- **Layered memory.** Role context is reconstructed from the current
  invocation, the Reel (L0, `branches/<role>/reel-index.jsonl` pointers to
  native Claude session JSONL), the Draft (L1, the single team process graph at
  `branches/main/draft/draft.json`), and the compiled-knowledge Book (L2, the
  main-branch paper-shaped package at `branches/main/book/`), plus shared
  artefacts under `branches/main/<subdir>/`, EACN history, and project
  `CLAUDE.md`. See [MANUAL/domains/reel-l0-memory.md](MANUAL/domains/reel-l0-memory.md)
  for the L0 design.
- **Skill discovery and domain assets.** Role skills live in
  `minions/roles/{role}/skills/*.md`; Expert domain-pack assets live in
  `minions/domains/*.md`.
- **Two-axis autonomous evolution.** Ethics audits skill-change proposals,
  Gru validates accepted changes, and Gru evolves the Expert roster from
  project trajectory. Backed by `mos_role_split`, `mos_role_merge`,
  `mos_role_evolve_evaluate`, and `mos_role_evolve_dismiss` MCP tools.
- **Visual format check.** `mos_visual_render` / `mos_visual_inspect` /
  `mos_visual_check` rasterize a PDF and detect layout defects (column void,
  trailing whitespace, edge overflow, float clustering). Available to every
  EACN-visible Role; reports persist under `branches/<role>/visual-reports/`.
- **Structured review.** Paper review runs through Gru's `mos_review_run`
  workflow. Its prompt assets (SYSTEM.md, procedural skills, reviewer
  personas, output templates) live under `minions/review/`, and a round
  produces 3-5 independent reviewer-instance reports plus a consolidated
  meta-review and rolling summary.
- **Experiment execution.** Experts run experiments through the `mos_exp_*`
  tools — direct primitives (`mos_exp_run`, `mos_exp_status`,
  `mos_query_gpus`) and a Python-side project queue
  (`mos_exp_queue_submit`, `mos_exp_queue_plan`,
  `mos_exp_queue_reconcile`, `mos_exp_gpu_pool_set`).
- **Read-only observability.** `minions-viz/` provides a machine-wide
  MinionsVIZ dashboard without draining role queues or mutating EACN3.

### Architecture

```text
Author
  |
  v
Gru
  |
  +-- project_37596/
  |     |
  |     +-- EACN3 backend on 127.0.0.1:37596
  |     |     +-- Ethics         -> branches/ethics/ + branches/main/ethics/ + book curation
  |     |     +-- Expert (generalist, auto-spawned)
  |     |     |     -> branches/expert-generalist/ + branches/main/exp/ + mos_exp_*
  |     |     +-- Expert-<domain> (spawned on demand)
  |     |           -> branches/expert-<slug>/ + domain pack
  |     |
  |     +-- branches/                # one git worktree per role plus main (shared surface)
  |     |     +-- main/ (Gru + shared surface), ethics/, expert-*/
  |     +-- parent_repo.git/         # per-project bare git repo
  |     +-- eacn3_data/eacn3.db      # project-local EACN3 SQLite
  |     +-- events/                  # per-agent EACN event JSONL
  |     +-- state/                   # runtime control state
  |     +-- logs/
  |
  +-- project_37601/
        |
        +-- separate backend, branches, EACN state, events, and logs
```

Cross-project communication is intentionally narrow: Roles cannot talk to other
projects directly. Gru can bridge projects through the Gru-only
`mos_project_bridge` path.

### Repository Layout

```text
minions/
  cli.py                    # mos CLI entry point
  gru/                      # Gru monitor loop
  lifecycle/                # projects, roles, wakeup, relay, health
  tools/                    # MCP tools and experiment execution
  state/                    # runtime state helpers
  roles/                    # shared Role contract, prompts, skills
  review/                   # paper-review prompt assets used by mos_review_run
  domains/                  # Expert domain-pack assets
  config/*.yaml.example     # local config templates

minions-viz/                # read-only React/Vite dashboard
mcp-servers/                # standalone MCP servers
  eacn3/                    # local editable EACN3 dependency (Python + Node plugin)
MANUAL/                     # on-demand reference for Role agents (lookup.py)
MARKDOWN_INDEX.md           # map of Markdown assets and discovery surfaces
tests/unit/                 # fast behavior tests
tests/smoke/                # integration-style smoke checks
```

Generated runtime output such as `projects/`, `minions/state/`, logs,
and caches is not committed.

### Prerequisites

- Python **3.11+**
- [`uv`](https://docs.astral.sh/uv/) for Python dependency management
- `git` 2.x
- Node **16+** and `npm` for the EACN3 MCP plugin and MinionsVIZ
- Claude CLI on `PATH`

MinionsOS seeds project worktrees from the directory that contains this
checkout. That parent directory must be a git repository before you create
projects:

```bash
cd <parent-of-MinionsOS>
git init
git add -A
git commit -m "init"
```

`./install.sh` warns about this condition, and `./mos doctor` re-checks it. To
override the seed source, set `gru.yaml: author_repo` (or
`MINIONS_AUTHOR_REPO`).

### Install

```bash
git clone https://github.com/Minions-Land/MinionsOS.git
cd MinionsOS
./install.sh
./mos doctor
```

`install.sh` is idempotent. It bootstraps `uv` when needed, syncs Python
dependencies, installs the local editable `mcp-servers/eacn3/` package, builds
the EACN3 MCP plugin, builds MinionsVIZ when needed, creates launcher
symlinks, and copies `minions/config/*.yaml.example` to local `.yaml` files
without overwriting existing config.

### Update

Pull a new release without disturbing your running projects:

```bash
./mos upgrade           # git pull --ff-only && incremental ./install.sh
./mos restart --all     # apply the new code/prompts to running processes
```

`mos upgrade` only touches the repo: it fast-forwards `git`, then runs an
incremental `install.sh` that rebuilds only what changed (Python deps, the
EACN3 plugin, MinionsVIZ — each gated on a content hash of its source tree, so
a source-only commit rebuilds correctly). Your projects under `projects/` are
gitignored and never touched; EACN3 databases, worktrees, and the Draft survive
untouched.

What `upgrade` does **not** do is restart anything already running. A live Role
froze its `SYSTEM.md`, tool whitelist, and MCP authorization at launch, and the
Gru monitor snapshotted `gru.yaml` once — none of these hot-reload. To apply an
upgrade to live processes, cold-restart them:

```bash
./mos restart --all              # Gru monitor + every running role
./mos restart --gru              # just the Gru monitor / watchdog sidecar
./mos restart <port>             # one project's running roles
./mos restart <port> --role expert  # a single role
```

Restart only recycles processes that are actually running; a not-running role
is left for the watchdog (or `mos project revive`) to start later on the new
code. Roles cold-start and reconstruct context from the Draft (L1), so no work
is lost. After upgrading, `mos upgrade` prints the exact restart command for
any live processes it detects.

`mos doctor` includes a `config-keys-current` check that flags any new
`*.yaml.example` key that an upgrade added but your existing local `*.yaml`
never gained (defaults still apply — merge the key manually to tune it).

### Configure

Local configuration lives under `minions/config/` and is intentionally ignored
by git:

- `gru.yaml` controls heartbeat cadence, logging, model/context settings,
  draft thresholds, and web-search policy.
- `experiment_targets.yaml` defines local and SSH execution targets for Expert.
  Paths may use `{project_workspace}` template expansion.

Inspect resolved paths with:

```bash
./mos config
./mos config --json
```

Launcher:

```bash
./gru                 # launch interactive Gru (Claude-hosted)
```

### Run

```bash
./gru                 # launch interactive Gru
./mos noter <port>    # launch read-only project observatory terminal
./mos status          # project dashboard
./mos status --json   # machine-readable project status
./mos doctor          # environment health checks
```

The `mos noter` command provides a read-only observatory terminal for one project,
showing backend, role, task, and artifact state without draining EACN role queues.

Project and role management:

```bash
./mos project list
./mos project list active
./mos project close <port>
./mos project revive <port>
./mos project repair <port>

./mos role list <port>
./mos role dismiss <port> <role>
```

Logs:

```bash
./mos logs
./mos logs --project <port>
./mos logs --project <port> --role expert --tail 100
./mos logs --project <port> --role expert --follow
```

### Roles

The default `scientific-paper` profile bootstraps **three** role kinds:

| Role | Responsibility | Primary write scope |
|---|---|---|
| Gru | Global supervisor, human interface, project lifecycle, cross-project bridge, runs `mos_review_run`, promotes Ethics-sealed content into the Book | `branches/main/`, `branches/main/<any>/` |
| Ethics | Memory curator (Draft→Book ingest + ratify), evidence/claim audit, contradiction adjudication | `branches/ethics/` (drafts), `branches/main/ethics/`, `branches/main/book/`, `branches/main/draft/draft.json`, `branches/main/handoffs/`, `branches/main/governance/` |
| Expert (×N, spawnable) | General science work — domain reasoning, code + experiments (`mos_exp_*`), paper drafting (Book→Paper). One generalist is auto-spawned; Gru spawns domain specialists as needed. | `branches/expert-<slug>/`, `branches/main/exp/`, `branches/main/handoffs/`, `branches/main/governance/` |

Role prompts are stored at `minions/roles/{role}/SYSTEM.md`. The shared Role
contract at `minions/roles/SYSTEM.md` is injected before each role-specific
prompt. Skills are discovered from `minions/roles/{role}/skills/` at wake-up
and injected as a `[Skills]` summary block.

Paper review uses prompt assets (system prompt, skills, personas, templates)
under `minions/review/`. Gru runs the round with the `mos_review_run` MCP tool,
which writes `reviewer-instance.md`, `fresh.md`, `revision_delta.md`,
`consolidated.md`, and `summaries/round-<n>.md` under
`branches/main/reviews/`. The review workflow audits a submitted paper
(Book→Paper output); Ethics audits the underlying evidence and claims in the
Draft/Book.

### Skill family and autonomous evolution

Beyond the human-driven extension paths (add a Role, add a skill, add a
domain pack, add an MCP tool), MinionsOS runs a **four-stage decorrelated
pipeline** that evolves the active Skill set and the Expert roster from project
trajectory itself. The four components live at distinct authority levels:

| Stage | Component | Operator | Output |
|---|---|---|---|
| 1. Propose | Proposal ledger | Gru records Skill / Expert change proposals from project trajectory | `branches/main/notes/skill-proposals.md` — append-only ledger of add/revise/merge/split/drop proposals |
| 2. Audit | `minions/roles/ethics/skills/skill-audit.md` | Ethics | Audit verdicts under `branches/main/ethics/` |
| 3. Validate + ship | `minions/roles/common/skills/skill-forge/SKILL.md` procedure | Gru routes accepted proposals here | Validated Role skill admitted to `minions/roles/*/skills/` |
| 4. Enact Expert roster | `mos_role_split`, `mos_role_merge`, `mos_role_evolve_evaluate`, `mos_role_evolve_dismiss`, `mos_spawn_expert`, `mos_dismiss_role` | Gru | Updated Expert roster on EACN |

The decorrelation is structural, not procedural: proposal, Ethics audit,
Gru validation, and consuming Roles stay separated. See
`minions/CLAUDE.md` "Skill and Agent population evolution" for the full Gru
intake contract.

### MCP Surface

The MinionsOS MCP server exposes lifecycle and execution tools from
`minions/tools/mcp_server.py`. All tools carry the `mos_` prefix.

**Gru-only — project lifecycle:**

```text
mos_project_create
mos_project_close
mos_project_dormant
mos_project_revive
mos_project_kill
mos_project_list
mos_project_set_phase
mos_project_checkpoint_workspace
mos_project_bridge
mos_start_monitor
mos_review_run
```

**Gru-only — role lifecycle:**

```text
mos_spawn_role
mos_spawn_expert
mos_attach_role
mos_dismiss_role
mos_kill_role
mos_list_roles
```

**Role event loop and context:**

```text
mos_await_events           # EACN-registered roles (Ethics, Expert)
mos_get_events
mos_unread_summary
mos_compact_context
mos_reset_context
mos_issue_report
```

**Cross-role publishing:**

```text
mos_publish_to_shared
```

**Reel — L0 raw verbatim transcripts (auto-captured; read-only for roles):**

```text
mos_reel_get
mos_reel_window
```

**Draft — L1 process memory (Ethics curates; all roles read):**

```text
mos_draft_append
mos_draft_view                # unified read: orient header + filtered node/edge slice
mos_draft_annotate
mos_draft_path
mos_draft_decay_compute       # half-life-based confidence decay
mos_draft_commit_shared       # Ethics periodic flush
```

**Book — L2 compiled knowledge (Ethics ingests; all roles read via mos_book_query):**

```text
mos_book_ingest
mos_book_ingest_batch
mos_book_lint
mos_book_query
mos_book_save_synthesis
mos_book_promote_verified
mos_book_crystallize_session
mos_book_audit_walk           # Ethics: list unresolved contradictions
mos_book_resolve_contradiction
```

**Role evolution (Agent-axis ops, gated by Ethics' `skill-audit`):**

```text
mos_role_evolve_evaluate      # produce evidence summary for split/merge/dismiss
mos_role_split                # one Expert → two with disjoint domains
mos_role_merge                # two Experts → one with union domain
mos_role_evolve_dismiss       # evidence-gated dismiss (distinct from mos_dismiss_role)
```

**Phase-transition signboard (governance):**

```text
mos_signboard_set
mos_signboard_read
mos_signboard_evaluate
mos_signboard_consume
mos_signboard_reopen
```

**Expert — experiment execution:**

```text
mos_exp_run
mos_exp_status
mos_exp_wait
mos_exp_kill
mos_exp_list
mos_exp_put
mos_exp_get
mos_exp_tail
mos_query_gpus
mos_exp_queue_submit
mos_exp_queue_plan
mos_exp_queue_reconcile
mos_exp_queue_status
mos_exp_gpu_pool_set
mos_exp_gpu_pool_get
```

**Expert — workflow-plugin discovery:**

```text
mos_list_workflow_plugins
```

**Visual format check (every EACN-visible Role):**

```text
mos_visual_render             # PDF → page_NNN.png via Poppler
mos_visual_inspect            # detectors on PDF / image / page directory
mos_visual_check              # end-to-end: render + inspect + persist report
```

**Expert — paper search and retrieval:**

```text
mos_search_arxiv
mos_search_pubmed
mos_search_biorxiv
mos_search_medrxiv
mos_search_google_scholar
mos_search_semantic
mos_search_papers_federated
mos_resolve_arxiv_ids
mos_read_arxiv_paper
mos_read_pubmed_paper
mos_read_biorxiv_paper
mos_read_medrxiv_paper
mos_download_arxiv
mos_download_pubmed
mos_download_biorxiv
mos_download_medrxiv
```

**EACN3 plugin tools** (`eacn3_*`) are advertised to role mains that are
allowed to use the bus; they are not part of the MinionsOS MCP server.

### Runtime Project Structure

```text
projects/project_{port}/
  CLAUDE.md                     # project narrative; Gru/author write, roles read
  AGENTS.md                     # subagent's view of project context
  meta.json                     # machine metadata
  parent_repo.git/              # per-project bare git repo, seeded from author HEAD
  branches/                     # one git worktree per role plus main (shared surface)
    main/                       # Gru + shared surface — branch minionsos/project-{port}
      draft/draft.json            # Ethics-curated Draft (L1 process memory)
      notes/                      # staged memory reports
      ethics/                     # Ethics published reports (flat)
      exp/exp-<id>/               # Expert experiment result bundles
      reviews/round-<n>/          # mos_review_run output (tool-owned)
      submissions/                # mos_submit deliverables
      handoffs/                   # cross-role handoffs
      governance/                 # signboard.json (phase-transition consensus)
      book/                       # Layer 2: Compiled Knowledge (Book)
        index.md                  #   Ethics-maintained catalog
        log.md                    #   Append-only ingest/lint journal (JSONL)
        sources/{role}-{slug}.md  #   One page per ingested artifact (carries reel_ref)
        contradictions/           #   Auto-detected claim conflicts (Ethics reads)
    ethics/                     # Ethics drafts
      reel-index.jsonl          # Layer 0 — pointers into native Claude session JSONL
    expert-<slug>/              # one per Expert (code, experiments, paper drafting)
      reel-index.jsonl          # Layer 0 — same pointer-index shape
  eacn3_data/eacn3.db           # per-project EACN3 SQLite database
  events/                       # per-agent EACN event JSONL audit stream
  state/                        # runtime control state (shared.lock, .reset_markers/)
  logs/
    backend.log
    role-{name}.log
```

The persistent cross-cycle memory surfaces are: **Reel** (L0,
`branches/<role>/reel-index.jsonl` → native Claude session jsonl, auto-captured),
the **Draft** (L1, `branches/main/draft/draft.json`, working coordination graph),
and the **Book** (L2, `branches/main/book/`, compiled durable knowledge — project-level
top of Memory). Roles reconstruct context at wake-up from
the Book hot cache, Book queries, Draft summary, Reel drill-down (on demand), and
project `CLAUDE.md`. There is no per-role private memory file.

### MinionsVIZ

`minions-viz/` is a read-only Observatory for all Gru installations on the
same machine. It uses `~/.minionsos/` for registry and daemon state, serves
one shared URL, and lets the UI filter by Gru and project.

```bash
./viz ensure
./viz start
./viz status
./viz open
./viz logs

./mos viz ensure
./mos viz status
```

Environment knobs:

| Variable | Purpose |
|---|---|
| `GRU_VIZ=0` | disable Gru auto-starting the dashboard |
| `GRU_VIZ_OPEN=0` | suppress browser open |
| `MINIONS_VIZ_PORT=<port>` | override the default port, normally 7891 |
| `MINIONS_VIZ_REBUILD=1` | force rebuild during `./install.sh` |
| `MINIONS_GRU_LABEL=<name>` | override this Gru's dashboard label |

MinionsVIZ never POSTs to EACN3 and never calls `/api/events/{agent_id}`,
which would drain real role event queues.

### Development

Python checks:

```bash
uv sync
uv run pytest tests/unit -q
MINIONS_FAKE_CLAUDE=1 uv run pytest tests/smoke/
uv run ruff check .
uv run ruff format --check .
```

Dashboard checks:

```bash
cd minions-viz
npm install
npm run build
npm run dev
```

Useful extension points:

- Add a Role prompt under `minions/roles/{role}/SYSTEM.md`.
- Add a Role skill under `minions/roles/{role}/skills/{lowercase-hyphen}.md`.
- Update review behavior through `minions/review/skills/`,
  `minions/review/templates/`, `minions/review/personas/`, and the
  `mos_review_run` invariant tests together.
- Add an Expert domain pack under `minions/domains/{lowercase-hyphen}.md`.
- Add an MCP tool under `minions/tools/`, register it in
  `minions/tools/mcp_server.py`, then update the whitelist and tests.

See `AGENTS.md`, root `CLAUDE.md`, and `minions/CLAUDE.md` for contributor
rules and deeper architecture notes.

### Troubleshooting

| Problem | Check |
|---|---|
| Gru behavior | `minions/state/logs/gru.log` |
| Project backend is down | `projects/project_{port}/logs/backend.log` |
| Role crashed or did not act | `projects/project_{port}/logs/role-{name}.log` |
| Project metadata looks wrong | `projects/project_{port}/meta.json` |
| EACN3 state needs inspection | `projects/project_{port}/eacn3_data/eacn3.db` |
| Experiment failed | `projects/project_{port}/branches/main/exp/exp-{id}/report.md` |
| Viz is not reachable | `./viz status` and `./viz logs` |
| Doctor fails parent-git check | initialize and commit the parent directory |

### Security and Configuration

Do not commit secrets, generated project worktrees, experiment credentials,
runtime state, logs, or local config. Cross-project communication should
remain Gru-mediated, and dashboard endpoints must remain read-only.

### License

No explicit license file is currently bundled. Treat the repository as
proprietary/internal until a license is added.

---

## 中文

**MinionsOS** 是一个本地多智能体操作系统，用于运行相互隔离、论文级规模的科研项目。
常驻的 **Gru** 负责总控；每个项目拥有独立的 **EACN3** 协调后端；常驻的
**Role** 进程在事件触发时唤醒处理任务，跨多个事件周期保持驻留。Claude Code 是
唯一的 Role 宿主。

**核心贡献是一套服务于自主科学发现的团队 Memory 机制。** 一个项目的知识沉淀在
一张结构化图谱——**Draft**——里：每个 Role 通过统一的视图（`mos_draft_view`）读取，
在工作落盘时追加节点（`mos_draft_append`；计划节点执行后被结果替换，绝不残留为僵尸）。
一个角色——**Ethics**——负责维护这张图（连跨角色的边、计算衰减、封存 dead-end），
并审查图上每条 claim 是否有真实证据。被验证的知识编译进 **Book**——即 main 分支上
论文形态的项目产出。Reel → Draft → Book 之间携带 provenance 链接，任何结论都能
回溯到产生它的执行帧。EACN3 是协调基座；Memory 图谱才是让一群冷启动智能体跨周期
积累、验证、复利知识的关键。

目标很直接：一位作者、一份 checkout、一个 Gru，同时管理多个互不串扰的研究项目。

### 目录

- [能力概览](#能力概览)
- [架构](#架构)
- [仓库结构](#仓库结构)
- [环境要求](#环境要求)
- [安装](#安装)
- [配置](#配置)
- [运行](#运行)
- [Roles](#roles-1)
- [Skill 家族与自演化](#skill-家族与自演化)
- [MCP 工具面](#mcp-工具面)
- [运行时项目结构](#运行时项目结构)
- [MinionsVIZ](#minionsviz-1)
- [开发](#开发)
- [排障入口](#排障入口)
- [安全与配置](#安全与配置)
- [许可](#许可)

### 能力概览

- **项目隔离。** 每个项目都有独立的 `projects/project_{port}/`、EACN3 后端、SQLite
  状态、独立 bare git 仓库、Role worktree、日志、产物以及事件审计流。
- **任务剖面（Mission Profile）。** 每个项目由一份 YAML 任务剖面
  (`minions/profiles/<name>.yaml`) 决定其角色阵容、产物 schema、评估策略、
  阶段调度和完成后行为。默认 `scientific-paper` 运行自主科学发现流水线：
  Gru、Ethics、Expert workers、同行评议产出、`mos_submit` / `mos_evaluate`
  和 benchmark 支持。剖面切换通过 `mos_project_create(profile=...)` 或
  CLI `--profile` 完成。
- **常驻 Role。** Gru、Ethics 和一个或多个 Expert 都是常驻 `claude`
  进程，运行在各自命名的 tmux 会话（`mos-{port}-{role}`）中。注册到 EACN
  的 Role 通过 `mos_await_events()` 驱动事件循环。Expert 是可生成的通用
  工作者（代码、实验、写作、画图、文献检索），由 Gru 按项目需求增减和调整
  Expert roster。
- **Gru 作为控制面。** Gru 是唯一人机入口，也是唯一可以创建项目、spawn Role、
  跨项目桥接的组件。
- **工具与写入边界。** Claude Role 通过 `--allowed-tools` 限制工具面；
  MinionsOS MCP server 在服务端额外执行项目生命周期工具授权。每个 Role 拥有
  自己的 `branches/<role>/`；跨角色产物始终经由 `branches/main/<subdir>/`
  通过 `mos_publish_to_shared` 流转。
- **分层记忆。** Role 上下文来自当前事件、Reel（L0，
  `branches/<role>/reel-index.jsonl` 指向原生 Claude session JSONL）、Draft（L1，唯一团队过程图，`branches/main/draft/draft.json`）、
  compiled-knowledge Book（L2，主分支论文形态产物，`branches/main/book/`）、
  `branches/main/<subdir>/` 的共享产物、EACN 事件记录以及项目 `CLAUDE.md`。
  L0 设计见 [MANUAL/domains/reel-l0-memory.md](MANUAL/domains/reel-l0-memory.md)。
- **Skill 发现和领域资产。** Role 技能放在 `minions/roles/{role}/skills/*.md`；
  Expert 领域包资产放在 `minions/domains/*.md`。
- **双轴自演化。** Ethics 审计 skill 变更提案，Gru 验证通过的变更，
  并由 Gru 根据项目轨迹演化 Expert roster。背后由 `mos_role_split`、
  `mos_role_merge`、`mos_role_evolve_evaluate`、`mos_role_evolve_dismiss`
  等 MCP 工具支持。
- **视觉格式检查。** `mos_visual_render` / `mos_visual_inspect` /
  `mos_visual_check` 把 PDF 栅格化并检测版式缺陷（栏内空洞、尾部留白、
  越界、浮动堆积等）。所有 EACN 上的 Role 都可调用，报告留存于
  `branches/<role>/visual-reports/`。
- **结构化评审。** 论文评审通过 Gru 的 `mos_review_run` MCP 工具运行。
  其提示资产（SYSTEM.md、流程 skill、reviewer persona、输出
  template）位于 `minions/review/`，单轮评审会产出 3-5 份独立 reviewer
  报告，加上 consolidated meta-review 和滚动 summary。
- **实验执行。** Expert 通过 `mos_exp_*` 工具执行实验——既包括直接原语
  （`mos_exp_run`、`mos_exp_status`、`mos_query_gpus`），也包括 Python 侧
  项目队列（`mos_exp_queue_submit`、`mos_exp_queue_plan`、
  `mos_exp_queue_reconcile`、`mos_exp_gpu_pool_set`）。
- **只读观察台。** `minions-viz/` 提供机器级单例的 MinionsVIZ 仪表盘，不消耗
  Role 事件队列，也不修改 EACN3。

### 架构

```text
作者
  |
  v
Gru
  |
  +-- project_37596/
  |     |
  |     +-- EACN3 backend on 127.0.0.1:37596
  |     |     +-- Ethics         -> branches/ethics/ + branches/main/ethics/ + book 维护
  |     |     +-- Expert (generalist, 自动生成)
  |     |     |     -> branches/expert-generalist/ + branches/main/exp/ + mos_exp_*
  |     |     +-- Expert-<domain> (按需生成)
  |     |           -> branches/expert-<slug>/ + 领域包
  |     |
  |     +-- branches/                # 每个 Role 一棵 worktree，加 main（共享表面）
  |     |     +-- main/ (Gru + 共享表面), ethics/, expert-*/
  |     +-- parent_repo.git/         # 项目独立的 bare git 仓库
  |     +-- eacn3_data/eacn3.db      # 项目独立的 EACN3 SQLite
  |     +-- events/                  # 每个 agent 的 EACN 事件 JSONL
  |     +-- state/                   # 运行时控制状态
  |     +-- logs/
  |
  +-- project_37601/
        |
        +-- 独立 backend、branches、EACN 状态、events 和日志
```

跨项目通信只有一条受控路径：Role 不能直接联系其它项目，只有 Gru 可以通过
`mos_project_bridge` 桥接。

### 仓库结构

```text
minions/
  cli.py                    # mos CLI 入口
  gru/                      # Gru 监控循环
  lifecycle/                # 项目、Role、wakeup、relay、health
  tools/                    # MCP 工具和实验执行
  state/                    # 运行状态辅助模块
  roles/                    # 共享 Role contract、提示词、skills
  review/                   # mos_review_run 使用的论文评审提示资产
  domains/                  # Expert 领域包资产
  config/*.yaml.example     # 本地配置模板

minions-viz/                # 只读 React/Vite 仪表盘
mcp-servers/                # 独立 MCP server
  eacn3/                    # 本地 editable EACN3 依赖（Python + Node 插件）
MANUAL/                     # Role agent 按需查阅的参考库（lookup.py）
tests/unit/                 # 快速单元测试
tests/smoke/                # 集成式 smoke 检查
```

`projects/`、`minions/state/`、日志、缓存等运行时
输出不会进入 git。

### 环境要求

- Python **3.11+**
- [`uv`](https://docs.astral.sh/uv/) 用于 Python 依赖管理
- `git` 2.x
- Node **16+** 和 `npm`，用于 EACN3 MCP 插件与 MinionsVIZ
- Claude CLI 位于 `PATH`

MinionsOS 会从当前 checkout 的父目录创建项目 worktree。创建项目之前，该
父目录必须是 git 仓库：

```bash
cd <MinionsOS 的父目录>
git init
git add -A
git commit -m "init"
```

`./install.sh` 会提示这个条件，`./mos doctor` 也会再次检查。如需指向其它
seed 仓库，可设置 `gru.yaml: author_repo`（或 `MINIONS_AUTHOR_REPO`）。

### 安装

```bash
git clone https://github.com/Minions-Land/MinionsOS.git
cd MinionsOS
./install.sh
./mos doctor
```

`install.sh` 可以重复执行：它会按需自举 `uv`、同步 Python 依赖、editable
安装本地 `mcp-servers/eacn3/`、构建 EACN3 MCP 插件、按需构建 MinionsVIZ、
创建启动脚本链接，并把 `minions/config/*.yaml.example` 复制为本地 `.yaml`
配置且不覆盖已有文件。

### 更新

拉取新版本而不破坏正在运行的项目：

```bash
./mos upgrade           # git pull --ff-only && 增量 ./install.sh
./mos restart --all     # 把新代码/prompt 应用到正在运行的进程
```

`mos upgrade` 只动仓库本身：先 fast-forward `git`，再跑增量 `install.sh`，
只重建发生变化的部分（Python 依赖、EACN3 插件、MinionsVIZ
—— 每一项都按其源码树的内容哈希判定，所以只改源码的提交也能正确触发重建）。
`projects/` 下的项目已被 gitignore，完全不受影响；EACN3 数据库、worktree、
Draft 都原样保留。

`upgrade` **不会**重启任何已在运行的进程。一个活跃的 Role 在启动时就冻结了它的
`SYSTEM.md`、工具白名单和 MCP 授权，Gru monitor 也只在启动时读取过一次
`gru.yaml` —— 这些都不会热重载。要把升级应用到活跃进程，需要冷重启：

```bash
./mos restart --all              # Gru monitor + 所有正在运行的 Role
./mos restart --gru              # 仅 Gru monitor / 看门狗 sidecar
./mos restart <port>             # 某个项目正在运行的 Role
./mos restart <port> --role expert  # 单个 Role
```

restart 只回收真正在运行的进程；没在运行的 Role 会留给看门狗（或
`mos project revive`）之后用新代码启动。Role 冷启动后会从 Draft（L1）重建
上下文，不丢工作。升级完成后，`mos upgrade` 会针对检测到的活跃进程打印出
对应的 restart 命令。

`mos doctor` 含一项 `config-keys-current` 检查：当升级新增了某个
`*.yaml.example` 键、而你已有的本地 `*.yaml` 没有同步到时会被标出（此时仍走
默认值 —— 手动合并该键即可调参）。

### 配置

本地配置位于 `minions/config/`，默认不进入 git：

- `gru.yaml` 控制 heartbeat、日志级别、模型/上下文配置、draft 阈值、
  web search 策略。
- `experiment_targets.yaml` 定义 Expert 使用的本地或 SSH 执行目标，路径
  支持 `{project_workspace}` 模板展开。

查看解析后的路径：

```bash
./mos config
./mos config --json
```

启动入口：

```bash
./gru                 # 启动交互式 Gru（Claude 宿主）
```

### 运行

```bash
./gru                 # 启动交互式 Gru
./mos noter <port>    # 启动某个项目的只读 observatory 终端
./mos status          # 项目仪表盘
./mos status --json   # 机器可读状态
./mos doctor          # 环境健康检查
```

`mos noter` 命令提供一个项目的只读观察终端，显示 backend、role、task 和
artifact 状态，不会消耗 EACN role 队列。

项目和 Role 管理：

```bash
./mos project list
./mos project list active
./mos project close <port>
./mos project revive <port>
./mos project repair <port>

./mos role list <port>
./mos role dismiss <port> <role>
```

日志：

```bash
./mos logs
./mos logs --project <port>
./mos logs --project <port> --role expert --tail 100
./mos logs --project <port> --role expert --follow
```

### Roles

默认的 `scientific-paper` profile 启动 **三种** 角色：

| Role | 职责 | 主要可写范围 |
|---|---|---|
| Gru | 全局主管、人机接口、项目生命周期、跨项目桥接、运行 `mos_review_run`、将 Ethics 封存的内容提升到 Book | `branches/main/`、`branches/main/<any>/` |
| Ethics | 记忆维护（Draft→Book 收录+认证）、证据/声明审计、矛盾裁决 | `branches/ethics/`（草稿）、`branches/main/ethics/`、`branches/main/book/`、`branches/main/draft/draft.json`、`branches/main/handoffs/`、`branches/main/governance/` |
| Expert (×N, 可生成) | 通用科研工作 —— 领域推理、代码+实验（`mos_exp_*`）、论文撰写（Book→Paper）。自动生成一个 generalist；Gru 按需生成领域专家。 | `branches/expert-<slug>/`、`branches/main/exp/`、`branches/main/handoffs/`、`branches/main/governance/` |

Role 提示词位于 `minions/roles/{role}/SYSTEM.md`。共享 Role contract 位于
`minions/roles/SYSTEM.md`，会在每个 role-specific 提示词前注入。Role skills
从 `minions/roles/{role}/skills/` 自动发现，并在唤醒时以 `[Skills]` 摘要块
注入。

论文评审提示资产（system 提示、skill、persona、template）
位于 `minions/review/`，单轮评审由 Gru 的 `mos_review_run` MCP 工具运行，
并在 `branches/main/reviews/round-<n>/` 下写入 `reviewer-instance.md`、
`fresh.md`、`revision_delta.md`、`consolidated.md` 和
`summaries/round-<n>.md`。Review workflow 审核提交的论文（Book→Paper
输出），Ethics 审核 Draft/Book 中的底层证据和声明。

### Skill 家族与自演化

除了人工驱动的扩展路径（新增 Role、skill、领域包、MCP 工具），MinionsOS
支持一条**4 阶段去相关流水线**，可以由项目轨迹本身驱动 Skill 库与 Expert
roster 的演化。四个组件分布在不同的权限层：

| 阶段 | 组件 | 操作者 | 输出 |
|---|---|---|---|
| 1. 提案 | Proposal ledger | Gru 根据项目轨迹记录 Skill / Expert 变更提案 | `branches/main/notes/skill-proposals.md` —— append-only 提案 ledger |
| 2. 审计 | `minions/roles/ethics/skills/skill-audit.md` | Ethics | `branches/main/ethics/` 下的审计裁决 |
| 3. 验证 + 入库 | `minions/roles/common/skills/skill-forge/SKILL.md` procedure | Gru 把通过审计的提案路由到此 | 验证通过的 Role skill 进入 `minions/roles/*/skills/` |
| 4. 落地 Expert roster | `mos_role_split`、`mos_role_merge`、`mos_role_evolve_evaluate`、`mos_role_evolve_dismiss`、`mos_spawn_expert`、`mos_dismiss_role` | Gru | EACN 上 Expert roster 更新 |

去相关性是结构性的，不是流程上的：提案、Ethics 审计、Gru 验证和消费
Role 保持分离。

### MCP 工具面

MinionsOS MCP server 从 `minions/tools/mcp_server.py` 暴露生命周期和执行
工具。所有工具均带 `mos_` 前缀。

**仅 Gru 可用——项目生命周期：**

```text
mos_project_create
mos_project_close
mos_project_dormant
mos_project_revive
mos_project_kill
mos_project_list
mos_project_set_phase
mos_project_checkpoint_workspace
mos_project_bridge
mos_start_monitor
mos_review_run
```

**仅 Gru 可用——Role 生命周期：**

```text
mos_spawn_role
mos_spawn_expert
mos_attach_role
mos_dismiss_role
mos_kill_role
mos_list_roles
```

**Role 事件循环与上下文：**

```text
mos_await_events           # 注册到 EACN 的 Role（Ethics、Expert）
mos_get_events
mos_unread_summary
mos_compact_context
mos_reset_context
mos_issue_report
```

**跨角色发布：**

```text
mos_publish_to_shared
```

**Reel —— L0 verbatim 转录（自动捕获，Role 只读）：**

```text
mos_reel_get
mos_reel_window
```

**Draft —— L1 进程记忆（Ethics 主写、所有 Role 可读）：**

```text
mos_draft_append
mos_draft_view                # 统一读取：定向头部 + 过滤后的节点/边切片
mos_draft_annotate
mos_draft_path
mos_draft_decay_compute       # 半衰期 confidence 衰减
mos_draft_commit_shared       # Ethics 周期性 flush
```

**Book —— L2 编译知识（Ethics 写；所有 Role 通过 mos_book_query 读）：**

```text
mos_book_ingest
mos_book_ingest_batch
mos_book_lint
mos_book_query
mos_book_save_synthesis
mos_book_promote_verified
mos_book_crystallize_session
mos_book_audit_walk           # Ethics：列出未解决的矛盾
mos_book_resolve_contradiction
```

**Role 演化（Agent 轴操作，由 Ethics 的 `skill-audit` 闸门授权）：**

```text
mos_role_evolve_evaluate      # 为 split/merge/dismiss 产出证据汇总
mos_role_split                # 一个 Expert → 两个、领域不重叠
mos_role_merge                # 两个 Expert → 一个、合并领域
mos_role_evolve_dismiss       # 证据闸控的 dismiss（区别于 mos_dismiss_role）
```

**阶段切换 signboard（治理）：**

```text
mos_signboard_set
mos_signboard_read
mos_signboard_evaluate
mos_signboard_consume
mos_signboard_reopen
```

**Expert 实验执行：**

```text
mos_exp_run
mos_exp_status
mos_exp_wait
mos_exp_kill
mos_exp_list
mos_exp_put
mos_exp_get
mos_exp_tail
mos_query_gpus
mos_exp_queue_submit
mos_exp_queue_plan
mos_exp_queue_reconcile
mos_exp_queue_status
mos_exp_gpu_pool_set
mos_exp_gpu_pool_get
```

**Expert——workflow-plugin 发现：**

```text
mos_list_workflow_plugins
```

**视觉格式检查（所有 EACN 上的 Role 可用）：**

```text
mos_visual_render             # PDF → page_NNN.png（Poppler）
mos_visual_inspect            # 在 PDF / 单图 / 页面目录上跑检测器
mos_visual_check              # 端到端：渲染 + 检测 + 持久化报告
```

**Expert——论文检索与下载：**

```text
mos_search_arxiv
mos_search_pubmed
mos_search_biorxiv
mos_search_medrxiv
mos_search_google_scholar
mos_search_semantic
mos_search_papers_federated
mos_resolve_arxiv_ids
mos_read_arxiv_paper
mos_read_pubmed_paper
mos_read_biorxiv_paper
mos_read_medrxiv_paper
mos_download_arxiv
mos_download_pubmed
mos_download_biorxiv
mos_download_medrxiv
```

**EACN3 插件工具**（`eacn3_*`）由 EACN3 MCP 插件提供给被允许使用总线的
Role main，不属于 MinionsOS MCP server。

### 运行时项目结构

```text
projects/project_{port}/
  CLAUDE.md                     # 项目叙事；Gru/作者写，Roles 读
  AGENTS.md                     # 子代理眼中的项目上下文
  meta.json                     # 机器元数据
  parent_repo.git/              # 项目独立的 bare git 仓库，从作者 HEAD seed
  branches/                     # 每个 Role 一棵 worktree，加 main（共享表面）
    main/                       # Gru + 共享表面 — minionsos/project-{port}
      draft/draft.json            # Ethics 维护的 Draft（L1 进程记忆）
      notes/                      # 已发布记忆报告
      ethics/                     # Ethics 已发布报告（flat）
      exp/exp-<id>/               # Expert 实验结果包
      reviews/round-<n>/          # mos_review_run 输出（工具独占）
      submissions/                # mos_submit 交付物
      handoffs/                   # 跨角色交接
      governance/signboard.json   # 阶段切换共识
      book/                       # Layer 2：编译知识（Book）
        index.md                  #   Ethics 维护的目录
        log.md                    #   ingest/lint append-only 日志
        sources/{role}-{slug}.md  #   每个被收录工件一个页面
        contradictions/           #   自动检测的论断冲突
    ethics/                     # Ethics 草稿
      reel-index.jsonl          # Layer 0 — 指向原生 Claude session JSONL
    expert-<slug>/              # 每个 Expert 一棵（代码、实验、论文撰写）
      reel-index.jsonl          # Layer 0 — 同样的指针索引结构
  eacn3_data/eacn3.db           # 项目独立的 EACN3 SQLite 数据库
  events/                       # 每 agent 的 EACN 事件 JSONL 审计流
  state/                        # 运行时控制状态（shared.lock、.reset_markers/）
  logs/
    backend.log
    role-{name}.log
```

跨周期持久化记忆共分三层（单项目可用）：
**Reel**（L0，`branches/<role>/reel-index.jsonl` → 原生 Claude session jsonl，hook 自动抓取）、
**Draft**（L1，`branches/main/draft/draft.json`，工作协调图）、
**Book**（L2，`branches/main/book/`，编译后稳定知识，项目级 Memory 顶层）。
Role 不维护任何 per-role 私有记忆文件；唤醒时依次读取 Book hot cache → Book query → Draft summary → Reel（按需钻入）以及项目 `CLAUDE.md`。

### MinionsVIZ

`minions-viz/` 是同一机器上所有 Gru checkout 共享的只读观察台。它用
`~/.minionsos/` 存储注册表和守护进程状态，提供一个共享 URL，并在 UI 中
按 Gru 和 Project 筛选。

```bash
./viz ensure
./viz start
./viz status
./viz open
./viz logs

./mos viz ensure
./mos viz status
```

环境变量：

| 变量 | 作用 |
|---|---|
| `GRU_VIZ=0` | 禁用 Gru 自动启动仪表盘 |
| `GRU_VIZ_OPEN=0` | 不自动打开浏览器 |
| `MINIONS_VIZ_PORT=<port>` | 覆盖默认端口，通常是 7891 |
| `MINIONS_VIZ_REBUILD=1` | 在 `./install.sh` 中强制重建 |
| `MINIONS_GRU_LABEL=<name>` | 覆盖当前 Gru 在仪表盘中的显示名 |

MinionsVIZ 不会向 EACN3 发送 POST，也不会调用 `/api/events/{agent_id}`，
避免消耗真实 Role 的事件队列。

### 开发

Python 检查：

```bash
uv sync
uv run pytest tests/unit -q
MINIONS_FAKE_CLAUDE=1 uv run pytest tests/smoke/
uv run ruff check .
uv run ruff format --check .
```

仪表盘检查：

```bash
cd minions-viz
npm install
npm run build
npm run dev
```

常见扩展点：

- 新 Role：添加 `minions/roles/{role}/SYSTEM.md`。
- 新 Role skill：添加 `minions/roles/{role}/skills/{lowercase-hyphen}.md`。
- 评审输出行为变更：同时更新 `minions/review/skills/`、
  `minions/review/templates/`、`minions/review/personas/` 与
  `mos_review_run` 不变量测试。
- 新 Expert 领域包：添加 `minions/domains/{lowercase-hyphen}.md`。
- 新 MCP 工具：在 `minions/tools/` 实现，注册到
  `minions/tools/mcp_server.py`，并更新白名单与测试。

贡献规则和更深入的架构说明见 `AGENTS.md`、根目录 `CLAUDE.md` 和
`minions/CLAUDE.md`。

### 排障入口

| 问题 | 查看 |
|---|---|
| Gru 行为异常 | `minions/state/logs/gru.log` |
| 项目后端未启动 | `project_{port}/logs/backend.log` |
| Role 崩溃或未行动 | `project_{port}/logs/role-{name}.log` |
| 项目元数据异常 | `project_{port}/meta.json` |
| 需要检查 EACN3 状态 | `project_{port}/eacn3_data/eacn3.db` |
| 实验失败 | `project_{port}/branches/main/exp/exp-{id}/report.md` |
| Viz 无法访问 | `./viz status` 和 `./viz logs` |
| doctor 父目录 git 检查失败 | 初始化并提交父目录 git 仓库 |

### 安全与配置

不要提交 secrets、生成的项目 worktree、实验凭据、运行时状态、日志或本地
配置。跨项目通信应继续由 Gru 桥接管控，dashboard 端点必须保持只读。

### 许可

当前仓库未附带显式 LICENSE 文件；在补充许可证前请按内部/专有代码处理。
