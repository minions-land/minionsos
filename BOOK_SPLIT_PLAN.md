# Book.py 模块化拆分计划

## 当前状态
- **文件**: `minions/tools/book.py`
- **大小**: 111 KB (~3100 行)
- **函数**: 83 个（12 个公共 API，71 个内部辅助）

## 功能分组分析

| 模块 | 公共 API | 内部函数 | 职责 |
|---|---|---|---|
| **ingest** | 2 | ~15 | 收录原始工件到 Book 页面 |
| **query** | 1 | ~10 | BM25 检索和查询 |
| **promote** | 2 | ~8 | 提升验证内容、认证页面 |
| **crystallize** | 1 | ~5 | 会话水晶化 |
| **lint** | 1 | ~10 | Book 完整性检查 |
| **contradiction** | 2 | ~6 | 矛盾检测和解决 |
| **_shared** | 0 | ~54 | 共享辅助函数 |

## 目标结构

```
minions/tools/book/
├── __init__.py              # 公共 API 导出
├── _shared.py               # 共享辅助函数和常量
├── ingest.py                # mos_book_ingest, mos_book_ingest_batch
├── query.py                 # mos_book_query (+ BM25)
├── promote.py               # mos_book_promote_verified, mos_book_ratify
├── crystallize.py           # mos_book_crystallize_session
├── lint.py                  # mos_book_lint
├── contradiction.py         # 矛盾检测和解决
└── other.py                 # mos_book_save_synthesis, open_question, dead_end
```

## 拆分步骤

### Phase 1: 创建目录和共享模块
1. 创建 `minions/tools/book/` 目录
2. 提取共享常量、辅助函数到 `_shared.py`
3. 创建 `__init__.py` 占位符

### Phase 2: 按功能拆分（逐个模块）
顺序：query → ingest → promote → lint → contradiction → crystallize → other

原因：query 依赖最少，crystallize 依赖最多

### Phase 3: 更新所有导入
1. 更新 `minions/tools/mcp/memory_tools.py`
2. 更新测试文件
3. 更新其他依赖 book.py 的代码

### Phase 4: 验证
1. 运行所有测试
2. 检查 ruff
3. 验证 MCP 工具仍然工作

## 依赖关系图

```
_shared.py (常量、辅助)
    ↓
query.py (BM25, 检索)
    ↓
ingest.py (依赖 query 进行去重检查)
    ↓
promote.py (依赖 ingest 格式)
    ↓
lint.py (依赖所有页面格式)
    ↓
contradiction.py (依赖 query 和 lint)
    ↓
crystallize.py (依赖多个模块)
```

## 风险和缓解

| 风险 | 缓解措施 |
|---|---|
| 循环导入 | 从底层开始（_shared），避免交叉依赖 |
| 测试失败 | 每个模块拆分后立即测试 |
| MCP 工具失效 | 保持 __init__.py 中的公共 API 不变 |
| 路径引用断裂 | 使用全局搜索更新所有 `from minions.tools.book import` |

## 验证清单

- [ ] 所有测试通过
- [ ] Ruff 检查通过
- [ ] MCP 工具可调用
- [ ] 文档中的导入示例更新
- [ ] CLAUDE.md 路径引用更新
- [ ] README.md 如有引用则更新
