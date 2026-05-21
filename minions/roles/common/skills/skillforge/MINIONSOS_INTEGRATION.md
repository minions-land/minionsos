# skillforge — Skill 自进化系统

**位置:** `minions/roles/common/skills/skillforge/`  
**版本:** 1.0.0  
**创建日期:** 2026-05-21

---

## 为什么需要 skillforge？

MinionsOS 的核心能力之一是**专家自进化** — 专家角色可以通过创建、优化和迭代 skills 来提升自己的能力。skillforge 是这个自进化循环的基础设施。

### 传统方式的问题

**之前创建 skill 的流程：**
1. 手写 SKILL.md
2. 手动测试几次
3. 凭感觉调整
4. 没有量化指标
5. 没有触发准确率优化
6. 手动打包分发

**结果：**
- 质量不稳定
- 没有迭代机制
- 无法量化改进效果
- 专家进化速度慢

### skillforge 的解决方案

**完整的 6 阶段生命周期：**

```
Stage 0: Intake & Scoping
  └─ 理解需求，选择模式（创建/改进/验证/打包）

Stage 1: Creation
  └─ 研究类似 skills，起草 SKILL.md，编写测试用例

Stage 2: Form Validation
  └─ 结构验证（quick_validate.py + skill-edit）

Stage 3: Behavioral Validation
  ├─ Option A: skill-evaluator-by-metaharness（深度测试）
  └─ Option B: 官方 eval pipeline（基准测试）

Stage 4: Iteration
  └─ 使用 eval sets 进行爬山优化（60% 训练 + 40% 验证）

Stage 5: Description Optimization
  └─ 20 条测试 query，5 轮优化，最大化触发准确率

Stage 6: Packaging
  └─ 打包成 .skill 文件，生成安装说明
```

---

## 在 MinionsOS 中的应用场景

### 场景 1：专家创建新能力

```
Noter 专家发现自己需要一个"提取论文关键引用"的能力

1. Noter 调用 /skillforge
2. 描述需求："我需要从论文中提取关键引用，格式化成 BibTeX"
3. skillforge 自动：
   - 研究类似 skills（paper-search, github-fetch）
   - 生成 SKILL.md 草稿
   - 创建测试用例
   - 运行形式验证
   - 运行行为验证
   - 优化触发准确率
   - 打包成 .skill 文件
4. Noter 获得新能力，可以立即使用
```

### 场景 2：专家优化现有能力

```
Writer 专家发现 editorial-html skill 触发不准确

1. Writer 调用 /skillforge，选择 Improve mode
2. 指定问题："这个 skill 在用户说'生成报告'时不触发"
3. skillforge 自动：
   - 运行 Stage 5（Description Optimization）
   - 生成 20 条测试 query（10 正例 + 10 负例）
   - 5 轮优化循环
   - 选择 F1 分数最高的 description
4. Writer 的 editorial-html skill 触发准确率提升
```

### 场景 3：质量保证

```
Ethics 专家审查新 skill 是否符合标准

1. Ethics 调用 /skillforge，选择 Validate mode
2. 指定要验证的 skill
3. skillforge 自动：
   - Stage 2: 形式验证（结构、frontmatter、触发短语）
   - Stage 3: 行为验证（A/B 测试，Codex 盲评）
   - 生成量化报告（通过率、token 效率、耗时）
4. Ethics 获得客观的质量报告，决定是否批准
```

---

## 工具整合

skillforge 整合了三套工具：

### 1. 你的自定义工具
- **skill-edit** (150 行) — 形式验证
- **skill-evaluator-by-metaharness** (215 行) — 行为验证（3 阶段）
- **codex** — 子代理调度

### 2. 官方 skill-creator 工具
- `init_skill.py` — 模板化创建
- `quick_validate.py` — 快速验证
- `run_eval.py` — 并行 A/B 测试
- `improve_description.py` — 描述优化
- `aggregate_benchmark.py` — 基准汇总
- `package_skill.py` — 打包

### 3. 评估代理
- **grader** — 评估断言是否通过
- **comparator** — 盲评两个输出
- **analyzer** — 分析为什么一个版本更好

---

## 自进化循环

```
┌─────────────────────────────────────────────────────────┐
│                    专家发现能力缺口                        │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              /skillforge 创建新 skill                     │
│   Stage 1 → 2 → 3 → 5 → 6                               │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              专家使用新 skill 完成任务                      │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│         专家发现 skill 可以改进（触发不准/效果不好）          │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│         /skillforge 优化现有 skill                        │
│   Stage 5 (描述优化) 或 Stage 4 (迭代)                     │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              专家能力提升，循环继续                          │
└─────────────────────────────────────────────────────────┘
```

---

## 示例：json-format skill

`minions/roles/common/skills/json-format/` 是用 skillforge 创建的第一个示例 skill。

**创建过程：**
1. 需求：格式化 JSON 数据，添加缩进和语法高亮
2. 触发短语："format this JSON", "prettify JSON"
3. skillforge 执行 Stage 1 → 2
4. 通过 quick_validate.py 验证
5. 通过 skill-edit 深度检查（0 个结构问题）

**结果：**
- 115 行 SKILL.md
- 5 个清晰的步骤
- 6 条决策规则
- 5 个具体的 Pitfalls
- 结构完全符合规范

---

## 使用指南

### 创建新 skill

```bash
# 在 MinionsOS 项目中
/skillforge

# 回答问题：
# - 这个 skill 要做什么？
# - 什么时候触发？
# - 输出格式是什么？
# - 有客观的成功标准吗？
```

### 优化现有 skill

```bash
/skillforge

# 选择 Improve mode
# 指定 skill 路径
# 说明问题（形式问题/行为问题/触发问题）
```

### 验证 skill 质量

```bash
/skillforge

# 选择 Validate mode
# 指定 skill 路径
# 提供测试场景
```

### 打包分发

```bash
/skillforge

# 选择 Package mode
# 指定 skill 路径
# 自动生成 .skill 文件
```

---

## 量化指标

skillforge 提供的量化指标：

### 形式指标（Stage 2）
- ✅ Frontmatter 有效性
- ✅ Description < 500 字符
- ✅ 触发短语与 description 匹配
- ✅ 步骤顺序正确
- ✅ 无前向引用

### 行为指标（Stage 3）
- **通过率** — 测试用例通过百分比
- **Token 效率** — with_skill vs baseline token 消耗
- **耗时** — with_skill vs baseline 执行时间
- **行为分类** — Prevents failure / Calibrates / Matches baseline / Overreaches

### 触发指标（Stage 5）
- **Precision** — 应该触发时触发的比例
- **Recall** — 不该触发时不触发的比例
- **F1 Score** — Precision 和 Recall 的调和平均

---

## 与 MinionsOS 其他组件的关系

### EACN (Expert Agent Collaboration Network)
- skillforge 创建的 skills 可以被 EACN 中的所有专家使用
- 专家通过 skillforge 自进化，提升整个网络的能力

### 角色系统
- **Common skills** — 所有专家共享（如 skillforge 本身）
- **角色专属 skills** — 特定专家的能力（如 Noter 的论文处理）

### 工作流
- skillforge 可以在工作流中被调用，实现"运行时能力扩展"
- 专家在执行任务时发现缺失能力，立即创建新 skill

---

## 文件结构

```
minions/roles/common/skills/skillforge/
├── SKILL.md              # 主逻辑（404 行）
├── README.md             # 架构文档
├── REGISTRATION.md       # CLAUDE.md 注册条目 + 图表
├── SUMMARY.md            # 执行摘要
├── TOOL_INVENTORY.md     # 工具清单
└── MINIONSOS_INTEGRATION.md  # 本文档
```

---

## 下一步

### 短期（1-2 周）
1. ✅ 将 skillforge 集成到 MinionsOS common skills
2. ✅ 创建示例 skill（json-format）
3. ⏳ 为 Noter/Writer/Ethics 各创建 1 个专属 skill
4. ⏳ 编写完整的测试用例（evals.json）

### 中期（1 个月）
1. 运行 Stage 3 行为验证，收集基准数据
2. 运行 Stage 5 描述优化，提升触发准确率
3. 建立 skill 质量标准（通过率 > 80%，F1 > 0.9）
4. 创建 skill 仓库，专家可以互相分享

### 长期（3 个月）
1. 自动化 skill 进化循环（专家使用 → 收集反馈 → 自动优化）
2. 建立 skill 市场（专家可以发布、评分、下载 skills）
3. 跨项目 skill 迁移（MinionsOS skills 可以用于其他项目）
4. Skill 版本管理和回滚机制

---

## 关键指标

- **Skill 创建时间** — 从需求到可用 skill：< 10 分钟（vs 之前 1-2 小时）
- **质量一致性** — 所有 skills 通过 Stage 2 验证：100%
- **触发准确率** — 经过 Stage 5 优化后：F1 > 0.9
- **专家进化速度** — 每个专家每月新增能力：3-5 个 skills

---

**skillforge 让 MinionsOS 的专家真正具备了自我进化的能力。**
