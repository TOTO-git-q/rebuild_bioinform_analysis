# 现有系统审计：targetcompass_lite（Phase 0）

> 文档定位：自动生信系统核心闭环重建项目的 Phase 0 现状审计。审计对象为旧系统 `targetcompass_lite`（外部生信靶点发现项目 TargetCompass v5 本地版），解压于 `_extract/targetcompass_v5_local_bundle_20260623T113401Z/`。本文为后续《迁移地图 MIGRATION_MAP.md》提供事实依据。
>
> 审计方式：实测（创建隔离 venv 安装依赖、`pip install -e .`、逐文件 `py_compile`、`pytest` 真实运行）+ 逐文件阅读 + 作者文档交叉印证。所有发现尽量带文件名与行号。

---

## 一、系统规模（实测）

| 指标 | 数值 |
|---|---|
| 源码模块 | **136 个 `.py`** |
| 源码行数 | **约 38110 行** |
| 测试文件 | **77 个** |
| 可收集测试用例 | 304 个（修复打包瑕疵后） |
| 唯一硬依赖 | `python-docx>=1.1.0`（pyproject.toml） |
| Python 要求 | `>=3.11`（实测 3.12 可跑） |

源码组织为「根目录扁平大模块 + 三个子包」：根目录约 95 个模块（含若干超大文件），加 `canonical/`（25 文件）、`methods/`（7 文件）、`db_adapters/`（7 文件）。

超大文件（迁移时重点关注的体量信号）：

| 文件 | 行数级 | 性质 |
|---|---|---|
| `webapp.py` | **4282 行** | 单体 HTTP 服务，God class（详见第五节） |
| `cli.py` | 1474 行 | 注册 113 个子命令，God 模块级单点注册 |
| `reporting.py` | 1005 行（48 def） | 报告生成引擎 |
| `evidence_db.py` | 965 行（30 def） | SQLite 证据库 |
| `evidence_planning.py` | 35 def | 证据规划引擎 |

---

## 二、打包瑕疵：7 个文件被"密钥脱敏脚本"损坏

交付包在打包时跑了一个脱敏脚本，把源码中敏感 token 一律替换成 `<REDACTED>`，从而制造出**语法错误**。这是打包瑕疵，**不是代码本身的 bug**。

实测：原始 bundle 直接 `pytest --co` 即报 **25 个 collection error**；逐文件 `py_compile` 显示**仅 7 个文件编译失败，其余 129 个全部正常**。

被污染的固定模式（共 7 文件 / 23 处）：

| 损坏文本 | 原本应为 |
|---|---|
| `api_key = <REDACTED>"OPENAI_API_KEY")` | `os.environ.get("OPENAI_API_KEY")` |
| `secret_key = <REDACTED>"...KEY"]` | `os.environ["...KEY"]` |
| `<REDACTED> RuntimeError(...)` | `raise RuntimeError(...)` |
| `<REDACTED> {"status": ...}` | `return {"status": ...}` |
| `api_key: <REDACTED>` | 类型注解 `str` |

受影响文件与行号：`llm_parser.py:87/160/201`、`llm_gateway.py:340/342`、`literature_validation.py:183/185`、`fulltext_llm_extraction.py:120/122`、`external_agent_adapter.py:83/85/175`、`local_backends.py`（多处）、`secrets.py:23`。

按上述固定模式还原后，**136 个文件全部编译通过**。结论：旧代码健康度本身良好，损坏纯属交付包脱敏副作用。

---

## 三、测试现状（实测）

在隔离 venv 中安装 `pytest`/`python-docx`、`pip install -e .`、修复上述 7 文件后运行：

- **293 passed / 10 failed / 1 error / 47 subtests passed，约 70 秒。**
- 10 个失败**全部为环境/打包性因素，无一为逻辑 bug**：
  - `test_canonical_artifacts::test_small_file_checksum`：checksum 不符——脱敏脚本**改动了测试 fixture 文件内容**（实测出空内容 sha256 `5891b5...`），校验逻辑本身正确。
  - `test_analysis_extensions`：断言里硬编码 Windows 路径分隔符 `configs\\causal_review_rubric.json`，Linux 上必失败（测试自身平台假设）。
  - `test_external_agent_import`（5 个）：bundle 未附带 `external_agents/bioinfo-agent-system/` 目录。
  - `test_local_backends`/`test_geo_raw`/`test_codex_engineering`：缺环境变量 `TARGETCOMPASS_S3_SECRET_KEY`、缺 `h5py`、需 git worktree / 网络。
- `test_scrna_10x.py` 因缺 `h5py` 无法收集（未强装）。

作者文档旁证：作者自述 `unittest discover tests` 约 **240 秒超时**，跨 9 个 stage 反复出现、超时前无 traceback、**始终未解决**，只有 8 个 canonical 测试文件单独跑过（57–59 用例）。本次用 pytest 70 秒跑完，说明超时主要源于测试编排/时长而非死锁。**全量测试套件从未被作者证明整体通过**——这是迁移时不能凭"测试存在"判定能力的关键警示。

---

## 四、canonical/ 子包评估（核心闭环的实际载体）

canonical/ 共 25 文件、约 4629 行，是旧系统一次真实落地的"规范化控制平面"重构，是**离目标核心闭环最近的部分**。

特征：全部 `@dataclass` + JSON 文件持久化（无 pydantic、无数据库），风格高度一致——事件溯源、内容哈希稳定 ID（`ids.py`）、`.tmp`+`replace` 原子写。

### 4.1 schemas.py（309 行）—— 核心数据模型基本齐备

每个类带 `schema_version`（默认 `"v5.canonical/0.1"`）+ `created_at` + `provenance` + `status`：

`ResearchSpec`(29)、`SubQuestion`(47)、`ScopeBundle`(64)、`EvidencePlan`(77)、`ResourceCandidate`(89)、`DatasetProfile`(103)、`DatasetSelectionDecision`(116)、`MethodContractRef`(128)、`CompatibilityDecision`(139)、`WorkflowPlan`(152)、`AnalysisTaskPacket/EngineeringTaskPacket/ReviewTaskPacket`(163/177/190)、`TaskRun`(202)、`ArtifactManifest`(214，含 `checksum_sha256/exists/is_placeholder/qc_status`)、`QCReport`(229)、`EvidenceItemRef`(240)、`Claim`(251)、`QuestionAlignmentReport`(266)、`FinalReportManifest`(277)、`ProjectEvent`(288)、`ProjectState`(300)。

- `CLAIM_LEVELS`(10–18) 定义 7 级断言阶梯（descriptive→…→experimentally_validated_target），全系统据此做"断言天花板，只能收紧不能放宽"。
- **两个缺口**：`WorkflowPlan` 只有 `task_ids: list[str]`、**无依赖边、不是真正 DAG**；`EvidenceItemRef`/`MethodContractRef` 是轻量引用，不承载正文。

### 4.2 状态机与事件溯源（干净）

`state.py:10-27` 16 阶段有限状态机 + 受限转移表 `LINEAR_NEXT` + 终态。`store.py` 双写 `v5/project_state.json`（快照）与 `v5/events.jsonl`（append-only 事件流）。**硬不变量**：`store.py:67-70` 强制 `EVIDENCE_SYNTHESIZED` 之前必须有 `QC_COMPLETED` 事件，否则报错（"未过 QC 不得合成证据"）。承认债务：并发事件写入未加锁。

### 4.3 mock 隔离（旧系统最严密处，多层冗余）

- `mock_runner.py` 全程**只到 `TASKS_READY` 就停，绝不产生 EvidenceItem/Claim**；资源全标 `verified=False / source_status="mock_placeholder"`。
- `validation.py:18 validate_no_unknown_verified_dataset` 是硬闸门：mock/placeholder 或 `AUTO_`/`MOCK_` 开头的 accession 不得标 verified。
- `external_agent_import.py` 硬标 `imported_as_evidence=False / reference_only=True`，扫描并拒绝 `AUTO_*`+verified 的导入。

### 4.4 对齐审计（真实计算，无硬编码结论）

`alignment_auditor.py`（285 行）逐 claim 校验必填字段、断言天花板（`_claim_exceeds_ceiling`）、scope 漂移、证据链可达性、阴性/失败证据省略检测，`_final_decision` 规则化输出 approve/needs_review/reject。**无任何硬编码科学结论。**

### 4.5 四层 QC 与 agent 契约

四层 QC 存在但分散：Schema 层（validation.py / task_packets.py）、执行层 QCReport（local_execution.py:290 / nextflow_execution.py:110）、证据准入层（artifacts.py:127 `validate_artifact_for_evidence`）、对齐审计层。agent 契约：`agent_specs.py` 定义 7 个强类型 agent（question_normalizer→…→evidence_synthesizer_reporter），各带 `forbidden_actions / max_claim_level / handoff_contract`；`agent_protocol.py` 强校验交接（断言天花板不得放松、dataset locking 校验）。交接是 JSON-only、只传 refs。

### 4.6 关键结论：与 v4 真实分析断开 = Phase 2 缺口

`resource_discovery.py:18-21` 是 canonical 内唯一真连网络处（NCBI eutils / EuropePMC / BioStudies / cellxgene）。但**控制平面与 v4 真实分析层之间的适配器一行未写**：`local_execution.py` 虽调用 v4 `planning.build_plan`，作者却明确 Phase 2/3/4 全未实现。**canonical 控制平面只跑 mock，与 v4 真实科学计算处于断开状态**——这正是重建时要补的核心缺口。

---

## 五、核心闭环逐环节状态

| 环节 | 状态 | 证据 |
|---|---|---|
| 自然语言问题→ResearchSpec | 部分实现 | schema 有 `ResearchSpec`；解析靠规则版 `spec_builder`/`llm_parser`，LLM 默认走 fallback |
| →SubQuestion / ScopeBundle | 已实现(schema) | schemas.py:47/64，结构化非关键词匹配 |
| →EvidencePlan | 已实现(schema) | schemas.py:77；v4 侧 `evidence_planning.py` 有完整引擎 |
| 资源发现 ResourceCandidate | 部分实现 | resource_discovery 真连 NCBI/EuropePMC/cellxgene；真实数据库适配器整体未做 |
| 数据可行性 DatasetProfile | 部分实现 | v4 `geo_importer` 真能导 GSE312006/GSE43292+fixture，其余 GSE 仅参考卡片 |
| DatasetManifest / 选择决策 | 已实现(schema) | `DatasetProfile` / `DatasetSelectionDecision` |
| MethodContract | 部分实现 | canonical 仅 `MethodContractRef`；契约体在 `methods/contracts.py`+v4 |
| Workflow DAG | **缺失(真 DAG)** | `WorkflowPlan` 只有 task_ids 列表，无依赖边/拓扑 |
| 任务执行 | mock + 真实双轨但断开 | mock 停在 TASKS_READY；真实路径存在但 v5→v4 适配器未接通 |
| 四层 QC | 已实现(框架) | 分散在 validation / executor QCReport / artifacts 准入 / alignment_auditor |
| EvidenceItem | 已实现(schema)+v4 真实库 | canonical 仅 `EvidenceItemRef`；v4 `evidence_db.py` 是真 SQLite 证据库 |
| Claim + 断言天花板 | 已实现 | `Claim` + `CLAIM_LEVELS` 7 级，agent_protocol 强制不可放宽 |
| QuestionAlignmentReport | 已实现 | alignment_auditor 真实确定性计算 |
| 复现包 / 终报 | 部分实现 | `FinalReportManifest`+report_manifest.py 聚合；v4 `reporting.py` 出 md/HTML/DOCX |
| **整体闭环贯通** | **缺失** | **v5↔v4 适配器（Phase 2）未实现，控制平面与真实分析断开** |

---

## 六、点名的反模式（带文件:行号实证）

### 6.1 文件路径字符串判断任务完成 —— 主反模式

- `work_order_dag.py:126`：无显式 attempt 状态时 `if outputs and all(row.get("exists") ...) : return "artifacts_ready"`，即**"全部产物文件存在 = 完成"**。
- `work_order_dag.py:113`：`artifact_id` 派生自 `content_hash({"path": ..., "exists": ...})`——**artifact 身份基于路径+存在性而非内容 checksum**。作者早期审计亲口点名此处。
- 对照：canonical 主路径干净，任务完成靠 `result_status` 字段（local_execution.py:88 / nextflow_execution.py:74），`canonical/artifacts.py` 已用真 checksum 修复 artifact 身份。

### 6.2 mock/合成数据进入流程

主路径受 `canonical/validation.py:18` + `agent_protocol.py:103` 双闸门拦截，**不污染证据池**。但残留两处"造数据"点：

- `external_agent_adapter.py:338 _synthesize_sarcopenia_plan`：外部 mock agent 失败时**写死一份 8 任务肌少症（sarcopenia）研究计划**（T1–T8，行 340–397）并落盘任务包（行 405）。属硬编码 fallback 内容。
- `engineering_closure.py:74`：真实 attempt 缺失时**合成一条 attempt 记录** `manifest.append(synthetic)`，被下游状态机读取——伪造执行记录。

### 6.3 硬编码科学结论 fallback

**未发现写死的"某基因=某结论/分数"**（reporting/scoring/sasp 的结论字段均由数据行计算）。硬编码仅限**评判逻辑/策划清单**：`causal_evidence.py:17 FALLBACK_CAUSAL_RUBRIC`（因果分级阈值）、`sasp_score.py:9 DEFAULT_SASP_CORE`（13 基因 panel）、`meta_analysis.py:114`（随机效应近似 SE 回退）。可接受但应外置为配置。

### 6.4 重复状态机（至少 4–5 套并行）

| 来源 | 状态词汇 |
|---|---|
| `canonical/state.py` | 16 个全大写 STAGE + 转移矩阵 |
| `run_state.py` | 自由字符串 status（idle/running/failed…）|
| `orchestrator.py` | success/failed/running/blocked/skipped/artifacts_ready |
| `work_order_dag.py` | 同上 + compiled |
| `task_registry.py:140` | 11+ 值（engineering_merged/qc_failed/queue_*…）|

`success/failed/running/artifacts_ready` 在三处各自硬编码字符串、无共享枚举——改一处需手工同步多处。作者早期审计承认此问题，靠"目录隔离+不接管 v4"暂时回避，**未真正合并**（合并是 Phase 3 待办）。

### 6.5 重复 schema/validator（5 处分散）

`schema_validation.py`（通用 JSON Schema 引擎）/ `validators.py`（spec+card 手工 `_require`）/ `canonical/validation.py`（业务规则）/ `methods/contracts.py`（method Protocol）/ `db_adapters/contracts.py`（db Protocol）。**明确重叠**：`validators.py:_require` 与 `canonical/validation.py:validate_required_fields` 功能重复；通用 schema 引擎本可覆盖 spec/card 校验却另写一套。

### 6.6 God class

- `webapp.py`：4282 行、单个 `Handler(BaseHTTPRequestHandler)`、`do_POST` 是 **55 分支 if/elif 路由链**、模块级 101 个 def，UI 渲染 + 表单 + GEO 导入 + 评审 + QC + 密钥管理全混一处——**确凿 God class**。
- 次级膨胀：`cli.py`（113 命令单点注册）、`reporting.py`（1005 行/48 def）、`evidence_db.py`（965 行/30 def）。

---

## 七、作者自述：已完成 / 未完成 / 已知问题

**定位**：v4 是已有"科学执行层"（真跑 DEG/scRNA/富集），v5 是新加"规范控制平面层"，策略为"控制平面先行、数据平面复用"——**v5 本身当前完全不接真实数据/不调真实 LLM/不跑真实分析，全是 mock**。

**作者声称已完成**（v5 九个 stage）：canonical schemas+稳定 ID(S1)、ProjectState+EventLog(S2)、7 AgentSpec+JSON 交接(S3)、停在任务包的 mock runner(S4)、外部六 agent 仅参考导入(S5)、带 checksum/placeholder/QC 的 Artifact Registry(S6，直接修复"文件存在判完成"反模式)、Question Alignment Auditor(S7)、带审批+租约的 Codex Worker 协议(S8)、文档(S9)。

**作者明确承认未完成**（v4→v5 迁移 Phase 2/3/4 全待办）：v5↔v4 适配器一行未写；真实数据库适配器全没做（GEO/PubMed/HPA/Open Targets/DisGeNET/GWAS Catalog/Reactome/MSigDB）；真实数据集验证、`DATASETS_LOCKED` 前强制验证、真实 LLM role 执行、沙箱化 Codex 真实执行全待办。

**作者承认且未消除的反模式/技术债**：重复状态机（承认重叠未合并）、`work_order_dag` 文件存在判完成、`external_agent_adapter` 硬编码 sarcopenia/SASP fallback、`AUTO_*` 占位数据集、轻量 schema 校验不覆盖跨字段科学规则、全量测试 240 秒超时未解决、并发事件写入未加锁。

**demo 真跑 vs mock**：本地可跑"输入→分析→人工审核→导出"链路，但真能进 bulk DEG 的只有带矩阵的 `GSE312006`/`GSE43292`+fixture；其余 GSE 是参考卡片不进分析；无 API Key 时 LLM 默认走本地 fallback。注意 `unfinished_tasks.md`/`mvp_development_list.md` 是**全部勾完**的清单，以"可演示/文件存在"为勾选标准，需折扣理解——**不能凭全勾清单判定系统已完成**。

---

## 八、一句话总结

旧系统是"一套设计严谨、自带科学护栏（断言天花板不可放宽 / placeholder 不可验证 / 产物 checksum / 对齐审计 / 未过 QC 不得合成证据）、但当前只跑 mock、且与真实分析层尚未接通的控制平面骨架"。`canonical/` 可作为新六边形架构的领域核心直接复用；v4 科学模块通过适配器复用；真正待建的是作者明确搁置的 v5↔v4 适配器；待清理的反模式集中在 v4 侧的重复状态机、`work_order_dag` 文件存在判完成、`external_agent_adapter`/`engineering_closure` 合成数据、以及 `webapp.py` God class。
