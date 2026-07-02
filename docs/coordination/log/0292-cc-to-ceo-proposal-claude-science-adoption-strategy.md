---
turn: 0292
from: CC
to: CEO
type: PROPOSAL
ref: claude-science-adoption-strategy
status: OPEN
date: 2026-07-01
---

# PROPOSAL：Claude Science 采用策略（方向性提案，非可执行 WO）

## 0. 性质与边界（先声明）

- 本条是**方向性提案**，不是工作单，**不请求现在执行任何代码改动**。
- 当前执行门禁在 WP-06（intake），Claude Science 相关工作全部落在更下游的端口，尚未到执行位。按 **G2**（只冻结当前与紧邻下一个 WO），本提案只登记方向、不冻结远期 WO 清单。
- 本提案**不修改产品目标、验收标准或宪法**（守 §1.5）。正式采用需 CEO 决策、Codex 落成 DECISION 后方对 CC 生效。

## 1. 背景

- 2026-06-30 Anthropic 发布 **Claude Science**：一个跑在自有机器（笔记本 / Linux / HPC 经 SSH）上的科研工作台，本质是 Claude + 60+ 生信 skills/connectors + reviewer agent + 可复现产物层；用现有模型、API 额度计费、标准公开模型。
- CEO 已提交 AI for Science / Claude Science Cohort 资助申请（最高 $30,000 API 额度，2026-09-01 → 12-01）。
- 关键契合点：我们的架构早已把 LLM 与外部资源放在**端口之后**（WP-05 供应商无关 LLM 端口已 COMPLETE；资源发现 / 执行端口为 RESERVED）。因此 Claude Science 可作为**端口背后的一个适配器**接入，**无需改动已冻结架构**。

## 2. 不可违犯约束（采用时必须守住）

1. **供应商无关（§5.6）**：Claude Science 只能作为 LLM 端口的**一个可替换适配器**，不得让领域核心或状态机依赖 Anthropic 专有行为。默认仍是"只有公开、非敏感信息可离开本地"。
2. **claim 天花板（§2.3）**：借助 Claude Science 做综合/审稿时，RNA DEG 仍封顶 `association`，不得越级。
3. **强制停审点（§4）**：以下每一处采用前必须停审 / 提交 BLOCKER，不得当普通实现细节绕过——
   - §4.5 数据/内容发送给外部 LLM/服务前；
   - §4.6 启用付费服务前（Claude Science / Modal 额度）；
   - §4.3 首次使用真实人类来源数据前。
4. **不硬编码疾病/GEO 方向（§5 禁止项）**：连接器取到的数据集不得被写死为永久产品方向。

## 3. 五个集成点（各自挂哪个端口 + 触发哪个停审点）

| # | 集成点 | 挂载位置（阶段/端口） | 价值 | 触发停审点 |
|---|---|---|---|---|
| 1（最高杠杆） | 真实数据/文献发现 | `RESOURCES_DISCOVERED` / `DATASETS_LOCKED` 的资源发现适配器（当前仅 fixture，生产适配器从未实现） | 用现成 60+ connectors（PubMed/GEO/10x/ClinicalTrials/ToolUniverse）替代自建爬虫与 accession 校验；取到的 ID 可核验，满足"禁止伪造 accession" | §4.3 真实数据、§4.5 外部服务 |
| 2 | LLM 推理层 | RESERVED 的网络 LLM 端口（WP-05 接口已就绪） | 问题规范化 / 拆解 / 证据规划 / 方法适配 / 综合，替换离线确定性 planner | §4.5 外部 LLM、§4.6 付费 |
| 3 | 扩充方法库 | `methods/`（registry + MethodContract） | 单细胞/CRISPR/蛋白结构等现成 skill 出草稿实现，CC 审入 registry | 无（草稿在本地审核，不自动执行） |
| 4 | 审稿增强 | `ALIGNMENT_AUDITED` / 断言天花板审计 | Claude reviewer 作为原问题对照之外的第二道独立检查（查引用/查算错），与护栏哲学同向 | §4.5 |
| 5 | 真实执行 | RESERVED 的 Nextflow 执行端口（本机/HPC/Modal） | 真数据集跑批时不用自建调度 | §4.3、§4.6 |

## 4. 一个诚实的边界

Claude Science 是**人在旁边、到新资源前先问**的交互式工作台；我们的 loop 要**无人值守自动跑**。因此在全自动 loop 内部，更可能采用其背后的 **skills/connectors + API**，而非交互界面。补助发的正是 **API 额度**，方向一致。这不改变"上层自动编排=我们自有价值、Claude Science=端口背后的手"的分工。

## 5. 建议的第一步（待到达相关阶段时）

当流水线推进到资源发现阶段，建议以**集成点 1（真实数据发现）**起一个**试点 WO**：在一个 `RESOURCES_DISCOVERED` 适配器里调用 Claude Science 连接器，取一个真实公开 bulk RNA-seq 数据集，跑通到复现包；产出"自建 vs Claude Science"对比（省时、可复现率、是否踩护栏），据此再决定是否推广到其余端口。该 WO 届时须经正常握手派发，并在执行前逐条过 §4 停审点。

## 6. 请求 CEO 裁定

1. 是否**认可本方向**（Claude Science 作为端口背后适配器、供应商无关、守停审点）作为登记在案的策略？
2. 若认可，请 Codex 在流水线到达资源发现/LLM 运行时阶段时，据此落成对应 WORK_ORDER；在此之前本提案保持 status: OPEN 仅作方向记录，不驱动执行。
3. 本提案不影响 WP-06e / PR #45 当前握手（那条仍轮到 Codex 复审）。
