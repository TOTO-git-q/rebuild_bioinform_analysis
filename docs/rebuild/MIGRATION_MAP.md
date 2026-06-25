# 迁移地图：targetcompass_lite → auto_bioinfo（Phase 0）

> 文档定位：把《现有系统审计 EXISTING_SYSTEM_AUDIT.md》的结论落成可执行的逐模块处置决策。处置类别共五种：
>
> - **直接复用**——搬进 `auto_bioinfo/`、仅做去耦清理。
> - **通过适配器复用**——领域价值真实，但须在新端口（`auto_bioinfo/ports/`）后包一层适配器接入；本次垂直切片可能未实际接入。
> - **重构迁移**——理念有用但实现需重写/收编。
> - **仅作测试或历史参考**——只读、不搬进生产路径。
> - **明确退役**——反模式来源或当前阶段不需要，不迁移。
>
> 新系统已搭好「轻量离线核心 + 预留 Postgres/MinIO/Nextflow/网络LLM 端口 + 以 canonical 为领域核心清理改造」，并跑通一条端到端垂直切片（自然语言问题→ResearchSpec→…→bulk_deg 真实执行→四层 QC→EvidenceItem→Claim(association 封顶)→QuestionAlignmentReport→报告→复现包），**43 个离线确定性测试全绿**。

---

## 一、canonical/* → auto_bioinfo/core/（直接复用，逐文件）

这是本次迁移的主干：旧 `canonical/` 已是干净的控制平面领域核心，整体搬入 `auto_bioinfo/core/` 并做去耦清理。

### 1.1 已搬入的文件（逐一对应）

| 旧文件 `canonical/` | 新文件 `core/` | 处置 |
|---|---|---|
| schemas.py | core/schemas.py | 直接复用 + 字段补全 |
| state.py | core/state.py | 直接复用 + 状态机扩展 |
| store.py | core/store.py | 直接复用 + 运行目录重命名 |
| events.py | core/events.py | 直接复用 |
| ids.py | core/ids.py | 直接复用 |
| validation.py | core/validation.py | 直接复用 |
| artifacts.py | core/artifacts.py | 直接复用（已是 checksum 身份） |
| task_packets.py | core/task_packets.py | 直接复用 |
| workflow_compiler.py | core/workflow_compiler.py | 直接复用 |
| handoff.py | core/handoff.py | 直接复用 |
| agent_specs.py | core/agent_specs.py | 直接复用 |
| agent_protocol.py | core/agent_protocol.py | 直接复用 |
| alignment_auditor.py | core/alignment_auditor.py | 直接复用 |

### 1.2 已做的清理（实测确认）

1. **状态机扩展**（`core/state.py`）：在旧 16 阶段基础上，`MAIN_SEQUENCE` 增补 `REPRODUCTION_BUNDLE_READY`(35) 与 `COMPLETED`(36)，补齐"复现包→完成"的闭环尾段；新增一组**合法非成功终态** `LEGAL_TERMINALS`(43-49)：`INSUFFICIENT_DATA / METHOD_NOT_APPLICABLE / INCONCLUSIVE / CONFLICTING_EVIDENCE`，并纳入 `TERMINAL_STAGES`(57-62) 与 `_SAFE_STOPS`(69)。意义：旧系统只能 success/FAILED/CANCELLED 终止，新系统允许系统**诚实地停在"数据不足/方法不适用/结论不确定/证据冲突"**而非伪造一个成功，直接配合断言天花板防过度断言。

2. **schemas 字段补全**（`core/schemas.py`）：按《核心闭环详细需求规格 v0.1》对 `ResearchSpec` / `EvidenceItem` / `DatasetManifest` 等补了所需字段，使 schema 覆盖到需求规格而非旧 TargetCompass 的子集。

3. **删除 report_manifest.py**：旧 `canonical/report_manifest.py` 耦合 TargetCompass 报告命名、且带悬空导入（依赖未一并迁移的 v4 报告对象）。已**不迁移**，报告职责由新的 `auto_bioinfo/report.py`（受约束报告）与 `reproduction/bundle.py` 承担。实测：`core/` 下确认无 `report_manifest.py`。

4. **运行目录段重命名 v5/ → state/**（`core/store.py:11-12`）：旧系统把运行态写到 `project_dir/v5/`（TargetCompass 版本命名）。新系统改写到 `project_dir/state/`，去掉对旧产品版本号的耦合（`project_state.json` / `events.jsonl` 路径同步迁移）。

### 1.3 未随 core 迁移的 canonical 文件（留作历史参考，见第四节）

旧 `canonical/` 还有 `mock_runner.py`、`local_demo_runner.py`、`local_execution.py`、`nextflow_execution.py`、`external_agent_import.py`、`codex_worker_protocol.py`、`codex_worker_execution.py`、`llm_role_execution.py`、`resource_discovery.py`、`memory_palace.py` 等——这些是执行/导入/外部集成层，不属"纯领域核心"，本次未搬入 `core/`，分别归入"历史参考"或"通过适配器复用"（见后）。

---

## 二、端口与适配器：新建（替代旧执行层）

新系统在 `auto_bioinfo/ports/__init__.py` 定义五个 Protocol 端口，全部标 `RESERVED`（生产适配位预留）：

| 端口 | 默认离线适配 | RESERVED 生产适配 |
|---|---|---|
| `PlannerPort` | `adapters/offline_planner.py`（确定性离线规划，无需 LLM/网络）| 网络 LLM 规划器 |
| `ResourceDiscoveryPort` | `adapters/fixture_resources.py`（提交的离线 fixture，诚实标注非真实数据）| GEO / Europe PMC / 注释源适配器 |
| `AnalysisMethodPort` | `methods/bulk_deg.py`（numpy-only 真实方法）| 容器化方法 + Nextflow 执行 |
| `ObjectStorePort` | 本地文件 | S3 / MinIO bucket |
| `EventStorePort` | JSONL on disk（`core/store`）| Postgres 事件库 |

意义：旧系统把 LLM/网络/数据库执行**直接硬编进业务模块**（如 `llm_gateway`、`local_backends` 的 PG+MinIO），新系统把它们收敛到端口后——离线默认实现保证确定性可测，生产实现是未来插拔点。

---

## 三、旧模块逐组处置

### 3.1 v4 科学计算模块 —— 通过适配器复用（本次未接入）

| 旧模块 | 处置 | 理由 |
|---|---|---|
| `deg.py`（limma DEG）| 通过适配器复用 | 科学计算真实有价值，但依赖 R/limma、非离线确定性 |
| `enrichment.py`（超几何+GSEA）| 通过适配器复用 | 同上 |
| `genetic.py`（coloc+MR）| 通过适配器复用 | 同上 |
| `scrna.py` / `scrna_10x.py` | 通过适配器复用 | 依赖 h5py 等重依赖 |
| `meta_analysis.py` / `causal_evidence.py` / `cell_type_evidence.py` | 通过适配器复用 | 真实分级/聚合逻辑可复用 |
| `evidence_db.py`（965 行 SQLite 证据库）| 通过适配器复用 | 真实证据库，但当前由 `core/store` + `evidence/synthesis.py` 离线承担 |
| `reporting.py`（1005 行）| 通过适配器复用 | 真实报告引擎，但耦合 TargetCompass 命名；新系统用受约束的 `report.py` |
| `db_adapters/`（UniProt/HPA/sqlite/tabular）| 通过适配器复用 | 已是"本地表格→证据行"转换器，结构干净，可作 `ResourceDiscoveryPort` 适配雏形 |
| `methods/`（方法插件层 + Protocol）| 通过适配器复用 | 插件化 Protocol 设计干净，可作 `AnalysisMethodPort` 注册表参考 |
| `nextflow_runner.py` / `nextflow_plane.py` 等 | 通过适配器复用（RESERVED）| 对应 `AnalysisMethodPort` 容器化适配位，本次未实现 |
| `llm_gateway.py` / `llm_parser.py` / `mcp_*` | 通过适配器复用（RESERVED）| 对应 `PlannerPort` 网络 LLM 适配位，本次离线 planner 替代 |
| `resource_discovery.py`（NCBI/EuropePMC/cellxgene）| 通过适配器复用（RESERVED）| 真实网络发现，对应 `ResourceDiscoveryPort` 生产适配 |

**关键决策：bulk_deg 改用 numpy 干净重写**（`methods/bulk_deg.py`），不复用旧 `deg.py`。理由：旧 `deg.py` 依赖 R/limma，不可离线确定性复现；新 `bulk_deg.py` 是 numpy-only 的 Welch t 检验 + BH FDR（`methods/_stats.py`），**确定性无随机、只依赖 numpy，第三方可独立复现**，且 MethodContract 把 `claim_capability` 硬封顶在 `association`（bulk_deg.py:11/61，注释明确"RNA 差异表达只是关联级证据"）。这保证了垂直切片在无 R 环境下离线全绿。

### 3.2 重复状态机 —— 明确退役

旧系统有 4–5 套并行状态机（审计 §6.4）。新系统以 `core/state.py` 单一 ProjectState 状态机收编，下列**全部退役**：

| 退役模块 | 退役理由 |
|---|---|
| `run_state.py` | 自由字符串 status，与 canonical 状态词汇双轨 |
| `orchestrator.py`（29KB）| 节点级状态硬编码字符串，重复编排 |
| `orchestration_graph.py` / `orchestration_policies.py` | 与 core 状态机重叠 |
| `work_order_dag.py` | **`:126` 文件存在判完成 + `:113` 路径派生 artifact 身份**，双反模式来源 |
| `task_registry.py` | 11+ 值状态视图，与 core 状态机重复 |
| `trace_orchestrator.py` / `recovery_center.py` | 围绕旧编排层 |

新系统编排统一走 `pipeline.py`（单一入口，run 即 resume、幂等），任务完成判定靠 `core` 的显式 status 字段 + checksum，**杜绝"文件存在=完成"**。

### 3.3 合成/伪造数据点 —— 明确退役

| 退役模块/函数 | 退役理由 |
|---|---|
| `external_agent_adapter.py:338 _synthesize_sarcopenia_plan` | 硬编码合成 8 任务肌少症研究计划落盘（行 340–405），造数据反模式 |
| `external_agent_adapter.py`（整模块，26KB）| 外部 agent 适配 + 上述合成 fallback |
| `engineering_closure.py:74` | 真实 attempt 缺失时 `manifest.append(synthetic)` 合成执行记录 |
| `external_task_runner.py` / `codex_engineering.py` / `codex_task_queue.py` | 旧 Codex 工程闭环，本阶段不需要 |

新系统证据一律源自 `methods/` 真实方法执行 + `evidence/synthesis.py`（ceiling 封顶），**不存在合成数据进入流程的路径**。fixture 数据集由 `adapters/fixture_resources.py` 提供并**诚实标注为非真实数据**。

### 3.4 God class —— 明确退役（不迁移其实现）

| 退役模块 | 退役理由 |
|---|---|
| `webapp.py`（4282 行，55 分支 do_POST，101 def）| God class，UI+表单+导入+评审+QC+密钥混一处 |
| `cli.py`（1474 行，113 命令）| God 模块级单点注册 |
| `services.py` / `mcp_*` / `container_plane.py` / `local_backends.py` | 服务/容器/PG+MinIO 后端，本阶段不需要 |

新系统接口面收敛到 `interfaces/cli.py`（仅 run/resume/inspect/export/validate 五命令），无 Web God class。Postgres/MinIO 作为端口预留（`ObjectStorePort` / `EventStorePort` 的 RESERVED 适配位），本阶段不实现。

### 3.5 重复 validator —— 收敛到 core/validation.py

`schema_validation.py` / `validators.py` / `methods/contracts.py` / `db_adapters/contracts.py` 中与校验重复的部分（审计 §6.5）退役，统一由 `core/validation.py` 承担业务规则校验。

### 3.6 硬编码评判逻辑 —— 重构迁移（外置为配置）

`causal_evidence.py:17 FALLBACK_CAUSAL_RUBRIC`、`sasp_score.py:9 DEFAULT_SASP_CORE`、`meta_analysis.py:114` 近似 SE 回退——属评判逻辑/策划清单而非伪造结论。本次未涉及（无 causal/SASP 切片），未来接入时应外置为可配置 rubric，而非内联常量。

---

## 四、仅作测试或历史参考

| 模块 | 处置 | 理由 |
|---|---|---|
| `canonical/mock_runner.py` | 历史参考 | mock 编排，停在 TASKS_READY；新系统直接跑真实 bulk_deg，不需要 mock runner |
| `canonical/local_demo_runner.py` | 历史参考 | demo 编排 |
| `canonical/external_agent_import.py` | 历史参考 | 外部六 agent 仅参考导入逻辑 |
| `canonical/codex_worker_protocol.py` / `codex_worker_execution.py` | 历史参考 | 受控 Codex 协议设计可借鉴，本阶段不接入 |
| `canonical/memory_palace.py` | 历史参考 | PilotDeck 记忆装置 |
| `projects/vascular_aging_demo/` | 历史参考 | 旧 demo 产出 |
| 旧 77 个测试 | 历史参考 | 新系统已写 43 个离线确定性测试覆盖核心闭环；旧测试可对照行为但不直接迁移 |

---

## 五、本次明确"未迁移 / 未实现"的范围

为避免误读"已搭好系统"的能力边界，明确以下属预留或待办，**本次垂直切片未实现**：

1. **真实 GEO / 文献 / 注释数据适配器**——`ResourceDiscoveryPort` 的 RESERVED 适配位。本次仅 `fixture_resources` 离线 fixture（诚实标注非真实数据）。
2. **Nextflow / 容器化方法执行**——`AnalysisMethodPort` 的 RESERVED 适配位。本次仅 `bulk_deg` numpy 离线方法。
3. **Postgres 事件库 / MinIO 对象存储**——`EventStorePort` / `ObjectStorePort` 的 RESERVED 适配位。本次为 JSONL + 本地文件。
4. **网络 LLM 规划**——`PlannerPort` 的 RESERVED 适配位。本次为 `offline_planner` 确定性规划。
5. **causal/MR、scRNA、富集、meta 等其它科学方法**——仅 bulk_deg 一条方法接入。
6. **多用户 / 服务化 / Web 界面 / MCP**——本阶段范围外。

新系统当前能力边界：**一条自然语言问题→离线确定性规划→fixture 数据集→bulk_deg 真实 numpy 执行→四层 QC→EvidenceItem→Claim（association 封顶）→QuestionAlignmentReport→受约束报告→复现包+比对**，全离线、确定性、43 测试全绿。这条切片证明了「领域核心 + 端口 + 离线适配」骨架可贯通核心闭环，真实数据/生产基础设施沿预留端口逐步接入即可，无需重写核心。
