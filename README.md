# MinionsOS V2

[English](#english) · [中文](#中文)

---

## English

> **Towards Fully Autonomous Scientific Discovery: A Multi-Agent Workflow on the EACN Protocol.**

### What it is

MinionsOS V2 is a multi-agent operating system for running autonomous research projects end-to-end. A single persistent **Gru** supervises many concurrent paper-sized projects; each project runs its own **EACN3** coordination bus and spawns ephemeral **Roles** — Noter, Coder, Experimenter, Writer, Reviewer, Ethics, and Expert — that wake on events, act, and exit.

One author, one checkout, one Gru, as many papers as you want — each fully isolated.

### Key features

- **Multi-project IP isolation.** Every project runs its own EACN3 backend on a dedicated port. The only cross-project path is `gru_relay(from_port, to_port, content, mode)`, which only Gru may call.
- **Event-driven ephemeral Roles.** No long-running Claude process per Role. A Python-side `WakeupScheduler` polls EACN on `1m` / `3m` / `5m` cadence (per-role override), dedupes events, and launches short-lived Claude subprocesses seeded with the Role's `SYSTEM.md` and the event batch. Empty polls cost zero Claude context.
- **Tool-whitelist enforcement.** Every subprocess launches with `--allowed-tools`; mains vs. subagents get different surfaces. The whitelist is the mechanism that keeps the EACN bus from becoming a free-for-all (see §4 of `CLAUDE.md`).
- **Git-worktree isolation per project.** Each project lives on its own branch `minionsos/project-{port}` inside a git worktree under `project_{port}/workspace/`.
- **Layered memory.** L1 transcript (session), L2 per-Role scratchpad at `project_{port}/memory/{role}.md`, L3 artifacts + EACN history, L4 `CLAUDE.md`. Scratchpad size is auto-policed with soft / hard / veto thresholds scaled to model context window.
- **Auto-generated project `CLAUDE.md`.** `project_create` drops a skeleton with `brief` / `topic_doc` / `template_dir` pointers so the author can stage topic and template materials without hand-editing.
- **Skill discovery.** Drop a file into `minions/roles/{role}/skills/*.md` and every wake-up injects a `[Skills]` block listing it — no code change.
- **Expert domain packs.** `minions/domains/` ships `dl-arch`, `optimization`, `theory`, `nlp`, `cv`; the pack is appended to the Expert system prompt at spawn time.
- **Evidence-first communication (soft).** EACN messages making substantive claims should carry `[evidence: <path|SHA|URL|event-id>]`, `[speculation]`, or `[derived: <base>]`. Ethics audits unmarked-claim ratios per Role.
- **Experiment targets.** Local and SSH execution via `exp_run / exp_put / exp_get / exp_tail / exp_status`, with `{project_workspace}` template expansion in `experiment_targets.yaml`.

### Architecture

```
Author
  │
  ▼
Gru  (global supervisor; human-facing window; cross-project relay)
  │
  ├── project_37596/         one paper = one project = one EACN3 backend
  │     └── EACN3 bus  (port 37596)
  │           ├── Noter         (→ artifacts/notes/)
  │           ├── Coder         (→ workspace/)
  │           ├── Expert-*      (→ workspace/ scratch; domain pack appended)
  │           ├── Experimenter  (→ workspace/ + remote GPUs via exp_*)
  │           ├── Writer        (→ workspace/paper/)
  │           ├── Reviewer      (→ artifacts/reviews/round-<n>/)
  │           └── Ethics        (→ artifacts/ethics/)
  │
  └── project_37601/ …           (another paper, physically isolated)

Cross-project path: Gru-only, via gru_relay()
Role lifecycle:    WakeupScheduler (Python) → invoke_role_ephemeral(Claude subprocess) → exit
```

See `CLAUDE.md` for the full directory tree and reader navigation.

### Prerequisites

- Python **3.11+**
- [`uv`](https://docs.astral.sh/uv/) (installed automatically by `install.sh` if missing)
- `git` 2.x
- Node **≥ 16** + `npm` (for the EACN3 MCP plugin build)
- Claude CLI on `PATH`

> **Important — parent directory must be a git repo.** MinionsOS creates per-project git worktrees branched off the directory that **contains** `MinionsOS_V2/`. If the parent is not a git repo, `project_create` will fail.
>
> Fix recipe:
> ```bash
> cd <parent-of-MinionsOS_V2>
> git init && git add -A && git commit -m 'init'
> ```
> The installer warns about this; `./mos doctor` re-checks it.

### Install

```bash
git clone --recursive <repo-url> MinionsOS_V2
cd MinionsOS_V2
./install.sh
./mos doctor          # sanity check: uv, node, git, EACN3, port-bind, parent-git
```

`install.sh` is idempotent: it bootstraps `uv`, installs Python 3.11, runs `uv sync`, installs EACN3 editable, builds the EACN3 MCP plugin, and copies `*.yaml.example → *.yaml`.

### Quick start

```bash
./gru                                  # launch interactive Gru (== ./minionsos == ./mos)

./mos status                           # dashboard of all projects
./mos status --json                    # machine-readable
./mos logs --project 37596             # project logs
./mos logs --role noter --tail 50      # tail a role log
./mos doctor                           # environment health check
./mos config                           # print config paths

./mos project list
./mos project close 37596
./mos project revive 37596
./mos role list 37596
./mos role dismiss 37596 noter
```

### Roles

| Role | One-liner | Writable scope |
|---|---|---|
| **Gru** | Global supervisor, human-facing window, cross-project relay | everything |
| **Noter** | Silent observer; records timeline & checkpoints | `artifacts/notes/` only |
| **Coder** | Software engineer; debugs, refactors, maintains `workspace/src/` | full `workspace/` |
| **Experimenter** | Execution manager; GPU scheduling & result collection | full `workspace/` + `exp_*` |
| **Writer** | Paper packaging; first draft → camera-ready | full `workspace/` |
| **Reviewer** | Area-chair-style evaluator; multi-round review loops | `artifacts/reviews/round-<n>/` only |
| **Ethics** | Evidence auditor & hallucination checker | `artifacts/ethics/` only |
| **Expert** | Domain consultant (dl-arch / optimization / theory / nlp / cv) | `workspace/` (soft: read mostly) |

Role system prompts live at `minions/roles/{role}/SYSTEM.md`.

### Key MCP tools

Defined in `minions/tools/mcp_server.py` + `minions/tools/experiment_ssh.py`:

**Project lifecycle (Gru only)**
`project_create` · `project_close` · `project_dormant` · `project_revive` · `project_list`

**Role lifecycle (Gru only)**
`spawn_role` · `spawn_expert` · `dismiss_role` · `list_roles`

**Coordination (Gru only)**
`gru_relay` · `gru_start_monitor`

**Experiment execution (Experimenter)**
`exp_run` · `exp_put` · `exp_get` · `exp_tail` · `exp_status`

**EACN bus (all Role mains)**
`eacn3_*` (provided by the EACN3 MCP plugin)

### Project layout

Each project lives under `project_{port}/`:

```
project_{port}/
├── CLAUDE.md              # project narrative (author + Gru write; roles read-only)
├── meta.json              # machine fields
├── workspace/             # git worktree on branch minionsos/project-{port}
├── eacn3_data/eacn3.db    # per-project EACN3 SQLite backend
├── memory/{role}.md       # L2 per-Role scratchpads
├── artifacts/
│   ├── notes/             # Noter summaries, checkpoints, final_summary.md
│   ├── reviews/round-<n>/ # Reviewer outputs
│   ├── ethics/            # Ethics reports / flags / investigations
│   ├── exp-{id}/          # Experimenter result bundles
│   └── external_feedback/ # injected via project_revive
└── logs/
    ├── backend.log
    └── role-{name}.log
```

### Debug entry points

| What broke | Where to look |
|---|---|
| Gru itself | `minions/state/logs/gru.log` |
| EACN3 backend for a project | `project_{port}/logs/backend.log` |
| A specific role | `project_{port}/logs/role-{name}.log` |
| Role crash loop | `role-{name}.log` — 3 crashes → Gru marks the role dismissed |
| Backend crash loop | `backend.log` — 3 crashes in 1h → Gru notifies author, stops auto-restart |
| Experiment failure | `artifacts/exp-{id}/report.md` — circuit-break after 3 consecutive same-script failures |
| EACN3 state | `project_{port}/eacn3_data/eacn3.db` (SQLite) |

### Hard rules (summary)

The authoritative versions live in the root `CLAUDE.md`.

1. **EACN3 is untouched.** It is a git submodule; upgrade by replacement. All access via `eacn3_*` tools.
2. **uv only.** No `pip`, `conda`, `mamba`, `virtualenv`, or bare `python -m venv`.
3. **IP isolation via `gru_relay`.** Roles on one project cannot contact roles on another directly.
4. **Subagent tool whitelists.** Enforced via `--allowed-tools` on spawn.
5. **Noter and Reviewer are read-only on `workspace/`.** Writes go to their dedicated artifact directories.
6. **Event-driven Role lifecycle.** No long-running Claude processes or in-Claude polling loops; `WakeupScheduler` drives everything.
7. **Only Gru spawns EACN-visible agents.** Subagents and team members are EACN-invisible by design.
8. **Idle time is working time (soft).** Prefer short bounded idle subagent tasks; no new directions / experiments / review rounds on idle time.
9. **Evidence-first communication (soft).** Substantive claims should carry `[evidence: …]`, `[speculation]`, or `[derived: …]` markers.

### Observatory (MinionsVIZ)

`minions-viz/` ships **MinionsVIZ**, a strictly read-only dashboard for
the whole MinionsOS system. It is a **machine-wide singleton**: every
Gru installation on the host shares one viz process at one URL, filtered
in the UI by a two-level **Gru ▾ / Project ▾** picker.

```bash
./install.sh        # builds minions-viz/dist on first run; creates ~/.minionsos/
./gru               # registers this Gru + auto-starts MinionsVIZ (no-op if up)

# Manual control:
./viz ensure                      # register + start (idempotent)
./viz start|stop|status|open|logs
./viz register|deregister|heartbeat
./mos viz ensure|start|stop|status|open|logs
```

- **Read-only guarantees.** Never POSTs to EACN3; never calls
  `/api/events/{agent_id}` (which would drain a real agent's queue). All
  HTTP endpoints are `GET` and idempotent.
- **User-level state.** `~/.minionsos/` (mode 0700) holds the Gru
  registry (`grus.json`) and the running viz's `{viz.pid, viz.port,
  viz.url, viz.lock}`.
- **Env knobs.** `GRU_VIZ=0` disables auto-start, `GRU_VIZ_OPEN=0`
  suppresses the browser open, `MINIONS_VIZ_PORT=N` overrides the port
  (default 7891; scans 7891..7910), `MINIONS_VIZ_REBUILD=1` forces a
  rebuild during `./install.sh`, `MINIONS_GRU_LABEL=<name>` overrides
  this Gru's label on register/ensure.

See `minions-viz/README.md` for tabs, HTTP/WebSocket API, and dev
workflow; `minions-viz/AGENTREAD.md` for the internal architecture.

### Contributing / dev

- Package architecture, coding conventions, and extension recipes (new Role / skill / domain / MCP tool) live in `minions/CLAUDE.md`.
- Tests under `tests/unit/`:
  ```bash
  uv run pytest tests/unit/
  uv run ruff check minions/
  ```
- Smoke tests stub Claude: `MINIONS_FAKE_CLAUDE=1 uv run pytest tests/smoke/`.

### License

See `pyproject.toml` / repository root. (No explicit license file is bundled at this stage; treat as proprietary until one is added.)

---

## 中文

> **迈向全自动科学发现：基于 EACN 协议的多智能体工作流。**

### 项目简介

MinionsOS V2 是一个用于自主驱动科研项目的多智能体操作系统。一个常驻的 **Gru** 主管同时监督多个论文级项目；每个项目运行独立的 **EACN3** 协调总线，并按事件触发 **Roles**（Noter 记录员、Coder 工程师、Experimenter 实验管理员、Writer 撰稿人、Reviewer 评审、Ethics 证据审计、Expert 领域专家）——短时唤醒、处理事件、立即退出。

一位作者、一份 checkout、一个 Gru，可同时承载任意多篇论文，项目间完全隔离。

### 核心特性

- **多项目 IP 隔离。** 每个项目拥有独立端口上的 EACN3 后端；跨项目唯一路径是只有 Gru 可调用的 `gru_relay(from_port, to_port, content, mode)`。
- **事件驱动的短时 Role 生命周期。** 不再为每个 Role 维持长时间 Claude 进程。Python 侧的 `WakeupScheduler` 按 `1m` / `3m` / `5m`（每 Role 可覆盖）轮询 EACN，去重后拉起短时 Claude 子进程，处理完即退；空轮询零 Claude 上下文开销。
- **工具白名单强约束。** 所有子进程通过 `--allowed-tools` 启动；main 与 subagent 拥有不同工具面（详见 `CLAUDE.md` §4）。
- **按项目的 git worktree 隔离。** 每个项目位于独立分支 `minionsos/project-{port}` 的 worktree 中。
- **分层记忆。** L1 当前会话 transcript；L2 每 Role 的 scratchpad（`project_{port}/memory/{role}.md`）；L3 artifacts + EACN 历史；L4 `CLAUDE.md`。scratchpad 大小按模型上下文窗口百分比自动管控（soft / hard / veto）。
- **项目 `CLAUDE.md` 自动生成。** `project_create` 生成含 `brief` / `topic_doc` / `template_dir` 指针的骨架，作者无需手动创建。
- **Skill 自动发现。** 把文件放进 `minions/roles/{role}/skills/*.md`，每次 wake-up 注入 `[Skills]` 即可，无需改代码。
- **Expert 领域包。** `minions/domains/` 内置 `dl-arch` / `optimization` / `theory` / `nlp` / `cv`；Expert spawn 时自动拼接对应领域包到系统提示尾部。
- **证据优先通信（软约定）。** 重要论断应标注 `[evidence: <路径|SHA|URL|事件 id>]` / `[speculation]` / `[derived: <基 claim>]`；Ethics 会按 Role 审计未标注比例。
- **实验目标抽象。** 本地与 SSH 远端执行统一通过 `exp_run / exp_put / exp_get / exp_tail / exp_status`；`experiment_targets.yaml` 支持 `{project_workspace}` 模板展开。

### 架构示意

```
作者
  │
  ▼
Gru（全局主管，唯一人机接口，跨项目 relay）
  │
  ├── project_37596/        一篇论文 = 一个项目 = 一个 EACN3 后端
  │     └── EACN3 总线 (port 37596)
  │           ├── Noter         (→ artifacts/notes/)
  │           ├── Coder         (→ workspace/)
  │           ├── Expert-*      (→ workspace/ 草稿；拼接领域包)
  │           ├── Experimenter  (→ workspace/ + 远端 GPU via exp_*)
  │           ├── Writer        (→ workspace/paper/)
  │           ├── Reviewer      (→ artifacts/reviews/round-<n>/)
  │           └── Ethics        (→ artifacts/ethics/)
  │
  └── project_37601/ …           （另一篇论文，物理隔离）

跨项目路径：仅 Gru，通过 gru_relay()
Role 生命周期：WakeupScheduler (Python) → invoke_role_ephemeral (Claude 子进程) → 退出
```

完整目录树与阅读导航见根目录 `CLAUDE.md`。

### 环境要求

- Python **3.11+**
- [`uv`](https://docs.astral.sh/uv/)（`install.sh` 会自动安装）
- `git` 2.x
- Node **≥ 16** + `npm`（用于构建 EACN3 MCP 插件）
- Claude CLI 在 `PATH` 中

> **重要 —— 父目录必须是 git 仓库。** MinionsOS 会在包含 `MinionsOS_V2/` 的**父目录**上建 worktree；若父目录不是 git 仓库，`project_create` 会直接失败。
>
> 修复方法：
> ```bash
> cd <MinionsOS_V2 的父目录>
> git init && git add -A && git commit -m 'init'
> ```
> 安装脚本会预警告此问题；`./mos doctor` 会再次检查。

### 安装

```bash
git clone --recursive <repo-url> MinionsOS_V2
cd MinionsOS_V2
./install.sh
./mos doctor          # 健康检查：uv / node / git / EACN3 / port / 父目录 git
```

`install.sh` 可重复执行：自举 `uv`、安装 Python 3.11、`uv sync`、editable 安装 EACN3、构建 EACN3 MCP 插件、复制 `*.yaml.example → *.yaml`。

### 快速开始

```bash
./gru                                  # 启动交互式 Gru（等价于 ./minionsos / ./mos）

./mos status                           # 所有项目仪表盘
./mos status --json                    # 机器可读
./mos logs --project 37596             # 项目日志
./mos logs --role noter --tail 50      # tail 某个 role 日志
./mos doctor                           # 环境健康检查
./mos config                           # 打印配置路径

./mos project list
./mos project close 37596
./mos project revive 37596
./mos role list 37596
./mos role dismiss 37596 noter
```

### Roles 一览

| Role | 一句话 | 可写范围 |
|---|---|---|
| **Gru** | 全局主管、人机接口、跨项目 relay | 全部 |
| **Noter** | 静默观察、时间线与 checkpoint | 仅 `artifacts/notes/` |
| **Coder** | 软件工程师；维护 `workspace/src/` | 整个 `workspace/` |
| **Experimenter** | 执行管理员；GPU 调度与结果收集 | `workspace/` + `exp_*` |
| **Writer** | 论文打包；初稿到 camera-ready | 整个 `workspace/` |
| **Reviewer** | Area-Chair 式正式评审 | 仅 `artifacts/reviews/round-<n>/` |
| **Ethics** | 证据审计与幻觉检查 | 仅 `artifacts/ethics/` |
| **Expert** | 领域专家（dl-arch / optimization / theory / nlp / cv） | `workspace/`（软：主要读） |

Role 系统提示位于 `minions/roles/{role}/SYSTEM.md`。

### 关键 MCP 工具

定义在 `minions/tools/mcp_server.py` 与 `minions/tools/experiment_ssh.py`：

- **项目生命周期（仅 Gru）：** `project_create` · `project_close` · `project_dormant` · `project_revive` · `project_list`
- **Role 生命周期（仅 Gru）：** `spawn_role` · `spawn_expert` · `dismiss_role` · `list_roles`
- **协调（仅 Gru）：** `gru_relay` · `gru_start_monitor`
- **实验执行（Experimenter）：** `exp_run` · `exp_put` · `exp_get` · `exp_tail` · `exp_status`
- **EACN 总线（所有 Role mains）：** `eacn3_*`（来自 EACN3 MCP 插件）

### 项目目录结构

每个项目位于 `project_{port}/` 下，含 `CLAUDE.md`（项目叙事，作者 + Gru 写、Roles 只读）、`meta.json`、`workspace/`（git worktree）、`eacn3_data/eacn3.db`、`memory/{role}.md`（L2 scratchpad）、`artifacts/{notes,reviews,ethics,exp-*,external_feedback}/`、`logs/`。

### 调试入口

| 问题 | 查看 |
|---|---|
| Gru 本身 | `minions/state/logs/gru.log` |
| 某项目的 EACN3 后端 | `project_{port}/logs/backend.log` |
| 某个 Role | `project_{port}/logs/role-{name}.log` |
| Role 连续崩溃 | `role-{name}.log` —— 3 次后 Gru 将其标记为 dismissed |
| 后端连续崩溃 | `backend.log` —— 1h 内 3 次后停止自动重启并通知作者 |
| 实验失败 | `artifacts/exp-{id}/report.md` —— 同脚本连续 3 次失败触发断路器 |
| EACN3 状态 | `project_{port}/eacn3_data/eacn3.db` (SQLite) |

### 硬性规则（摘要）

完整版见根 `CLAUDE.md`。

1. **EACN3 不可改动。** 作为 submodule，仅整体替换升级；所有访问走 `eacn3_*` 工具。
2. **仅 uv。** 不使用 `pip` / `conda` / `mamba` / `virtualenv` / 裸 venv。
3. **IP 隔离靠 `gru_relay`。** 跨项目 Role 之间不可直接通信。
4. **子进程工具白名单。** 通过 spawn 时的 `--allowed-tools` 强制。
5. **Noter / Reviewer 对 `workspace/` 只读。** 只能写各自的 artifact 目录。
6. **事件驱动的 Role 生命周期。** 无长进程、无 Claude 内轮询；由 `WakeupScheduler` 调度。
7. **仅 Gru 可 spawn EACN 可见 agent。** subagent 与 team 成员对 EACN 不可见。
8. **空闲即工作（软）。** 鼓励小粒度 idle 子任务；不启动新方向 / 新实验 / 新评审轮次。
9. **证据优先（软）。** 重要论断应附 `[evidence: …]` / `[speculation]` / `[derived: …]`。

### Observatory（MinionsVIZ 观察台）

`minions-viz/` 是 **MinionsVIZ**——整个 MinionsOS 系统的严格只读仪表盘。它是**机器级单例**：同一主机上多份 Gru checkout 共享同一个 viz 进程与同一个 URL，前端用 **Gru ▾ / Project ▾** 两级下拉筛选。

```bash
./install.sh        # 首次构建 minions-viz/dist；创建 ~/.minionsos/
./gru               # 注册当前 Gru + 自动启动 MinionsVIZ（已在运行则 no-op）

# 手动控制：
./viz ensure                      # register + start（幂等）
./viz start|stop|status|open|logs
./viz register|deregister|heartbeat
./mos viz ensure|start|stop|status|open|logs
```

- **只读保证。** 不 POST 任何 EACN3 后端；绝不调用 `/api/events/{agent_id}`（那会消耗真实 agent 的事件队列）。所有 HTTP 端点都是 `GET` 且幂等。
- **用户级状态。** `~/.minionsos/`（0700）存放 Gru 注册表 `grus.json` 与运行中 viz 的 `{viz.pid, viz.port, viz.url, viz.lock}`。
- **环境变量。** `GRU_VIZ=0` 关闭自动启动；`GRU_VIZ_OPEN=0` 不打开浏览器；`MINIONS_VIZ_PORT=N` 指定端口（默认 7891，扫描 7891..7910）；`MINIONS_VIZ_REBUILD=1` 强制在 `./install.sh` 中重建；`MINIONS_GRU_LABEL=<name>` 覆盖 Gru 在注册表中的显示名。

更多细节（tab 组成、HTTP / WebSocket API、开发流程）见 `minions-viz/README.md`；架构内部机制见 `minions-viz/AGENTREAD.md`。

### 参与开发

- 包架构、编码规范、扩展方法（新 Role / skill / domain / MCP 工具）见 `minions/CLAUDE.md`。
- 测试：

  ```bash
  uv run pytest tests/unit/
  uv run ruff check minions/
  MINIONS_FAKE_CLAUDE=1 uv run pytest tests/smoke/
  ```

### 许可

见 `pyproject.toml` 与仓库根目录。当前未附带显式 LICENSE 文件；在补充前请按内部代码对待。
