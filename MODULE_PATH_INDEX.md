# MinionsOS 模块路径索引

**生成日期**: 2026-06-04
**目的**: 记录所有大文件（>50KB）的位置、依赖关系和调用者

---

## 大文件清单

| 文件 | 大小 | 行数 | 模块 | 状态 |
|---|---|---|---|---|
| `minions/tools/book.py` | 111 KB | 3099 | Book L2 内存 | 🟡 需要拆分 |
| `minions/lifecycle/project.py` | 100 KB | 2793 | 项目生命周期 | 🟡 需要拆分 |
| `minions/cli.py` | 76 KB | 2100 | CLI 入口 | ✅ 合理（CLI 自然会大） |
| `minions/tools/draft.py` | 64 KB | 1770 | Draft L1 内存 | 🟢 暂不拆分 |
| `minions/tools/experiment_scheduler.py` | 63 KB | 1602 | 实验调度 | 🟡 可拆分 |

---

## `minions/tools/book.py` - Book L2 内存层

### 公共 API (12个)

```python
# 收录
mos_book_ingest(source_role, source_path, slug, title, ...) -> dict
mos_book_ingest_batch(sources: list[dict]) -> dict

# 查询
mos_book_query(query, ...) -> BookQueryResult  # BM25 检索

# 提升
mos_book_promote_verified(source_path, ...) -> dict
mos_book_ratify(source_path, rationale, ...) -> dict

# 会话水晶化
mos_book_crystallize_session(role, session_id, ...) -> dict

# 综合保存
mos_book_save_synthesis(role, content, context_query, ...) -> dict

# 开放问题
mos_book_open_question(question, context, requester_role) -> dict

# 死胡同
mos_book_dead_end(approach, why_failed, ...) -> dict

# 审计
mos_book_audit_walk() -> dict
mos_book_resolve_contradiction(page_path, resolution, ...) -> dict

# 完整性检查
mos_book_lint(port: int | None = None) -> dict
```

### 导入此模块的文件 (21个)

**核心工具**:
- `minions/tools/draft.py` - Draft 层调用 `mos_book_ingest`
- `minions/tools/mcp/memory_tools.py` - MCP 包装层

**测试**:
- `tests/unit/test_book.py`
- `tests/unit/test_book_v2.py`
- `tests/unit/test_book_contradictions.py`
- `tests/unit/test_book_lint.py`
- `tests/unit/test_book_wiki_v2.py`
- `tests/unit/test_memory_e2e.py`
- `tests/unit/test_memory_v2.py`
- `tests/unit/test_memory_provenance_e2e.py`
- `tests/unit/test_draft_reel_integration.py`
- `tests/unit/test_draft_book_hooks.py`
- `tests/unit/test_noter_ethics_chain.py`
- `tests/unit/test_v15_10_fixes.py`

### 测试暴露的内部函数 (2个)

```python
_book_root(port: int) -> Path  # 获取 Book 根目录
_render_source_frontmatter(...) -> str  # 渲染源页面 frontmatter
```

### 文档引用

- `MANUAL/domains/reel-l0-memory.md` - 提到 `_render_source_frontmatter` 和 reel_ref

### 建议的拆分结构

```
minions/tools/book/
├── __init__.py           # 导出所有公共 API
├── _shared.py            # 共享常量、辅助函数
├── ingest.py             # ingest, ingest_batch
├── query.py              # query (BM25)
├── promote.py            # promote_verified, ratify
├── crystallize.py        # crystallize_session
├── synthesis.py          # save_synthesis
├── questions.py          # open_question, dead_end
├── audit.py              # audit_walk, resolve_contradiction
└── lint.py               # lint
```

**向后兼容**: 保持 `minions/tools/book.py` 作为 re-export 层

---

## `minions/lifecycle/project.py` - 项目生命周期

### 公共 API (估计 15-20个)

```python
# 项目创建和关闭
mos_project_create(...)
mos_project_close(port)
mos_project_dormant(port)
mos_project_revive(port)
mos_project_kill(port)

# 项目列表
mos_project_list(...)

# 阶段管理
mos_project_set_phase(port, phase)

# 检查点
mos_project_checkpoint_workspace(port, message, github_push)

# 跨项目桥接
mos_project_bridge(...)

# 监控
mos_start_monitor(...)
```

### 文档引用

- `CLAUDE.md` - 2 处提到项目生命周期和 checkpoint
- `minions/CLAUDE.md` - 提到项目 create/close/dormant/revive 行为

### 建议的拆分结构

```
minions/lifecycle/project/
├── __init__.py           # 导出所有公共 API
├── _shared.py            # 共享辅助函数
├── create.py             # project 创建
├── close.py              # project 关闭、dormant
├── revive.py             # project 恢复
├── list.py               # project 列表
├── checkpoint.py         # 检查点和 GitHub 推送
├── phase.py              # 阶段管理
└── bridge.py             # 跨项目桥接
```

---

## `minions/cli.py` - CLI 入口

### 状态: ✅ 合理大小

**原因**: CLI 入口点自然会包含：
- 所有命令定义
- Click 装饰器
- 帮助文本
- 参数解析

**建议**: 保持现状，这是 CLI 工具的正常大小

---

## `minions/tools/draft.py` - Draft L1 内存层

### 状态: 🟢 暂不拆分

**原因**:
- Draft 是紧密耦合的图结构
- 拆分可能引入循环依赖
- 64KB 相对可控（相比 111KB 的 book.py）

**建议**: 添加更多内部注释和分段，暂不拆分

---

## `minions/tools/experiment_scheduler.py` - 实验调度

### 公共 API

```python
# 实验队列
mos_exp_queue_submit(...)
mos_exp_queue_plan(...)
mos_exp_queue_reconcile(...)
mos_exp_queue_status(...)

# GPU 池
mos_exp_gpu_pool_set(...)
mos_exp_gpu_pool_get(...)
```

### 建议的拆分结构

```
minions/tools/experiment/
├── __init__.py
├── scheduler.py          # 队列和调度逻辑
└── gpu_pool.py           # GPU 池管理
```

**优先级**: P2 - 相对独立，拆分风险低

---

## 导入路径约定

### 当前模式

```python
# MCP 包装层
from minions.tools import book as _book
from minions.tools import draft as _draft

# 直接导入
from minions.tools.book import mos_book_ingest
from minions.tools.draft import mos_draft_view

# 测试内部函数
from minions.tools.book import _book_root
```

### 重构后模式（保持兼容）

```python
# 方式 1: 旧路径继续工作（兼容层）
from minions.tools.book import mos_book_ingest  # OK

# 方式 2: 新路径（可选）
from minions.tools.book.ingest import mos_book_ingest  # 也 OK

# 方式 3: 包级别导入（推荐）
from minions.tools import book
book.mos_book_ingest(...)  # OK
```

---

## 依赖关系图

### Book 模块依赖

```
外部依赖:
- minions.paths (路径辅助)
- minions.tools._returns (DictLikeBaseModel)
- minions.errors (DraftError)

被依赖:
- minions/tools/draft.py (调用 mos_book_ingest)
- minions/tools/mcp/memory_tools.py (MCP 包装)
- 18 个测试文件
```

### Project 模块依赖

```
外部依赖:
- minions.config (配置加载)
- minions.paths (路径辅助)
- minions.lifecycle.* (各种生命周期辅助)

被依赖:
- minions/tools/mcp/project_tools.py (MCP 包装)
- minions/gru/loop.py (Gru 监控循环)
- 未统计的测试文件
```

---

## 重构优先级矩阵

| 文件 | 大小 | 依赖数 | 复杂度 | 优先级 | 风险 |
|---|---|---|---|---|---|
| book.py | 111 KB | 21 | HIGH | P1 | HIGH |
| project.py | 100 KB | ? | HIGH | P1 | HIGH |
| experiment_scheduler.py | 63 KB | ? | MEDIUM | P2 | MEDIUM |
| draft.py | 64 KB | ? | HIGH | P3 | HIGH (暂不做) |
| cli.py | 76 KB | N/A | LOW | P4 | LOW (保持现状) |

---

## 重构执行建议

### 每个大文件重构的步骤

1. **准备阶段**
   - 创建模块目录
   - 分析依赖关系
   - 编写测试基准

2. **拆分阶段**
   - 提取共享辅助函数到 `_shared.py`
   - 按功能域逐个拆分
   - 每个子模块完成后立即测试

3. **迁移阶段**
   - 创建 `__init__.py` 导出层
   - 保持旧文件作为兼容层（re-export）
   - 逐步更新导入路径

4. **验证阶段**
   - 运行所有单元测试
   - 运行集成测试
   - 检查 MCP 工具可用性

5. **清理阶段**
   - 确认所有测试通过后删除旧文件
   - 更新文档中的导入示例
   - 提交并记录

### 时间估算

| 文件 | 准备 | 拆分 | 验证 | 总计 |
|---|---|---|---|---|
| book.py | 30min | 3h | 1h | ~4.5h |
| project.py | 30min | 3h | 1h | ~4.5h |
| experiment_scheduler.py | 20min | 1h | 30min | ~2h |

**总计**: 约 11 小时的仔细执行

---

## 文档更新清单

重构完成后需要更新：

- [ ] `CLAUDE.md` - 路径引用
- [ ] `minions/CLAUDE.md` - 架构描述
- [ ] `MANUAL/domains/*.md` - 工具引用
- [ ] `README.md` - 如有代码示例
- [ ] `ARCHITECTURE_FINAL_REPORT.md` - 标记为已完成
- [ ] 各测试文件中的注释

---

## 附录：模块大小目标

**理想模块大小**:
- 单个文件: < 20 KB (~500 行)
- 复杂模块: < 30 KB (~800 行)
- 最大容忍: < 50 KB (~1300 行)

**当前vs目标**:
- book.py: 111 KB → 分成 8-10 个模块，每个 ~10-15 KB ✅
- project.py: 100 KB → 分成 7-8 个模块，每个 ~12-15 KB ✅
- experiment_scheduler.py: 63 KB → 分成 2 个模块，每个 ~30 KB ✅
