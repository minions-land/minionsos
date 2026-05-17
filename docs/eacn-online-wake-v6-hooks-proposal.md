# EACN Online Wake Hooks Proposal for MinionsOS

版本：v0.2
范围：只改 MinionsOS 的 wake/runtime，不改 EACN3 协议
核心判断：唤醒走 hooks，Role 会话常驻，问题先 compact；compact 过于频繁时，先写 scratchpad checkpoint，再 `/clear`。

## 1. 结论先说

我建议把现有的“轮询驱动唤醒”改成“hooks 驱动唤醒”：

- EACN3 仍然是网络事实源。
- MinionsOS 不再替 Role 代读正文事件。
- wake 的入口改成 hooks。
- 每个 Role 的会话保持常开，不再按事件临时起停。
- session 自己上 EACN3 读网络、处理任务、写回复。
- 真正有问题时，先 compact；compact 一直触发，就把 durable state 写进 scratchpad，然后 `/clear`。

这不是把调度拿掉，而是把调度改成“发唤醒信号”，不再“代读代办”。

## 2. 这个提案要解决什么

当前旧模型的核心问题不是“能不能工作”，而是边界太厚：

- scheduler 先 poll EACN3。
- scheduler 再决定哪些事件该给哪个 Role。
- scheduler 还把事件正文打包进 ephemeral 会话。
- Role 自己看见的不是网络原始事实，而是被加工过的批次。

这样会带来三个副作用：

1. 正文交付和唤醒决策绑死。
2. 会话是短跑式的，状态连续性弱。
3. inbox / buffer 容易变成第二个消息系统。

你的提议很明确：

- wake 用 hooks。
- session 全部常开。
- 有问题先 compact。
- compact 太多次，就写 scratchpad，然后 `/clear`。

这条线我赞成。

## 3. 新系统合同

### 3.1 唤醒合同

任何会触发实际工作的事件，都应该通过 hook 进入 resident session：

- `direct_message`
- `task_broadcast`
- `adjudication_task`
- `task_timeout`
- `result_submitted`
- `discussion_update`
- `subtask_completed`
- project phase 变化
- scratchpad 维护事件
- 人工触发

hook 的职责只有一个：生成 wake intent。

hook 不做这些事：

- 不替 Role 读完整事件正文。
- 不替 Role 决定业务结论。
- 不把网络事件塞成“半加工 prompt”。

### 3.2 会话合同

每个 Role 对应一个 resident session：

- session 默认常开。
- wake 不等于 spawn 新进程。
- wake 只是把 hook 信号送到已有 session。
- session 自己决定是否立即读 EACN、是否继续处理、是否 compact。

### 3.3 存储合同

scratchpad 是 durable state。

它只保存这些东西：

- 未决任务
- 尚未写入外部系统的决策
- 关键上下文
- 待确认依赖
- 需要跨 wake 保留的事实

它不保存这些东西：

- 完整对话转录
- 已完成任务的过程细节
- 低价值重复推理
- 纯临时工作上下文

## 4. Hook 结构

我建议把 hook 分成两层。

### 4.1 生命周期 hooks

沿用现有 `LifecycleEvent` 风格，用来表达项目和 Role 生命周期：

- `project_created`
- `project_revived`
- `role_dispatched`
- `role_completed`
- `role_dismissed`
- `review_completed`

它们负责状态变化，不负责业务正文。

### 4.2 Wake hooks

新增一层面向 wake 的 hooks，专门接 EACN 和运行时信号：

- EACN 入站事件
- project phase 变化
- scratchpad 维护
- manual wake

wake hook 的输出是一个轻量 `WakeIntent`，建议字段如下：

| 字段 | 含义 |
|---|---|
| `project_port` | 项目端口 |
| `role_name` | 目标 Role |
| `reason` | 唤醒原因 |
| `source_event_id` | 来源事件 id |
| `source_type` | `direct_message` / `task_broadcast` / `maintenance` 等 |
| `urgency` | `high` / `normal` / `maintenance` |
| `dedup_key` | 去重键 |
| `compact_hint` | 是否建议先 compact |

wake hook 不应该携带完整任务正文。正文仍然由 Role 自己去 EACN 取。

## 5. 触发矩阵

| 触发源 | 目标 | 动作 |
|---|---|---|
| `direct_message` | 收信 Role | 立即 wake |
| `task_broadcast` | domain / invited 匹配的 Role | wake |
| `adjudication_task` | 匹配裁决 Role | wake |
| `result_submitted` | 相关 initiator / adjudicator | wake |
| `task_timeout` | initiator + active executors | wake |
| `discussion_update` | task 参与者 | wake |
| `subtask_completed` | parent executors | wake |
| phase change | 当前 phase allowlist | wake 或保持 hot |
| scratchpad soft/hard/veto | 对应 Role | compact / maintenance wake |
| human trigger | 指定 Role | wake |

这里最重要的是：**hook 触发的是 session 热度，不是业务结论。**

## 6. Resident session 的行为

### 6.1 Wake 后做什么

session 被 hook 唤醒后，自己按需做下面这些动作：

1. 读 `eacn3_next` 或 `eacn3_get_events`。
2. 必要时读 `eacn3_get_task`、`eacn3_get_messages`、`eacn3_list_open_tasks`。
3. 对消息、任务、裁决、澄清做业务处理。
4. 写结果、发消息、bid、submit、select、update。
5. 更新 scratchpad。

### 6.2 不再做什么

session 不再依赖 scheduler 预先把正文喂进来。

它也不应该：

- 每次被唤醒就创建新会话。
- 把 inbox 当作主消息系统。
- 把 buffered event 当作事实本身。

### 6.3 常开会话的含义

“全部开着”不一定等于一个永远忙碌的前台进程。

更准确地说，是：

- 每个 Role 都保留一个可恢复的 resident 会话对象。
- 会话的逻辑身份不变。
- 运行时可以短暂 idle，但不因为一次 wake 就销毁重建。

## 7. Compact 和 `/clear`

这是这版 proposal 的关键。

### 7.1 compact 的语义

compact 不是“省略信息”，而是“压缩到 durable state”。

compact 之后应保留：

- 当前未完任务
- 关键事实
- 决策依据
- 未解决分歧
- 下一步动作

compact 之后应丢弃：

- 重复事件
- 已处理完的对话
- 临时推理链
- 与当前工作无关的历史噪声

### 7.2 什么时候 compact

建议 compact 在这些情况下触发：

- scratchpad 进入 soft/hard 区间
- session 连续处理多个 hook 后上下文开始膨胀
- 发生明显状态漂移
- 同一任务反复回到同一推理点
- 业务事件很少，但上下文已经很脏

### 7.3 什么时候 `/clear`

`/clear` 是 hard reset，但不是失忆。

触发条件建议是：

- compact 连续发生太多次
- scratchpad 总是回到阈值上方
- session 结构已经不适合继续滚动
- 模型上下文已经不再稳定

进入 `/clear` 前必须先做 checkpoint：

- 当前在办任务
- 已完成事项
- 未决问题
- 重要结论
- 后续恢复点

然后才清掉 transient context，再从 scratchpad 恢复。

## 8. 我建议的状态机

可把 session 状态简化成这几个：

| 状态 | 含义 |
|---|---|
| `open` | 会话存在，可接 hook |
| `hot` | 正在处理 wake |
| `compacting` | 正在原地压缩上下文 |
| `checkpointing` | 正在写 durable state |
| `clearing` | 正在做 `/clear` 后重建 |

这里不再把“sleeping = 退出会话”当作默认状态。

## 9. 可靠性策略

### 9.1 去重

hook 必须幂等。

同一个事件重复到达时：

- 不能重复唤醒同一任务链条。
- 不能重复写同一条 wake intent。
- 不能因为重复 hook 把 session 轰炸到失控。

### 9.2 hook storm 合并

短时间内大量相同类型事件到达时，应合并成一次 wake：

- 同任务的多条更新合并成一个 intent。
- 同 Role 的多个 wake 合并成一个 hot window。
- 维护事件优先级高于业务事件。

### 9.3 失败恢复

如果 hook 丢了或 session 崩了：

- 先恢复 session 状态。
- 再从 durable metadata 复原未处理 wake intent。
- 只在恢复场景做轻量 reconciliation。

不把 steady-state 建立在轮询正文上。

## 10. 对现有模块的影响

### 10.1 `minions/lifecycle/hooks.py`

建议继续作为 hook registry 的骨架，但把它从“纯生命周期事件”扩展成“生命周期 + wake intent 事件”。

### 10.2 `minions/lifecycle/wakeup.py`

这层建议从“poll + dispatch”改成“hook relay + resident session control”。

它不再是主 poller。

### 10.3 `minions/lifecycle/role.py`

建议补出 resident session 语义：

- `open_role_session(...)`
- `wake_role_session(...)`
- `compact_role_session(...)`
- `clear_role_session(...)`

现有的 ephemeral 启动可以保留给兼容路径，但不该再是主路径。

### 10.4 `minions/lifecycle/role_inbox.py`

建议缩到 fallback 用途：

- 只放 wake intent
- 只做恢复缓冲
- 不再放完整 EACN 正文

### 10.5 scratchpad

scratchpad 从“可选记忆”变成“恢复锚点”。

它是 `/clear` 之后的重建依据，不是消息中转站。

## 11. 和旧 proposal 的差别

| 维度 | 旧 proposal | 新 proposal |
|---|---|---|
| wake 入口 | scheduler poll | hooks |
| 会话模型 | ephemeral | resident |
| 事件正文 | scheduler 代读并注入 | Role 自己读 EACN |
| inbox | 主缓冲 | fallback 缓冲 |
| context 管理 | burst + cooldown 为主 | compact + `/clear` 为主 |
| 失败恢复 | 继续轮询 | checkpoint 后重建 |
| 主责任 | 调度器 | hook + session |

## 12. 我对这版的判断

这版的好处是边界更清楚：

- wake 只负责“叫醒谁”。
- Role 只负责“醒来后怎么处理网络”。
- scratchpad 只负责 durable state。
- `/clear` 只在上下文已经不值得继续滚动时使用。

它也更接近你说的那句话：

**所有会话都开着，问题先 compact；compact 过多，就写 scratchpad，然后 `/clear`。**

## 13. 需要你确认的几个选择

我建议你先拍板这三点：

1. `clear` 是不是允许重建同一个逻辑 session，而不是生成新身份。
2. `compact` 是不是默认每次 wake 后都可触发，还是只在阈值上触发。
3. `role_inbox` 要不要彻底退到 fallback，还是保留少量 steady-state 缓冲。

如果这三点对齐了，后面就可以把旧的 poll-first 方案直接收掉，改成 hook-first 方案。
