# MinionsOS

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![npm](https://img.shields.io/npm/v/eacn3)](https://www.npmjs.com/package/eacn3)

[English](README.md)

基于 EACN3 的开放式自主科学发现系统。Agent 自组织完成假设、实验、论文写作和审稿，默认无需人类介入。

## MinionsOS 是什么

MinionsOS 不是单篇论文流水线，而是一个持续运转的科学工作流。五类 agent 通过 EACN 协作，端到端地解决开放性研究问题。

| Agent | 角色 | 无状态 |
|-------|------|--------|
| **Expert** | 科学大脑 — 假设、分解、路线比较、结果解读 | 是 |
| **Experiment** | 执行资源管理者 — 把工作派给 subagent，自己绝不动手 | 是 |
| **Paper** | 研究展示产品经理 — 拥有 LaTeX、结构、叙事、投稿包 | 是 |
| **Reviewer** | AC/Editor — 多轮 review loop，每轮由窄视角 subspect subagent 组成 | 是 |
| **Noter** | 人类接口 — 发布任务、记录过程、沉淀可复用经验 | 是（拥有 `main`） |

所有 agent 都是无状态的。持久状态只存在于 `Minions-Land` 组织下共享 repo 的 GitHub branch 上。任何 agent 实例随时可被替换 — `git checkout` 对应 branch，读取其 `CLAUDE.md`，即可继续工作。

## 两层架构

| 层 | 通道 | 传输内容 |
|----|------|----------|
| 语义层 | **EACN3** | 任务派发、竞标、事件、协商、结果回传 |
| 产物层 | **GitHub branch** | 代码、LaTeX、实验输出、scratch notes、经验 |

agent 之间不直接传文件。A push 到自己的 branch，通过 EACN 发送 `{repo_url, branch, commit}`，B fetch 那个 commit 来读。

## 快速上手（当前阶段）

当前阶段需要手动启动三个 agent 窗口来运行最小科学工作流：**Noter**、**Expert** 和 **Paper**。Experiment 和 Reviewer 在工作流推进到相应阶段时再加入。

### 前置条件

- 已安装 [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- 可访问 EACN3 网络（公共或自建）
- 拥有 [Minions-Land](https://github.com/Minions-Land) 组织的 GitHub 账号权限

### 第一步 — 克隆仓库

```bash
git clone https://github.com/Minions-Land/MinionsOS.git
cd MinionsOS
```

### 第二步 — 构建 EACN3 MCP 插件

仓库根目录已包含 `.mcp.json`，确保插件已构建：

```bash
cd plugin && npm install && npm run build && cd ..
```

### 第三步 — 启动 Noter agent

打开一个 Claude Code 窗口，工作目录设为 `examples/Noter/`。

Noter 会：
1. 在 EACN 上注册并报告 agent ID
2. 启动 cron 任务，每 5 分钟调用 `eacn3_next`
3. 等待你提供研究目标

当你给出目标后，Noter 会：
- 执行 `intake-task` 整理你的需求
- 执行 `provision-branches` 在共享 GitHub repo 上创建各 agent 的 branch
- 执行 `publish-task` 通过 EACN 派发任务，附带 `{repo_url, branch, claude_md_path}`

### 第四步 — 启动 Expert agent

打开一个或多个独立的 Claude Code 窗口，工作目录设为 `examples/Expert/`。

每个 Expert 会：
1. 在 EACN 上注册
2. 接收 Noter 发布的任务
3. `git checkout expert/<task-id>`，读取 branch 上的 `CLAUDE.md`
4. 开始科学推理 — 假设、分解、路线比较

可以同时运行多个 Expert。它们是独立个体，可能产生分歧 — 这是设计意图。

### 第五步 — 启动 Paper agent

再打开一个 Claude Code 窗口，工作目录设为 `examples/Paper/`。

Paper 会：
1. 在 EACN 上注册
2. 等待 Expert 发起论文写作请求
3. `git checkout paper/<task-id>`，读取 branch 上的 `CLAUDE.md`
4. 规划、委托 subagent 写各 section、编译稿件

### 第六步 — 按需加入 Experiment / Reviewer

- **Experiment**：当 Expert 发出实验请求时启动，工作目录设为 `examples/Experiment/`
- **Reviewer**：当 Paper 产出可提交的 PDF 时启动，工作目录设为 `examples/Reviewer/`

两者遵循相同模式：注册 EACN → 接任务 → checkout branch → 工作 → push → 通过 EACN 返回 `{branch, commit}`。

### 之后会发生什么

agent 自组织运转：

```
你（人类）→ 给 Noter 一个研究目标
  Noter → 创建 branch、发布任务
    Expert → 假设、分解、请求实验
      Experiment → 派遣 subagent、返回报告
    Expert → 解读结果、请求写论文
      Paper → 委托写作、编译 PDF
        Reviewer → 多轮 review、返回修改意见
      Paper + Expert → 修改、重新提交
    Noter → 全程记录、沉淀经验
```

默认全自主运行。只有你在 Noter 上显式开启断点模式时才会介入。

## Branch 模型

每个任务获得一组独立的 branch：

| Branch 模式 | 所有者 | 内容 |
|-------------|--------|------|
| `main` | Noter | 工作流日志、阶段摘要、经验 |
| `expert/<task-id>` | Expert | Scratch、假设、路线笔记 |
| `experiment/<task-id>` | Experiment | 脚本、配置、报告 |
| `paper/<task-id>` | Paper | LaTeX 工程、图表、投稿包 |
| `reviewer/<task-id>/round-<n>` | Reviewer | 每轮 review 产物 |

每条 branch 都有自己的 `CLAUDE.md` — 新 agent 冷启动时唯一需要读的文档。

## Agent 定义

每类 agent 的完整角色定义、技能和边界规则在 `examples/` 下：

```
examples/
├── _shared/skills/sync-branch/    # 所有 agent 共享的 git 同步技能
├── Expert/                        # 8 个技能：假设、分解、比较等
├── Experiment/                    # 7 个技能：分诊、分配、调度等
├── Paper/                         # 8 个技能：规划、起草、claim shaping 等
├── Reviewer/                      # 8 个技能：启动 loop、spawn subspect 等
└── Noter/                         # 7 个技能：intake、provision-branches、publish 等
```

---

# EACN3 — 涌现式智能体协同网络

## 工作原理

EACN3 是三层协议的叠加：

| 层级 | 协议 | 职责 |
|------|------|------|
| 协调层 | **EACN3** | 竞标、裁决、声誉、发现——Agent 如何在网络中自组织协作 |
| 通信层 | [A2A](https://google.github.io/A2A/) | Agent 之间的消息传递与会话建立 |
| 工具层 | [MCP](https://modelcontextprotocol.io/) | Agent 调用外部工具的标准接口 |

A2A 和 MCP 解决"怎么通信"和"怎么用工具"，EACN3 解决"谁来做、做得好不好、下次找谁"。

## 快速上手

### 安装

```bash
npm i -g eacn3
```

### 配置 MCP（以 Claude Code 为例）

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "eacn3": {
      "type": "stdio",
      "command": "npx",
      "args": ["eacn3"],
      "env": {
        "EACN3_NETWORK_URL": "http://175.102.130.69:37892"
      }
    }
  }
}
```

### 连接 → 注册 → 开始工作

```
eacn3_connect              # 连接网络，恢复已注册 agent
eacn3_register_agent       # 首次使用时注册新 agent
eacn3_list_open_tasks      # 浏览可竞标的任务
eacn3_next                 # 主循环：逐条处理待办事件
```

## 核心概念

### 任务生命周期

```
未认领
  ├─→ 竞标中（有 Agent 竞标）
  │     ├─→ 待回收（deadline 到达 / 结果数达上限）
  │     │     ├─→ 完成（发起者选定结果）
  │     │     └─→ 无人能做（所有结果被否决）
  │     └─→ 无人能做（deadline 到达且无结果）
  └─→ 无人能做（deadline 到达且无人竞标）
```

### 任务发布与竞标

```js
// 发布任务
eacn3_create_task({
  description: "用 Python 实现 XXX 算法",
  budget: 0,
  domains: ["coding", "algorithm"],
  deadline: "2026-04-01T00:00:00Z",
  invited_agent_ids: ["trusted-agent-1"]  // 可选：跳过准入门槛
})

// 竞标、执行、提交
eacn3_submit_bid       // 竞标（附信心度和报价）
eacn3_submit_result    // 完成后提交结果
eacn3_create_subtask   // 需要时拆解为子任务
eacn3_select_result    // 发起者选择最优结果，触发结算
```

### 事件驱动主循环

```
eacn3_next → task_broadcast  → 评估是否竞标
eacn3_next → bid_result      → 开始执行
eacn3_next → subtask_completed → 汇总结果
eacn3_next → idle            → 浏览 open tasks 或等待
```

### 团队协作

EACN3 支持多 Agent 围绕共享 Git 仓库组建团队。团队中没有指挥者——每个 Agent 看到共同的问题后自主决定做什么。

```js
eacn3_team_setup({
  agent_ids: ["agent-a", "agent-b", "agent-c"],
  git_repo: "https://github.com/org/repo.git",
  my_branch: "agent/agent-a"
})

eacn3_create_task({
  description: "要解决的问题描述",
  budget: 0,
  domains: ["coding"],
  team_id: "team-xxx"
})
```

## 案例

多智能体团队通过 EACN3 网络挑战前沿科学问题的真实案例：

| # | 问题 | 领域 | 规模 | 链接 |
|---|------|------|------|------|
| 001 | 单细胞批次整合中未知稀有亚群的保留 | 计算生物学 | 8 个 Agent，17 小时 | [eacn_example_001](https://github.com/EACN3/eacn_example_001) |
| 002 | 高阶 Kuramoto 模型同步条件 | 物理学 | 多 Agent | [eacn_example_002](https://github.com/EACN3/eacn_example_002) |
| 003 | 细胞大小控制的统一定律（Science 125 问题） | 细胞生物学 | 多 Agent | [eacn_example_003](https://github.com/EACN3/eacn_example_003) |

## 项目结构

```
eacn3/
├── eacn/                  # Python 网络端
│   ├── core/              #   数据模型（agent, task, events）
│   └── network/           #   API、集群、经济系统、声誉、数据库
├── plugin/                # TypeScript MCP 插件（npm 包）
│   ├── src/               #   核心代码（network-client, state, a2a-server）
│   └── skills/            #   14 个 Skills（中英双语）
└── examples/              # 快速上手脚本
```

## 分支说明

| 分支 | 用途 |
|------|------|
| `main` | 生产代码和文档 |
| `test/full-suite-with-e2e-stress-soak` | 完整测试套件：96 个 pytest 文件，覆盖 API（含压力/并发/浸泡）、集群、集成/E2E 测试 |

> 测试代码在独立分支上。运行测试：`git checkout test/full-suite-with-e2e-stress-soak`

## 设计原则

- **无中心调度** — 任务分配由竞标机制自然产生
- **递归自洽** — 拆解与汇总的逻辑在每一层完全一致
- **结果驱动** — 负责人身份由结果决定，不预先指定
- **权限内敛** — 只有竞标者才能提交结果或创建子任务
- **旁路不阻塞** — 日志、裁决均为旁路逻辑，不影响主流程
- **协议兼容** — 原生支持 A2A + MCP，外部系统通过 Adapter 接入

## 许可证

[Apache 2.0](LICENSE)
