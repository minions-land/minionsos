# EACN Workspace / Session / Push Proposal for MinionsOS V5

版本：v0.1
范围：在 `v6-hooks` proposal 基础上，新增 workspace 规划、常驻 PID、命名 session、以及本地 commit / 可选 GitHub push 机制。
关系：重复的唤醒、phase、compact、`/clear` 语义，以 [`eacn-online-wake-v6-hooks-proposal.md`](./eacn-online-wake-v6-hooks-proposal.md) 为准。

## 1. 先给结论

我建议把 V5 的运行模型再往前推一层：

- `workspace` 不再只是单一编辑目录，而是一个严格的工作区容器。
- 每个 active role 都有自己的 canonical 工作区。
- 每个 role 的 Claude / Codex PID 常驻，不再按事件临时起停。
- 唤醒不靠 cron 轮询 EACN3，而靠 hooks。
- 每个 role 都有稳定的 `session_name`，kill 后可按同名恢复。
- 每次形成 durable checkpoint 就 commit；如果配置了远端目标，再 push 到 GitHub。

这里的核心不是“多开几个目录”，而是把三件事拆开：

1. 代码和文档的写入位置。
2. EACN3 的唤醒来源。
3. Claude / Codex 的会话身份。

这三件事现在应该是独立的。

## 2. 目标约束

你这次新增的要求，我理解成下面五条硬约束：

1. `workspace` 里有 `main` 工作区，以及每个 role 的独立工作区。
2. 默认不强制 GitHub push；`github_push_target = null` 时只做本地 commit。
3. role PID 常驻，`cd` 到自己的工作区里跑，支持随时 resume。
4. 不允许 cron 轮询 EACN3；EACN3 唤醒必须来自 hooks。
5. `project kill` 只关 PID，不毁 session 语义；下次唤醒要能回到同一个逻辑 session。

## 3. Workspace 规划

我建议把 `project_{port}/workspace/` 定义为“工作区容器”，而不是唯一 checkout。

### 3.1 建议目录

```text
project_{port}/
  workspace/
    main/
    roles/
      coder/
      writer/
      experimenter/
      expert-<domain>/
      reviewer/
      ethics/
      noter/
    shared/
  memory/
  logs/
  artifacts/
  eacn3_data/
  state/
```

### 3.2 各目录含义

| 路径 | 含义 |
|---|---|
| `workspace/main/` | 项目的主集成工作区。最终合并、人工检查、主线交付都以它为准。 |
| `workspace/roles/<role>/` | 该 role 的 canonical 工作区。写权限按 role 分类分配。 |
| `workspace/shared/` | 跨 role 交接文件、合并草案、公共中间产物。 |
| `memory/` | durable scratchpad，不属于源码工作区。 |
| `state/` | session ledger、workspace 绑定、远端发布配置等控制面状态。 |

### 3.3 权限原则

- `main` 是主集成面，不是所有 role 的默认写入面。
- expert / coder / writer / experimenter 这类会产出变更的 role，应该有自己的 writable worktree。
- noter / reviewer / ethics 若是只读或半只读角色，可以有自己的工作目录，但权限应受限。
- canonical key 必须是 `agent_id`，不要只靠 display name。

### 3.4 为什么这样拆

这样做有三个好处：

- 每个 role 的上下文、文件、commit 历史不会互相污染。
- 人可以直接进入某个 role 的工作目录查看当前状态。
- 之后做 `resume` 时，逻辑 session 和物理 workspace 是一一对应的。

## 4. Git 提交与 GitHub Push

这里我建议把“GitHub folder”收敛成 git 语义上的“远端发布目标”。

因为 git 真正 push 的是 branch / ref，不是本地文件夹；如果你想表达“远端仓库中的某个命名空间”，最稳妥的实现是 branch namespace。

### 4.1 默认行为

- `github_push_target = null`
- 只做本地 `git commit`
- 不做 `git push`

这时所有历史都留在本机 workspace 对应的 git 历史里。

### 4.2 配置了远端目标时

建议新增一个 nullable 配置，例如：

```yaml
workspace_publish_target:
  remote: git@github.com:org/repo.git
  branch_prefix: minionsos
  enabled: true
```

或等价的单字段配置。

行为建议是：

1. 在 role workspace 内完成修改。
2. 形成一个 durable checkpoint 时 commit。
3. 如果远端启用，则 push 到约定的 branch namespace。

### 4.3 推荐命名

建议 branch / session 命名保持一致，例如：

- `minionsos/p37596/main`
- `minionsos/p37596/coder`
- `minionsos/p37596/expert-statistics`

这样 commit、workspace、session、log 都能互相对上。

### 4.4 什么时候 commit / push

我不建议“每个 token 都 push”，那会把历史冲散。

建议的粒度是：

- 完成一个可恢复工作单元。
- 写出一个 durable checkpoint。
- 发生 phase 切换。
- 发生 compact 后的重整。

也就是说，单位不是“每次编辑”，而是“每个可恢复成果”。

## 5. 常驻 PID 与命名 Session

### 5.1 常驻 PID

每个 active role 对应一个常驻 PID：

- PID 不因一次 wake 而重启。
- PID 的 cwd 固定在该 role 的 canonical workspace。
- PID 只在 `project kill` 或显式 dismiss 时退出。

### 5.2 Session 名称

每个 role 都应该有一个稳定的逻辑 session 名称，例如：

- `p37596/main`
- `p37596/coder`
- `p37596/expert-statistics`

这个名字不是一次性 launch label，而是整个生命周期的逻辑身份。

### 5.3 Session ledger

建议把下面这些字段存到 `state/` 里：

| 字段 | 含义 |
|---|---|
| `session_name` | 逻辑 session 名称 |
| `agent_id` | EACN agent id |
| `role_name` | MinionsOS role |
| `workspace_root` | 当前工作区根目录 |
| `branch_name` | 当前 git branch |
| `host` | `claude` / `codex` |
| `pid` | 当前常驻 PID |
| `last_commit` | 最近一次 durable commit |
| `phase` | 当前 project phase |
| `phase_version` | phase 版本号 / epoch |
| `resume_hint` | host-specific resume 信息 |

### 5.4 kill / revive 语义

- `./mos project kill`：关 PID，不删 session ledger，不删 workspace。
- 下次唤醒：按 `session_name` 回到同一逻辑 session。
- 如果 host 支持原生 resume，就直接 resume。
- 如果 host 不支持，就用同一 workspace + 同一 session 账本重建连续性。

## 6. Hooks 代替 Cron

这部分沿用 v6 的 hooks 思路，但这里更明确：**不允许 cron 轮询 EACN3**。

### 6.1 允许的 hook 来源

1. `direct_message` 入站。
2. `task_broadcast` 路由命中。
3. 当前 `phase` 允许该 role 在线。
4. role 自己提出需要上网的意图，但必须先过 phase / router 裁决。
5. `project` 本地主动动作，例如创建 task、发消息、phase 切换。

### 6.2 hook 做什么

hook 只做两件事：

- 产生 wake intent。
- 把 wake intent 送给对应的 resident session。

hook 不做这些事：

- 不替 role 读完整 EACN 正文。
- 不替 role 做业务判断。
- 不把事件正文提前灌到 prompt。

### 6.3 wake 的含义

wake 不是重启，不是新拉子代理，也不是 cron tick。

wake 的意思是：

- 这个 resident session 现在可以上 EACN3。
- 它自己决定先看 `eacn3_next`、`eacn3_get_events`，还是先查 task / message / open task。

### 6.4 阶段门控

建议保留 phase allowlist：

- `direct_message`：硬唤醒收信者。
- `task router match`：硬唤醒候选者。
- `phase allowlist`：决定该 role 是否有在线资格。
- 两者都不满足时，不唤醒。

## 7. Role 会话的运行方式

### 7.1 启动时

每个 role 的启动流程建议变成：

1. 进入自己的 workspace。
2. 装载 `minions/roles/<role>/SYSTEM.md` 和对应 `skills/`，这些都是模板源。
3. 读取 project-level session ledger。
4. 恢复 scratchpad。
5. 建立 resident PID 和 host session 名称。

### 7.2 运行中

role 在自己工作区里持续工作，状态循环大致是：

- idle
- hot
- compacting
- checkpointing
- clear/reconnect

### 7.3 Template 来源

`/Users/mjm/MinionsOS_V5/minions/roles/` 应该被视为模板源，不是 runtime 真相。

也就是说：

- `SYSTEM.md`、`skills/` 仍然是角色模板。
- runtime session 只是加载这些模板。
- 不应该把角色模板复制成多个“真相副本”散在各个 workspace 里。

## 8. Compact 与 resume 的关系

### 8.1 正常 compact

上下文增长时，host 自动 compact 是允许的，甚至应该鼓励。

MinionsOS 只需要知道：

- 这次 compact 是正常的。
- 还是已经频繁到需要 checkpoint / clear。

### 8.2 5 次 productive 之后

可以保留一个类似 v5 的经验阈值：

- 连续 5 次有效上网处理后，建议强制做一次 durable checkpoint。
- 之后继续工作，不需要退出 PID。

### 8.3 连续 compact 过多

如果短时间连续 compact：

- 写 scratchpad summary。
- 把未决状态压缩成 durable state。
- 下一次上网前做 `clear/reconnect`。

这一步不是为了重启，而是为了重新稳定上下文边界。

## 9. 与现有系统的联动

### 9.1 EACN3 不改协议

EACN3 仍然是任务、消息、裁决、discover 的事实源。

这版 proposal 不要求修改 EACN3 协议本体，只要求 MinionsOS 的调用方式变成：

- role 自己上网
- wake broker 只发许可

### 9.2 `role_inbox` 降级

`role_inbox` 不应该再是主消息通道。

它最多保留成：

- wake intent fallback
- checkpoint replay 辅助
- 崩溃恢复元数据

不再承担“代读 EACN 正文”的职责。

### 9.3 Noter / Experimenter / Gru

- Gru 继续掌管 phase。
- Noter 继续做人类可见的观察和摘要，但不要回到 cron + EACN 代读模型。
- Experimenter 的资源队列仍可保留它自己的调度机制，因为那不是 EACN wake poll。

## 10. 建议的实现顺序

我建议按下面顺序落地：

1. 先把 workspace container 和 role workspace 目录结构定死。
2. 再加 session ledger 和 named session。
3. 再把常驻 PID 的 cwd / resume 绑定到 role workspace。
4. 再把 hooks 接进 wake。
5. 最后加本地 commit / 远端 push。

这样做的好处是：

- workspace 和 session 先稳定。
- hooks 只改唤醒方式，不改编辑面。
- commit/push 最后接，不会把控制面和内容面混在一起。

## 11. 风险点

1. GitHub push 语义必须用 branch / ref 来表达，不要把它当成真实文件夹。
2. `project kill` 之后 resume 是否能恢复到“同一会话”，取决于 Claude / Codex host 的具体能力。
3. 读模板和运行状态必须分离，否则 workspace 会变成模板副本垃圾场。
4. 如果把所有 role 都设成 writable worktree，需要明确谁能 merge 到 `main`，否则会把主线打乱。

## 12. 我建议你拍板的三个问题

1. `workspace/roles/` 里，是否所有 active role 都有独立工作区，还是只给会写代码/文档的 role。
2. `github_push_target` 是否就是一个可选远端 repo + branch namespace。
3. `main` 的 merge 权限是否只给 Gru，还是允许特定 role 自动合并。

如果这三点定了，后面就可以把它直接拆成 V5 的实现任务。
