# MinionsOS V5 Proposal：不可修改 EACN3、EACN-only 交互的 Rust 适配内核

## 三条硬原则

### 1. 不修改 EACN3

MinionsOS V5 不能修改：

`EACN3/`

EACN3 是不可变依赖和协议边界。MinionsOS 只能适配 EACN3，不能 patch EACN3。

这意味着：

- 不修改 `EACN3/eacn/**`
- 不修改 `EACN3/plugin/**`
- 不依赖 `project_{port}/eacn3_data/eacn3.db` 内部 schema
- 不计划“修复 EACN3 ack”
- 不在 MinionsOS 内维护 fork 版 EACN3 行为

### 2. 所有 Agent 交互必须通过 EACN

MinionsOS 内所有有语义的交互都必须通过 EACN：

- Role -> Role
- Role -> Gru
- Gru -> Role
- Role -> Noter
- Role -> Reviewer / Ethics / Expert
- 跨项目 relay
- task assignment
- clarification
- status report
- blocker report
- artifact produced notification
- review request
- experiment request
- evidence request

本地文件不能成为通信通道。

禁止把这些东西当成通信机制：

- 直接写 `logs/*.jsonl` 让另一个 Role 读取
- 写 `memory/{role}.md` 给别的 Role 留话
- 写 artifact 后不通过 EACN 通知
- 让 Role 轮询本地 inbox 文件
- 让 Viz/TUI 写文件触发 Role 行动
- 用 SQLite row 作为 Role-to-Role message

本地文件可以存证据、缓存、journal、状态、日志，但不能替代 EACN message/task。

### 3. Local State 是 Runtime 可靠性层，不是第二通信系统

V5 的 SQLite journal 只解决一个问题：EACN3 当前 event endpoint 是 drain-on-read，
MinionsOS 需要避免自己 drain 后丢事件。

所以 journal 是 transport reliability buffer，不是新的 bus。

Role 看到的 event batch，语义来源必须仍然是 EACN event。Role 的回复也必须回到 EACN。

## 核心判断

V5 不是把 MinionsOS 全部 Rewrite in Rust。

V5 是：

> 在不修改 EACN3 的前提下，用 Rust 做 MinionsOS 自己的 runtime kernel；同时保证所有
> agent 语义交互仍然只走 EACN。

Rust 负责：

- EACN event ingestion
- MinionsOS-owned durable journal
- process supervision
- project/role runtime state
- TUI
- read-only observability server

Python 保留：

- Role prompts / skills
- MCP capability tools
- paper search
- experiment execution
- reviewer workflow
- 现有科研和工具逻辑

EACN3 仍然是唯一协作网络。MinionsOS V5 只是让这个网络在本地项目系统里更可靠、更可监管、
更好操作。

## 对前一版 Proposal 的关键修正

前一版里“Role 从 MinionsOS journal 接收事件批次”的说法需要更精确：

不应理解为：

- journal 是新消息系统
- Role 之间通过 journal 通信
- MinionsOS 绕过 EACN 做本地投递

正确理解是：

- EACN 是唯一语义来源。
- `mosd` 是唯一允许 drain EACN events 的 runtime component。
- `mosd` drain 后立即把 EACN event 原样写入 MinionsOS journal。
- journal 只用于 crash recovery、lease、retry、dedup。
- Role wakeup 时收到的是“从 EACN event replay 出来的 batch”。
- Role 处理完后，必须通过 EACN adapter tools 回复、提交结果或创建任务。

## V5 核心设计

### 1. `mosd`：Rust Runtime Daemon

`mosd` 是 MinionsOS-owned daemon，不放进也不修改 `EACN3/`。

职责：

- 发现 active projects。
- 调用 EACN3 public HTTP APIs。
- 作为唯一 event poller drain EACN events。
- 将 drained EACN events 写入 MinionsOS durable journal。
- lease journaled EACN events 给 Role invocation。
- 启动并监管 Claude/Codex Role 子进程。
- 追踪 backend、Role、experiment、Gru 健康。
- 给 TUI 和 Viz 提供只读 snapshot。

`mosd` 不提供 Role-to-Role messaging API。所有 messaging API 都必须最终落到 EACN。

### 2. EACN Adapter Layer

新增 MinionsOS-owned adapter layer，例如：

`crates/minions-eacn-adapter/`

迁移阶段也可以先保留 Python adapter。

adapter 是 MinionsOS 唯一知道 EACN3 endpoint 形状的地方。

它提供 typed operations：

- `list_tasks`
- `list_open_tasks`
- `send_message`
- `create_task`
- `submit_bid`
- `submit_result`
- `get_task_results`
- `register_agent`
- `register_server`
- `poll_events`

但有一个强限制：

- `poll_events` 只能被 `mosd` 调用。
- Role 不能直接调用 event-draining operations。

Role 可用的是非 drain EACN adapter tools，例如：

- `eacn_send_message`
- `eacn_create_task`
- `eacn_submit_bid`
- `eacn_submit_result`
- `eacn_get_task`
- `eacn_list_open_tasks`

Role 不应默认获得：

- `eacn3_get_events`
- `eacn3_next`
- `eacn3_await_events`

因为这些会绕过 MinionsOS journal，隐式消费 EACN queue。

### 3. Sole Poller Invariant

V5 必须强制：

> 对每个 project-local EACN agent id，只允许 `mosd` drain events。

这不是为了削弱 EACN，而是为了保护 EACN-only 语义：所有消息仍来自 EACN，但不会被多个本地
消费者抢先 drain 掉。

Role process 不 poll EACN。Role process 只处理 `mosd` 交给它的 EACN event batch。

### 4. EACN-only Interaction Invariant

新增更强 invariant：

> 任何需要另一个 agent 知道、判断、执行、确认、审阅、引用的内容，都必须作为 EACN
> message/task/result 出现。

具体规则：

- 写 artifact 后，必须发 EACN notification，附 artifact path。
- 写 experiment result 后，必须通过 EACN submit/result 或 message 通知请求方。
- 写 review report 后，必须通过 EACN 通知 Gru/Writer/相关 Role。
- Health monitor 如果发现 actionable issue，必须发 EACN 给 Gru/Noter。
- TUI 的 “wake role” 不能直接写本地 flag，必须创建 EACN message/task。
- Cross-project relay 仍只由 Gru 通过 EACN relay path 完成。
- Scratchpad 只属于当前 Role 自己，不能作为对外留言板。
- Logs 只用于 debug，不能作为 handoff。

### 5. Durable Journal 语义

因为 EACN3 是 drain-on-read，且 ack 不可用，V5 不能承诺真正 exactly-once delivery。

V5 应承诺：

- 一旦 EACN event 被写入 MinionsOS journal，就至少投递一次。
- Role crash 后，lease 过期，event 可重试。
- 重复投递通过 event hash、task id、result id、role-side idempotency 容忍。
- EACN3 HTTP response 返回之后、MinionsOS journal commit 之前的极小 crash window，是不修改
  EACN3 前提下的固有限制。
- V5 通过单一 poller、即时 SQLite WAL transaction、小 batch、metrics 把窗口降到最低。

journal 不是通信源，只是 EACN event 的可靠缓存。

### 6. MinionsOS-Owned State

V5 runtime source of truth 应迁移到 MinionsOS 自己的 SQLite DB。

建议表：

- `projects`
- `roles`
- `agent_identities`
- `event_journal`
- `event_leases`
- `invocations`
- `processes`
- `health_events`
- `artifact_index`

但这些表不能替代 EACN communication。

例如：

- `artifact_index` 可以记录 artifact。
- 但“artifact 已完成”必须通过 EACN message/result 通知。
- `health_events` 可以记录故障。
- 但 actionable fault 必须通过 EACN 发给 Gru/Noter。
- `invocations` 可以记录 Role run。
- 但 Role run 的 outcome 必须通过 EACN task result/message 表达。

### 7. Rust TUI First

新增 `mosctl tui` 作为默认本地 cockpit。

它展示：

- project list
- backend health
- role state
- pending EACN journal events
- leased events
- failed / poisoned events
- scratchpad status
- logs
- EACN task graph
- role invocation history

但 TUI 不能成为通信系统。

TUI 执行动作时：

- wake role -> EACN direct message 或 targeted task
- request review -> EACN task to Reviewer
- request experiment -> EACN task to Experimenter
- notify Gru -> EACN message to Gru queue
- relay -> Gru-mediated EACN relay

TUI 可以读本地状态，但写入语义动作必须进入 EACN。

### 8. Viz 仍然只读

React Viz 或 Rust snapshot server 都只能观察。

它们不能：

- POST/PUT/DELETE EACN3
- 调用 `/api/events/{agent_id}`
- 写本地文件触发 Role
- 作为消息入口

Viz 可以展示 EACN task graph、journal health、logs、artifacts，但不能成为 agent 通信通道。

## 迁移计划

### Phase 0：契约与测试

- 文档化两条硬原则：
  - EACN3 immutable
  - EACN-only interaction
- 增加测试：V5 运行后 `git diff -- EACN3` 必须为空。
- 增加 prompt invariant：Role 不得通过本地文件与其他 Role 通信。
- 定义 MinionsOS EACN adapter interface。
- 定义哪些 EACN operations 是 drain，哪些是 non-drain。

### Phase 1：Rust Observer

- `mosd` 只读 MinionsOS state 和 EACN health。
- 暂不接管调度。
- 输出对齐 `./mos status --json`。
- 不写 `EACN3/`。
- 不引入任何本地通信通道。

### Phase 2：EACN Adapter Tools

- 增加 MinionsOS-owned non-drain EACN tools。
- Role 默认不再使用 raw `eacn3_*` wildcard。
- 明确禁止 Role 直接调用 event-draining tools。
- 所有 Role replies/status/artifact notifications 走 EACN。

### Phase 3：Journal Takeover

- `mosd` 成为唯一 event poller。
- Python `WakeupScheduler` 在 `MINIONS_RUNTIME=rust` 下关闭。
- Role invocation 初期仍可复用 Python prompt/agent-host builder。
- journal 只存 EACN events，不接受本地 synthetic inter-role messages，除非这些 synthetic
  events 同时对应一条真实 EACN message/task。

### Phase 4：Process Supervision

- Rust 接管 backend、Role subprocess、Gru sidecar、experiment reconcile 的监管。
- Python lifecycle functions 变成 `mosd` clients。
- 生命周期操作如果要通知 Role，必须创建 EACN message/task。

### Phase 5：TUI And Runtime Viz

- `mosctl tui` 成为默认操作面。
- Rust read-only snapshot server 替换 Express runtime。
- React Viz 作为可选 frontend artifact。
- TUI/Viz 不成为通信系统。

## 成功标准

- V5 install、test、runtime 后，`git diff -- EACN3` 永远为空。
- 没有 Role process 可以直接 drain EACN queue。
- 所有 event-draining 都通过 `mosd`。
- 所有 Role/Gru/Project 语义交互都能在 EACN task/message/result 中追踪。
- 本地 journal 中的每条待处理事件都能追溯到 EACN event source。
- 写 artifact 后必须存在对应 EACN notification/result。
- Health actionable event 必须通过 EACN 到达 Gru/Noter。
- 已 journaled EACN events 可在 daemon crash/restart 后恢复。
- Role crash 触发 lease retry，而不是 event loss。
- TUI 启动小于 100ms。
- 迁移期间现有 Python unit tests 继续通过。

## 非目标

- 不重写 EACN3。
- 不 patch EACN3 plugin。
- 不依赖 EACN3 内部 SQLite schema。
- 不在 drain-on-read API 上承诺真正 exactly-once delivery。
- 不把本地 SQLite、jsonl、logs、scratchpads 变成 agent 通信机制。
- V5 第一阶段不把 scientific tools、prompts、reviewer assets、paper workflows 迁移到 Rust。

## 最终定位

V5 的正确方向是：

> EACN3 不可变；EACN 是唯一语义交互网络；MinionsOS 用 Rust 建一个可靠 runtime kernel，负责
> 监管、journal、lease、重试、TUI 和只读观测，但不制造第二套通信系统。

Rust 解决的是本地操作系统层问题。

EACN 继续解决 agent collaboration 问题。

Python 继续承载科研能力层。

## V5 的 Rust 划分决策

在 V5 里，Rust 只应该落在那些满足以下条件的地方：

- 规则稳定，变化频率低。
- 出错代价高，且需要强确定性。
- 属于本地运行时，不属于科研语义。
- 能够独立验证，不依赖 EACN3 内部实现。

因此，Rust 最值得承接的是：

- EACN 事件的 journal / lease / retry 这类可靠性内核。
- wake signal / phase snapshot 这类可验证契约的归一化与校验。
- process supervision、只读观测、TUI 这些低层操作面。

Rust 不值得承接的是：

- Role prompt、skill、paper workflow、experiment workflow。
- EACN3 的业务协议本身。
- 任何经常随研究主题变化的协作语义。

换句话说，V5 的 Rust 价值不是“把一切都重写”，而是把最容易抖动、最容易丢状态、最容易在多进程下出错的底层边界固定住。

## 当前落地状态

第一阶段已经新增 root Rust workspace 和 `crates/minions-runtime-core`。

这个 crate 目前只承接稳定、纯函数、可测试的运行时契约：

- `PhasePolicy`：判断当前 phase 允许哪些 role online。
- `RoleRecord` / `RoleState`：归一化 role 的可调度状态。
- `TaskRecord`：抽取 EACN task routing 需要的最小字段。
- `task_router_targets`：决定 public open task、invited role、invited agent id 应该唤醒哪些 role。
- `role_task_domains`：过滤 `minionsos`、`project-local` 这类 generic domain，避免 open task 唤醒所有人。

它刻意不访问 EACN3、不启动 daemon、不处理 prompt，也不替代 Python runtime。当前作用是把 V5 已经形成的 phase/router/wake 边界固化成独立可验证的 Rust contract，后续再逐步把 journal、lease、process supervision 等低层可靠性能力迁入 Rust。
