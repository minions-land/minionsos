# Question

我现在关于这个项目，收集了五个用户反馈，你需要根据用户反馈在我们的项目里面调研，了解，评估，然后给出这个反馈的真实
  性以及解决潜在问题的proposal。你需要充分思考ultrathink
 
  1-Buffered现在很容易堆积。就是堆一大堆。你了解一下现在Buffered的形式，看看这些bufferd都是什么东西，然后有没有办法
  在唤醒role之前给buffered做一次合并处理，比如可以把当前的buffered按照某种templete去给到模型（相当于做一次compact，
  但是是有规律的compact，比如opentask的合并等）。或者buffered只在网络断了的情况下用，正常情况就是单纯上网络去看。而
  且这个EACN3网络似乎有留存能力。所以似乎Buffered作用是没有的。反正这一块有这个疑惑，你要从好用，剩tokens，并且充分
  发挥EACN3本身的智能体涌现 能力的角度。这个角度需要你充分了解buffered里面存什么。
 
  2-目前./noter的Task显示有误，都是12，但是12是./noter里面显示的最大task数量，实际上远比这个多。然后我希望加入更多
  的，比如direct message，或者详细对Task做分类，比如opentask，裁决任务等；以及目前./noter里面的Role板块的Task的现实
  永远都是-，似乎大家都没在接任务？我觉得这块需要详细调研EACN3里面的特征（但是不能改EACN3里面的代码），然后根据这个
  设计更好的./noter展示界面。现在的界面已经非常好了，我只是觉得一些细节可以更加丰富一点。可以保持现在的模式，只是增
  加更多的细节。
 
  3-目前的用户反馈，系统似乎不会自己进行实验，这块了解一下MinionsOS系统是怎么进行实验的。有用户反馈说需要权限才能做
  实验。
 
  4-Noter目前还是记录的太频繁了，用户反馈5min就记一次，太频繁了，建议改成30min生成一个报告就好了。充分了解目前Noter
  记笔记的模式。
 
  5-Last but not least：目前我觉得Tokens压力有点大，两个方面吧，一个是我觉得是不是当前Prompt一次暴露的太多了，对于每
  个role。另一个就是实际上其实Agent是有缓存机制的，就是如果命中缓存还是挺便宜的。我觉得可以做完一个任务之后可以
  cooldown个30s，继续上去进行一波轮询，如果没有自己的事情再下线然后cool down一下，有自己的事情就继续做，做到一定程度
  的上下文积累的后（比如连续上线做5次任务后）就写scatchpad下线cooldown。总而言之就是我们希望要省一点tokens。现在
  tokens消耗很大。另一个就是现在一下叫起所有的role不太现实，我觉得总体分为调研，辩论，代码，实验，写作，审稿阶段吧，
  不同阶段是可以反复往跳的，阶段的切换由Gru决定，也可以由role决定。如果role决定换任务，这个需要Gru进行裁决，裁决通过
  就切换。不同阶段允许open task唤醒的role是不同的（但是direct message是可以唤醒的）。为了实现这个目的，需要让role动
  态知道，此时是哪个阶段，会有哪些role在线
 
  充分了解以上五个机制，充分调研，然后对我进行解释，以及讨论和proposal确定。你可以用第一性原则来思考和argue


# MinionsOS Runtime Feedback Proposal

版本：v0.1
日期：2026-04-30
范围：只记录调研结论和修改 proposal，暂不修改 EACN3 代码。

## 总体判断

这五条反馈大体都指向同一个系统性问题：MinionsOS 现在已经有事件驱动、短生命周期 role、EACN3 持久队列、scratchpad、Noter 观察面板和实验队列，但这些机制之间的边界还不够清楚。结果是：

- 本地 Buffered 从“可靠性 retry journal”滑向“第二个任务队列”。
- `./noter` 显示的是局部窗口，却看起来像全局事实。
- 实验能力存在，但入口、权限和 readiness 对用户不透明。
- Noter 的模型报告频率和 terminal 刷新频率容易被混淆。
- Token 成本主要来自过多 role 被 open task 唤醒，以及每次唤醒暴露过多静态 prompt 和未压缩事件。

原则上，修改方向应该是：

1. EACN3 的 task/message store 继续做网络事实源。
2. MinionsOS 本地 buffer 只做“已经 drain 出来的事件”的可靠性保护。
3. 对模型输入做确定性 compact，而不是用另一个模型先总结一遍。
4. public open task 只唤醒当前阶段真正可能参与的 role；direct message 永远可以唤醒目标 role。
5. Noter 展示要明确“窗口、总量、分类、来源”，避免把展示限制误读成系统状态。

## 1. Buffered 堆积

### 真实性判断

反馈基本成立，但需要精确定义。

`Buffered` 不是 EACN3 网络里的离线队列，而是 MinionsOS 自己为每个 role 写的本地 retry journal：

- 代码位置：`minions/lifecycle/role_inbox.py`
- 文件形式：`project_<port>/logs/veto_buffer-<role>.jsonl`
- 每行格式：`{"event": <raw event>}`

它存在的原因是 EACN3 的 `/events/{agent_id}` 是 drain-on-read：一旦 scheduler 从 EACN3 取走事件，EACN3 端就删除这些事件。MinionsOS 如果在 drain 之后、role 真正启动之前崩溃，事件会丢。所以当前设计会在 dispatch 前先把这批事件写入本地 buffer，dispatch 成功后再清掉。

用户关于“EACN3 似乎有留存能力，所以 Buffered 作用是不是没有”的判断有一半正确：

- 正确部分：EACN3 确实有离线留存，默认每个 agent 最多 200 条、TTL 86400 秒。因此在还没有 poll/drain 前，不应该急着把事件搬到本地。
- 不正确部分：一旦 MinionsOS 已经 drain 了 EACN3，本地必须有 retry journal，否则 dispatch 失败会丢消息。

所以问题不在于 Buffered 完全没用，而在于它现在承担了太多职责：既做可靠性保护，又承接 cooldown、role in-flight、scratchpad veto、dispatch fail、open-task scan 等调度背压。

### 当前 Buffered 里会存什么

从现有 scheduler 流程看，本地 buffer 可能包含：

- EACN3 原始事件：`direct_message`、`task_broadcast`、`bid_result`、`adjudication_task` 等。
- synthetic open task 事件：`id = open-task:<task_id>:<role>`，来源是 scheduler 主动 `list_open_tasks` 扫描后合成的 `task_broadcast`。
- synthetic time trigger：例如 Noter 的周期性 `time_trigger`。
- scratchpad veto 相关的被保留业务事件；veto 时 role 只会先被唤醒做 scratchpad compaction，真实业务事件继续留在 buffer。

当前关键流程在 `minions/lifecycle/wakeup.py`：

1. 每 tick 先读本地 `role_inbox.read_events`。
2. 到达 poll interval 后调用 EACN3 `poll_events`。
3. 再把 open task scan 合成的事件追加进去。
4. 只要 `new_events` 非空，就先 `role_inbox.replace_events(...)`。
5. 再尝试 dispatch role。
6. dispatch 成功才 `role_inbox.clear(...)`。
7. 如果 role 仍在 in-flight、有 live PID、cooldown 中、scratchpad veto、或 dispatch 失败，就继续 `replace_events(...)` 留在 buffer。

这解释了为什么 Buffered 容易堆积：scheduler 会先把事件拿到本地，再检查能不能真正让 role 消费。只要 role 暂时不能消费，本地 buffer 就变成等待区。

### 第一性原则分析

事件应分成三类处理：

1. 必须无损的事件：direct message、adjudication、bid_result、任务结果、明确发给某个 role 的消息。这类不能随便摘要、不能丢。
2. 可从 EACN3 task store 重建的市场信号：open task、task broadcast、任务状态快照。这类不应该无限进入本地 buffer。
3. 派生触发器：time trigger、scratchpad maintenance、health/status trigger。这类通常只需要最新一次。

因此，本地 buffer 的正确定位应该是：

- 它是“drained retry journal”，不是“任务队列”。
- 它只保护已经从 EACN3 destructive drain 出来的事件。
- 它不应该在 role 明显不能启动时继续主动 poll EACN3。
- 它可以对模型输入做确定性 compact，但 compact 规则必须保留可追溯性。

### Proposal 1A：dispatch readiness 先于 EACN drain

把 `_tick` 的顺序调整为：先判断这个 role 现在是否有机会启动，再决定是否 poll EACN3 或合成 open-task 事件。

建议规则：

- 如果 role 仍 in-flight：不 poll EACN3，不追加 open-task scan，只保留已有本地 buffer。
- 如果 role 有 live PID：不 poll EACN3，不追加 open-task scan。
- 如果 role 在 30s cooldown：不 poll EACN3，不追加 open-task scan。
- 如果 scratchpad 达到 veto：优先发 maintenance compaction；业务事件留在本地，不继续扩大本地 buffer。
- 如果本地 buffer 为空且 role 不 ready：完全不做网络 drain，让事件继续留在 EACN3 离线队列里。

这样可以直接减少 Buffered 膨胀，因为正常的短期背压不会把 EACN3 队列搬到本地。

风险：

- 如果某个 role 长时间不 ready，EACN3 的 per-agent offline queue 仍有 200 条上限和 24h TTL。
- 但这个风险比本地无限堆积更可控，而且 open task 可以从 task store 重新扫描，不依赖离线消息逐条保存。

### Proposal 1B：dispatch 前做确定性 inbox compact

在 role 真正唤醒前，把 `buffered + newly_polled + synthetic_open_tasks` 经过一个纯函数 compact：

```text
compact_events(events) -> compacted_events
```

建议按类型处理：

| 类型 | compact 策略 |
| --- | --- |
| `direct_message` | 不摘要、不丢正文；按 sender/thread 分组为 batch，保留每条 message id、timestamp、content。 |
| `task_broadcast` / `open-task:*` | 按 `(task_id, role)` 合并，只保留最新 task payload，附带 `compacted_from_count`、`first_seen`、`last_seen`、`matched_by`。 |
| `discussion_update` | 按 `task_id` 合并，保留最新状态和最近 K 条讨论片段；过长原文落盘 archive 并给路径。 |
| `bid_result` / `task_collected` / `task_timeout` | 按 `task_id` 保留最新终态或关键状态变化，保留原始 event ids。 |
| `adjudication_task` | 按 `task_id` 保留最新 adjudication payload；不能丢。 |
| `time_trigger` | 多个合并成最新一个。 |
| `scratchpad_compaction_required` | 多个合并成最新一个。 |

这个 compact 不应该调用模型。理由：

- 省 token 的关键是少给模型重复结构，而不是多调用一次模型。
- direct message 和裁决类事件带有协作语义，模型摘要可能改变含义。
- 确定性 compact 可测试、可审计、可复现。

建议 compact 后的事件加 metadata：

- `compacted: true`
- `compacted_from_count`
- `raw_event_ids`
- `first_seen`
- `last_seen`
- `archive_path`，如果原始 payload 太大而落盘。

### Proposal 1C：open task 不再长期进入本地 buffer

open task 更像市场快照，不是必须逐条可靠投递的私信。

建议：

- 如果 role 当前不 ready，不做 open task scan。
- 如果 role ready，scan 后只把“当前最相关的候选任务快照”注入本次 prompt。
- 如果 dispatch 失败，可以短暂写入 retry buffer；下一次 ready 时应重新从 EACN3 task store 取最新状态并合并，而不是一直 replay 老的 open-task event。

这会更符合 EACN3 的涌现协作模式：task store 是共享市场，role 醒来时看当前市场，而不是消费一堆过期广播。

### Proposal 1D：Noter UI 改名和细分

`Buffered` 这个名字容易让用户误以为是 EACN3 网络 buffer。建议改成：

- `Local retry`
- 或 `Drained retry`

同时显示类型分布，例如：

```text
Local retry: 18 (dm=3, open_task=12, task=2, timer=1)
```

如果 buffer 长时间增长，Noter 可以显示原因：

- `role in-flight`
- `cooldown`
- `scratchpad veto`
- `dispatch failed`
- `live PID`

### Proposal 1E：落地顺序

建议实现顺序：

1. 新增 `role_inbox.compact_events(events)` 纯函数和单元测试。
2. 在 `wakeup.py` 中加入 “readiness-before-drain” gate。
3. 把 open-task synthetic event 改成“ready 时的市场快照”，并只在 dispatch 失败后短期 retry。
4. Noter 把 `Buffered` 改名并显示 event type breakdown。
5. 加入 buffer size/age guard：超大 payload 落盘 archive，prompt 中只给路径和摘要 metadata。

### 第 1 项待讨论决策点

我建议我们先确认这些决策：

1. 是否接受 `readiness-before-drain` 作为 P0？推荐接受。
2. direct message 是否绝不做内容摘要，只做结构化分组？推荐接受。
3. open task 是否从“本地可积压事件”改成“ready 时读取的市场快照”？推荐接受。
4. 本地 retry 是否允许设置 size/age 上限，超限时只 archive 原文并把 pointer 给模型？推荐接受。
5. UI 名称用 `Local retry` 还是 `Drained retry`？我倾向 `Local retry`，用户更容易理解。

## 2. `./noter` Task 与 Role 展示

### 真实性判断

反馈成立。

现在 `./noter` 顶部的 `tasks=12` 实际只是当前页面展示数量，因为 `minions/cli.py` 的 `--max-tasks` 默认是 12，`minions/lifecycle/noter_terminal.py` 里直接显示 `len(snapshot.tasks)`。这不是 EACN3 task 总数。

Role 表里的 `Task` 来自 state store 的 `current_task` 字段，但现有系统没有稳定地在 bid、execute、submit、complete 等节点维护它，所以大多数 role 永远显示 `-`。

### Proposal

不改 EACN3 代码，只在 MinionsOS 侧增强 read-only 展示：

1. 把顶部 `tasks=12` 改成更明确的 `tasks_shown=12`。
2. 增加 task summary：按 status 分类统计，例如 `open/bidding/executing/awaiting_retrieval/completed/no_one`。
3. 增加 task 类型视图：public open task、direct/invited task、adjudication task、subtask、result/collection。
4. Role 表的 `Task` 改成 `Current / inferred`：
   - 优先显示 state store `current_task`。
   - 如果为空，从 EACN task bids/results 中推断该 role 最近参与的 task。
   - 推断值要标记为 `inferred`，避免当成强事实。
5. 增加 direct message / unread 观察：
   - 不 drain role 队列。
   - 优先读本地 retry buffer、Gru inbox、Noter audit mirror、EACN 本地 SQLite 只读统计。
   - 如果只能拿到估算值，UI 必须标 `observed` 或 `estimated`。

## 3. 系统不会自己实验 / 实验需要权限

### 真实性判断

反馈部分成立。

MinionsOS 已经有 Experimenter role、`exp_*` MCP 工具和 Python-side experiment queue reconcile。实验不是完全不存在。但用户感受到“不会自己实验”是合理的，因为实验入口、目标机器 readiness、权限边界和失败原因现在不够可见。

“需要权限”可能来自：

- 非 Experimenter role 试图调用 `exp_*` 工具，被 MCP 权限挡住。
- `experiment_targets.yaml` 没有配置，或者用户不知道 local target 怎么用。
- 远程 SSH/GPU target 需要凭据。
- Gru prompt 明确要求 Gru 不直接使用 `exp_*`，而是委托 Experimenter。

### Proposal

1. 增加 `mos experiment doctor` 或 Noter/Gru 状态块，显示：
   - configured targets
   - local target 是否可用
   - queue length
   - last failure
   - credential missing / permission denied 的具体原因
2. 对新项目默认准备 local experiment workspace，并清楚显示“本地实验可用/不可用”。
3. Gru 只能提出实验需求，Experimenter 负责排队和执行；这个边界保留。
4. 当实验失败是权限问题时，让 Experimenter 产出结构化 remediation，而不是只报错。

## 4. Noter 记录太频繁

### 真实性判断

反馈对旧项目或旧配置可能成立；对当前默认配置不完全成立。

当前默认 `noter_report_interval` 已经是 `30m`：

- `minions/config/__init__.py`
- `minions/config/gru.yaml.example`

但旧项目可能在 `projects.json` 里已经存了 `time_trigger_interval: "5m"`，不会自动随新默认值迁移。另一个容易混淆点是 `./noter --interval` 默认 30 秒，这是 terminal 刷新频率，不是模型生成报告频率。

### Proposal

1. 增加旧项目 migration：如果 Noter 的 5m 来自旧默认值，而不是用户显式设置，则迁移为 config 默认 30m。
2. Noter terminal UI 明确显示：
   - `terminal_refresh=30s`
   - `noter_report_interval=30m`
3. Noter time trigger 如果没有新 EACN 活动、没有 artifact 变化、没有健康状态变化，则跳过生成正式报告或生成 cheap heartbeat，不唤醒模型。
4. 支持 on-demand Noter 报告：用户需要时 `wake` 或 direct message Noter。

## 5. Token 压力、Prompt 暴露、Cooldown 与阶段唤醒

### 真实性判断

反馈成立。

token 压力主要来自两处：

1. 每次 role 唤醒都会加载较大的静态 prompt、common contract、技能摘要和事件 JSON。
2. public open task 会让多个 role 同时被唤醒，导致 token 成本乘以 role 数。

另外，Gru 的 phase 现在只是 vocabulary，不是 enforced state。也就是说，系统会说“Plan / Experiment / Writing / Review”，但 scheduler 不会根据 phase 限制哪些 role 可以被 public open task 唤醒。

### Proposal

1. 引入项目 runtime phase state，由 Gru 维护：
   - `research/survey`
   - `debate/plan`
   - `code`
   - `experiment`
   - `writing`
   - `review`
   - `rebuttal/camera-ready`
   - `closed`
2. phase 只 gate public/open-task wakeups；direct message 永远能唤醒目标 role。
3. 每次 role prompt 只注入一个小型 runtime context：

```text
current_phase
phase_reason
allowed_open_task_roles
online_roles
recent_phase_decisions
```

4. 默认 phase-role gate：

| Phase | 允许 public open task 唤醒 |
| --- | --- |
| research/survey | expert, ethics |
| debate/plan | expert, coder, ethics |
| code | coder, expert |
| experiment | experimenter, coder, expert, ethics |
| writing | writer, expert, ethics |
| review | reviewer, writer, ethics |
| rebuttal/camera-ready | writer, reviewer, expert, ethics |
| closed | 无；只响应 direct message |

5. role 可以提出 phase transition，但必须由 Gru 裁决并记录原因。人类命令优先级最高。
6. 增加 bounded burst activation：
   - 一个 role 完成任务后，最多继续短轮询 30 秒。
   - 如果还有明确属于自己的事件，可以连续处理。
   - 连续处理 5 个 batch 后必须写 scratchpad/checkpoint 并下线 cooldown。
   - 所有 drain 出来的事件必须先进入 journal，避免短轮询中途失败丢消息。
7. Prompt 瘦身：
   - role SYSTEM 保留稳定 contract。
   - 每次唤醒只注入 diff/phase/event compact。
   - 大型技能说明改为按需引用路径或短 manifest。
   - 对可缓存的静态 prompt 保持稳定，动态内容后置，最大化 provider prompt cache 命中。

## 推荐讨论顺序

1. Buffered / Local retry：先解决事件可靠性和 token 膨胀的根。
2. Noter 展示：让用户能看懂系统状态，避免误诊。
3. Noter 频率：区分 terminal refresh 和 model report。
4. Experimenter readiness：把“能不能实验、为什么不能”变成可观察事实。
5. Phase gating + token policy：这是更大的调度策略改造，应在前几项稳定后做。
