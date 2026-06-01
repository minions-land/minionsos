# MinionsOS 重构规范（RECONSTRUCTION_SPEC）

> 本文件是本次「大换血」的唯一权威锚点。以 `HUMAN_COMMAND.md` 与用户当面口述为准。
> 一切实现按本文件的三个核心点与分阶段序列执行；该删除的直接删除（git 可回溯）。
> 不被历史 Memory 污染——本文件优先级高于任何 memory 文件。
>
> 状态：DRAFT（Phase 0 锁定中）。日期 2026-05-31。

---

## 0. 三个核心点（一定要准）

MinionsOS = **一个基于 EACN3 的多智能体「自主科学发现」工作流**。只有三件事，讲准即可：

### 点一：EACN3 多智能体自主科学发现工作流 + 配套 skill/MCP
- 系统建立在 EACN3 之上（角色作为 EACN3 上的 Agent 协作）。我们在其上增加：
  本地启动的工程优化、一批 Skills、以及一个项目管理 Skill。
- **Gru 是唯一的 to-human 窗口**，并负责维护整个系统的正常运行（监控、看护、推进）。
- 角色「适配」EACN3 既有原语；**绝不为补角色缺口去扩 EACN3**。

### 点二：项目集团队 Memory —— Reel → Draft → Book
- **Reel（L0）**：每个 Agent 及其 Subagent 的原始 session.json（带指针，可被 Draft 索引）。
  只有 Agent 自己能读自己的原始 session；**Gru 与 Ethics 能读所有人的**。
- **Draft（L1）**：**唯一的图结构**。一个带结构的「多智能体科研流程」JSON 知识图谱
  （团队级、项目集级）。每个 role agent 在「有行动的 await_event 之后、有实际产出落盘」时，
  向 draft 里 append。每个 node 至少保证两件事：
  1. 存有对应 agent 原始 session 的指针（`reel_ref`）；
  2. 该 node 对应实际落盘文件的相对路径（供 Ethics 审查盖章）。
  - 能力 = 关系型探索图（typed nodes/edges + dead ends）+ 双链 wiki 的知识组织能力。

### 点三：Book = main branch 架构 = 团队最终共识（从 Draft 来，用于生成论文）
- **取消 share branch。** 每个 role branch 只 commit/落盘自己的东西。
- Book 即 main branch 中落盘的内容（`Book.md / logic / src / evidence / draft / proposal`
  这套 **Book 布局**）。由 **Ethics 审查盖章后、Gru 搬运**到 main branch 对应位置。
- Book 是后续「生成论文」的来源。

> **命名纪律（D5）：全系统不出现「ARA」字眼。** 我们的设计 base 在 ARA 的思想之上，
> 但对外/对内一律用自己的话：main 布局叫「Book 布局」；P5 审稿叫「严谨性审查
> （证据相关性 / 可证伪性 / 范围标定 / 论证连贯 / 探索完整性 / 方法严谨）」，不叫
> 「ARA Seal Level 2」；Book→Paper 那个 skill 叫「Book 编译成论文」，不提「ARA compiler 的逆」。

---
## 1. 锁定决策（Phase 0，已与用户确认）

| # | 决策点 | 结论 |
|---|---|---|
| D1 | Worker 模型 | **Coder + Writer 合并进 Expert**。Expert 成为唯一通用 worker（即「Common Agent」）：写代码、跑实验、写作、画图、查文献；可选 domain pack 赋予专长。可 spawn 1..N。Coder/Writer 角色删除，其 skills 进入共享 skill 库。**关键语义（用户澄清）：放松「gate」—— coding/writing/画图是每个 Agent 的 baseline 能力，不再绑定到单一专才角色；技能放入 `common/skills/` 让所有 Expert（及 Gru 的收尾写作）都能发现复用。Bootstrap 时系统自动生成一个 generalist Expert（domain 优先取人类输入，不精确时由系统按 topic 理解生成）推进项目。** |
| D2 | Noter | **并入 Ethics（见 D6）**。原计划保留 Noter 为独立记忆维护者；2026-06-01 用户从第一性原理提出把 Noter 并进 Ethics，已采纳。 |
| D3 | Benchmark 模式 | **删除**。只保留 scientific-paper 一个 profile。删 hle-answer.yaml、benchmark.py、adjudicator.py、answer_grader/test_runner 策略、`mos benchmark` CLI。`mos_evaluate` 直接走 peer review。 |
| D4 | Rigor gate | **信息性，非硬门禁**。审稿打六维严谨性分、Area-Chair 出 rigor 评估；Accept/Reject 仍是 Gru/human 判断。scope/over-claim 发现要醒目，确保不 overclaim，但不用脆弱的数值阈值卡流程。 |
| D5 | 命名纪律 | **全系统不提「ARA」**。base 在其思想之上，但一律用自己的术语（Book 布局 / 严谨性审查 / Book 编译成论文）。 |
| D6 | Noter+Ethics 合并 | **合并为单一 `ethics` 角色**（authz key 保留 `ethics`）：记忆管理（Draft+Book，连 edge、decay、dedup、crystallize）+ 证据审查 + 任务裁决，一个 Agent 一条龙。**红线：合并体永不产出实质科研 claim**——claim 永远来自 Expert，产出者≠认证者的隔离不破；它自画的解释性 edge 用与审 Expert claim 同样的证据标准。循环模型从「纯定时器」改为「EACN await_events 事件驱动 + idle tick 兜底记忆维护」；triage 纪律：先 audit/adjudication（gate 全队），idle 才做记忆卫生。退役 `mos_noter_wait`。作为 **P3.5** 在 P4 之前落地。 |

## 2. 目标角色阵容（post-rebuild，三角色）

```
Gru      唯一 to-human 窗口 · 系统看护 · 人驱动写作 · 拥有 main/Book 晋升权
Ethics   合并体：记忆管理（Draft+Book，连 edge/decay/dedup/crystallize）
           + 证据审查 + 任务裁决 · 跨人读 Reel · EACN 可见（事件驱动）
           红线：永不产实质科研 claim（claim 只来自 Expert）
Expert×N 唯一通用 worker = "Common Agent"：code · experiments · write · lit-search
           + 可选 domain pack = 专长。EACN 可见，可 spawn。
```

删除：`coder`、`writer`、`noter` 角色（目录、SYSTEM.md、whitelist、profile 引用、boundary）。
coder/writer skills → 共享 skill 库（被 Expert/Gru 发现复用）；noter 的记忆维护职责
（Draft flush/decay/dedup、Book ingest/promote/crystallize）并入 Ethics。

## 3. 目标 main branch（Book）布局

```
project-{port}/            # main branch（Gru 拥有；Ethics 盖章后 Gru 搬运）
  Book.md                  # Root manifest + layer index（~200 tokens）
  logic/                   # 认知层 What & Why（GRU 可重组）
    problem.md             #   观察 → gap → 关键洞见
    claims.md              #   可证伪断言 + proof refs
    concepts.md            #   形式定义
    experiments.md         #   声明式实验计划（仅方向，无精确数字）
    solution/
      architecture.md      #   系统设计 + 组件图
      algorithm.md         #   数学 + 伪代码
      constraints.md       #   边界条件
      heuristics.md        #   实现技巧 + 理由
    related_work.md        #   带类型的依赖图
  src/                     # 物理层 How
    configs/               #   超参 + 理由
    environment.md         #   依赖、硬件、seed
  evidence/                # 原始证据
    tables/                #   精确结果表（数字不取整）
    figures/               #   图的抽取数据点
  draft/                   # 探索图
    draft.yaml             #   研究 DAG（带类型节点 + dead ends）— 由 L1 Draft 导出
  proposal/                # 项目启动前收集的任何材料/文档/数据
```

注意：**Draft（L1，活的 JSON 图）** 是工作态、唯一图结构；`draft/draft.yaml` 是其在
Book 里的「共识快照导出」。两者区分：L1 是过程记忆（频繁写），Book/draft 是已盖章共识。

## 4. 分阶段执行序列（一点一点做扎实，禁止「一下整一堆再修补」）

每个 Phase 自带烟雾测试，绿灯后再进下一阶段。Phase 顺序按「依赖最少、最可逆」排列。

- **P1 — Codex 全退役**（纯删除，独立于一切决策；最可逆）✅ DONE 2026-06-01
  删 `mcp-servers/codex-subagent/`、`_gen_codex_config.py`、`_CODEX_BRIDGE_TOOLS`、
  agent_host=codex 字段、codex hook、所有 role/skill/doc 中 codex 引用、相关测试。
  门禁：`uv run pytest tests/unit/`、`ruff check`、`.mcp.json` 不再含 codex。
  实测：1140 passed / ruff clean / .mcp.json = [minionsos, eacn3, keepalive]。
  附带：删除每项目 `AGENTS.md`（Codex 上下文镜像，已无消费者）。
  遗留（留待最终文档 pass）：CLAUDE.md/README.md/docs 中 codex 散文、
  `minions/__init__.py` 预存 trailing-newline format nit、vision_loop.py 历史注释。

- **P2 — 删除 Shelf / Library + benchmark 模式**（纯删除）✅ DONE 2026-06-01
  删 `shelf.py`、`library.py`、`adjudicator.py`、`benchmark.py`、`hle-answer*`、
  answer_grader/test_runner、`mos benchmark` CLI、相关 MCP 注册/whitelist/测试。
  门禁：pytest 绿、`mos --help` 无 benchmark、profile 仅剩 scientific-paper。
  实测：1112 passed / ruff clean / profiles=['scientific-paper'] / audit 0 errors。
  附带：删 `minions/review/{templates,skills}/answer/`（adjudication answer-shape 资产）；
  evaluator 简化为 paper-only（mos_submit kind=paper、mos_evaluate 直走 peer review）。

- **P3 — 角色合并：Coder+Writer → Expert(=Common)**（结构变更）✅ DONE 2026-06-01
  Expert 成为唯一通用 worker；coder/writer skills 进共享库；config 三表
  （_WHITELIST/_SERVER_AUTHZ/ROLE_CLASSIFICATION/ROLE_WRITE_BOUNDARIES）去 coder/writer；
  profile roles_active 改 [gru, noter, expert, ethics]；Gru SYSTEM 改为人驱动写作。
  门禁：pytest 绿、whitelist resolve 测试覆盖新阵容、项目能 bootstrap。
  实测：1109 passed / ruff(minions) clean / audit 0 errors / Expert 发现 70 个合并 skill
  （含 run-experiments、abstract-writing、paper-compile）。
  实现要点：Expert 主体 server-authz 吸收全部 mos_exp_* 实验工具 + paper-search；
  FIXED_ROLES={noter,ethics}；新增 `_bootstrap_generalist_expert` 在 project_create
  自动 spawn 一个 generalist Expert（domain=「<项目名> generalist」）；experiment
  scheduler 完成通知改为按 batch.requester 路由（不再硬编码 "coder"）；signboard
  milestone fixed_roles 全部收敛为 ("ethics",)（worker 经 experts:True 要求）。
  Gru SYSTEM.md 人驱动写作改造 + Book→Paper skill 归入 P5。

- **P3.5 — Noter 并入 Ethics（合并体）**（结构变更，P4 之前）✅ DONE 2026-06-01
  Ethics 吸收 Noter 全部记忆维护职责（Draft flush/decay/dedup、Book
  ingest/promote/lint/hot/crystallize），循环改 EACN `await_events` 事件驱动 + idle
  兜底；退役 `mos_noter_wait` 与 noter 角色目录/SYSTEM；whitelist 取并集（Ethics 拿到
  noter 的 Book-write + draft-commit 工具）；roles_active → [gru, ethics, expert]；
  FIXED_ROLES → {ethics}；config 三表去 noter；agent_host/hooks/launcher/digest/
  milestone-vote 去 noter 定时路径。**红线写进 Ethics SYSTEM：永不产实质 claim；
  自画 edge 同证据标准；triage 先 audit/adjudication 后记忆卫生。**
  门禁：pytest 绿、whitelist resolve 覆盖三角色、项目能 bootstrap（gru+ethics+expert）、
  Ethics 能发现合并后的记忆+审查 skill。
  实测：1093 passed / ruff(minions+tests) clean / audit 0 errors / roster=[ethics,expert,gru]
  / Ethics server-authz 含 mos_draft_*+book_ingest+ratify、发现 74 skill。
  实现要点：book.py/draft.py 的 publish role + source_role + temp-dir 由 noter→ethics；
  publish/agent_host/gru-loop 去 noter 分支；删 `noter_wait.py`；`./noter` 只读人类终端
  保留（wake 改打 ethics）。**Ethics SYSTEM.md 的合并契约 + 红线文本归入下一步补全。**
  遗留：gru.yaml 的 noter_periodic/report/model 字段暂留（无驱动，dead config），
  P4/清理 pass 处理。

- **P4 — main=Book 布局 + 取消 share branch**（最大结构变更，最后做）✅ DONE 2026-06-01
  删 shared worktree 创建与 `project_shared_*` 路径；`mos_publish_to_shared` 移除，
  role 只写自己 branch；新增 Gru-only `mos_promote_to_book`（Ethics-sealed → main 对应
  Book 位置 + commit on main）；**活 Draft 落 `branches/main/draft/draft.json`（所有 role 直写）**；
  signboard/governance、reviews/round-<n>、submissions 全部落 main branch（Gru 拥有）；
  Book ingest 源改 role branch、destination 改 main。
  门禁：pytest 绿、新项目按 Book 布局创建、Draft 写入与 Book 晋升端到端跑通。
  P4 锁定设计（2026-06-01 用户确认）：(a) 活 Draft 在 main；(b) Gru 工件全在 main；
  (c) 晋升用新 `mos_promote_to_book` 工具，Ethics 经 Draft 标注盖章、Gru 搬运。
  实测：1093 passed / ruff(minions) clean / audit 0 errors；project_create 端到端建出
  main=Book 布局（book/logic/src/evidence/draft/proposal/... 全 seed 在 main，无 -shared
  worktree）；`mos_promote_to_book` 端到端：Gru 把 sealed 文件搬进 logic/claims.md 并 commit，
  append 模式可加 claim，非-Book dst 正确拒绝。
  实现关键 / 设计协调：`project_shared_workspace==project_main_workspace`（路径层折叠，30
  个 caller 一处改动到位）；`create_shared_worktree` 变 no-op shim；main worktree seed
  时直接铺 Book 布局。**`mos_publish_to_shared` 保留**（不删）——它现在写 main 共享面，由
  per-project flock 串行化并发写；这与「role 只写自己 branch」协调为：Draft/signboard/
  reviews/submissions 直写 main（满足 Q1/Q2），role *deliverables* 走 role-branch→Ethics
  盖章→Gru `mos_promote_to_book` 进 Book（满足 Q3）。P4c：role SYSTEM.md（common/gru/
  ethics）的 branches/shared→main 文案 sweep。

- **P5 — 审稿接入六维严谨性 + Book 编译成论文 skill**（增量能力）✅ DONE 2026-06-01
  review 的 aspect/template/SYSTEM 折入六维严谨性（证据相关性 / 可证伪性 / 范围标定 /
  论证连贯 / 探索完整性 / 方法严谨；信息性，非门禁）；
  新增 `book-to-paper` skill：从 Book 生成
  abstract→introduction→related work→methodology→experiments→conclusion 的论文。
  门禁：review 产物含严谨性评估、能从样例 Book 生成可编译论文骨架。

  **Book→Paper 是必须实证验证的核心能力（用户 2026-06-01 强调）：**
  - 方法：拿真实论文（先用 ARA repo 自带的 `resnet-ara-example/` Book + 对应
    `resnet-paper.pdf` ground-truth 配对；可再借鉴 ARA 的 compile 思路把更多论文
    做成我们的 Book repo）→ 用我们**全部** writer 相关 skill（写作 + 排版 latex +
    画图 figure/chart）从 Book 端到端生成 Paper → 与 ground-truth 对比生成质量。
  - **迭代到收敛**：多轮 generate→compare→改 skill，直到我判断 book→paper（结合所有
    writer skill）质量稳定收敛，才正式落盘 skill。不 overclaim：每轮要有可对比的
    质量证据，而不是声称「能生成」。
  - **测试用纯 end-to-end（无 human-in-loop）**，以逼出系统的本质能力；但**生产写作
    仍保留 human-drive（Gru 人驱动）**——测试的 e2e 只是能力验证手段，不改变生产形态。

  **P5 as-built（实测，2026-06-01）：**
  - P5a 六维严谨性：折入 review 的 SYSTEM/aspect/simulate/run-round/finalize +
    aspect-note/reviewer-instance/consolidated/summary 模板；信息性非门禁；3-pass
    结构不破；decision parser 不受影响；review 内零 ARA/Seal/codex 字眼，路径全 main。
  - P5b Book→Paper：新增 `minions/roles/common/skills/book-to-paper.md`（v2），
    在真实配对（ResNet Book ↔ resnet-paper.pdf 12页）上**端到端实证两轮**：
    · R1（3 judges 评分）：端到端编出真实 13 页 PDF，9 张表数字零造假/零取整；
      mean≈3.7，未收敛——结构 3/5（单栏非双栏、缺概念图、无 appendix）、范围 4/5
      （一处 over-claim「ruled out」vs Book「argue/unlikely」）、证据 4/5。
    · R1→v2：把 7 条 delta 折进 skill（**最高优先级：modality 保真反 over-claim** +
      scope reconciliation + caption fidelity + trajectory 规则 + venue 双栏 +
      概念图 TikZ + 条件 conclusion/appendix）。
    · R2（v2）：双栏 + appendix + 残差块 TikZ 概念图 + refs 26→47 + **over-claim 已修**
      （intro 带 `% MODALITY GUARD`、"We argue… indicates"）+ 0 overfull + 数字精确。
      判定：**收敛，落盘 v2**。诚实记录：R2 的 judge agent 中途 wedge（empty-content
      失败），R2 评分是我直接对编译产物 vs ground-truth 的评估，非独立多评委——已在
      `book2paper-validation/round-2/RESULTS.md` 写明，不 overclaim。
  - 门禁实测：1093 passed / ruff(minions) clean / audit 0 errors / review+skill 零 ARA。

## 5. 不动的地方

- **viz / GUI / TUI 界面代码完全不动**（minions-viz/、minions-tui/）。不为本次重构适配。
- EACN3 本体（mcp-servers/eacn3/）作为依赖边界，不为补角色缺口而改。
- Agent 进化 / Skill 进化部分**保留**（留待以后或 human-drive 主动 split/merge）。
- 里程碑机制**保留**，但明确为 **Gru 或 human-drive 发起**（非全自动）。

## 6. 严谨性原则（不 overclaim）

- 任何「收益」不得作为 claim 直接上报：实践出真理，要在真实数据上度量 status-quo 与 fix。
- 每个 Phase 完成后跑门禁测试，如实报告通过/失败/跳过。
- 删除即删除（git 回溯）；但删前确认无悬挂引用（grep 调用点）。

