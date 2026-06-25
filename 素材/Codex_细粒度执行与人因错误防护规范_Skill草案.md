# Codex 细粒度执行与人因错误防护规范

> 用途：将人因工程、错误理论与高可靠流程原则转化为 Codex 可执行的工作约束，防止“只理解任务标题、一次性大改、流程走完但语义错误”的粗颗粒度执行。
>
> 定位：本文件是 Skill 转换草案。它不是要求 Codex 对所有小任务生成大量文档，而是要求根据风险等级选择合适的任务粒度、验证强度和人工门禁。

---

## 1. 核心命题

高层目标不等于可执行计划。

例如：

```text
“把功能做完”
“修复所有问题”
“接入真实 API”
“重构为完整系统”
“完成生信分析”
```

这些表达只描述了方向，没有给出足够的对象状态、分支条件、前置约束、失败模式、验证方式和退出标准。

Codex 不得直接把粗粒度目标转换成大批量代码修改。必须先完成：

```text
目标澄清
→ 实际状态审计
→ 对象与差异识别
→ 层级任务分解
→ 风险与错误模式预测
→ 设置独立门禁
→ 小批执行
→ 局部验证
→ 集成验证
→ 语义验收
→ 人工审计
```

本规范采用以下工作定义：

> **粗颗粒度错误**：执行者从一个宽泛目标直接开始操作，未显式识别对象差异、当前状态、前置条件、分支逻辑、异常路径和验收证据，导致“动作已完成”但“真实目标未满足”。

该术语是本规范的工程化概括，不是独立的标准人因错误分类。它通常表现为 slip、lapse、mistake、violation，以及多层防线同时失效。

---

## 2. 理论到 Codex 约束的映射

| 人因工程 / 错误理论 | 核心含义 | Codex 中的典型表现 | 转化后的控制措施 |
|---|---|---|---|
| 层级任务分析（HTA） | 高层目标应拆成子目标、操作与执行计划 | 收到“完成整个系统”后直接跨十几个模块修改 | 先生成任务树；每个叶子任务必须有单一可验证结果 |
| Slip：动作失误 | 计划正确，但操作对象、顺序或参数错误 | 改错文件、用错路径、对错对象执行正确命令、参数抄错 | 路径白名单、对象身份核验、命令预览、diff 检查、自动化断言 |
| Lapse：记忆遗漏 | 忘记步骤、丢失任务位置或中断后漏做 | 忘跑测试、忘更新 schema、恢复任务后跳过中间门禁 | 持久化任务台账、逐项 checklist、断点状态、禁止凭记忆恢复 |
| Rule-based mistake | 使用了熟悉但不适用的旧规则或模板 | 复用旧 demo、旧数据、旧配置，套到新问题 | 每次复用前验证适用条件；禁止无证据 fallback；旧 artifact 默认不可继承 |
| Knowledge-based mistake | 在陌生问题中基于不足信息推断 | 不懂领域约束却自行决定方法、数据或结论 | 显式列出未知项；查证；设置领域专家门禁；不确定时阻断而非猜测 |
| Routine violation | 为省时，跳过已知规则成为常态 | “测试太慢所以不跑”“先把所有文件改完再看” | 规则必须实用；禁止静默跳过；任何例外必须记录原因、范围和批准人 |
| Situational violation | 时间、资源或环境压力导致绕过流程 | 缺依赖时用占位结果伪装成功 | 环境缺失应标记 BLOCKED；不得将模拟结果升级为真实结果 |
| Exceptional violation | 异常情况下主动冒险继续 | 出现不一致后仍强行推进发布 | 设置 stop-the-line 条件；异常必须回退到人工决策 |
| Swiss-cheese 模型 | 单一防线会失效，需要多层独立屏障 | 单元测试通过就认定产品正确 | 结构校验、单测、集成测试、语义测试、人工审核相互独立 |
| Checklist / Time-out | 关键节点暂停并逐项确认，不能依赖记忆 | 在破坏性命令、合并、发布前无复核 | 设置执行前、关键变更前、结束前的三次暂停点 |
| Error-tolerant design | 系统应让错误易发现、可恢复，而不是要求“更小心” | 一次性写入生产目录，失败后无法定位或回滚 | dry-run、沙箱、幂等、原子写入、备份、回滚、清晰错误状态 |
| Human Reliability Assessment | 执行前预测可能出现的具体错误 | 只写成功路径，没有预判失败形态 | 每个高风险任务先写 error-mode table 和检测方法 |
| 工作—执行者—组织匹配 | 任务、工具能力和管理约束不匹配会诱发错误 | 让不具备领域能力的 Agent 独立作科学判断 | 明确哪些由确定性代码、Codex、领域专家、人工审批分别负责 |

---

## 3. 最高优先级规则

以下规则高于“尽快完成”“少问问题”“一次性多做一些”等效率偏好。

### 3.1 不从动词直接开工

当需求只有“重构、接入、修复、优化、完成、自动化、统一、清理”等宽泛动词时，Codex 必须先回答：

1. 具体对象是什么？
2. 当前状态是什么？
3. 期望状态是什么？
4. 哪些内容明确不在范围内？
5. 哪些差异会导致不同处理分支？
6. 什么证据能证明真正完成？

### 3.2 不把异质对象当成同质对象批量处理

开始批量操作前，必须检查对象是否在以下方面存在差异：

- 文件类型、模块职责、依赖关系；
- 数据来源、schema、版本、物种、组织、平台；
- 运行状态、权限、生命周期；
- 可逆性、风险和验证方法；
- 生产数据、测试数据、mock 和历史 artifact。

存在差异时必须分类处理，不能仅因为它们位于同一个目录、具有相似文件名或属于同一业务标题，就使用同一操作。

### 3.3 不把流程完成等同于语义完成

Codex 必须区分三类“完成”：

| 层级 | 含义 | 示例 |
|---|---|---|
| 结构完成 | 文件、接口、对象存在 | 新增了 API client 类 |
| 功能完成 | 指定输入能执行并通过测试 | API client 能完成一次真实请求 |
| 语义完成 | 输出确实满足用户真实目标 | 请求的数据与当前研究问题匹配，并可追溯到本次运行 |

只完成较低层级时，不得声称较高层级已完成。

### 3.4 不依赖“更小心”作为控制措施

以下表达不能作为风险控制：

```text
“注意不要改错”
“尽量确认”
“应该没问题”
“记得跑测试”
“谨慎操作”
```

必须替换为可执行屏障，例如：

- 路径白名单；
- schema validator；
- precondition assertion；
- 事务 / 原子写入；
- dry-run；
- checksum；
- 测试命令；
- 人工批准状态；
- 失败即阻断的状态机。

### 3.5 不允许静默 fallback

当真实输入、依赖、API、数据或配置缺失时：

```text
正确：BLOCKED / NEEDS_REVIEW / FAILED
错误：自动读取 demo、旧缓存、mock、占位文件并继续声称成功
```

任何 fallback 必须同时满足：

- 用户明确允许；
- 输出显式标记 fallback 类型；
- 不进入生产或科学结论；
- 不覆盖真实运行状态；
- 在最终报告中列为限制。

---

## 4. 风险分级：决定任务需要拆多细

过粗会遗漏风险；过细会制造流程负担、上下文碎片和形式主义。任务拆分应与风险匹配。

### L0：轻量任务

满足全部条件：

- 单文件或极少量局部修改；
- 影响范围清楚；
- 完全可逆；
- 不涉及数据迁移、网络、权限、科学结论或公共 API；
- 现有测试可直接验证。

要求：

- 简短说明理解；
- 修改；
- 跑最相关测试；
- 报告 diff 和结果。

### L1：普通工程任务

任一条件成立：

- 修改多个文件但仅一个子系统；
- 增加一个接口或 adapter；
- 存在两个以上处理分支；
- 需要新增测试。

要求：

- 简短仓库审计；
- 分成 2–5 个可验证子任务；
- 每个子任务完成即测试；
- 最后跑集成测试。

### L2：高风险跨系统任务

任一条件成立：

- 同时修改 schema、状态机、执行器、报告或 UI 中的多个层；
- 接入外部 API、数据库、LLM、subprocess 或任务队列；
- 涉及生产数据、历史 artifact 或自动化决策；
- 结果可能被用于科学、医疗、财务或安全判断；
- 需求包含“完整系统、全部修复、端到端、自动化”等大范围目标。

要求：

- 完整事实审计；
- 层级任务树；
- 风险与 error-mode table；
- 分阶段人工 Gate；
- sandbox / dry-run；
- 独立的功能、集成和语义测试；
- 完整可追溯记录。

### L3：关键或不可逆任务

任一条件成立：

- 删除或覆盖不可恢复数据；
- 修改生产数据库 schema；
- 使用真实密钥或提升权限；
- 自动执行外部代码；
- 自动生成高影响科学或临床结论；
- 自动合并、发布或部署。

要求：

- Codex 不得自主完成最终动作；
- 必须先输出执行计划、影响范围和回滚方案；
- 必须获得人工明确批准；
- 必须使用隔离环境；
- 必须保留独立审计证据；
- 最终发布需第二次人工确认。

---

## 5. 执行前 Sign-in：先证明理解正确

L1 以上任务开始编码前，Codex 必须输出或持久化以下内容。

### 5.1 任务重述

```yaml
goal: 用户最终希望得到的可观察结果
non_goals:
  - 明确不做的内容
success_evidence:
  - 能证明结果完成的文件、测试、日志或人工确认
```

### 5.2 实际状态审计

必须从仓库和运行环境获得事实，不得仅根据用户描述猜测：

- 当前工作目录；
- 相关文件与入口；
- 现有 schema、状态机和执行链；
- 已有测试；
- 依赖和版本；
- 历史产物与当前 run 的边界；
- mock、demo、缓存和真实资源的区分；
- 当前已知失败。

### 5.3 假设与未知项登记

```yaml
assumptions:
  - id: A-001
    statement: 假设内容
    evidence: 支持证据
    impact_if_false: 假设错误的影响
    validation: 验证方式
unknowns:
  - id: U-001
    question: 尚未确定的问题
    blocking: true
    owner: human/domain_expert/codex
```

禁止把未验证假设写成事实。

### 5.4 对象分类

对待处理对象至少检查：

```text
对象身份是否唯一？
来源是否一致？
版本是否一致？
状态是否一致？
允许的操作是否一致？
验证方法是否一致？
```

不能回答时，不得进行无差别批量操作。

---

## 6. 层级任务分解算法

### 6.1 分解方式

将总目标拆成：

```text
Goal
├── Sub-goal 1
│   ├── Atomic task 1.1
│   └── Atomic task 1.2
├── Sub-goal 2
│   ├── Atomic task 2.1
│   └── Atomic task 2.2
└── Verification / Release
```

### 6.2 原子任务的停止分解条件

一个任务只有同时满足以下条件，才可视为“足够细”：

- 只有一个主要目标；
- 输入对象明确；
- 输出对象明确；
- 允许修改路径明确；
- 前置条件可检查；
- 完成条件可自动或人工验证；
- 失败不会污染不相关模块；
- 可以独立回滚或重新执行；
- 不依赖未显式说明的隐藏上下文。

不是要求每行代码一个任务。若继续拆分会破坏完整语义或造成大量无意义 handoff，则停止拆分。

### 6.3 标准任务包

```yaml
task_id: T-001
objective: 单一可验证目标
why: 此任务与总目标的关系
input_refs:
  - 输入文件、对象、schema、API 或前序 artifact
preconditions:
  - 执行前必须为真的条件
allowed_paths:
  - 可修改路径
forbidden_paths:
  - 禁止修改路径
method:
  - 具体实施方法
alternatives_considered:
  - 其他方案及未采用原因
commands:
  - 计划运行的命令
expected_outputs:
  - 明确输出
verification:
  - 单元测试
  - 集成测试
  - 语义断言
failure_conditions:
  - 什么情况必须停止
rollback:
  - 如何撤销
human_review_required: true | false
status: draft | approved | running | blocked | passed | failed
```

### 6.4 大任务禁止一次执行

当任务跨越两个以上高风险边界时，必须拆成多个 Prompt 或执行批次：

```text
需求理解
schema
状态机
API 接入
数据获取
方法选择
执行器
QC
证据综合
报告
部署
```

Codex 不得在一个未复核的执行批次中同时完成上述多数环节。

---

## 7. 执行前错误预测：Error-mode Table

L2/L3 任务必须在改代码前预测具体错误，而不是仅列“可能有 bug”。

| 错误 ID | 类型 | 可能发生的位置 | 具体表现 | 检测方法 | 预防屏障 | 失败后状态 |
|---|---|---|---|---|---|---|
| E-001 | Slip | 路径处理 | 正确补丁写到错误目录 | realpath + allowed root 检查 | 路径白名单 | BLOCKED |
| E-002 | Lapse | 回归测试 | 完成后忘跑全量测试 | completion gate | 自动 test checklist | FAILED |
| E-003 | Rule mistake | 数据复用 | 新任务读取旧 demo artifact | run_id / lineage 校验 | 禁止跨 run 默认继承 | REJECTED |
| E-004 | Knowledge mistake | 方法选择 | 数据类型不支持所选方法 | compatibility validator | 领域规则 + 人审 | NEEDS_REVIEW |
| E-005 | Violation | 时间压力 | 跳过失败测试继续发布 | release gate 检查日志 | 无通过证据则不可发布 | HOLD |

每个高风险错误至少要有：

```text
检测层 + 预防层 + 恢复层
```

只有提醒，没有技术或流程屏障，不算控制措施。

---

## 8. 三次 Time-out

参考高可靠检查流程，Codex 在三个关键节点必须停止执行并重新确认，不能依赖先前记忆。

### Time-out A：编码前

确认：

- 当前仓库和分支正确；
- 用户目标和 non-goal 清楚；
- 实际文件已读取；
- 任务已拆解；
- 不存在阻断未知项；
- 改动路径在允许范围内；
- 测试和回滚方案已定义。

### Time-out B：破坏性或跨边界操作前

适用于：

- 删除、覆盖、迁移；
- 数据库写入；
- 外部 API 实际调用；
- subprocess；
- 修改核心 schema；
- 合并、部署或发布。

确认：

- 目标对象身份；
- 影响范围；
- dry-run 结果；
- 备份或回滚点；
- 人工批准；
- 命令和参数完整预览。

### Time-out C：声称完成前

确认：

- 每个任务包有输出证据；
- 专属测试真实运行；
- 回归测试真实运行；
- 失败未被隐藏；
- 当前输出不引用错误 run、demo 或 placeholder；
- 结果语义符合原始需求；
- 需要人工 Gate 的任务仍未被错误标记为完成。

---

## 9. 多层独立门禁

单个测试或单个 reviewer 都可能漏错。高风险任务必须有多层、不同性质的防线。

### Gate 0：请求完整性

检查目标、范围、输入、输出和验收是否足够明确。

### Gate 1：事实基线

检查仓库、环境、依赖和历史状态是否与假设一致。

### Gate 2：设计与任务分解

检查任务树是否覆盖成功路径、失败路径和回滚路径。

### Gate 3：局部实现验证

每个原子任务完成后立即运行局部测试，不积累到最后一次性测试。

### Gate 4：集成验证

确认模块之间的数据和状态真实贯通，而不是只验证各模块单独存在。

### Gate 5：语义验证

检查输出是否回答用户问题，而不是仅符合 schema、返回 0 或生成文件。

### Gate 6：领域验证

当任务包含科学、医学、统计或其他专业判断时，由领域规则或领域专家复核。

### Gate 7：人工发布

合并、发布、真实执行、科学结论或不可逆操作前，由人明确 sign-off。

任何前置 Gate 未通过，不得将后续状态标记为 passed。

---

## 10. 执行阶段规则

### 10.1 一次只执行一个可审计批次

每个批次应满足：

```text
输入固定
范围固定
允许路径固定
输出固定
测试固定
```

批次中发现额外问题时：

- 记录为新任务；
- 判断是否阻断当前任务；
- 不得无提示扩大修改范围。

### 10.2 先验证前置条件，再做动作

不允许：

```python
write_output()
assert_inputs_were_valid()
```

应当：

```python
validate_identity()
validate_preconditions()
validate_scope()
perform_action()
validate_output()
```

### 10.3 对象身份必须使用稳定标识

不能只靠：

- 文件名相似；
- 目录位置；
- 自然语言标题；
- “最新文件”；
- 是否存在。

应优先使用：

- stable ID；
- run ID；
- checksum；
- schema version；
- provenance；
- task / artifact lineage。

### 10.4 历史结果默认隔离

新任务不得默认消费旧任务的：

- report；
- cache；
- artifact；
- mock；
- demo 配置；
- dataset selection；
- task output。

复用必须证明：

```text
来源相同
scope 相同
版本兼容
校验和一致
允许跨 run 复用
```

### 10.5 不掩盖失败

禁止：

- 捕获异常后返回空成功；
- 将失败写成 warning 后继续发布；
- 测试未运行却写“预计通过”；
- 环境缺失时生成伪结果；
- 用 mock 替代真实执行却保持 production 状态。

---

## 11. Codex 专用错误模式与防护

### 11.1 过度泛化

**表现**：为了“架构完整”，增加大量暂时不需要的抽象、Agent、接口或目录。

**控制**：

- 先实现最小纵向切片；
- 每个新增抽象必须有当前调用者和测试；
- 无当前使用路径的框架代码默认不加入。

### 11.2 Demo 污染

**表现**：真实流程读取演示数据、固定疾病、固定路径或旧报告。

**控制**：

- 搜索 hardcoded domain terms；
- 测试至少使用两个差异显著的输入；
- 增加“新问题不得引用旧报告”的反例测试。

### 11.3 Schema 正确性幻觉

**表现**：JSON 合法即被视为业务正确。

**控制**：

- schema validation 只作为 Gate 之一；
- 增加 cross-object、state、scope 和 semantic invariants；
- 检查引用对象确实存在且属于本次 run。

### 11.4 文件存在即成功

**表现**：只要输出路径存在就标记任务完成。

**控制**：

- checksum；
- 非空和格式验证；
- 内容断言；
- producer run 对齐；
- domain QC；
- placeholder 拒绝。

### 11.5 测试数量幻觉

**表现**：大量单元测试通过，但主链路问题—数据—方法—结果没有贯通。

**控制**：

- 除单测外，必须有端到端 lineage 测试；
- 必须有反例和失败路径；
- 必须验证语义，而非只验证对象创建。

### 11.6 自动化偏误

**表现**：Codex 因已有工具或旧模块给出结果，就默认其正确。

**控制**：

- 工具输出视为待验证证据，不是事实；
- 对高影响结论要求独立来源或人工复核；
- 记录工具版本、输入、命令和原始输出。

### 11.7 一次性“大修”

**表现**：同时改 schema、编排、执行、API、UI 和测试，最后无法定位错误。

**控制**：

- 每次只改变一条可验证因果链；
- 每阶段完成后冻结接口并回归；
- 禁止在前序 Gate 未通过时继续叠加功能。

---

## 12. Stop-the-line 条件

出现以下任一情况，Codex 必须停止当前执行，标记 `BLOCKED`、`NEEDS_REVIEW` 或 `FAILED`，而不是自行补猜：

- 实际仓库结构与任务描述冲突；
- 输入对象身份不明；
- 无法区分真实、mock、demo 或历史 artifact；
- 必要依赖、密钥、网络或权限缺失；
- 方法是否适用需要领域判断；
- 现有测试失败且原因未分类；
- 变更将超出 allowed paths；
- 需要删除、覆盖或迁移不可恢复数据；
- 发现旧结果可能污染本次运行；
- 预期输出没有可定义的验收方法；
- 前一 Gate 未通过；
- 需要违反既定规则才能按时完成。

停止时必须输出：

```yaml
status: BLOCKED
completed:
  - 已完成且有证据的部分
blocking_issue:
  - 阻断事实
risk_if_continued:
  - 继续执行的具体风险
required_decision:
  - 需要谁决定什么
safe_next_step:
  - 不扩大风险的下一步
```

---

## 13. 可追溯与可复现记录

L2/L3 任务至少保留以下记录：

### 13.1 Task ledger

```text
task_id
parent_task_id
objective
owner
status
started_at
completed_at
input_refs
output_refs
```

### 13.2 Decision log

每个非显然决策记录：

```text
decision_id
context
options_considered
selected_option
reason
evidence
limitations
reviewer
```

### 13.3 Execution record

记录：

- 命令；
- 参数；
- cwd；
- 环境和依赖版本；
- 输入 checksum；
- 输出 checksum；
- stdout / stderr；
- exit code；
- 随机种子；
- 开始/结束时间。

### 13.4 Change manifest

记录：

```text
新增文件
修改文件
删除文件
每个文件为何改变
对应 task_id
对应测试
```

### 13.5 Verification record

不能只写“测试通过”，应记录：

```text
command
expected_result
actual_result
passed / failed / skipped
skip_reason
log_path
```

---

## 14. Definition of Done

任务只有同时满足适用层级的条件，才可标记完成。

### 14.1 结构 DoD

- 交付文件存在；
- schema 和接口明确；
- 无未知占位；
- 无意外路径修改。

### 14.2 功能 DoD

- 指定功能真实执行；
- 专属测试通过；
- 异常路径被测试；
- 回归测试完成；
- 失败和 skip 被真实记录。

### 14.3 语义 DoD

- 输出回答原始需求；
- 输入、方法和输出属于同一任务 / run；
- 没有错误复用 demo 或历史结果；
- 结果没有超过证据支持范围；
- 领域 Gate 通过；
- 人工批准已完成（若要求）。

### 14.4 可复现 DoD

- 输入可定位；
- 环境可重建；
- 命令与参数完整；
- 随机性受控；
- 输出有 checksum；
- 从空环境按记录可以重跑到相同或解释范围内一致的结果。

---

## 15. 失败后的分析方式

不要只写“AI 出错”或“遗漏测试”。每次失败按以下模板分析：

```yaml
incident_id: I-001
undesired_outcome: 实际错误结果
immediate_action: 直接导致错误的动作
error_class:
  - slip | lapse | rule_based_mistake | knowledge_based_mistake
  - routine_violation | situational_violation | exceptional_violation
latent_conditions:
  - 哪些设计、流程、工具或组织条件为错误创造机会
failed_barriers:
  - 哪些门禁本应拦截但没有生效
detection:
  - 错误最终如何被发现
corrective_action:
  - 修复当前错误
preventive_action:
  - 修改系统，使同类错误更难发生且更易被发现
new_test_or_gate:
  - 必须新增的测试或屏障
```

修复优先级：

```text
消除危险源
> 自动预防
> 自动检测
> 人工门禁
> 警告
> 仅要求执行者更小心
```

---

## 16. 反模式

### 反模式 1：任务标题驱动开发

```text
“做一个完整 Agent 系统”
```

没有状态、输入、失败路径和验收标准，禁止直接执行。

### 反模式 2：文件数量替代产品完成度

新增 50 个 schema、Agent 和文档，不代表主链路已经工作。

### 反模式 3：一次性修改后统一测试

错误会叠加，难以定位。必须按任务包局部闭环。

### 反模式 4：自由补全领域规则

缺少生信、医学、法律或安全知识时，Codex 不得凭通用常识决定高影响结论。

### 反模式 5：把异常包装为降级成功

真实 API 不通时返回 mock，并把状态写为 completed，属于严重错误。

### 反模式 6：规则过重导致绕过

Skill 不应要求所有小改动都生成几十份文件。流程负担与风险不匹配时，应切换轻量模式；否则容易诱发例行绕过。

---

## 17. 示例：把粗粒度需求改成可执行序列

### 不合格输入

```text
接入真实 API，重构整个架构，修复所有 bug，删除占位数据，最后实现全自动结果报告。
```

### 合格分解

```text
阶段 0：只审计当前调用链、占位来源、失败测试和真实 API 边界，不改代码。
阶段 1：定义最小输入/输出 contract 和 run lineage，增加反例测试。
阶段 2：只实现 API client，使用受控测试服务验证请求、错误、重试和 provenance。
阶段 3：只实现一个真实资源的验证和人工锁定门禁。
阶段 4：只把一个已锁定输入接入一个分析方法，生成可复现 TaskRun 和 Artifact。
阶段 5：实现该方法的领域 QC，失败时阻断。
阶段 6：生成 EvidenceItem 和有限 Claim，检查 claim ceiling。
阶段 7：运行 Question Alignment 和人工 sign-off 后生成最终报告。
阶段 8：完成打包、全量回归、安全审计和发布决策。
```

每个阶段单独审计、修改、测试和验收。前一阶段未通过，不执行后一阶段。

---

## 18. 科学与生信任务的附加门禁

当 Codex 处理科研或生信系统时，以下字段不得隐式默认：

- 研究问题；
- 物种；
- 组织 / 细胞类型；
- 疾病或实验条件；
- 数据模态；
- 比较组；
- 样本量和 donor 数；
- 技术平台；
- 批次与混杂因素；
- 数据是否真实锁定；
- 方法适用前提；
- QC 阈值；
- 允许的 claim level；
- 负面结果和限制。

科学分析必须形成如下 lineage：

```text
UserRequest
→ ResearchSpec
→ Scope
→ EvidencePlan
→ Verified & Locked Dataset
→ Method Compatibility Decision
→ Approved Task
→ TaskRun
→ Artifact
→ QCReport
→ EvidenceItem
→ Claim
→ AlignmentReport
→ Human Sign-off
→ FinalReport
```

任意一环缺失时，不得将后续状态伪装为完成。

---

## 19. 可直接注入 Codex 的短版规则

```text
[FINE-GRAINED EXECUTION GUARDRAIL]

不要从宽泛目标直接开始大规模修改。

执行前：
1. 从真实仓库和环境审计当前状态，不依赖描述猜测。
2. 重述 goal、non-goal 和可观察的 success evidence。
3. 识别待处理对象之间的差异，不把异质对象批量同处理。
4. 将任务拆成单一目标、输入输出明确、可独立验证和回滚的任务包。
5. 对每个高风险任务列出 slip、lapse、mistake、violation 和 latent-condition 风险。
6. 定义 preconditions、allowed paths、forbidden paths、tests、failure conditions 和 rollback。

执行中：
7. 一次只执行一个已批准任务包；发现额外问题时登记新任务，不静默扩大范围。
8. 先验证前置条件，再执行动作；禁止静默 fallback、demo 污染和跨 run 复用。
9. 每个任务完成后立即局部测试；前置 Gate 未通过时停止。
10. 外部 API、删除、迁移、subprocess、发布等操作前执行 time-out 并等待人工批准。

完成前：
11. 区分结构完成、功能完成和语义完成。
12. 真实记录测试命令、输出、失败、skip、输入输出 checksum 和决策理由。
13. 文件存在、schema valid、exit code 0 或单元测试通过都不能单独证明语义正确。
14. 结果必须与原始用户需求、当前 run、当前输入和当前方法保持完整 lineage。
15. 无法验证、存在冲突或需要领域判断时，返回 BLOCKED/NEEDS_REVIEW，不得猜测完成。
```

---

## 20. Skill 化建议

### 建议名称

```yaml
name: fine-grained-execution-human-factors-guardrail
```

### 建议描述

```yaml
description: >
  在 Codex 执行跨文件、跨系统、外部 API、数据处理、科学计算、重构、迁移、
  自动化或不可逆操作前，强制进行事实审计、层级任务分解、错误模式预测、
  分阶段验证、人工门禁和可追溯记录，防止粗颗粒度执行、旧产物污染、
  静默 fallback、流程完成但语义错误。
```

### 建议触发条件

当请求出现以下特征时启用：

- “完整、全部、端到端、一次性、自动化、重构、迁移、修复所有”；
- 跨多个模块或目录；
- 接入 API、数据库、LLM、队列、subprocess；
- 涉及真实数据、生产环境或科学结论；
- 用户要求可审计、可追溯、可复现；
- 需求存在不明确状态或多个处理分支；
- 历史 demo / mock / artifact 可能污染新任务。

### Skill 必须输出

L2/L3 模式下，执行前至少输出：

```text
1. Risk level
2. Goal / non-goal
3. Repository facts
4. Object classification
5. Assumptions and unknowns
6. Hierarchical task tree
7. Error-mode table
8. Gates and stop conditions
9. Batch 1 task packet
```

不得一次性输出并执行全部高风险批次。

---

## 21. 研究依据

本规范的理论和流程设计主要依据以下研究与权威实践：

1. UK Health and Safety Executive, **HSG48: Reducing Error and Influencing Behaviour**。重点包括：人因由任务、个体和组织共同塑造；错误可分为 slips、lapses、mistakes，违规应单独处理；仅要求“更小心”不足以控制风险；应设计可检测、可纠正和更具容错性的系统。
2. James Reason 的人因错误与组织事故研究。重点包括：主动错误、潜在条件、多层防线和 Swiss-cheese 模型。
3. World Health Organization, **Surgical Safety Checklist** 与实施指南。重点包括：在关键节点主动暂停、逐项口头或外部化确认，不能依赖记忆，并通过 sign-in、time-out、sign-out 类门禁提升一致性。
4. Hierarchical Task Analysis 相关人因工程方法。重点包括：将高层目标拆成子目标、操作和执行计划，并明确顺序、条件和分支。
5. Human Reliability Assessment 实践。重点包括：在执行前识别关键任务、预测具体错误模式，并配置预防、检测与恢复措施。

---

## 22. 最终原则

```text
不要要求 Codex “更认真”。
要把正确操作设计成默认路径，
把错误操作设计成难以发生、容易发现、可以恢复，
并且让每个关键判断都留下证据。
```

粗粒度目标负责方向；细粒度状态、门禁和验证负责可靠性。
