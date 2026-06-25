# 目标架构（Phase 0 / 本次落地版）

- **状态**：本次交付实现 = 轻量离线核心 + 一条端到端垂直切片；重型基础设施以端口预留。
- **北极星**：把自然语言科研问题转成"可检查理解、每步留痕、可追溯、不越级、可复现、能保守停止"的科学结论。

## 1. 两份需求文档的取舍

仓库里两份权威文档在落地深度上冲突：

| 维度 | 详细需求规格 v0.1 | 超细颗粒度架构落地计划 v1.0 |
|---|---|---|
| 形态 | 一条真实纵向切片即可（§12） | 28 工作包、完整生产化 |
| 持久化 | JSON/JSONL/SQLite、事件日志 | PostgreSQL 事件库 + outbox |
| 存储/执行 | 本地即可 | MinIO + Nextflow + Docker Compose + 队列 |
| 测试 | 离线、确定性、可重复 | 同上 + 安全/SBOM/clean-room |

**取舍（已与需求方确认）**：本次按 **轻量离线核心 + 预留接口** 落地——满足需求规格 v0.1 的"最小验收闭环"，把 v1.0 的 Postgres/MinIO/Nextflow/队列作为**未来目标架构**，以端口（`Protocol`）预留接口位、本次不实现。理由：v1.0 的重型基础设施与"默认测试必须离线确定性"直接冲突，且一次性铺开会变成"一堆相互依赖的空壳"，违反实施 prompt 的纪律。

## 2. 分层与依赖方向（六边形）

```
        interfaces (CLI)            ← 入口，无业务逻辑
              │
        pipeline.py                 ← 唯一编排：按阶段守卫驱动状态机
        ┌─────┴───────────────────────────────┐
   application:                          domain core (auto_bioinfo/core)
   quality / evidence /                  schema · 状态机 · 事件溯源store ·
   report / reproduction /               稳定ID · 校验护栏 · artifact登记+证据闸门 ·
   execution(账本/对象)                   task packets · 工作流编译 · 交接契约 · 对照审计
        └─────┬───────────────────────────────┘
            ports (Protocol)              ← 唯一对外接缝
        ┌─────┴─────┬───────────┬──────────────┐
   PlannerPort  ResourceDisc  AnalysisMethod  ObjectStore/EventStore
        │           │            │              │(均 RESERVED 留位)
   offline_     fixture_      bulk_deg        本地文件系统(默认)
   planner      resources     (numpy)         Postgres/MinIO=未来
```

**依赖铁律**：箭头恒向内。`adapters → ports → core`，core 不 import 任何具体数据库/LLM/执行环境。替换端口实现（例如把本地 JSON 事件日志换成 Postgres）**不改领域状态机**。

## 3. 权威数据源与不可变性

- **项目状态 = 事件日志的投影**：`state/events.jsonl`（append-only）是权威，`state/project_state.json` 只是可重建的投影。状态只能经事件推进（`core/store.transition_state`），非法迁移被状态机拒绝。
- **稳定 ID + 内容校验和**：对象 ID 由 `make_stable_id(prefix, payload)`（sha256 前缀）生成，与文件路径无关；artifact 以 `checksum_sha256` 内容寻址。**杜绝"文件存在即完成"**——这是原系统 `work_order_dag.py:113/126` 的反模式，本次以内容校验和 + `result_status` 字段替代。
- **锁定即不可改**：`DatasetManifest` 锁定后任何变更须产生新版本（schema 已建模 `manifest_version`/`supersedes`）。

## 4. 核心闭环（22 阶段状态机）

主序列 15 个工作阶段 + `HUMAN_REVIEW_REQUIRED` 暂停 + 6 个合法非成功终态。每个工作阶段都能"保守停止"到 `INSUFFICIENT_DATA / METHOD_NOT_APPLICABLE / INCONCLUSIVE / CONFLICTING_EVIDENCE / FAILED / CANCELLED`，而不是抛异常或硬凑。

不可绕过的科学链（ADR-0005）：

```
真实执行(TaskRun) → 带校验和的 Artifact → 四层QC(QCReport) → 证据准入闸门
→ EvidenceItem → Claim(天花板封顶) → QuestionAlignmentReport(跑题/越级/遗漏阴性 检查) → 报告/复现包
```

任何一环缺失都不得进入下一环：未过 QC 的 artifact 进不了证据池（`core/artifacts.validate_artifact_for_evidence`）；Claim 等级被 `validate_claim_ceiling` 和对照审计两处封顶；对照审计非 `approve` 则不出干净报告、转人工复核。

## 5. Agent 与确定性服务边界

- **Agent（本次=离线确定性 planner）**只做"理解/规划/综合"的语义环节：问题规范化、子问题拆解、证据计划、范围解析。它的输出仍要过 schema + 天花板校验，**绝不直接写权威状态或 Claim**。生产可换成网络 LLM 适配器（PlannerPort），契约不变。
- **确定性服务**做事实与执行：方法执行、校验和、四层 QC、artifact 登记、证据准入、状态机/事件日志、复现比对。这些永不交给语言模型。

## 6. 真实执行（垂直切片）

`bulk_deg`（`methods/bulk_deg.py`）是注册方法：读 fixture 计数矩阵 + 分组 → CPM/log2 → 逐基因 Welch t 检验（numpy-only，自带有出处的正则不完全 Beta 函数算 p 值，对齐 scipy 到 ~1e-10）→ BH FDR → 标准 DEG 表。完全确定性、只依赖 numpy，第三方可从复现包逐字节复跑。其 MethodContract 把 `claim_capability` 钉死在 `association`——RNA 差异表达永远不能升级为蛋白/分泌/因果。

## 7. 预留的生产端口（本次不实现）

| 端口 | 默认实现 | RESERVED 生产适配器 | 对应 ADR |
|---|---|---|---|
| EventStorePort | JSONL on disk | PostgreSQL 事件库 + outbox | ADR-0003 |
| ObjectStorePort | 本地文件系统 | S3 / MinIO | ADR-0004 |
| AnalysisMethodPort | numpy 进程内方法 | 容器化方法 / Nextflow | ADR-0004 |
| ResourceDiscoveryPort | 提交的离线 fixture | GEO / Europe PMC / 注释源（审计化 HTTP 工具代理） | ADR-0004 |
| PlannerPort | 离线确定性规则 | provider-agnostic 网络 LLM 网关 | ADR-0004 |

## 8. 与 v1.0 完整计划的对应

本次落地覆盖 v1.0 的 R0（骨架）+ R1（规划闭环）+ 部分 R2（数据锁定，用 fixture）+ R3/R4 的"一条真实方法端到端 + 四层 QC + 证据/Claim + 报告"+ R5 的复现包，全部以轻量离线形态。未覆盖：真实公共库发现、sc/snRNA donor-level 路线、Postgres/MinIO/Nextflow 生产化、安全硬化/可观测性/多用户——这些在 `MIGRATION_MAP.md` 与 `DELIVERY_REPORT.md` 标为后续阶段。
