# MinionsOS V3

[English](#english) | [中文](#中文)

---

## English

**MinionsOS V3** is a local multi-agent operating system for running isolated,
paper-sized research projects. A persistent **Gru** supervisor manages projects,
each project owns its own **EACN3** coordination backend, and event-driven
Claude **Roles** wake up only when there is work to process.

The design goal is simple: one author, one checkout, one Gru, many isolated
research projects.

### What You Get

- **Project isolation.** Every project has its own `project_{port}/` directory,
  EACN3 backend, SQLite state, git worktree, logs, artifacts, and role memory.
- **Event-driven Roles.** Noter, Coder, Experimenter, Writer, Reviewer, Ethics,
  and Expert are short-lived Claude subprocesses launched by the Python
  `WakeupScheduler`.
- **Gru as the control plane.** Gru is the human-facing supervisor and the only
  component allowed to create projects, spawn roles, and relay across projects.
- **Tool and write boundaries.** Role tool access is constrained with
  `--allowed-tools`; Noter, Reviewer, and Ethics write only to their artifact
  areas, while Coder, Experimenter, Writer, and Expert operate in `workspace/`.
- **Layered memory.** Role context is reconstructed from the current invocation,
  per-role scratchpads, artifacts, EACN history, and project `CLAUDE.md`.
- **Skill and domain discovery.** Role skills live in
  `minions/roles/{role}/skills/*.md`; Expert domain packs live in
  `minions/domains/*.md`.
- **Experiment execution.** Experimenter can run local or SSH-backed jobs with
  `exp_run`, `exp_put`, `exp_get`, `exp_tail`, and `exp_status`.
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
  |     |     +-- Noter          -> artifacts/notes/
  |     |     +-- Coder          -> workspace/
  |     |     +-- Experimenter   -> workspace/ + exp_* tools
  |     |     +-- Writer         -> workspace/
  |     |     +-- Reviewer       -> artifacts/reviews/round-<n>/
  |     |     +-- Ethics         -> artifacts/ethics/
  |     |     +-- Expert-*       -> workspace/ + domain pack
  |     |
  |     +-- workspace/           # git worktree
  |     +-- memory/{role}.md     # role scratchpads
  |     +-- artifacts/
  |     +-- logs/
  |
  +-- project_37601/
        |
        +-- separate backend, worktree, memory, artifacts, and logs
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
  roles/                    # role SYSTEM.md prompts and skills
  domains/                  # Expert domain packs
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
- Claude CLI on `PATH` for real role execution

MinionsOS creates project worktrees from the directory that contains this
checkout. That parent directory must be a git repository before you create
projects:

```bash
cd <parent-of-MinionsOS_V3>
git init
git add -A
git commit -m "init"
```

`./install.sh` warns about this condition, and `./mos doctor` checks it again.

### Install

```bash
git clone https://github.com/Minions-Land/MinionsOS_V3.git
cd MinionsOS_V3
./install.sh
./mos doctor
```

`install.sh` is idempotent. It bootstraps `uv` when needed, syncs Python
dependencies, installs the local editable `EACN3/` package, builds the EACN3 MCP
plugin, builds MinionsVIZ when needed, creates launcher symlinks, and copies
`minions/config/*.yaml.example` to local `.yaml` files without overwriting
existing config.

### Configure

Local configuration lives under `minions/config/` and is intentionally ignored by
git:

- `gru.yaml` controls heartbeat cadence, logging, model/context settings,
  scratchpad thresholds, and web-search policy.
- `experiment_targets.yaml` defines local and SSH execution targets for
  Experimenter. Paths may use `{project_workspace}` template expansion.

Inspect resolved paths with:

```bash
./mos config
./mos config --json
```

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
| Gru | Global supervisor, human interface, project lifecycle, cross-project relay | all project state |
| Noter | Timeline, checkpoints, summaries | `artifacts/notes/` |
| Coder | Code maintenance, debugging, implementation | `workspace/` |
| Experimenter | Job dispatch, remote execution, result collection | `workspace/`, `artifacts/exp-*` |
| Writer | Paper drafting, packaging, rebuttal, camera-ready work | `workspace/` |
| Reviewer | Area-chair-style review rounds | `artifacts/reviews/round-<n>/` |
| Ethics | Evidence audit, unsupported-claim detection | `artifacts/ethics/` |
| Expert | Domain consultation with optional packs such as `nlp`, `cv`, `theory` | usually read-mostly in `workspace/` |

Role prompts are stored at `minions/roles/{role}/SYSTEM.md`.

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
gru_relay
project_eacn_send_message
project_eacn_create_task
gru_start_monitor
```

Experimenter tools:

```text
exp_run
exp_put
exp_get
exp_tail
exp_status
```

EACN3 tools are provided by the EACN3 MCP plugin as `eacn3_*` and are available
only to role mains that are allowed to use the bus.

### Runtime Project Structure

```text
project_{port}/
  CLAUDE.md                 # project narrative; Gru/author write, roles read
  meta.json                 # machine metadata
  workspace/                # git worktree on minionsos/project-{port}
  eacn3_data/eacn3.db       # per-project EACN3 SQLite database
  memory/{role}.md          # L2 role scratchpads
  artifacts/
    notes/
    reviews/round-<n>/
    ethics/
    exp-{id}/
    external_feedback/
  logs/
    backend.log
    role-{name}.log
```

Scratchpads are size-policed relative to the configured model context window:
soft compression hint at 10%, hard compression at 15%, and spawn veto at 20% by
default.

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
| Experiment failed | `project_{port}/artifacts/exp-{id}/report.md` |
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

**MinionsOS V3** 是一个本地多智能体操作系统，用于运行相互隔离的论文级科研项目。常驻的
**Gru** 负责总控；每个项目拥有独立的 **EACN3** 协调后端；Claude
**Roles** 由事件触发，短时唤醒、处理任务、完成后退出。

目标很直接：一位作者、一份 checkout、一个 Gru，同时管理多个互不串扰的研究项目。

### 能力概览

- **项目隔离。** 每个项目都有独立的 `project_{port}/`、EACN3 后端、SQLite
  状态、git worktree、日志、产物和 Role 记忆。
- **事件驱动 Role。** Noter、Coder、Experimenter、Writer、Reviewer、Ethics
  和 Expert 都是由 Python `WakeupScheduler` 拉起的短生命周期 Claude 子进程。
- **Gru 作为控制面。** Gru 是唯一人机入口，也是唯一可创建项目、spawn Role、跨项目
  relay 的组件。
- **工具和写入边界。** Role 通过 `--allowed-tools` 限制工具面；Noter、Reviewer、
  Ethics 只能写各自 artifact 区域；Coder、Experimenter、Writer、Expert 在
  `workspace/` 工作。
- **分层记忆。** Role 上下文来自当前事件、每 Role scratchpad、artifacts、EACN
  历史以及项目 `CLAUDE.md`。
- **Skill 和领域包发现。** Role 技能放在 `minions/roles/{role}/skills/*.md`；
  Expert 领域包放在 `minions/domains/*.md`。
- **实验执行。** Experimenter 可通过 `exp_run`、`exp_put`、`exp_get`、
  `exp_tail`、`exp_status` 统一管理本地或 SSH 远端任务。
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
  |     |     +-- Noter          -> artifacts/notes/
  |     |     +-- Coder          -> workspace/
  |     |     +-- Experimenter   -> workspace/ + exp_* tools
  |     |     +-- Writer         -> workspace/
  |     |     +-- Reviewer       -> artifacts/reviews/round-<n>/
  |     |     +-- Ethics         -> artifacts/ethics/
  |     |     +-- Expert-*       -> workspace/ + domain pack
  |     |
  |     +-- workspace/           # git worktree
  |     +-- memory/{role}.md     # Role scratchpad
  |     +-- artifacts/
  |     +-- logs/
  |
  +-- project_37601/
        |
        +-- 独立后端、worktree、记忆、产物和日志
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
  roles/                    # Role SYSTEM.md 和 skills
  domains/                  # Expert 领域包
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
- Claude CLI 位于 `PATH` 中，用于真实 Role 执行

MinionsOS 会从当前 checkout 的父目录创建项目 worktree。创建项目之前，该父目录必须是
git 仓库：

```bash
cd <MinionsOS_V3 的父目录>
git init
git add -A
git commit -m "init"
```

`./install.sh` 会提示这个条件，`./mos doctor` 也会再次检查。

### 安装

```bash
git clone https://github.com/Minions-Land/MinionsOS_V3.git
cd MinionsOS_V3
./install.sh
./mos doctor
```

`install.sh` 可以重复执行：它会按需自举 `uv`、同步 Python 依赖、editable 安装本地
`EACN3/`、构建 EACN3 MCP 插件、按需构建 MinionsVIZ、创建启动脚本链接，并把
`minions/config/*.yaml.example` 复制为本地 `.yaml` 配置且不覆盖已有文件。

### 配置

本地配置位于 `minions/config/`，默认不进入 git：

- `gru.yaml` 控制 heartbeat、日志级别、模型/上下文配置、scratchpad 阈值和 web search
  策略。
- `experiment_targets.yaml` 定义 Experimenter 使用的本地或 SSH 执行目标，路径支持
  `{project_workspace}` 模板展开。

查看解析后的路径：

```bash
./mos config
./mos config --json
```

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
| Gru | 全局主管、人机接口、项目生命周期、跨项目 relay | 全部项目状态 |
| Noter | 时间线、checkpoint、总结 | `artifacts/notes/` |
| Coder | 代码维护、调试、实现 | `workspace/` |
| Experimenter | 任务调度、远端执行、结果收集 | `workspace/`、`artifacts/exp-*` |
| Writer | 论文撰写、打包、rebuttal、camera-ready | `workspace/` |
| Reviewer | Area-Chair 式多轮评审 | `artifacts/reviews/round-<n>/` |
| Ethics | 证据审计、无依据论断检测 | `artifacts/ethics/` |
| Expert | 结合 `nlp`、`cv`、`theory` 等领域包提供咨询 | 通常以只读为主，必要时写 `workspace/` |

Role 提示词位于 `minions/roles/{role}/SYSTEM.md`。

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
gru_relay
project_eacn_send_message
project_eacn_create_task
gru_start_monitor
```

Experimenter 可用：

```text
exp_run
exp_put
exp_get
exp_tail
exp_status
```

EACN3 MCP 插件提供 `eacn3_*` 工具，只分配给允许访问总线的 role main。

### 运行时项目结构

```text
project_{port}/
  CLAUDE.md                 # 项目叙事；Gru/作者写，Roles 读
  meta.json                 # 机器元数据
  workspace/                # minionsos/project-{port} 分支的 git worktree
  eacn3_data/eacn3.db       # 每项目独立的 EACN3 SQLite 数据库
  memory/{role}.md          # L2 Role scratchpad
  artifacts/
    notes/
    reviews/round-<n>/
    ethics/
    exp-{id}/
    external_feedback/
  logs/
    backend.log
    role-{name}.log
```

scratchpad 大小按模型上下文窗口比例管控：默认 10% soft、15% hard、20% veto。

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
| 实验失败 | `project_{port}/artifacts/exp-{id}/report.md` |
| Viz 无法访问 | `./viz status` 和 `./viz logs` |
| doctor 父目录 git 检查失败 | 初始化并提交父目录 git 仓库 |

### 安全与配置

不要提交 secrets、生成的项目 worktree、实验凭据、运行时状态、日志或本地配置。跨项目通信
应继续由 Gru relay 管控，dashboard 端点必须保持只读。

### 许可

当前仓库未附带显式 LICENSE 文件；在补充许可证前请按内部/专有代码处理。
