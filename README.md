# MinionsOS

[English](#english) | [中文](#中文)

---

## English

**MinionsOS** is a local multi-agent operating system for running isolated,
paper-sized research projects. A persistent **Gru** supervisor manages projects,
each project owns its own **EACN3** coordination backend, and event-driven
agent-host **Roles** wake up only when there is work to process. Claude Code
remains the default host; Codex is supported as an opt-in host through the same
MinionsOS lifecycle and EACN3 bus.

The design goal is simple: one author, one checkout, one Gru, many isolated
research projects.

### What You Get

- **Project isolation.** Every project has its own `project_{port}/` directory,
  EACN3 backend, SQLite state, git worktree, logs, artifacts, and role memory.
- **Long-lived Roles.** Noter, Coder, Experimenter, Writer, Ethics, and Expert
  run as resident `claude` processes inside named tmux sessions
  (`mos-{port}-{role}`). Each Role drives its own event loop via
  `mos_await_events()`.
- **Gru as the control plane.** Gru is the human-facing supervisor and the only
  component allowed to create projects, spawn roles, and relay across projects.
- **Tool and write boundaries.** Claude roles still receive `--allowed-tools`;
  MinionsOS also enforces project-lifecycle tool permissions inside its MCP
  server so Codex roles keep the same role boundaries. Each Role owns
  `branches/<role>/`; cross-role artefacts always travel through
  `branches/shared/<subdir>/` via `mos_publish_to_shared`.
- **Layered memory.** Role context is reconstructed from the current invocation,
  the Exploration DAG (`branches/shared/exploration/dag.json`), shared
  artefacts under `branches/shared/<subdir>/`, EACN history, and project
  `CLAUDE.md`.
- **Skill discovery and domain assets.** Role skills live in
  `minions/roles/{role}/skills/*.md`; Expert domain-pack assets live in
  `minions/domains/*.md`.
- **Structured review.** Paper review runs through Gru's `mos_review_run` MCP
  tool, not through a long-lived Role. Its prompt assets (SYSTEM.md, procedural
  skills, reviewer personas, output templates) live under `minions/review/`,
  and a round produces 3-5 independent reviewer-instance reports plus a
  consolidated meta-review and rolling summary.
- **Experiment execution.** Experimenter can submit work to a Python-side
  project queue with `mos_exp_queue_submit`, keep GPUs filled via
  `mos_exp_queue_reconcile`, change the dynamic GPU allow-list with
  `mos_exp_gpu_pool_set`, and still use direct `mos_exp_run` / `mos_exp_status` /
  `mos_query_gpus` primitives for one-off debugging.
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
  |     |     +-- Noter          -> branches/noter/   + branches/shared/notes/, exploration/
  |     |     +-- Coder          -> branches/coder/
  |     |     +-- Experimenter   -> branches/experimenter/ + branches/shared/exp/ + exp_* tools
  |     |     +-- Writer         -> branches/writer/
  |     |     +-- Ethics         -> branches/ethics/  + branches/shared/ethics/
  |     |     +-- Expert-*       -> branches/expert-<slug>/ + domain pack
  |     |
  |     +-- branches/                # one git worktree per role plus shared
  |     |     +-- main/, noter/, coder/, experimenter/, writer/, ethics/, expert-*/, shared/
  |     +-- eacn3_data/eacn3.db      # project-local EACN3 SQLite
  |     +-- events/                  # per-agent EACN event JSONL
  |     +-- state/                   # runtime control state
  |     +-- logs/
  |
  +-- project_37601/
        |
        +-- separate backend, branches, EACN state, events, and logs
```

Cross-project communication is intentionally narrow: roles cannot talk to other
projects directly. Gru can bridge projects through the Gru-only relay path.

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
EACN3/                      # local editable EACN3 dependency
tests/unit/                 # fast behavior tests
tests/smoke/                # integration-style smoke checks
```

Generated runtime output such as `project_{port}/`, `minions/state/`, logs,
caches, and `graphify-out/` should not be committed.

### Prerequisites

- Python **3.11+**
- [`uv`](https://docs.astral.sh/uv/) for Python dependency management
- `git` 2.x
- Node **16+** and `npm` for the EACN3 MCP plugin and MinionsVIZ
- Claude CLI on `PATH` for the default host, or Codex CLI on `PATH` when
  `agent_host: codex` / `MINIONS_AGENT_HOST=codex` is used

MinionsOS creates project worktrees from the directory that contains this
checkout. That parent directory must be a git repository before you create
projects:

```bash
cd <parent-of-MinionsOS>
git init
git add -A
git commit -m "init"
```

`./install.sh` warns about this condition, and `./mos doctor` checks it again.

### Install

```bash
git clone https://github.com/Minions-Land/MinionsOS.git
cd MinionsOS
./install.sh
./mos doctor
```

`install.sh` is idempotent. It bootstraps `uv` when needed, syncs Python
dependencies, installs the local editable `EACN3/` package, builds the EACN3 MCP
plugin, builds MinionsVIZ when needed, creates launcher symlinks, and copies
`minions/config/*.yaml.example` to local `.yaml` files without overwriting
existing config. It also ensures `.codex/config.toml` exists for Codex MCP
mounts.

### Configure

Local configuration lives under `minions/config/` and is intentionally ignored by
git:

- `gru.yaml` controls heartbeat cadence, logging, model/context settings,
  scratchpad thresholds, web-search policy, and the active agent host
  (`agent_host: claude` or `agent_host: codex`).
- `experiment_targets.yaml` defines local and SSH execution targets for
  Experimenter. Paths may use `{project_workspace}` template expansion.

Inspect resolved paths with:

```bash
./mos config
./mos config --json
```

Agent host selection:

```bash
./gru                              # default: Claude Code
MINIONS_AGENT_HOST=codex ./gru     # one-shot Codex override
```

or set in `minions/config/gru.yaml`:

```yaml
agent_host: claude
# Codex-only options (apply when agent_host: codex):
codex_model:        # optional; leave empty to use Codex CLI defaults
codex_reasoning_effort: xhigh
codex_bypass_approvals_and_sandbox: true
codex_sandbox: danger-full-access
codex_approval_policy: never
```

Claude compatibility is intentionally preserved: `CLAUDE.md` remains the shared
project context file, and new projects also get a small `AGENTS.md` shim so Codex
users can discover the same context.

### Run

```bash
./gru                 # launch interactive Gru
./noter <port>        # launch read-only Noter terminal for one project
./mos status          # project dashboard
./mos status --json   # machine-readable project status
./mos doctor          # environment health checks
```

Typical operator layout is one Gru terminal plus one Noter terminal per active
project:

```bash
./gru
./noter 37596
./noter 37601
```

The Noter terminal reports backend, role, task, and notes state without draining
EACN role queues. Type `wake <message>` inside it to queue an on-demand Noter
summary request through the project's EACN bus.

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
./mos logs --project <port> --role coder --tail 100
./mos logs --project <port> --role coder --follow
```

### Roles

| Role | Responsibility | Primary write scope |
|---|---|---|
| Gru | Global supervisor, human interface, project lifecycle, cross-project relay | `branches/main/`, `branches/shared/<any>/` |
| Noter | Timeline, checkpoints, summaries, Exploration DAG curation | `branches/noter/`, `branches/shared/notes/`, `branches/shared/exploration/dag.json` |
| Coder | Code maintenance, debugging, implementation | `branches/coder/`, `branches/shared/handoffs/` |
| Experimenter | Job dispatch, remote execution, result collection | `branches/experimenter/`, `branches/shared/exp/`, `branches/shared/handoffs/` |
| Writer | Paper drafting, packaging, rebuttal, camera-ready work | `branches/writer/`, `branches/shared/handoffs/` |
| Ethics | Evidence audit, unsupported-claim detection | `branches/ethics/`, `branches/shared/ethics/`, `branches/shared/handoffs/` |
| Expert | Domain consultation with optional packs such as `nlp`, `cv`, `theory` | `branches/expert-<slug>/` (read-mostly), `branches/shared/handoffs/` |

Role prompts are stored at `minions/roles/{role}/SYSTEM.md`.

The shared Role contract at `minions/roles/SYSTEM.md` is injected before each
role-specific prompt. Skills are discovered from `minions/roles/{role}/skills/`
at wake-up and injected as a `[Skills]` summary block.

Paper review is not a Role: review prompt assets (system prompt, skills,
personas, templates) live under `minions/review/`, and a round is run by
Gru's `mos_review_run` MCP tool which writes `reviewer-instance.md`,
`fresh.md`, `revision_delta.md`, `consolidated.md`, and
`summaries/round-<n>.md` under `branches/shared/reviews/round-<n>/`.

### MCP Surface

The MinionsOS MCP server exposes lifecycle and execution tools from
`minions/tools/`.

Gru-only tools:

```text
project_create
project_close
project_dormant
project_revive
project_list
spawn_role
spawn_expert
dismiss_role
list_roles
project_bridge
gru_start_monitor
review_run
```

Experimenter tools:

```text
exp_run
exp_status
exp_wait
exp_kill
exp_list
exp_put
exp_get
exp_tail
query_gpus
exp_queue_submit
exp_queue_reconcile
exp_queue_status
exp_gpu_pool_set
exp_gpu_pool_get
```

Writer paper-search tools:

```text
search_arxiv
search_pubmed
search_biorxiv
search_medrxiv
search_google_scholar
read_arxiv_paper
read_pubmed_paper
read_biorxiv_paper
read_medrxiv_paper
download_arxiv
download_pubmed
download_biorxiv
download_medrxiv
```

EACN3 tools are provided by the EACN3 MCP plugin as `eacn3_*` and are available
only to role mains that are allowed to use the bus.
For Codex, `.codex/config.toml` starts a MinionsOS-side MCP proxy that filters
the advertised EACN3 tool list before Codex sees it; the EACN3 plugin and
network remain unmodified.

### Runtime Project Structure

```text
project_{port}/
  CLAUDE.md                     # project narrative; Gru/author write, roles read
  AGENTS.md                     # Codex-friendly pointer to the same project context
  meta.json                     # machine metadata
  branches/                     # one git worktree per role plus shared
    main/                       # Gru — branch minionsos/project-{port}
    noter/                      # Noter drafts
    coder/, experimenter/, writer/, ethics/, expert-<slug>/
    shared/                     # branch minionsos/project-{port}-shared
      exploration/dag.json      # Noter-curated Exploration DAG
      notes/                    # Noter staged reports
      ethics/                   # Ethics published reports
      exp/exp-<id>/             # Experimenter result bundles
      reviews/round-<n>/        # mos_review_run output (tool-owned)
      handoffs/                 # cross-role handoffs (incl. external feedback)
  eacn3_data/eacn3.db           # per-project EACN3 SQLite database
  events/                       # per-agent EACN event JSONL audit stream
  state/                        # runtime control state (shared.lock, .reset_markers/)
  logs/
    backend.log
    role-{name}.log
```

The only persistent cross-cycle role memory is the Exploration DAG at
`branches/shared/exploration/dag.json`. Roles do not keep per-role scratchpad
files; they reconstruct context at wake-up from the current transcript, the
DAG, EACN history, shared artefacts, and project `CLAUDE.md`.

### MinionsVIZ

`minions-viz/` is a read-only Observatory for all Gru installations on the same
machine. It uses `~/.minionsos/` for registry and daemon state, serves one shared
URL, and lets the UI filter by Gru and project.

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

MinionsVIZ never POSTs to EACN3 and never calls `/api/events/{agent_id}`, which
would drain real role event queues.

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

- Add a role prompt under `minions/roles/{role}/SYSTEM.md`.
- Add a role skill under `minions/roles/{role}/skills/{lowercase-hyphen}.md`.
- Update review behavior through `minions/review/skills/`,
  `minions/review/templates/`, `minions/review/personas/`, and the
  `mos_review_run` invariant tests together.
- Add an Expert domain pack under `minions/domains/{lowercase-hyphen}.md`.
- Add MCP tools under `minions/tools/`, then update whitelists and tests.

See `AGENTS.md`, root `CLAUDE.md`, and `minions/CLAUDE.md` for contributor
rules and deeper architecture notes.

### Troubleshooting

| Problem | Check |
|---|---|
| Gru behavior | `minions/state/logs/gru.log` |
| Project backend is down | `project_{port}/logs/backend.log` |
| Role crashed or did not act | `project_{port}/logs/role-{name}.log` |
| Project metadata looks wrong | `project_{port}/meta.json` |
| EACN3 state needs inspection | `project_{port}/eacn3_data/eacn3.db` |
| Experiment failed | `project_{port}/branches/shared/exp/exp-{id}/report.md` |
| Viz is not reachable | `./viz status` and `./viz logs` |
| Doctor fails parent git check | initialize and commit the parent directory |

### Security and Configuration

Do not commit secrets, generated project worktrees, experiment credentials,
runtime state, logs, or local config. Cross-project communication should remain
Gru-mediated, and dashboard endpoints must remain read-only.

### License

No explicit license file is currently bundled. Treat the repository as
proprietary/internal until a license is added.

---

## 中文

**MinionsOS** 是一个本地多智能体操作系统，用于运行相互隔离的论文级科研项目。常驻的
**Gru** 负责总控；每个项目拥有独立的 **EACN3** 协调后端；Role
由事件触发，短时唤醒、处理任务、完成后退出。Claude Code 是默认
agent host，Codex 可通过同一套 MinionsOS 生命周期和 EACN3 bus 显式启用。

目标很直接：一位作者、一份 checkout、一个 Gru，同时管理多个互不串扰的研究项目。

### 能力概览

- **项目隔离。** 每个项目都有独立的 `project_{port}/`、EACN3 后端、SQLite
  状态、git worktree、日志、产物和 Role 记忆。
- **常驻 Role。** Noter、Coder、Experimenter、Writer、Ethics 和 Expert
  都以常驻 `claude` 进程运行在各自命名的 tmux 会话
  （`mos-{port}-{role}`）中，靠 `mos_await_events()` 驱动自己的事件循环。
- **Gru 作为控制面。** Gru 是唯一人机入口，也是唯一可创建项目、spawn Role、跨项目
  relay 的组件。
- **工具和写入边界。** Claude Role 继续通过 `--allowed-tools` 限制工具面；
  MinionsOS MCP server 也会在服务端执行项目生命周期工具授权，因此 Codex Role
  具有同样边界。每个 Role 拥有自己的 `branches/<role>/`；跨角色产物始终经由
  `branches/shared/<subdir>/` 通过 `mos_publish_to_shared` 流转。
- **分层记忆。** Role 上下文来自当前事件、Exploration DAG
  （`branches/shared/exploration/dag.json`）、`branches/shared/<subdir>/` 的
  共享产物、EACN 历史以及项目 `CLAUDE.md`。
- **Skill 发现和领域资产。** Role 技能放在 `minions/roles/{role}/skills/*.md`；
  Expert 领域包资产放在 `minions/domains/*.md`。
- **结构化评审。** 论文评审通过 Gru 的 `mos_review_run` MCP 工具运行，而不是
  常驻 Role。其提示资产（SYSTEM.md、流程 skill、reviewer persona、输出
  template）位于 `minions/review/`，单轮评审会产出 3-5 份独立 reviewer
  报告，加上 consolidated meta-review 和滚动 summary。
- **实验执行。** Experimenter 可通过 Python 侧项目队列
  `mos_exp_queue_submit` / `mos_exp_queue_reconcile` 填满 GPU，通过
  `mos_exp_gpu_pool_set` 动态调整可用 GPU 集合，并保留 `mos_exp_run` /
  `mos_exp_status` / `mos_query_gpus` 等直接调试原语。
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
  |     |     +-- Noter          -> branches/noter/   + branches/shared/notes/, exploration/
  |     |     +-- Coder          -> branches/coder/
  |     |     +-- Experimenter   -> branches/experimenter/ + branches/shared/exp/ + exp_* tools
  |     |     +-- Writer         -> branches/writer/
  |     |     +-- Ethics         -> branches/ethics/  + branches/shared/ethics/
  |     |     +-- Expert-*       -> branches/expert-<slug>/ + 领域包
  |     |
  |     +-- branches/                # 每个 Role 一棵 worktree，加一棵 shared
  |     |     +-- main/, noter/, coder/, experimenter/, writer/, ethics/, expert-*/, shared/
  |     +-- eacn3_data/eacn3.db      # 项目独立的 EACN3 SQLite
  |     +-- events/                  # 每个 agent 的 EACN 事件 JSONL
  |     +-- state/                   # 运行时控制状态
  |     +-- logs/
  |
  +-- project_37601/
        |
        +-- 独立 backend、branches、EACN 状态、events 和日志
```

跨项目通信只有一条受控路径：Role 不能直接联系其它项目，只有 Gru 可以通过 relay
桥接项目。

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
EACN3/                      # 本地 editable EACN3 依赖
tests/unit/                 # 快速单元测试
tests/smoke/                # 集成式 smoke 检查
```

`project_{port}/`、`minions/state/`、日志、缓存、`graphify-out/` 等运行时输出不应提交。

### 环境要求

- Python **3.11+**
- [`uv`](https://docs.astral.sh/uv/) 用于 Python 依赖管理
- `git` 2.x
- Node **16+** 和 `npm`，用于 EACN3 MCP 插件与 MinionsVIZ
- 默认 host 需要 Claude CLI 位于 `PATH`；当使用 `agent_host: codex` 或
  `MINIONS_AGENT_HOST=codex` 时需要 Codex CLI 位于 `PATH`

MinionsOS 会从当前 checkout 的父目录创建项目 worktree。创建项目之前，该父目录必须是
git 仓库：

```bash
cd <MinionsOS 的父目录>
git init
git add -A
git commit -m "init"
```

`./install.sh` 会提示这个条件，`./mos doctor` 也会再次检查。

### 安装

```bash
git clone https://github.com/Minions-Land/MinionsOS.git
cd MinionsOS
./install.sh
./mos doctor
```

`install.sh` 可以重复执行：它会按需自举 `uv`、同步 Python 依赖、editable 安装本地
`EACN3/`、构建 EACN3 MCP 插件、按需构建 MinionsVIZ、创建启动脚本链接，并把
`minions/config/*.yaml.example` 复制为本地 `.yaml` 配置且不覆盖已有文件。它也会确保
Codex 使用的 `.codex/config.toml` 存在。

### 配置

本地配置位于 `minions/config/`，默认不进入 git：

- `gru.yaml` 控制 heartbeat、日志级别、模型/上下文配置、scratchpad 阈值、web search
  策略，以及当前 agent host（`agent_host: claude` 或 `agent_host: codex`）。
- `experiment_targets.yaml` 定义 Experimenter 使用的本地或 SSH 执行目标，路径支持
  `{project_workspace}` 模板展开。

查看解析后的路径：

```bash
./mos config
./mos config --json
```

Agent host 选择：

```bash
./gru                              # 默认 Claude Code
MINIONS_AGENT_HOST=codex ./gru     # 单次使用 Codex
```

也可以写入 `minions/config/gru.yaml`：

```yaml
agent_host: claude
# 仅当 agent_host: codex 时生效的 Codex 选项：
codex_model:        # 可选；留空则使用 Codex CLI 默认值
codex_reasoning_effort: xhigh
codex_bypass_approvals_and_sandbox: true
codex_sandbox: danger-full-access
codex_approval_policy: never
```

为了保持 Claude 兼容性，`CLAUDE.md` 仍是共享项目上下文文件；新项目还会生成一个轻量
`AGENTS.md`，方便 Codex 用户发现同一份上下文。

### 运行

```bash
./gru                 # 启动交互式 Gru
./noter <port>        # 启动某个项目的只读 Noter 终端
./mos status          # 项目仪表盘
./mos status --json   # 机器可读状态
./mos doctor          # 环境健康检查
```

推荐的操作布局是一个 Gru 终端，加上每个活跃项目一个 Noter 终端：

```bash
./gru
./noter 37596
./noter 37601
```

Noter 终端只报告 backend、role、task 和 notes 状态，不会消费 EACN role 队列。
在 Noter 终端输入 `wake <message>` 会通过该项目的 EACN bus 排队一次按需 Noter
摘要请求。

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
./mos logs --project <port> --role coder --tail 100
./mos logs --project <port> --role coder --follow
```

### Roles

| Role | 职责 | 主要可写范围 |
|---|---|---|
| Gru | 全局主管、人机接口、项目生命周期、跨项目 relay | `branches/main/`、`branches/shared/<any>/` |
| Noter | 时间线、checkpoint、总结、Exploration DAG 维护 | `branches/noter/`、`branches/shared/notes/`、`branches/shared/exploration/dag.json` |
| Coder | 代码维护、调试、实现 | `branches/coder/`、`branches/shared/handoffs/` |
| Experimenter | 任务调度、远端执行、结果收集 | `branches/experimenter/`、`branches/shared/exp/`、`branches/shared/handoffs/` |
| Writer | 论文撰写、打包、rebuttal、camera-ready | `branches/writer/`、`branches/shared/handoffs/` |
| Ethics | 证据审计、无依据论断检测 | `branches/ethics/`、`branches/shared/ethics/`、`branches/shared/handoffs/` |
| Expert | 结合 `nlp`、`cv`、`theory` 等领域包提供咨询 | `branches/expert-<slug>/`（以读为主）、`branches/shared/handoffs/` |

Role 提示词位于 `minions/roles/{role}/SYSTEM.md`。

共享 Role contract 位于 `minions/roles/SYSTEM.md`，会在每个 role-specific
提示词前注入。Role skills 从 `minions/roles/{role}/skills/` 自动发现，并在唤醒时以
`[Skills]` 摘要块注入。

论文评审不是 Role：评审提示资产（system 提示、skill、persona、template）
位于 `minions/review/`，单轮评审由 Gru 的 `mos_review_run` MCP 工具运行，
并在 `branches/shared/reviews/round-<n>/` 下写入 `reviewer-instance.md`、`fresh.md`、
`revision_delta.md`、`consolidated.md` 和 `summaries/round-<n>.md`。

### MCP 工具面

MinionsOS MCP server 从 `minions/tools/` 暴露生命周期和执行工具。

仅 Gru 可用：

```text
project_create
project_close
project_dormant
project_revive
project_list
spawn_role
spawn_expert
dismiss_role
list_roles
project_bridge
gru_start_monitor
review_run
```

Experimenter 可用：

```text
exp_run
exp_status
exp_wait
exp_kill
exp_list
exp_put
exp_get
exp_tail
query_gpus
exp_queue_submit
exp_queue_reconcile
exp_queue_status
exp_gpu_pool_set
exp_gpu_pool_get
```

Writer 论文检索工具：

```text
search_arxiv
search_pubmed
search_biorxiv
search_medrxiv
search_google_scholar
read_arxiv_paper
read_pubmed_paper
read_biorxiv_paper
read_medrxiv_paper
download_arxiv
download_pubmed
download_biorxiv
download_medrxiv
```

EACN3 MCP 插件提供 `eacn3_*` 工具，只分配给允许访问总线的 role main。
Codex 会通过 `.codex/config.toml` 启动 MinionsOS 侧 MCP proxy，在 Codex 看到
工具列表之前过滤 EACN3 工具；EACN3 插件和网络本身不做修改。

### 运行时项目结构

```text
project_{port}/
  CLAUDE.md                     # 项目叙事；Gru/作者写，Roles 读
  AGENTS.md                     # 指向同一项目上下文的 Codex 入口
  meta.json                     # 机器元数据
  branches/                     # 每个 Role 一棵 worktree，加一棵 shared
    main/                       # Gru — minionsos/project-{port}
    noter/                      # Noter 草稿
    coder/, experimenter/, writer/, ethics/, expert-<slug>/
    shared/                     # minionsos/project-{port}-shared 分支
      exploration/dag.json      # Noter 维护的 Exploration DAG
      notes/                    # Noter 已发布报告
      ethics/                   # Ethics 已发布报告
      exp/exp-<id>/             # Experimenter 结果包
      reviews/round-<n>/        # mos_review_run 输出（工具独占）
      handoffs/                 # 跨角色交接（含 external feedback）
  eacn3_data/eacn3.db           # 项目独立的 EACN3 SQLite 数据库
  events/                       # 每 agent 的 EACN 事件 JSONL 审计流
  state/                        # 运行时控制状态（shared.lock、.reset_markers/）
  logs/
    backend.log
    role-{name}.log
```

Role 唯一持久化的跨周期记忆是 `branches/shared/exploration/dag.json` 中的
Exploration DAG。Role 不维护任何 per-role scratchpad 文件；唤醒时它们从当前
transcript、DAG、EACN 历史、共享产物以及项目 `CLAUDE.md` 重建上下文。

### MinionsVIZ

`minions-viz/` 是同一机器上所有 Gru checkout 共享的只读观察台。它用
`~/.minionsos/` 存储注册表和守护进程状态，提供一个共享 URL，并在 UI 中按 Gru 和
Project 筛选。

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

MinionsVIZ 不会向 EACN3 发送 POST，也不会调用 `/api/events/{agent_id}`，避免消耗真实
Role 的事件队列。

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
- 新 MCP 工具：在 `minions/tools/` 中实现，并更新白名单与测试。

贡献规则和更深入的架构说明见 `AGENTS.md`、根目录 `CLAUDE.md` 和 `minions/CLAUDE.md`。

### 排障入口

| 问题 | 查看 |
|---|---|
| Gru 行为异常 | `minions/state/logs/gru.log` |
| 项目后端未启动 | `project_{port}/logs/backend.log` |
| Role 崩溃或未行动 | `project_{port}/logs/role-{name}.log` |
| 项目元数据异常 | `project_{port}/meta.json` |
| 需要检查 EACN3 状态 | `project_{port}/eacn3_data/eacn3.db` |
| 实验失败 | `project_{port}/branches/shared/exp/exp-{id}/report.md` |
| Viz 无法访问 | `./viz status` 和 `./viz logs` |
| doctor 父目录 git 检查失败 | 初始化并提交父目录 git 仓库 |

### 安全与配置

不要提交 secrets、生成的项目 worktree、实验凭据、运行时状态、日志或本地配置。跨项目通信
应继续由 Gru relay 管控，dashboard 端点必须保持只读。

### 许可

当前仓库未附带显式 LICENSE 文件；在补充许可证前请按内部/专有代码处理。
