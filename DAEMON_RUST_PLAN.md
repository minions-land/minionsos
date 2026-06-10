# MinionsOS 守护进程 Rust 化方案

## 架构设计（辩证反转）

### 核心原则

> **CLI 是 Rust 壳 + Python 核（壳要快，核被调即退）**  
> **守护进程是 Rust 核 + Python 决策器（核要永跑且可靠，决策器被调即退）**

**统一铁律：让 Python 永不长跑。**

---

## 当前 Python 守护进程结构（实测）

### 主循环 + 7 个看门狗线程

```python
GruLoop (主类)
├── _tick() 主心跳                        # while True: 每 N 秒
│   ├── backend_health() HTTP 探测
│   ├── respawn_backend() 崩溃恢复
│   └── session_alive() tmux 检查
│
├── _experiment_scheduler_thread()        # 实验队列调和
├── _role_evolution_thread()              # SPLIT/MERGE/DISMISS 评估
├── _gru_drive_thread()                   # 驱动活跃项目（调 Claude）
├── _wedge_watchdog_thread()              # 检测卡死角色、kill tmux
├── _gru_digest_thread()                  # 周期摘要
├── _stagnation_vote_thread()             # 停滞检测
└── _parked_prompt_thread()               # 停滞 prompt 唤醒（发 tmux 按键）
```

### 职责分类

| 线程 | 性质 | Python 是否必需 | Rust 化难度 |
|------|------|-----------------|-------------|
| **主 tick** | 纯 I/O（HTTP + 进程管理） | ❌ 否 | ✅ 容易 |
| **wedge watchdog** | 纯 I/O（读日志 + kill tmux） | ❌ 否 | ✅ 容易 |
| **parked prompt** | 纯 I/O（tmux send-keys） | ❌ 否 | ✅ 容易 |
| **experiment scheduler** | 领域决策（SQLite 队列调和） | ✅ 是 | ⚠️ 中等 |
| **role evolution** | 领域决策（SPLIT/MERGE 评估） | ✅ 是 | ⚠️ 中等 |
| **gru drive** | 领域决策（调 Claude 推理） | ✅ 是 | ⚠️ 复杂 |
| **digest/stagnation** | 领域决策（活动采样） | ✅ 是 | ⚠️ 中等 |

---

## Rust 守护进程架构

### Phase 2A: 核心监督层（Rust 永跑）

```rust
┌─────────────────────────────────────────────────────────┐
│  minionsd (Rust 守护进程 — 这部分永远在跑)                 │
│                                                            │
│  主循环 (tokio runtime)                                    │
│  ├─ tick_health_monitor()          每 N 秒                 │
│  │   ├─ HTTP GET /health          (reqwest)               │
│  │   ├─ respawn_backend()         (Command::spawn)        │
│  │   └─ tmux session check        (Command::output)       │
│  │                                                         │
│  ├─ wedge_watchdog()               每 M 秒                 │
│  │   ├─ 读角色日志尾巴             (std::fs::read)         │
│  │   ├─ 检测 wedge pattern                                │
│  │   └─ kill tmux session          (Command::spawn)       │
│  │                                                         │
│  ├─ parked_prompt_watchdog()       每 K 秒                 │
│  │   ├─ 检测停滞 prompt                                    │
│  │   └─ tmux send-keys C-c         (Command::spawn)       │
│  │                                                         │
│  └─ 计时状态 (HashMap<(port,role), Instant>)              │
│      ├─ last_wedge_kill                                    │
│      ├─ last_parked_kick                                   │
│      └─ crash_counter              (serde JSON 持久化)    │
│                                                            │
│  每隔 T 秒,对"需要领域决策"的事:                            │
│     spawn python -m minions.gru.decisions                  │
│        --action experiment_scheduler                        │
│        --port 37680                                         │
│     → 拿 JSON 结果 → 子进程退出 (Python 不长跑)           │
└────────────────────────────────────────────────────────────┘
```

### Phase 2B: Python 决策器（短命子进程）

```python
# minions/gru/decisions.py (新文件)

@click.command()
@click.option('--action', type=click.Choice([
    'experiment_scheduler',
    'role_evolution',
    'gru_drive',
    'digest',
    'stagnation',
]))
@click.option('--port', type=int)
@click.option('--role', type=str, default=None)
def main(action, port, role):
    """被 Rust 守护进程调用的短命决策器."""
    
    if action == 'experiment_scheduler':
        result = reconcile_experiment_queue(port)
        print(json.dumps(result))
    
    elif action == 'role_evolution':
        result = evaluate_role_evolution(port)
        print(json.dumps(result))
    
    elif action == 'gru_drive':
        result = drive_project(port, role)
        print(json.dumps(result))
    
    # ... 其他决策
```

**关键：** Python 进程生命周期是"被调 → 决策 → 输出 JSON → 退出"，典型运行 < 5 秒。永远在跑的只有 Rust。

---

## 实施计划

### Phase 2A: Rust 监督核心（4-5 周）

#### Week 1: 基础设施
- [ ] 创建 `minions-daemon` crate
- [ ] `tokio` 异步运行时 + 多线程调度器
- [ ] 配置加载（读 `gru.yaml`）
- [ ] 日志系统（`tracing` + 文件输出）
- [ ] 状态持久化（`CrashCounter` JSON 序列化）

#### Week 2: 主 tick 循环
- [ ] `tick_health_monitor()`
  - HTTP health 探测（`reqwest`）
  - `backend_health()` — GET `http://127.0.0.1:{port}/health`
  - `respawn_backend()` — spawn `uv run python -m minions.lifecycle.project respawn {port}`
  - tmux 会话检查 — `tmux list-sessions | grep mos-{port}-{role}`
- [ ] CrashCounter 逻辑（3 次/1h 阈值）
- [ ] 健康事件记录（写 `projects/project_{port}/logs/health_events.jsonl`）

#### Week 3: Watchdog 线程
- [ ] `wedge_watchdog()`
  - 读角色日志尾巴（`tail -c {bytes}`）
  - 检测 wedge pattern（静止 > threshold 秒）
  - `tmux kill-session -t mos-{port}-{role}`
- [ ] `parked_prompt_watchdog()`
  - 检测停滞 prompt（heartbeat > 4 分钟无更新）
  - `tmux send-keys -t mos-{port}-{role} C-c`
- [ ] Cooldown 逻辑（同一角色 N 分钟内不重复操作）

#### Week 4: Python 决策器接口
- [ ] `spawn_decision_worker()` — spawn Python 子进程
  - `Command::new("uv").arg("run").arg("python").arg("-m")...`
  - 捕获 stdout（JSON 结果）
  - 超时控制（30 秒）
- [ ] 实现 `experiment_scheduler` 调用
  - 每 `experiment_reconcile_interval` 秒调用一次
  - 解析返回的 JSON
- [ ] 实现 `role_evolution` 调用

#### Week 5: 集成测试 + 并排验证
- [ ] Python 决策器端实现（`minions/gru/decisions.py`）
  - 提取现有 `_reconcile_experiment_queues()` 逻辑
  - 提取 `_evaluate_role_evolution()` 逻辑
- [ ] 并排运行测试（Rust 守护进程 + Python 决策器 vs 原 Python 守护进程）
- [ ] 行为一致性验证

---

## 技术栈

### Rust 依赖

```toml
[dependencies]
tokio = { version = "1", features = ["full"] }
reqwest = { version = "0.12", features = ["json"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tracing = "0.1"
tracing-subscriber = "0.3"
anyhow = "1"
chrono = "0.4"
minions-core = { path = "../minions-core" }
```

### 关键模块

```
minions-daemon/
├── src/
│   ├── main.rs                 # 入口 + tokio runtime
│   ├── config.rs               # 加载 gru.yaml
│   ├── health.rs               # 主 tick：health 探测 + respawn
│   ├── watchdog/
│   │   ├── mod.rs
│   │   ├── wedge.rs            # Wedge 检测 + kill
│   │   └── parked.rs           # Parked prompt 唤醒
│   ├── decisions.rs            # Python 决策器调用接口
│   ├── state.rs                # CrashCounter + 计时状态
│   └── eacn_client.rs          # EACN3 HTTP client (from minions-core)
```

---

## 为什么这个分解是对的

### 验证"Rust 核 + Python 决策器"的正确性

| 关注点 | CLI 模式 | 守护进程模式 | 为什么不同 |
|--------|---------|-------------|-----------|
| **谁长跑** | 没人（CLI 短命） | **Rust 核** | 守护进程必须永跑 |
| **Python 生命周期** | 调一次退出 | **调一次退出** | 两者一致！ |
| **可靠性来源** | 启动速度（壳快） | **长跑稳定（核稳）** | 痛点不同 |
| **Rust 负责** | 壳（参数 + 快速查询） | **核（监督循环 + I/O）** | 职责互换 |
| **Python 负责** | 核（复杂逻辑） | **决策器（领域逻辑）** | 都是"算",但一个长跑一个不长跑 |

### 什么被移到 Rust（收益在哪）

✅ **主 tick 循环** — HTTP 探测 + 进程管理，纯 I/O，Rust 强项  
✅ **Wedge/parked watchdog** — 读日志 + shell 命令，纯 I/O  
✅ **计时状态** — HashMap + 序列化，Rust 类型安全防状态漂移  
✅ **CrashCounter** — 简单计数逻辑，移到 Rust 避免 GC 影响  

❌ **领域决策（实验调度/角色演化/Gru drive）** — 留 Python，因为：
- 调 Claude API、读 SQLite、复杂业务逻辑
- Python 已有测试覆盖
- 作为短命子进程，Python 的 GC/状态漂移风险不存在

---

## 预期收益

### 可靠性提升

1. **永跑的监督核心用 Rust**
   - 无 GC 停顿
   - 类型安全（状态不漂移）
   - 错误必显式处理
   - 最近 3 版本修的"启动/恢复/检查" bug 根源被铲除

2. **Python 不再长跑**
   - 决策器运行 < 5 秒就退出
   - 内存/状态/线程竞争问题天然消失
   - Python 的优势（快速迭代、丰富库）保留在决策层

3. **故障域天然隔离**
   - Python 决策器崩溃 → 只影响本次决策，下次重试
   - Rust 监督核崩溃 → systemd 重启整个守护进程（但概率低）
   - 两者互不影响

### 部署简化

- 单一 Rust 二进制守护进程
- Python 作为"决策脚本"被调用（需要 Python 环境，但不作为守护进程）

### 性能（边际）

- 主 tick 的 HTTP 探测、进程检查变快（Rust I/O 效率高）
- 但整体瓶颈还是等 Claude/实验/远端操作，所以性能不是主要收益

---

## 风险与缓解

### 风险 1: Rust/Python 接口复杂度

**缓解：** 接口极简，只是 JSON stdin/stdout
```rust
let output = Command::new("uv")
    .args(&["run", "python", "-m", "minions.gru.decisions"])
    .args(&["--action", "experiment_scheduler", "--port", &port.to_string()])
    .output()?;
let result: DecisionResult = serde_json::from_slice(&output.stdout)?;
```

### 风险 2: Python 决策器超时/卡死

**缓解：**
- Rust 侧设置超时（30 秒）
- 超时则 kill 子进程，记录错误，下次重试
- 不影响监督核心继续运行

### 风险 3: 过渡期两套代码并存

**缓解：**
- Phase 2A 完成前，Python 守护进程继续用
- Phase 2A 完成后，并排验证（同时跑两个，对比行为）
- 验证通过后，一次性切换

---

## 下一步行动

如果决定启动 Phase 2A，我建议：

**Week 1 立即开始：**
1. 创建 `minions-daemon` crate
2. 实现配置加载（读 `gru.yaml`）
3. 实现主 tick 循环框架（tokio + 定时器）
4. 实现 HTTP health 探测（第一个真实功能）

**验收标准（Week 1 结束）：**
- `minionsd` 能跑起来
- 能读取 `projects.json`
- 能探测 EACN3 backend `/health`
- 能记录日志到文件

要不要我立即开始 Week 1 的实施？
