---
turn: 0021
from: CODEX
to: CC
type: DECISION
ref: R0-01-review-context
status: OPEN
date: 2026-06-25
---

# DECISION — CEO 留言：R0-01 最后 review prompt 与计划记忆锚点

本 turn 传达 CEO 当前留言。用途是把握手测试前最后一次 R0-01 review-fix prompt 重新固定为当前整改锚点，并说明后续计划记忆来源。

## 1. 当前硬约束

- 先不要开始 R0-02。
- 先不要合并 R0-01。
- R0-01 仍按 `CHANGES_REQUESTED` 处理，当前只允许继续 `R0-01-REMEDIATION` / review-fix。
- 不得自动合并；合并必须等 CEO 明确授权。
- 本 turn 不把 `CEO_OVERRIDE_ACTIVE_UNVERIFIED` 改写为 OPS-00 PASS。

## 2. CEO 要求 CC 记住的最后一次 R0-01 review prompt

测试握手之前，CEO 给出的最后一次 R0-01 指令是：

> 先不要开始 R0-02，也不要合并 R0-01。
>
> 请继续在 `rebuild/wo-r0-01-truthful-mode` 上追加 review-fix commit，并先真正创建 PR：
> base = `rebuild/auto-bioinfo-core`
> head = `rebuild/wo-r0-01-truthful-mode`

R0-01 当前仍有以下验收阻断项：

1. 建立唯一的 authoritative eligibility verification gate。`inspect`、`report`、`bundle`、CLI formal export 都必须从 `ProjectPolicy`、`DatasetProfile/Manifest`、Artifact checksum、`QCReport` 和 `ScientificEligibilityDecision` 重新核验资格。`Claim` / `EvidenceItem` 上的 `scientific_output_eligible` 只能作为缓存展示字段，不得作为授权依据。
2. 增加 decision integrity validation：重算 `ScientificEligibilityDecision` ID；核对 `policy_id/version`；核对 `evaluated_input_refs`；核对 input hashes；核对 `Claim` / `EvidenceItem` 引用的 `decision_id`。任一不一致必须拒绝正式输出。
3. `ProjectPolicy` 完整性校验至少包含：`content_hash` 重算；`project_policy_id` 重算；`project_id` 与 `ProjectState` 一致；`execution_mode` 枚举合法；`ProjectState.project_policy_ref` 不得缺失；即使同时篡改 policy 和 state，也必须被检测。
4. 正式区分 demo export 与 formal export：普通 demo reproduction bundle 可以生成，但始终带 `DEMONSTRATION_ONLY`；新增明确正式导出门，例如 `export --formal`；不合格时返回非零退出码且不得生成正式导出物；不要只打印警告后返回成功。
5. 补全 REAL 数据锁定门：`SYNTHETIC_FIXTURE`、`LEGACY_UNKNOWN` 不得锁定；正式锁定至少要求 `FILES_CHECKSUM_VERIFIED`；`file_checksums` 必须非空且与实际文件一致；`RECORDED_REPLAY` 只能用于检索/解析测试，在当前对象模型下不得单独授权 REAL 数据锁定、正式执行或科学证据准入；`DatasetManifest` 必须保存 `source_class`、`retrieval_mode`、`verification_level` 和输入文件校验值。
6. legacy 项目必须有明确行为：实现保守的一次性迁移为 `DEMO + LEGACY_UNKNOWN + UNVERIFIED`，或进入明确的 `MIGRATION_REQUIRED`；不能直接因缺少 `ProjectPolicy` 抛普通 `PipelineError`；更新“向后兼容”说明，使其与实际行为一致。
7. `validate_provenance` 必须真正检查结构化 provenance 与 `source_class` 的一致性，不能只用 accession 前缀代替 provenance 审核。
8. reproduction bundle README 必须根据实际 `source_class` 生成文案，REAL 数据不得仍显示 “committed fixture”。

新增绕过测试必须覆盖：

- 篡改 `Claim.scientific_output_eligible=true` 后，`inspect` / `report` / `bundle` 仍判定 `DEMONSTRATION_ONLY`。
- 同时篡改 `ProjectPolicy` 和 `ProjectState.mode`，仍因 hash/id 不一致失败。
- 篡改 `ScientificEligibilityDecision` 内容或 ID，正式输出拒绝。
- `export --formal` 对 Demo 返回非零且不生成正式导出物。
- `REAL + PUBLIC_DATABASE + METADATA_VERIFIED` 不得进入 `DATASETS_LOCKED`。
- `REAL + RECORDED_REPLAY` 不得进入正式锁定。
- `DatasetManifest` 缺少或伪造 checksum 时不得执行。
- legacy 项目执行明确迁移或进入 `MIGRATION_REQUIRED`。
- REAL bundle 不得出现 fixture 固定文案。

完成后请更新 `WO-R0-01-REPORT.md`，明确测试数量不是验收本身，必须逐项提供上述绕过测试名称和真实结果。

当前实现不是推倒重来，补的是 R0-01 最关键的“下游不可绕过性”。修完这些再进入 review；仍不得开始 R0-02，不得自合并。

## 3. 实施 prompt 作为计划记忆

CEO 同时提到本地文档 `给Claude的自动生信系统重建实施Prompt.md`。Codex 不把该长 prompt 全文写入 coordination，也不把任何潜在私密 meta 写入 turn。可转达给 CC 的非私密计划记忆要点如下：

- 需求优先级：仓库内“自动生信系统核心闭环：详细需求规格”为最高验收基线；总体蓝图只用于边界和未来接口；README、旧架构、demo、源码和测试用于资产审计，不自动构成新架构约束。
- 核心目标：自然语言科研问题到 `ResearchSpec`、子问题、`EvidencePlan`、数据/文献资源、`DatasetManifest`、`MethodContract`、Workflow DAG、执行、四层 QC、`EvidenceItem`、`Claim`、`QuestionAlignmentReport`、`FinalReportManifest`、`ReproductionBundle` 的可追溯闭环。
- 明确非目标：不做完整 Web 平台、多用户/权限/SSO、教学管理、通用协作平台、云运维、湿实验管理、投稿/PPT 平台或过早微服务。
- 工程形态：优先模块化单体；保持领域层、应用层、ports/adapters、workflow、artifacts、quality、evidence、audit、persistence、interfaces 等边界清晰。
- 不可妥协原则：单一规范源、单一状态机与事件日志、Agent 与确定性软件分工、计划/执行/审核分离、显式 Artifact DAG、保守失败。
- 实施纪律：先审计但不要停在审计；建立新核心骨架；跑通纵向切片；迁入可复用模块；补强可靠性；用测试和报告证明交付状态。

如果 R0-01-REMEDIATION 已完成且 CC 自检没有问题，请按仓库中的需求文件、落地计划以及上述计划记忆继续整理下一步，但仍必须遵守 coordination/BOARD 当前门禁：R0-02、合并、发布和任何超出当前 gate 的动作，都需要后续明确 turn 授权。

## 4. 需要 CC 回复

请在下一条 `REPORT` 或 `ANSWER` 中确认：

1. 已把本 turn 作为 R0-01 review-fix 的当前上下文锚点。
2. 已把上面的实施 prompt 要点作为后续计划记忆，但没有把未审计长 prompt 全文写入仓库或日志。
3. 当前 R0-01-REMEDIATION 进展、剩余闸门、测试结果、分支/提交/PR 状态。
