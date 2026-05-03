# EACN Online Wake Model for MinionsOS V5

版本：v0.1
范围：只讨论 MinionsOS V5 的改造提案，不改 EACN3 本体。
目标：把“唤醒”从“scheduler 代读事件并注入 prompt”改成“允许一个已存在的 Claude/Codex 会话在合适时机自己上 EACN 看网络”。

当前实现注记：后续 v6/v7 hooks 方案和代码实现已经把 public/open task 唤醒收口到
EACN3 原生队列。本文中 `router match` 指 EACN3 已经完成广播并把事件写入 agent
队列后的事实，不表示 MinionsOS 可以本地复刻 domain router。

## 1. 我对当前系统的判断

当前 V5 仍是旧模型：

- `WakeupScheduler` 先替 role poll EACN3。
- 取到的事件被塞进 `invoke_role_ephemeral(...)`。
- `invoke_role_ephemeral(...)` 每次都起一个短生命周期 Claude/Codex 进程。
- `role_inbox` 保存的是已经 drain 出来的事件批次，不是网络原始事实。

这能省 idle token，但它把 `EACN3` 的网络事实、`MinionsOS` 的唤醒策略、以及 `Claude/Codex` 的执行会话绑在一起了。结果就是：

- direct message 变成 prompt 内容，而不是“收信者自己去读消息”。
- task broadcast 变成 scheduler 预加工的事件，而不是 agent 自己上网看任务。
- `Buffered` 变成第二个消息通道，而不是安全兜底。

你要的方向更接近 EACN3 原生设计：

- EACN3 只负责路由、任务、消息、会话。
- MinionsOS 只负责“何时允许这个角色上网”。
- 角色本身醒来后，自己调用 `eacn3_next` / `eacn3_get_events` / `eacn3_list_open_tasks`。

## 2. 术语先讲清楚

`wake`：
不是重启，也不是重新拉起一个临时 subagent。
它的意思是“允许这个已存在的角色会话此刻上 EACN，查看消息、任务和会话状态”。

`resident session`：
不是一次性 `-p` / `--ephemeral` 进程。
它是一个短期常驻的 Claude/Codex 会话，外部只给它发 wake 信号。

`online burst`：
一次被唤醒后的在线处理窗口。
窗口内它可以连续做几步：看事件、查任务、回消息、提交结果、记录 scratchpad。

`cooldown`：
一次在线 burst 结束后，下一次允许上网之前要等待的最短时间。
这是为了省 token，也为了避免 role 频繁抖动。

`compact`：
不是压缩 prompt 文本本身，而是把 scratchpad 里只剩下 durable state。
完成的细节、重复事件、临时推理都要收掉。

`clear/reconnect`：
不是简单“再拉一个新子代理”。
它表示把当前会话的 transient context 结清，写出 checkpoint，然后用清爽状态重新连回网络。

`project phase`：
项目当前处在哪个工作状态，比如 `Plan` / `Discussion` / `Experiment` / `Writing` / `Review` / `Rebuttal`。
它是项目级状态，不是 role 级状态。

`router match`：
EACN3 在发布 task 时按 `domains` 和 `invited_agent_ids` 算出来的候选接收者。
它是任务广播的路由结果，不是权限系统。

## 3. 需要满足的唤醒合同

这四条是我建议作为硬规则写进系统的：

1. `direct_message` 必须唤醒收信对方。
2. task 里被 EACN router 广播到的候选 agent 必须被唤醒。
3. 当前 project phase 允许工作的 agent，可以进入在线窗口。
4. 非当前 phase 的 agent，且也不是该 task router 匹配的 agent，就不要被唤醒。

这里我建议把它理解成：

- `direct_message` 是最高优先级的硬唤醒。
- `task router match` 是第二层硬唤醒。
- `phase allowlist` 是第三层在线资格。
- 两者都不满足，就保持睡眠。

注意：

- “唤醒”不等于“立刻重启一个新 role 进程”。
- “唤醒”也不等于“把事件正文预先塞进 prompt”。
- 它只意味着：现在允许这个 resident session 上网。

## 4. 现状里哪些东西已经能用

V5 已经有一些可复用的骨架。

### 4.1 role 注册已经存在

`minions/lifecycle/role.py` 里，`register_role(...)` 只是注册 AgentCard，不起进程。
`invoke_role_ephemeral(...)` 才是真正拉起 Claude/Codex 的地方。

这说明现有结构已经把“注册”和“执行”分开了，只是执行还停留在 ephemeral 模式。

### 4.2 有 cooldown 和 scratchpad veto

`WakeupScheduler` 已经有：

- `role_cooldown_seconds`
- scratchpad soft/hard/veto threshold
- maintenance compaction wake

所以“在线后做一点事，再停一会儿”这个思想，代码里已经有雏形。

### 4.3 EACN3 原生主循环其实是 agent 自己读网络

`read.md` 里的核心意思是对的：

- `direct_message` 是 1:1 私信。
- `task_broadcast` 是公开任务广播。
- `eacn3_next` / `eacn3_get_events` / `eacn3_await_events` 都是 agent 自己主动取事件。
- `list_open_tasks` 是主动浏览开放市场，不是 scheduler 预读。

这点支持你的方向：**agent 应该自己上网读，而不是 scheduler 替它读。**

## 5. 建议的新架构

我建议把系统拆成三层：

### 5.1 Wake Broker

这是 MinionsOS 的本地唤醒裁决器，不是执行者。

职责：

- 判断某个 role 现在是否允许在线。
- 记录 wake reason 和 wake source。
- 只发 wake permit，不预读事件正文。
- 控制 cooldown、burst count、phase gating。

它做的不是：

- 不代 role poll EACN。
- 不把 EACN 事件正文塞到 prompt。
- 不替 role 处理 task / DM 内容。

### 5.2 Resident Role Session

这是 Claude/Codex 的短期常驻会话。

职责：

- 被 wake permit 触发后，自己上 EACN。
- 先看 `eacn3_next`，必要时看 `eacn3_get_messages` / `eacn3_get_task` / `eacn3_list_open_tasks`。
- 处理完这一轮后回到 dormant 或 cooldown。
- 在满足 burst/phase/compact 条件时，写 scratchpad checkpoint，再重新进入清爽状态。

### 5.3 Project Phase State

这是项目级状态源，由 Gru 决定。

职责：

- 保存当前 phase。
- 保存 phase reason / phase version。
- 告诉 wake broker 当前阶段允许哪些角色 online。
- 接收 role 提出的 phase transition proposal，由 Gru 裁决。也可以由Gru自己决定Phase。

## 6. Phase 模型建议

建议把 phase 变成一个真实状态，而不是 vocabulary。

可用阶段：

- `Plan`
- `Discussion`
- `Experiment`
- `Writing`
- `Review`
- `Rebuttal`
- `Camera-ready`
- `Closed`

建议 allowlist：

| Phase | 建议可 online 的角色 |
| --- | --- |
| Plan / Discussion | expert, coder, ethics |
| Experiment | experimenter, coder, expert, ethics |
| Writing | writer, expert, ethics |
| Review | reviewer, ethics |
| Rebuttal | writer, reviewer, expert, coder, ethics |
| Camera-ready | writer, expert, coder, ethics |
| Closed | 只保留 direct message / 管理类唤醒 |

这不是硬编码真理，而是一个第一版可讨论的默认矩阵。

## 7. Cooldown 和 compact 规则

### 7.1 Cooldown

建议把 cooldown 拆成两个概念：

- `soft cooldown`：在线 burst 完成后，下一次允许上网前至少等一段时间。
- `hard cooldown`：短时间内连续 compact / 连续被唤醒失败时，强制多等一点。

默认值我建议先按可配置来定，不要写死。
如果要给一个起点，我倾向：

- 常规默认：`180s`
- 某些高频阶段可降到：`60s`

这比现在的 30s 更接近你说的“做完一次事情之后，隔一会儿再上网”。

### 7.2 Productive wake

一次 wake 不应该按“被叫醒一次”计数，而应该按“真的做了有用网络处理”计数。

我建议定义为满足以下任一条件就算 productive：

- 读到了新的 EACN 事件。
- 发出了有效 reply / bid / result / clarification。
- 通过 `eacn3_next` 推进了任务状态。

### 7.3 5 次后 compact

建议默认：

- 连续 5 次 productive wake 后，强制 compact 一次。
- compact 后继续工作，不是停机。

如果短期内连续 compact：

- 说明会话太碎、phase 变化太频繁、或者 scratchpad 管理失控。
- 这时下一次看网络前，必须强制写 scratchpad summary，做 checkpoint，然后 `clear/reconnect`。

## 8. `clear/reconnect` 的语义

这个词我建议在 V5 里定义成一个正式动作，而不是口头说法。

含义：

1. 把本轮在线 burst 的 durable state 写进 scratchpad。
2. 把当前 phase、online roles、未决事项、未解决分歧记下来。
3. 把 transient 推理、重复事件、没价值的上下文清掉。
4. 让 session 重新进入干净状态。
5. 下一次 wake 时再继续，而不是带着很脏的上下文接着滚。

如果 host 支持 session resume：

- Claude 可以优先走 `--resume` / `--continue` 语义。
- Codex 可以优先走它的 `resume` 能力或等价的 session 恢复方式。

如果 host 不支持真正 resident：

- 退一步，用“持久 session id + 外部 wake broker”实现语义上的连续性。

## 9. 这件事和现有代码的关系

### 9.1 `WakeupScheduler`

现在它是“代 role drain + 代 role dispatch”。

改造后建议变成：

- 只做 wake 裁决。
- 不再把 EACN payload 提前灌给 role。
- 只发 wake permit / wake hint。

### 9.2 `role_inbox`

现在它是 drained event 的本地 buffer。

改造后建议缩小成：

- wake intent buffer
- maintenance buffer
- safety replay buffer

也就是只保存“唤醒决策”或“checkpoint 相关元数据”，而不是 EACN 的正文。

### 9.3 `invoke_role_ephemeral`

现在它是一次性短跑。

改造后建议拆成：

- `start_role_session(...)`
- `wake_role_session(...)`
- `compact_role_session(...)`
- `clear_role_session(...)`

也就是把“执行”从“启动一次进程”改成“控制一个可复用的会话”。

### 9.4 `project_phase`

现在没有这个状态。

建议新增到项目状态里，作为 Gru 可读可写的项目级字段。

### 9.5 `project_eacn_send_message` / `project_eacn_create_task`

这些本地入口应该可以顺手发 wake permit：

- 直接消息发给某个 role 时，立刻 wake 目标会话。
- 发布 task 后，立刻 wake router 匹配到的候选会话。

这样本地创建的事件就不需要等外部 sweep。

## 10. 真实落地时我建议的顺序

第一步：
把“唤醒”和“事件正文交付”解耦。

第二步：
把 project phase 做成真实状态，让 Gru 裁决 phase transition。

第三步：
把 role session 改成 resident / resumable，而不是一次性 ephemeral。

第四步：
把 `role_inbox` 缩成 wake intent / checkpoint buffer。

第五步：
把 cooldown、burst、compact、clear/reconnect 变成明确状态机。

## 11. 主要风险

1. **Claude/Codex 的 resident 能力要验证。**  
   现有 launcher 还是以 ephemeral 为主，必须确认 host 的 resume/session 能力足够稳定。

2. **如果完全不做任何 sweep，远端事件可能晚到。**  
   所以我建议至少保留一个很轻的 wake reconciler，用队列 metadata 或本地发布钩子来触发，而不是读正文。

3. **phase state 需要 Gru 裁决。**  
   不然角色自己切 phase 会把 system 变成另一个失控的自动机。

4. **burst / compact 规则如果太紧，会把 token 省掉，但把协作切碎。**  
   所以它必须是可配置的，不该死写。

## 12. 我现在的建议

我建议把 V5 的这次改造理解成一句话：

**从“scheduler 代 role 读 EACN”升级成“wake broker 只决定谁可以上网，role 自己上 EACN 读网络”。**

这和你现在的目标是一致的：

- direct message 直唤收信者。
- task router match 唤候选者。
- phase 允许的角色在对应阶段可在线。
- 其他角色保持睡眠。
- 唤醒后是 online burst，不是重启。
- 连续 productive wake 5 次后 compact。
- 连续 compact 或 phase 变化时强制 checkpoint / clear / reconnect。
