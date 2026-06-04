# MinionsOS 深度架构审查 - 最终报告

**日期**: 2026-06-04
**目标**: 检查多余功能、冲突、矛盾、重复，优化 `minions/` 目录

---

## 执行总结

### 发现的问题分类

| 严重性 | 问题类型 | 数量 | 状态 |
|---|---|---|---|
| 🔴 HIGH | 超大单体文件 | 4个 | 需要拆分 |
| 🟡 MEDIUM | 未使用代码 | 1个 | 可删除 |
| 🟢 LOW | 小量代码重复 | 2处 | 可优化 |
| ✅ OK | MCP 分层架构 | N/A | 合理设计 |

---

## 🔴 关键发现 1: 超大单体文件

### 问题：4个文件过大，影响可维护性

| 文件 | 大小 | 行数 | 职责 |
|---|---|---|---|
| `tools/book.py` | 113 KB | ~3000 | Book 层所有操作 |
| `lifecycle/project.py` | 102 KB | ~2700 | 项目生命周期全部逻辑 |
| `tools/draft.py` | 66 KB | ~1769 | Draft 层所有操作 |
| `tools/experiment_scheduler.py` | 64 KB | ~1700 | 实验调度 + GPU 池 |

### 影响

- **可维护性**: 单个文件太长，难以定位和修改
- **测试**: 难以隔离测试
- **合并冲突**: 多人协作容易冲突
- **认知负担**: 新贡献者难以理解边界

### 建议

#### `book.py` (113KB) - 拆分为子模块

```python
# 现状: 所有功能在一个文件
minions/tools/book.py (113KB)

# 建议: 按功能域拆分
minions/tools/book/
  ├── __init__.py         # 公共 API
  ├── ingest.py           # mos_book_ingest, _ingest_batch
  ├── query.py            # mos_book_query, BM25 检索
  ├── promote.py          # mos_book_promote_verified, ratify
  ├── lint.py             # mos_book_lint, _scan_book_edges
  ├── contradiction.py    # 矛盾检测和解决
  └── crystallize.py      # mos_book_crystallize_session
```

**优先级**: HIGH - 最大的文件

#### `project.py` (102KB) - 拆分为功能模块

```python
# 现状
minions/lifecycle/project.py (102KB)

# 建议
minions/lifecycle/project/
  ├── __init__.py           # 公共 API
  ├── create.py             # mos_project_create
  ├── close.py              # mos_project_close, dormant
  ├── revive.py             # mos_project_revive
  ├── checkpoint.py         # mos_project_checkpoint_workspace
  ├── list.py               # mos_project_list
  └── _shared.py            # 共享辅助函数
```

**优先级**: HIGH - 第二大文件

#### `experiment_scheduler.py` (64KB) - 分离 GPU 池

```python
# 现状
minions/tools/experiment_scheduler.py (64KB)
  - 实验队列
  - GPU 池管理
  - 通知逻辑

# 建议
minions/tools/experiment/
  ├── scheduler.py          # 队列和调度
  ├── gpu_pool.py           # GPU 池管理
  └── ssh_exec.py           # (或保持独立 experiment_ssh.py)
```

**优先级**: MEDIUM

#### `draft.py` (66KB) - 暂不拆分

**原因**: 
- Draft 是一个紧密耦合的图结构
- 拆分可能引入不必要的循环导入
- 1769 行相对可控（相比 3000 行）

**建议**: 暂时保持，添加更多内部注释和分段

---

## 🟡 关键发现 2: 未使用代码

### `tools/visual_audit_reference.py` (9KB, 227行) - 未被任何代码导入

**检查结果**:
```bash
$ grep -r "visual_audit_reference" minions/ --include="*.py"
# 结果: 0 匹配
```

**文件内容**: 视觉审计的参考数据（颜色、字体等标准）

**问题**: 
- 可能是遗留代码
- 或者是文档性质的参考文件

**建议**: 
1. 如果是参考数据 → 移动到 `docs/` 或 `MANUAL/`
2. 如果是死代码 → 删除

**优先级**: MEDIUM - 安全删除

---

## 🟢 关键发现 3: 小量代码重复

### 3.1 Git 工具函数重复

**位置**: `lifecycle/git_utils.py` vs `lifecycle/_project_worktree.py`

**重复函数**:
```python
# git_utils.py
def git_ref_exists(ref: str) -> bool: ...
def is_git_dirty() -> bool: ...

# _project_worktree.py (几乎相同)
def git_ref_exists(ref: str, cwd: Path) -> bool: ...
def is_git_dirty(cwd: Path) -> bool: ...
```

**原因**: 可能为避免循环导入而重复实现

**影响**: LOW - 仅2个简单函数，代码量少

**建议**: 
```python
# 统一到 git_utils.py
def git_ref_exists(ref: str, cwd: Path | None = None) -> bool:
    """..."""
    # 实现
```

**优先级**: LOW

### 3.2 配置加载模式

**位置**: `config/__init__.py` exports `load_gru_config` from `config/loader.py`

**模式**:
```python
# config/loader.py - 实现
def load_gru_config(...) -> GruConfig: ...

# config/__init__.py - 导出
from minions.config.loader import load_gru_config
```

**结论**: 这是**标准的 Python 模块组织模式** - `__init__.py` 作为 public API

**建议**: 保持现状 ✅

---

## ✅ 验证通过: MCP 分层架构

### 模式：实现层 + 包装层（合理设计）

```
minions/tools/*.py           ← 实现层（业务逻辑）
    ↓ import
minions/tools/mcp/*.py       ← MCP 包装层（Pydantic + @mcp.tool()）
```

### 分析结果

| 维度 | 结论 |
|---|---|
| 代码重复 | ❌ 无重复 - 包装层100%调用实现层 |
| 职责分离 | ✅ 清晰 - 实现层可被CLI/测试调用 |
| 可测试性 | ✅ 好 - 实现层是纯函数 |
| MCP Schema | ✅ 自动生成 - Pydantic 提供 |

**示例**:
```python
# tools/draft.py - 实现
def mos_draft_view(query: str | None, ...) -> dict:
    """业务逻辑"""
    ...

# tools/mcp/memory_tools.py - 薄包装
@mcp.tool()
def mos_draft_view(args: DraftViewArgs) -> dict:
    """MCP 工具注册"""
    _require_tool_allowed("mos_draft_view")
    return _draft.mos_draft_view(
        query=args.query,
        ...
    )
```

**建议**: 保持此架构 ✅ - 这是**适配器模式**的正确应用

---

## 功能协作分析

### 检查的功能域

| 功能域 | 相关模块 | 结论 |
|---|---|---|
| 项目生命周期 | project.py + project_tools.py | ✅ 合理分层 (实现+MCP) |
| 角色管理 | role.py + role_launcher.py + role_evolution.py + spawn_tools.py | ✅ 按职责分离 |
| 上下文管理 | compact.py + reset.py + context_pressure.py | ✅ 独立工具，无冲突 |
| Git 操作 | git_utils.py + _project_worktree.py | 🟢 有小量重复 |
| 配置加载 | __init__.py + loader.py | ✅ 标准模块模式 |

### 未发现的问题

❌ 功能冲突 - 无
❌ 矛盾设计 - 无
❌ 目的重复 - 无（除了上述小量 git 工具重复）

---

## 其他发现

### 已验证模块用途

| 模块 | 用途 | 状态 |
|---|---|---|
| `tools/utils.py` | 提供 `strip_ansi_escapes` | ✅ 被使用 |
| `lifecycle/parked_prompt.py` | Gru 反楔子检测 | ✅ 被使用 |
| `lifecycle/wedge_detect.py` | 楔子检测 | ✅ 被使用 |
| `tools/draft_audit.py` | Draft 审计 | ✅ 被使用 |
| `scaffold/` | `mos audit` 命令 | ✅ 被使用 |

---

## 优化建议优先级

### P0 - 立即执行（安全，高收益）

1. **删除未使用代码**
   ```bash
   git rm minions/tools/visual_audit_reference.py
   ```
   - 影响: 零 - 未被调用
   - 收益: 减少 9KB 维护负担

### P1 - 短期（1-2周）

2. **拆分 `book.py` (113KB)**
   - 拆分为 ingest/query/promote/lint/contradiction 子模块
   - 收益: 大幅提升可维护性
   - 风险: 中 - 需要仔细处理内部依赖

3. **拆分 `project.py` (102KB)**
   - 拆分为 create/close/revive/checkpoint 子模块
   - 收益: 提升可维护性
   - 风险: 中

### P2 - 中期（1个月）

4. **合并 Git 工具函数**
   - 统一 `git_ref_exists` 和 `is_git_dirty`
   - 收益: 小 - 消除少量重复
   - 风险: 低

5. **拆分 `experiment_scheduler.py` (64KB)**
   - 分离 GPU 池管理
   - 收益: 中
   - 风险: 低

### P3 - 低优先级

6. **为大文件添加内部文档**
   - `draft.py` 添加更多注释和分段
   - 收益: 提升可读性
   - 风险: 零

---

## 执行计划

### Phase 1: 清理（本周）

```bash
# 1. 删除未使用代码
git rm minions/tools/visual_audit_reference.py
git commit -m "cleanup: remove unused visual_audit_reference.py"

# 2. 验证测试通过
uv run pytest tests/unit/
uv run ruff check minions/
```

### Phase 2: 重构大文件（下周）

```bash
# 1. 创建 book 子模块
mkdir -p minions/tools/book
# 移动和拆分代码...

# 2. 创建 project 子模块  
mkdir -p minions/lifecycle/project
# 移动和拆分代码...

# 3. 逐步验证每个子模块
uv run pytest tests/unit/test_book.py
uv run pytest tests/unit/test_project.py
```

### Phase 3: 优化（下月）

```bash
# 1. 合并 git 工具
# 2. 拆分 experiment_scheduler
# 3. 文档改进
```

---

## 总结

### 当前架构质量

| 维度 | 评分 | 说明 |
|---|---|---|
| 模块化 | 🟡 7/10 | 大部分良好，4个文件过大 |
| 代码重复 | 🟢 9/10 | 极少重复，MCP 分层合理 |
| 可维护性 | 🟡 7/10 | 超大文件影响维护 |
| 可测试性 | 🟢 8/10 | 实现层与 MCP 层分离良好 |
| 文档 | 🟢 8/10 | CLAUDE.md 和 MANUAL/ 完善 |

### 关键洞察

1. **MCP 分层架构是正确的** - 不要"修复"它
2. **主要问题是文件大小** - 不是功能冲突
3. **未发现架构矛盾** - 整体设计一致
4. **极少代码重复** - 仅2个 git 函数

### 优化收益预估

| 优化 | 工作量 | 收益 |
|---|---|---|
| 删除未使用代码 | 5分钟 | 减少9KB维护 |
| 拆分 book.py | 2-4小时 | 大幅提升可维护性 |
| 拆分 project.py | 2-4小时 | 大幅提升可维护性 |
| 合并 git 工具 | 30分钟 | 消除小量重复 |

---

## 附录：对比 EACN3

**EACN3 的架构特点**:
- 模块小而聚焦
- 清晰的层次
- 最小的依赖

**MinionsOS 当前状态**:
- ✅ 层次清晰（MCP 分层）
- ✅ 依赖合理
- 🟡 部分模块过大

**差距**: 主要是文件大小，不是架构问题。拆分4个大文件后，MinionsOS 将达到 EACN3 级别的整洁度。
