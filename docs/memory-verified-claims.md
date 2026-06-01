# Memory 机制：经测试验证的 Claim 清单

**原则：每一条 claim 都有对应的通过测试。不在此列的，不要写进论文。**

代码版本：V23.0 后 | 三层 Memory（Reel → Draft → Book）| 单一维护角色：Ethics

---

## 一、三层 Memory 结构（架构事实）

| 层 | 是什么 | 存储位置 | 谁写 |
|---|---|---|---|
| **Reel** (L0) | 原始会话轨迹，不可变 | `branches/<role>/reel/<session>/` | PostToolUse hook 自动捕获 |
| **Draft** (L1) | 核心团队进展知识图谱，可多方式索引 | `branches/main/draft/draft.json` | 所有角色 append；Ethics 连边 |
| **Book** (L2) | main branch 上的论文结果组织形式 | `branches/main/book/` + `logic/`/`src/`/`evidence/` | Ethics ingest；Gru promote |

三层之间有**相互索引链接**（`reel_ref` 指针），保证"什么来自什么"可追溯。
*（此可追溯性是内部审计保证，不是论文 claim。）*

<!-- BODY -->

## 二、可以 claim 的功能（有通过测试）

### Claim 1：跨层 provenance 链接可追溯
> 在 Draft 节点产生时捕获的 `reel_ref`，随 ingest 传播到 Book 源页面，
> 形成 Reel → Draft → Book 的可追溯链。

- **验证**：`test_memory_provenance_e2e.py::test_reel_ref_travels_from_draft_append_to_book_page`
- **反向验证已确认**：若 `reel_ref` 不传播，测试正确失败（非空断言）。
- 代码：`draft.py:804`（append 自动注入 `metadata.reel_ref`）+ `book.py:266`（写入 Book frontmatter）。

### Claim 2：冷启动上下文重建
> 角色 compact/wake 后，无需丢失的 transcript，仅凭 Book `hot.md` 滚动缓存 +
> `mos_draft_relevant` 关键词推送，即可重建与当前任务相关的历史上下文。

- **验证**：`test_memory_provenance_e2e.py::test_cold_start_context_reconstruction`
- 测试断言：相关节点（残差连接假设、ResNet backbone 决策）被召回；无关节点（batch size）排名靠后——证明是**排序召回**，不是全量倾倒。
- 代码：`book.py:3307`（`mos_book_hot_get`）+ `draft.py:1299`（`mos_draft_relevant`，关键词重叠 + 类型加权，**无 embedding，docstring 已诚实标注**）。

### Claim 3：矛盾审计闭环
> Book ingest 的词法检测器识别"否定极性冲突"（一句肯定、一句否定共享论断词），
> 自动写出 contradiction 页面，作为 Ethics 的幻觉审计输入；页面同时引用对立双方来源。

- **验证**：`test_memory_provenance_e2e.py::test_contradiction_audit_loop`
- 代码：`book.py:543`（`_opposed_shared_terms`）+ `book.py:561`（`_detect_contradictions`）。
- 注意：检测是**词法的**（否定标记 + 共享论断词），不是语义/LLM 的。论文中按"词法矛盾检测"claim，不要说"深度语义冲突检测"。

### Claim 4：Book → Paper 布局耦合稳定
> book-to-paper skill 消费的 Book 布局目录（`logic`/`src`/`evidence`/`Book.md`）
> 与 worktree 实际 seed 的布局一致；论文章节顺序固定
> （abstract→introduction→related work→methodology→experiments→conclusion）。

- **验证**：`test_book_to_paper_contract.py`（3 个契约测试）
- **反向验证已确认**：若 `SHARED_SUBDIRS` 删除 `logic`，契约测试正确捕获。
- 注意：Book→Paper 的**生成质量**是 LLM 驱动的，由 `docs/Reconstruction/book2paper-validation/`（round-1/2 + 编译 PDF）实证验证，**不是**单元测试能保证的。契约测试只钉住"布局不漂移"这一确定性前提。

---

## 三、不要 claim 的（无验证或不存在）

| 不要说 | 实情 |
|---|---|
| "语义相似度 / embedding 检索" | Draft 检索是关键词重叠；Book 检索是 Okapi BM25（词频，非向量）。docstring 本身诚实。 |
| "深度语义矛盾检测" | 词法否定极性匹配，非 LLM。 |
| "自动识别跨角色推理模式(motif)并连边" | `mos_draft_annotate` 是 Ethics **手动**调用的工具；motif 判断是 Ethics 的认知工作，非机械自动化。按"Ethics 辅助连边"claim。 |
| "矛盾触发外部裁决任务" | 合并后 Ethics **本身就是 adjudicator**，自读 contradiction 页面自裁决（见 `ethics/SYSTEM.md` §contradiction workflow），不需要也没有"触发外部 adjudication task"的联动。当前设计正确，无需构建。 |

---

## 四、think-then-act 推理结论（是否需要额外构建）

针对早期审计标记的"不能 claim"项，用 think 推理"是否需要额外做这个功能"：

1. **跨层 provenance**：功能已存在，缺的是验证 → **只补测试**（Claim 1）。✅
2. **motif 自动识别**：**不该自动化**——语义判断是 Ethics 认知工作，强行机械化反而 overclaim → **不构建，调整 claim 措辞**。
3. **contradiction → adjudication 联动**：基于旧的双角色假设；合并后 Ethics 自审即闭环 → **当前设计正确，不构建**。
4. **冷启动重建**：核心 claim 但缺端到端验证 → **必须补测试**（Claim 2）。✅

**净结论**：不新增任何功能；补 6 个端到端/契约测试，验证已有功能链路；修正 2 处措辞避免 overclaim。

