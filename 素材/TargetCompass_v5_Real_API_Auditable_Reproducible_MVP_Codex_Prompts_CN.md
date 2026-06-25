# TargetCompass v5：真实 API、无业务预设、可人工审计、可追溯复现的完整 MVP 重构 Prompt

## 使用方式

**不要把整份文档一次性交给 Codex。**

请严格按照 `Prompt 0 → Prompt 11` 的顺序执行，每次只复制一个 Prompt。每个阶段都必须遵循：

1. 先读取当前仓库和上一个阶段总结，不依赖记忆猜测结构；
2. 先审计，再做最小改动；
3. 只建立一个权威生产路径，不新增第二套平行流程；
4. 运行阶段专属测试和全量回归测试；
5. 如实记录失败，不得伪造通过；
6. 每个阶段只生成一个阶段总结文档；
7. 当前阶段未达到验收条件时，不进入下一阶段。

本文件的目标不是让系统支持所有生物信息学问题，而是形成一个**范围明确、链路完整、无业务预设、可接真实 API、可人工审核、可复现的 MVP**。对于未注册的方法、无法验证的数据或证据不足的问题，系统必须结构化返回“不支持、需要补充信息或需要人工审核”，不得编造结果。

---

# 一、最终 MVP 的定义

完成后的系统必须支持以下主流程：

```text
用户输入自然语言研究需求
    ↓
Research Planner 生成结构化研究计划
    ↓ 人工审核 Gate 1
真实 API 检索资源与文献
    ↓
Dataset Verifier 解析元数据并形成候选数据集
    ↓ 人工审核并锁定数据 Gate 2
Method Planner 从已注册方法中选择兼容方法
    ↓ 人工审核分析设计 Gate 3
确定性 Executor 执行已批准任务
    ↓
方法级 QC + Artifact Registry
    ↓
EvidenceItem → Claim → Question Alignment Audit
    ↓
生成结构化报告草稿
    ↓ 人工最终签出 Gate 4
最终报告 + 完整复现清单
```

完整 MVP 的“完整”指：

- 对系统已注册并声明支持的分析类型，可以从用户问题走到最终报告；
- 每一步都有结构化输入、输出、状态、理由、方法、参数和证据引用；
- API 接通后使用真实 API 和真实元数据，不生成替代数据；
- API 不可用、数据不足、方法不兼容或 QC 失败时，流程停止并明确说明原因；
- 不允许自动复用其他项目或其他 run 的结果；
- 最终结果可以通过保存的输入、代码版本、方法参数、随机种子、环境信息和数据校验和复现。

---

# 二、必须修复的已知问题

本轮改造必须显式解决以下问题：

1. 当前本地运行入口先调用 mock pipeline，再调用真实资源检索，生产路径和验证路径混合。
2. 当前 v5 task compiler 会读取项目根目录旧版 `research_spec.json`、`dataset_cards/` 和 `analysis_plan.json`，可能执行与本轮用户问题无关的旧任务。
3. 当前执行链在没有 locked dataset 时仍可能进入 `TASKS_RUNNING`。
4. 当前资源候选只要 accession 和 title 存在就可能标记为 verified，不能代表数据适合分析。
5. 当前 report manifest 调用 alignment auditor 时传入空的 `EvidenceItem` 和 `Claim`，并未审核真实结果。
6. 当前状态机可能进入 `REPORT_READY`，但 report manifest 同时仍为 `review_required`。
7. 当前部分 post-analysis 逻辑会全局执行模块或复用项目中已有输出，缺少当前 run 的 lineage 限制。
8. 当前运行目录不够隔离，旧 artifact 可能进入新问题的报告。
9. 当前生产代码、默认配置、CLI、文档和测试中存在领域特异预设或默认研究主题。
10. 当前 wheel 配置只打包顶层 package，可能遗漏 `canonical/`、`methods/`、`db_adapters/` 等子包。
11. 当前交付文档声明了未实现或未打包的 doctor/test 命令。
12. 当前外部 Agent 资源不是完整交付的一部分，但测试和运行路径可能依赖它。
13. 当前工程执行路径存在 `shell=True`、路径模式校验过宽和 forbidden path 可绕过风险。
14. 当前最终审计早于后续 API、执行器和 Worker 代码，结论已经失效。

---

# 三、全局不可违反的规则

## 3.1 无业务预设

生产代码、默认配置和默认提示词中不得硬编码任何：

- 疾病；
- 组织；
- 物种；
- 细胞类型；
- 基因、蛋白或通路；
- 生物学评分体系；
- 数据集 accession；
- 默认研究主题；
- 默认候选靶点；
- 默认分析结论。

测试只允许使用中性的合成 fixture，例如 `condition_a`、`condition_b`、`tissue_x`、`dataset_001`。测试 fixture 必须放在 `tests/fixtures/`，不能被生产代码自动加载。

## 3.2 禁止生产占位

生产路径不得创建或消费：

- `AUTO_*`；
- `MOCK_*`；
- `mock_placeholder`；
- `placeholder dataset`；
- 假 accession；
- 假 API response；
- 假 EvidenceItem；
- 假 Claim；
- “文件存在即成功”的伪结果。

单元测试可使用 stub/fake server，但必须与生产 Provider 实现隔离。API 缺失或不可用时，生产流程必须进入 `BLOCKED`、`HUMAN_REVIEW_REQUIRED` 或 `FAILED`，不能回退为伪数据。

## 3.3 Markdown 不是系统事实源

- `*.md` 只允许作为人类可读文档或报告渲染结果；
- 状态、任务、审批、数据集锁、方法选择、执行记录、QC、证据和 Claim 必须使用 JSON、JSONL 或 SQLite；
- 任何 Markdown 文件不能被当作 verified dataset、任务完成凭据或 canonical object；
- 报告中的 Markdown/HTML 必须由结构化 canonical report 生成。

## 3.4 一次运行一个独立证据链

每次用户请求必须生成唯一 `run_id`，所有对象写入：

```text
projects/<project_id>/runs/<run_id>/
```

禁止默认读取其他 run 或项目根目录中的旧结果。确需复用时，必须生成显式 `ReuseDecisionRecord`，记录来源 run、对象 checksum、复用理由和人工批准。

## 3.5 人工审核优先

默认审批模式为 `manual`。以下四个 Gate 必须人工批准后才能继续：

1. 研究计划；
2. 数据集锁定；
3. 分析方法和任务计划；
4. 最终 Claim 和报告。

可以实现显式 `--approval-mode auto` 供 CI 或受控内部验证使用，但必须记录 actor、策略和每个自动批准理由；默认不得开启。

## 3.6 LLM 只负责受限的语义任务

LLM 可以用于：

- 结构化用户问题；
- 提出候选检索词；
- 解释方法选择；
- 从已审核 EvidenceItem 草拟 Claim；
- 生成报告文字。

LLM 不得用于：

- 伪造数据集元数据；
- 决定文件是否存在；
- 计算 checksum；
- 绕过 QC；
- 执行统计分析；
- 自动批准自身输出；
- 将关联结果写成因果结论；
- 修改原始分析结果；
- 生成未引用 EvidenceItem 的 Claim。

---

# 四、目标最简架构

## 4.1 只保留 4 个概念 Agent

### Agent A：Research Planner

职责：

- 读取用户原始需求；
- 生成 `ResearchSpec`、`SubQuestion[]`、`ScopeBundle`、`EvidencePlan`；
- 明确歧义、假设、排除条件和 claim ceiling；
- 判断请求是否在当前方法注册表支持范围内。

禁止：

- 选择或锁定具体数据集；
- 生成分析结果；
- 自动批准研究计划；
- 写入业务默认值。

### Agent B：Resource Curator

职责：

- 根据已批准研究计划调用真实资源 API；
- 保存检索式、API 请求、响应摘要和原始响应 checksum；
- 建立 `ResourceCandidate` 和 `DatasetProfile`；
- 对每个候选给出可用性、scope 匹配和缺失元数据说明；
- 生成人工可审核的 `DatasetSelectionProposal`。

禁止：

- 仅凭 accession/title 将数据标记 analysis-ready；
- 自动锁定数据集；
- 伪造样本分组、样本量或平台信息；
- 把文献中提到的数据集当作已下载可分析数据。

### Agent C：Workflow Planner

职责：

- 只从方法注册表中选择方法；
- 对 locked dataset 执行 compatibility check；
- 记录候选方法、拒绝的方法、选择理由、参数和 claim ceiling；
- 生成 `WorkflowPlan` 和 `AnalysisTaskPacket[]`。

禁止：

- 发明未注册方法；
- 使用未锁定数据；
- 把工程任务混入分析任务；
- 自动执行任务；
- 添加与用户问题无关的全局 post-analysis。

### Agent D：Evidence Auditor & Reporter

职责：

- 读取通过 QC 的 TaskRun 和 Artifact；
- 构建 `EvidenceItem[]`；
- 生成严格引用 EvidenceItem 的 `Claim[]`；
- 审核每个 Claim 是否回答 SubQuestion、是否 scope 漂移、是否超过 claim ceiling；
- 保留失败、阴性结果和限制；
- 生成结构化报告草稿。

禁止：

- 修改原始结果；
- 忽略 failed QC；
- 在无 EvidenceItem 时生成 Claim；
- 自动签出最终报告；
- 省略不支持结论的证据。

## 4.2 确定性服务，不作为 Agent

以下能力必须由确定性代码实现：

- `PipelineOrchestrator`：唯一状态机和唯一生产入口；
- `ProviderRegistry`：LLM、数据资源、文献资源 API；
- `DatasetLockGate`：数据验证和人工锁定；
- `MethodRegistry`：方法 contract、输入要求、输出和 QC；
- `ExecutionWorker`：只执行已批准 task packet；
- `ArtifactProvenanceStore`：checksum、lineage、事件和审批；
- `ScientificQCEngine`：方法级 QC；
- `HumanApprovalGate`：审批、拒绝、签名和审计。

Codex 工程 Worker、MCP、长期 memory、PostgreSQL/MinIO、容器编排和多用户系统不属于本 MVP 主链。已有代码可以保留为可选开发工具，但默认 CLI、默认 import 和生产运行不得依赖它们。

## 4.3 推荐生产模块

不要为每个阶段继续创建大量平行模块。最终生产路径应收敛到以下职责：

```text
targetcompass_lite/canonical/
  models.py          # canonical schema、enum、ID、validation
  store.py           # run 目录、state、events、approval、artifact/provenance
  providers/         # 真实 LLM、数据资源、文献 API Provider
  planner.py         # 4 个 Agent 的结构化调用和 contract
  datasets.py        # metadata 验证、下载、profile、lock gate
  methods.py         # method registry、compatibility、task packet
  executor.py        # 已批准任务的确定性执行
  evidence.py        # method QC、EvidenceItem、Claim、alignment
  report.py          # canonical report 与 HTML/Markdown 渲染
  pipeline.py        # 唯一 orchestrator 和状态转换
```

如果直接合并文件会导致大范围破坏，可以保留现有文件作为 compatibility shim，但必须满足：

- 只有 `pipeline.py` 是生产入口；
- 只有一套 state/event store；
- 只有一套 task packet compiler；
- 只有一套 artifact registry；
- 旧模块不得自行推进状态；
- 旧模块不得读取其他 run 的对象；
- compatibility shim 只做参数转换，不做隐式规划。

---

# 五、Canonical 运行目录与审计对象

每个 run 必须至少包含：

```text
projects/<project_id>/runs/<run_id>/
  run_manifest.json
  state.json
  events.jsonl
  config_snapshot.json
  environment_manifest.json
  objects/
  api_calls/
  approvals/
  datasets/
  tasks/
  executions/
  artifacts/
  qc/
  evidence/
  reports/
  reproduce.json
```

## 5.1 RunManifest 必填字段

- `run_id`
- `project_id`
- `raw_user_request`
- `created_at`
- `created_by`
- `approval_mode`
- `code_version`
- `git_commit`，无 git 时为空并记录原因
- `package_version`
- `config_hash`
- `method_registry_hash`
- `provider_config_hash`
- `parent_run_id`，默认空
- `reuse_decision_refs`
- `status`

## 5.2 DecisionRecord 必填字段

每一次拆解、选择、审批或拒绝都必须记录：

- `decision_id`
- `run_id`
- `decision_type`
- `actor_type`
- `actor_id`
- `input_object_refs`
- `candidate_options`
- `selected_option`
- `rejected_options`
- `rationale`
- `method_or_policy_ref`
- `assumptions`
- `limitations`
- `created_at`
- `payload_hash`

## 5.3 TaskPacket 必填字段

- `task_id`
- `run_id`
- `subquestion_ids`
- `dataset_lock_refs`
- `method_contract_id`
- `method_version`
- `method_selection_decision_ref`
- `input_artifact_refs`
- `parameters`
- `random_seed`
- `expected_outputs`
- `qc_requirements`
- `failure_conditions`
- `claim_ceiling`
- `dependencies`
- `approved`
- `approval_ref`

## 5.4 ExecutionManifest 必填字段

- `execution_id`
- `task_id`
- `run_id`
- `executor`
- `started_at`
- `finished_at`
- `command_or_function`
- `arguments`
- `working_directory`
- `environment_ref`
- `input_checksums`
- `output_paths`
- `stdout_ref`
- `stderr_ref`
- `exit_status`
- `random_seed`
- `software_versions`

---

# 六、状态机和人工 Gate

建议状态：

```text
INTAKE
PLAN_READY
PLAN_APPROVED
RESOURCES_DISCOVERED
DATASET_REVIEW_REQUIRED
DATASETS_LOCKED
WORKFLOW_READY
WORKFLOW_APPROVED
TASKS_RUNNING
QC_COMPLETED
EVIDENCE_AUDITED
REPORT_DRAFT_READY
REPORT_APPROVED
COMPLETED
HUMAN_REVIEW_REQUIRED
BLOCKED
FAILED
CANCELLED
```

强制规则：

- `PLAN_READY → PLAN_APPROVED` 必须有 Gate 1 approval；
- `RESOURCES_DISCOVERED → DATASETS_LOCKED` 必须有至少一个 analysis-ready dataset 和 Gate 2 approval；
- `DATASETS_LOCKED → WORKFLOW_APPROVED` 必须有 method compatibility、task packets 和 Gate 3 approval；
- 未批准 task 不得进入 `TASKS_RUNNING`；
- QC fail 的 task 不得生成 approved EvidenceItem；
- 无 EvidenceItem 时不得生成 Claim；
- alignment 非 `approve` 时不得进入 `REPORT_APPROVED`；
- `REPORT_APPROVED → COMPLETED` 必须有 Gate 4 approval；
- API 缺失、数据不支持或方法不兼容时进入 `BLOCKED` 或 `HUMAN_REVIEW_REQUIRED`，不得自动跳步。

---

# Prompt 0：仓库事实审计与重构基线

```text
你现在位于 TargetCompass v5 本地开发包仓库中。

本阶段只做审计，不改代码。不要依赖历史总结，不要假设文件和命令存在。

目标：建立真实事实基线，为“真实 API、无业务预设、单一生产链、可审计可复现 MVP”重构提供依据。

请执行：

1. 输出 cwd、Python 版本、操作系统、顶层目录和 package 版本。
2. 列出 targetcompass_lite/canonical/、targetcompass_lite/methods/、targetcompass_lite/db_adapters/、tests/ 的实际文件。
3. 阅读以下路径及其直接依赖：
   - targetcompass_lite/canonical/local_demo_runner.py
   - targetcompass_lite/canonical/local_execution.py
   - targetcompass_lite/canonical/mock_runner.py
   - targetcompass_lite/canonical/resource_discovery.py
   - targetcompass_lite/canonical/report_manifest.py
   - targetcompass_lite/canonical/alignment_auditor.py
   - targetcompass_lite/canonical/codex_worker_execution.py
   - targetcompass_lite/llm_gateway.py
   - targetcompass_lite/cli.py
   - pyproject.toml
4. 画出当前真实调用链：CLI → runner → planning → resource → task compiler → executor → QC → report。
5. 明确列出所有平行 orchestrator、平行 state、平行 artifact registry 和平行 report path。
6. 查找生产代码和默认配置中的领域特异常量、默认问题、默认数据集、默认方法和默认项目。不要只搜索测试。
7. 查找生产代码中的 AUTO、MOCK、placeholder、demo fallback 和缺失 API 时的替代路径。
8. 证明当前 task compiler 的输入来自哪里，是否读取 run-specific canonical object，还是读取项目根目录旧对象。
9. 证明当前 report 的 EvidenceItem 和 Claim 是否来自本次 TaskRun。
10. 检查状态机是否允许未锁数据运行、未通过 alignment 进入 REPORT_READY。
11. 检查所有 subprocess、shell=True、路径白名单和 forbidden path 实现。
12. 构建 wheel，列出 wheel 内所有 targetcompass_lite 子包，确认 canonical/methods/db_adapters 是否被打包。
13. 运行：
    python -m unittest discover tests -v
14. 记录每个失败的真实命令、异常、是否属于代码错误/打包错误/跨平台错误/环境缺失。

只生成：
  docs/v5_real_api_mvp_stage0_audit.md

报告必须包含：

# v5 Real API MVP Stage 0 Audit
## Repository identity
## Current production entrypoints
## Current end-to-end call graph
## Duplicate architecture paths
## Cross-run contamination risks
## Hardcoded domain presets
## Placeholder and mock runtime paths
## Dataset verification defects
## State and report gate defects
## Evidence and claim lineage defects
## API provider status
## Security defects
## Packaging defects
## Test baseline
## Minimal refactor plan
## Files to change
## Files to keep as compatibility shims

禁止修改源码、测试、配置和项目数据。
```

### Prompt 0 验收

- 有真实调用图，不只是文件列表；
- 已证明旧项目对象是否会进入新 run；
- 已证明 Claim/Evidence 是否来自当前执行；
- 已完成 wheel 内容审计；
- 已运行全量测试；
- 没有代码改动。

---

# Prompt 1：建立唯一生产入口、run 隔离和最简架构

```text
读取 docs/v5_real_api_mvp_stage0_audit.md。

目标：建立唯一的 v5 生产 orchestrator、唯一状态机和严格 run 隔离。先修复跨问题、跨 run、跨项目复用旧对象的根本缺陷。

实现要求：

1. 新增或重构唯一入口：
   targetcompass_lite/canonical/pipeline.py

2. 提供：
   - create_run(project_dir, raw_user_request, actor, approval_mode="manual")
   - load_run(project_dir, run_id)
   - run_until_gate(project_dir, run_id)
   - resume_run(project_dir, run_id)
   - fail_run(project_dir, run_id, reason)

3. 每次请求生成唯一 run_id，并创建：
   projects/<project_id>/runs/<run_id>/

4. run 内必须保存：
   - run_manifest.json
   - state.json
   - events.jsonl
   - config_snapshot.json
   - environment_manifest.json
   - objects/
   - approvals/
   - tasks/
   - executions/
   - artifacts/
   - qc/
   - evidence/
   - reports/

5. 生产 pipeline 禁止默认读取：
   - 项目根目录 research_spec.json
   - 项目根目录 dataset_cards/
   - 项目根目录 analysis_plan.json
   - 其他 run 的 results/
   - 旧 demo 报告

6. 需要复用旧对象时，必须：
   - 显式指定 source_run_id；
   - 生成 ReuseDecisionRecord；
   - 验证 checksum；
   - 人工批准；
   - 默认关闭。

7. compile_registered_analysis_task_packets 必须改为只接收显式参数：
   - run_id
   - approved ResearchSpec ref
   - approved EvidencePlan ref
   - locked DatasetProfile refs
   - method registry snapshot ref
   不得在函数内部重新读取项目根目录并重新规划。

8. 禁止旧模块直接 transition_state。旧模块只能返回结构化结果，由 pipeline 统一转移状态。

9. 将现有 mock runner、local demo runner、report manifest 入口从默认生产路径移除。它们可暂时保留为 compatibility shim，但不能被主 CLI 自动调用。

10. 建立一次运行一个 lineage 的强制校验：所有 TaskPacket、TaskRun、Artifact、QCReport、EvidenceItem、Claim 必须具有相同 run_id。

11. 新增测试：
    - 同一项目连续创建两个不同问题的 run，第二个 run 不得引用第一个 run 的对象和 artifact；
    - 一个新 run 即使项目根目录存在旧 research_spec、dataset_cards 和 report，也不得读取；
    - run_id 不同的对象不能进入同一 report；
    - 未显式 ReuseDecisionRecord 时禁止跨 run 复用；
    - events.jsonl append-only；
    - 只有 pipeline 可以推进状态。

建议新增测试文件：
  tests/test_v5_run_isolation.py
  tests/test_v5_single_pipeline.py

运行：
  python -m unittest tests.test_v5_run_isolation tests.test_v5_single_pipeline -v
  python -m unittest discover tests -v

只生成：
  docs/v5_real_api_mvp_stage1_pipeline_summary.md

不得在本阶段接真实 API，不得生成报告，不得删除旧用户数据。
```

### Prompt 1 验收

- 有唯一生产入口；
- 新 run 不会读取旧项目根对象；
- task compiler 不再自行调用旧 planning；
- 所有运行对象带 run_id；
- 旧 runner 不再是默认路径；
- 隔离测试真实通过。

---

# Prompt 2：清除业务预设、生产占位和交付 Bug

```text
读取前两个阶段总结。

目标：生产代码无领域特异预设、无运行时 mock/placeholder 回退；修复打包、CLI、跨平台测试和交付不一致。

实现要求：

1. 审计 production code、默认 config、CLI 默认参数和内置 prompt。
2. 删除所有疾病、组织、物种、细胞类型、基因、通路、评分体系、数据集 accession 和默认研究主题的硬编码 fallback。
3. 默认 ResearchSpec 必须为空并由用户输入生成；字段缺失时输出 open_questions，不得填业务默认值。
4. 生产 pipeline 中不得调用 run_mock_canonical_pipeline。
5. mock_runner 仅保留在 tests 或明确的 dev-only 命令中；生产命令不得 import 它。
6. 生产代码不得生成 AUTO_*、MOCK_*、mock_placeholder 或假 accession。
7. API 缺失时返回结构化 BLOCKED：
   - missing_provider
   - missing_api_key
   - provider_unreachable
   - unsupported_request
   不得生成替代候选数据、假 EvidenceItem 或假报告。
8. Markdown 不能作为 canonical object。检查所有以 .md 作为状态或任务输入的路径，并替换为 JSON object ref。
9. 将遗留示例和大体积演示项目从默认 runtime、默认 CLI 和 wheel 中排除。不要删除用户文件；可移动到 legacy_examples/ 或仅在源码仓库保留，但不得自动读取。
10. 修复 pyproject.toml，使用正确的 package discovery，确保所有需要的子包进入 wheel。
11. 实现真实存在的 doctor 命令，或删除所有交付文档中不存在的命令。最终必须统一为：
    tc-lite v5 doctor
12. doctor 至少检查：
    - package imports
    - provider config
    - writable project/run path
    - method registry
    - optional external tools
    - no secrets printed
13. 外部 Agent contract 不得是生产运行硬依赖。若 bundle 不包含它，应：
    - 不影响安装；
    - 不影响主 pipeline；
    - 对应测试明确 skip 或使用 repository-local fixture。
14. 修复 checksum 测试中的错误预期。
15. 修复写死路径分隔符的测试，所有 path 使用 pathlib 或 POSIX-normalized refs。
16. 新增 build/install smoke test：
    - build wheel
    - 在临时虚拟环境安装
    - import canonical modules
    - 运行 tc-lite v5 doctor
17. 测试 fixture 必须使用中性合成名称，且放在 tests/fixtures/。

新增测试建议：
  tests/test_v5_no_domain_presets.py
  tests/test_v5_no_runtime_placeholders.py
  tests/test_v5_packaging_install.py
  tests/test_v5_doctor.py

运行：
  python -m unittest tests.test_v5_no_domain_presets tests.test_v5_no_runtime_placeholders tests.test_v5_doctor -v
  python -m unittest tests.test_v5_packaging_install -v
  python -m unittest discover tests -v

只生成：
  docs/v5_real_api_mvp_stage2_cleanup_summary.md
```

### Prompt 2 验收

- 生产代码无业务默认值；
- API 缺失不产生假数据；
- wheel 安装后可 import 全部 v5 模块；
- doctor 命令和文档一致；
- 默认 bundle 不依赖遗留示例和外部 Agent 目录；
- 跨平台和 checksum 测试修复。

---

# Prompt 3：实现真实 API Provider 层

```text
读取前序总结。

目标：建立可真实接入的 Provider 层。生产实现必须发真实 HTTP 请求；测试使用可控 fake server。不得在生产路径返回硬编码响应。

新增或整理：

  targetcompass_lite/canonical/providers/base.py
  targetcompass_lite/canonical/providers/http.py
  targetcompass_lite/canonical/providers/llm.py
  targetcompass_lite/canonical/providers/ncbi.py
  targetcompass_lite/canonical/providers/europe_pmc.py
  targetcompass_lite/canonical/providers/registry.py

最小 Provider contract：

1. LLMProvider
   - generate_structured(role, system_prompt, input_objects, output_schema)
   - 返回 parsed_output、raw_response_ref、model、provider、usage、request_hash、response_hash

2. DatasetProvider
   - search(query, filters, limit)
   - fetch_metadata(accession)
   - resolve_downloads(accession)

3. LiteratureProvider
   - search(query, filters, limit)
   - fetch_record(record_id)

真实实现至少支持：

- 一个 OpenAI-compatible LLM HTTP Provider；
- NCBI E-utilities 的数据集/文献检索；
- Europe PMC 文献检索。

配置要求：

- 只从环境变量或明确 config file 读取；
- 不提交 API key；
- 提供 .env.example，但只有变量名和说明；
- 支持 base_url、model、timeout、max_retries；
- API key 和 Authorization header 不得写入日志；
- doctor 只报告 configured/not_configured，不显示 secret。

调用审计：

每次 API 调用写入 run 目录 api_calls/，包括：

- call_id
- run_id
- provider
- operation
- endpoint_name，不记录完整含密钥 URL
- request_params_redacted
- request_hash
- started_at
- finished_at
- HTTP status
- retry_count
- response_hash
- raw_response_path
- parser_version
- parse_status
- error_type

可靠性：

- timeout；
- 指数退避；
- 尊重 rate limit；
- content-addressed cache；
- 网络失败不生成占位；
- JSON parse/schema validation 失败进入 BLOCKED；
- raw response 保存后才解析；
- 同一 response 可离线重放解析。

LLM 输出要求：

- 必须返回 JSON object；
- 必须通过本地 schema validation；
- 不允许从 Markdown code fence 猜测成功；
- 最多进行有限次数 repair；
- repair 也必须记录独立 API call；
- 失败时保留 raw response 并停止。

测试：

1. 使用本地 fake HTTP server 测试真实 HTTP client，而不是 monkeypatch 返回最终对象；
2. 测试 timeout、429、5xx、invalid JSON、schema invalid、重试和 secret redaction；
3. 测试 raw response cache 和离线 replay；
4. 提供可选 live smoke test，只有设置环境变量时运行，未设置时 skip；
5. live smoke 不得写入仓库根目录。

建议测试：
  tests/test_v5_provider_http.py
  tests/test_v5_provider_llm.py
  tests/test_v5_provider_ncbi.py
  tests/test_v5_provider_europe_pmc.py
  tests/test_v5_provider_live_smoke.py

运行：
  python -m unittest tests.test_v5_provider_http tests.test_v5_provider_llm tests.test_v5_provider_ncbi tests.test_v5_provider_europe_pmc -v
  python -m unittest discover tests -v

只生成：
  docs/v5_real_api_mvp_stage3_provider_summary.md
```

### Prompt 3 验收

- 真实 Provider 实现存在；
- 无 key 时 BLOCKED，不回退 mock；
- 所有调用可审计、可重放；
- secrets 不出现在日志；
- fake server 测试覆盖网络异常；
- live smoke 可选且隔离。

---

# Prompt 4：Research Planner 与研究计划人工 Gate

```text
读取前序总结。

目标：实现无业务预设的 Research Planner，将用户自然语言需求转为结构化、可审计的研究计划。

实现 Research Planner：

输入：
- run_id
- raw_user_request
- optional user constraints
- method registry capabilities summary

输出：
- ResearchSpec
- SubQuestion[]
- ScopeBundle
- EvidencePlan
- DecisionRecord
- open_questions
- supportability assessment

ResearchSpec 必须包含：

- original_question
- normalized_question
- objective
- target_population_or_system
- comparison
- outcomes
- species
- tissue_or_context
- conditions
- modalities_requested_or_inferred
- inclusion_criteria
- exclusion_criteria
- assumptions
- ambiguities
- claim_ceiling
- unsupported_aspects

规则：

1. 所有字段必须来自用户输入、明确引用或标为 unknown。
2. 不得自动填入任何业务默认值。
3. 缺少关键设计信息时，生成 open_questions，并将状态设为 PLAN_READY/HUMAN_REVIEW_REQUIRED。
4. Research Planner 只能看到 method registry 的 capability summary，不能发明方法。
5. 每个 SubQuestion 必须有：
   - subquestion_id
   - question
   - required_evidence_types
   - required_data_modalities
   - minimum_claim_level
   - max_claim_level
6. EvidencePlan 必须区分：
   - dataset evidence
   - statistical evidence
   - literature evidence
   - optional validation evidence
7. 生成 DecisionRecord，记录：
   - 如何拆解问题；
   - 每个子问题为何必要；
   - 哪些假设来自用户、哪些是 Agent 提议；
   - 哪些部分当前 MVP 不支持。
8. 使用 LLM Provider 的结构化输出；若用户直接提交完整 JSON ResearchSpec，可走无 LLM 的 deterministic import 路径。
9. 实现 Gate 1：
   - review_plan(run_id)
   - approve_plan(run_id, actor, comment)
   - reject_plan(run_id, actor, reason)
10. 未批准不得调用资源 API。

CLI：

- tc-lite v5 run --project <id> --question "..."
- tc-lite v5 review --project <id> --run <run_id> --gate plan
- tc-lite v5 approve --project <id> --run <run_id> --gate plan --actor <name> --comment "..."
- tc-lite v5 reject --project <id> --run <run_id> --gate plan --actor <name> --reason "..."

测试：

- 使用中性合成问题，不得依赖任何内置研究主题；
- 相同输入和相同 LLM fixture 产生相同结构化对象 hash；
- 缺失信息产生 open_questions；
- 未批准计划不能调用资源 Provider；
- LLM 输出越出 method capabilities 时标记 unsupported；
- 计划审批写入 immutable approval record；
- 拒绝后不能自动继续。

建议测试：
  tests/test_v5_research_planner.py
  tests/test_v5_plan_approval.py

运行：
  python -m unittest tests.test_v5_research_planner tests.test_v5_plan_approval -v
  python -m unittest discover tests -v

只生成：
  docs/v5_real_api_mvp_stage4_research_planner_summary.md
```

### Prompt 4 验收

- 无业务默认；
- 问题拆解有 DecisionRecord；
- 计划审核前不检索资源；
- 支持 deterministic JSON import；
- 结构化输出失败会停止。

---

# Prompt 5：Resource Curator、数据验证与人工锁定

```text
读取前序总结。

目标：将“搜索到资源”和“可以分析的数据集”严格分离，建立真实 API 检索、metadata 验证、analysis readiness 和人工 Dataset Lock。

实现状态，不再使用单一 verified 布尔值：

DISCOVERED
METADATA_VERIFIED
SCOPE_MATCHED
ANALYSIS_READY
LOCKED
REJECTED
BLOCKED

ResourceCandidate 必须记录：

- provider
- accession_or_record_id
- authoritative_url_or_endpoint_ref
- title
- description
- retrieved_at
- raw_response_ref
- raw_response_hash
- discovery_query_ref
- current_verification_status

DatasetProfile 必须记录：

- accession
- organism/species
- tissue/context
- condition labels
- modality
- platform
- sample_count
- group definitions
- donor_count when applicable
- case/control or comparison design
- raw/processed availability
- download references
- file formats
- metadata completeness
- scope match results
- analysis readiness checks
- limitations
- source field provenance

规则：

1. accession + title 只能达到 DISCOVERED，不能达到 ANALYSIS_READY。
2. METADATA_VERIFIED 必须来自 authoritative API response。
3. SCOPE_MATCHED 必须逐字段对比 approved ScopeBundle，并记录 match/mismatch/unknown。
4. ANALYSIS_READY 必须满足方法注册表所需最低字段：
   - 可获得的数据文件；
   - 清晰的样本或观测单位；
   - 可识别的分组/比较；
   - 所需 organism、modality 和输入格式；
   - 最低样本/供体条件；
   - 无关键未知元数据。
5. 缺失字段必须保持 unknown，不得由 LLM 猜测。
6. 文献记录不能作为已下载数据集。
7. 支持两种输入：
   - 真实公共资源 API；
   - 用户显式提供的本地数据和 metadata。
8. 本地数据也必须建立 DatasetProfile、checksum 和 analysis readiness。
9. 生成 DatasetSelectionProposal，包含所有候选、排除理由和建议排序。
10. 实现 Gate 2：
    - review_datasets
    - lock_datasets
    - reject_dataset
11. lock 必须记录 actor、选择理由、数据版本、metadata hash、download refs 和 checksum。
12. 没有 LOCKED dataset 时，pipeline 不得进入 workflow compilation。
13. 下载必须写入当前 run datasets/，或使用 content-addressed shared cache 加 run-local immutable reference；不得静默读取旧项目 data/。

新增测试：

- title/accession 存在但缺分组信息时不能 analysis-ready；
- scope mismatch 被明确标记；
- metadata unknown 不得由 LLM 补全；
- 文献记录不能锁成 dataset；
- 本地数据 checksum 改变后旧 lock 失效；
- 未人工批准不能 LOCKED；
- 无 locked dataset 不能生成 WorkflowPlan；
- API raw response 与 DatasetProfile 字段 provenance 可追溯；
- 两个 run 的下载和锁不交叉。

建议测试：
  tests/test_v5_resource_curator.py
  tests/test_v5_dataset_readiness.py
  tests/test_v5_dataset_lock.py

运行：
  python -m unittest tests.test_v5_resource_curator tests.test_v5_dataset_readiness tests.test_v5_dataset_lock -v
  python -m unittest discover tests -v

只生成：
  docs/v5_real_api_mvp_stage5_dataset_lock_summary.md
```

### Prompt 5 验收

- 数据状态分级；
- 不再靠 title/accession verified；
- 无锁定数据绝不执行；
- 每个字段能追溯到 API response 或本地 metadata；
- 人工 lock 可审计。

---

# Prompt 6：方法注册表、方法选择和可审核任务拆解

```text
读取前序总结。

目标：建立最小但严格的方法注册表，让每个分析任务都能说明为什么选这个方法、用了什么参数、替代方法为何未选。

MethodContract 必须包含：

- method_id
- method_version
- implementation_ref
- supported_modalities
- required_input_schema
- required_metadata_fields
- supported_designs
- minimum_sample_requirements
- parameter_schema
- default_parameters，必须是统计/工程默认，不得是业务主题默认
- output_schema
- qc_contract
- failure_conditions
- claim_ceiling
- deterministic_or_seeded
- software_dependencies

规则：

1. 先审计现有分析模块，只将真正可执行、输入输出明确、测试覆盖的方法注册。
2. 专项方法可作为插件保留，但不得被全局默认执行。
3. Workflow Planner 只能选择 registered method。
4. 每个 DatasetProfile × MethodContract 生成 CompatibilityDecision：
   - compatible
   - incompatible
   - needs_review
   并列出逐项检查。
5. MethodSelectionDecision 必须记录：
   - 候选方法；
   - 选择方法；
   - 拒绝方法；
   - 选择理由；
   - 数据设计适配；
   - 统计假设；
   - 参数；
   - claim ceiling；
   - 已知限制。
6. WorkflowPlan 必须由 SubQuestion → Task 映射组成。
7. AnalysisTaskPacket 必须包含本文件第 5.3 节全部字段。
8. 禁止自动添加与 ResearchSpec/EvidencePlan 无关的 post-analysis 模块。
9. 禁止 compiler 内部重新读取旧 analysis_plan 或重新构造研究主题。
10. 实现 Gate 3：人工审核 WorkflowPlan 和 task packets。
11. 审批页面/CLI 必须能显示：
    - 每个子问题；
    - 对应数据集；
    - 方法名与版本；
    - 参数；
    - 预期输出；
    - QC；
    - 失败条件；
    - 替代方法和拒绝理由。

测试：

- 未注册方法不能进入 TaskPacket；
- 不兼容数据不能生成 approved task；
- 每个 task 绑定 locked dataset 和 subquestion；
- 专项插件不会被全局自动执行；
- 参数不符合 schema 时失败；
- 未 Gate 3 批准不能执行；
- 方法选择 DecisionRecord 完整；
- task plan 不读取其他 run 或旧 analysis_plan。

建议测试：
  tests/test_v5_method_registry.py
  tests/test_v5_method_compatibility.py
  tests/test_v5_workflow_approval.py

运行：
  python -m unittest tests.test_v5_method_registry tests.test_v5_method_compatibility tests.test_v5_workflow_approval -v
  python -m unittest discover tests -v

只生成：
  docs/v5_real_api_mvp_stage6_workflow_summary.md
```

### Prompt 6 验收

- 方法选择不是自由文本；
- 所有 task 指向 registered method；
- 数据、方法、参数、QC 和子问题绑定；
- 可看到选择与拒绝理由；
- 未审批不执行。

---

# Prompt 7：确定性执行器与可复现实验记录

```text
读取前序总结。

目标：只执行已经批准的 AnalysisTaskPacket，并为每次执行生成足够复现的 ExecutionManifest、TaskRun、ArtifactManifest 和环境快照。

实现要求：

1. 生产执行入口：
   execute_approved_task(project_dir, run_id, task_id)
   execute_ready_tasks(project_dir, run_id, max_tasks=None)

2. 执行前强制检查：
   - task.run_id == current run_id
   - task approved
   - approval_ref 存在且未撤销
   - dataset lock 有效
   - input checksum 未变化
   - method contract 存在且版本一致
   - dependency task 已成功

3. 执行只允许调用 MethodContract 指定的 Python callable 或安全 argv。
4. 禁止 shell=True。
5. 不允许用户问题、LLM 文本或 API 文本直接拼接 shell command。
6. 工作目录必须在当前 run 下。
7. 输出必须写入当前 run executions/ 或 artifacts/。
8. 禁止扫描项目根目录寻找“最新结果”。
9. 所有随机方法必须显式设置并记录 seed。
10. 保存 environment_manifest：
    - Python 版本
    - OS
    - package version
    - installed dependency versions
    - method implementation hash
    - optional external executable versions
11. 每个任务保存：
    - stdout
    - stderr
    - exit status
    - started/finished time
    - input checksums
    - output checksums
    - exact parameters
    - function/argv
12. ArtifactManifest 不得只判断 exists，必须包含 checksum、size、producer execution、schema、QC pending 状态。
13. 实现幂等与 resume：
    - 相同 task + 相同 input checksums + 相同 method/version/params 可以识别已有成功执行；
    - 是否复用必须生成 ExecutionReuseDecision；
    - input 或代码变化必须重新运行。
14. 生成 reproduce.json，包含任务 DAG、输入、环境、方法、参数、seed、命令和 checksum。
15. 可选生成 reproduce.sh/reproduce.ps1，但 JSON 是权威记录。

安全路径：

- 所有 path 先 resolve；
- 必须位于允许 root；
- 检查父目录和 symlink escape；
- forbidden path 使用规范化路径和祖先匹配，不只用字符串等值或简单 fnmatch；
- 工程 Codex worker 不进入科学分析主链。

测试：

- 未批准 task 被拒绝；
- dataset checksum 改变后被拒绝；
- run_id 不匹配被拒绝；
- 旧 run artifact 不能作为隐式输入；
- shell metacharacter 不会被执行；
- symlink/path traversal 被拒绝；
- stdout/stderr/environment/seed 被记录；
- 相同输入可通过显式复用决定复用；
- 修改参数后必须重新运行；
- 输出文件变化会改变 checksum。

建议测试：
  tests/test_v5_executor_security.py
  tests/test_v5_execution_lineage.py
  tests/test_v5_reproducibility.py

运行：
  python -m unittest tests.test_v5_executor_security tests.test_v5_execution_lineage tests.test_v5_reproducibility -v
  python -m unittest discover tests -v

只生成：
  docs/v5_real_api_mvp_stage7_execution_summary.md
```

### Prompt 7 验收

- 只有批准任务能执行；
- 无 shell=True；
- 执行与当前 run 严格绑定；
- 每个输出有 checksum 和生产者；
- 生成可复现记录；
- 路径限制不可绕过。

---

# Prompt 8：方法级科学 QC、EvidenceItem 与 Claim 链

```text
读取前序总结。

目标：把“程序成功运行”与“科学结果可以支持证据”分开，建立方法级 QC → EvidenceItem → Claim 的真实链路。

实现 Scientific QC contract：

每个 MethodContract 必须绑定 QCEvaluator。QCReport 至少包含：

- qc_report_id
- run_id
- task_id
- execution_id
- method_id/version
- input_integrity_checks
- design_checks
- statistical_checks
- output_schema_checks
- warning_checks
- overall_status: pass / warn / fail
- blocking_issues
- limitations
- reviewer_required

通用 QC：

- 输入 checksum 与 lock 一致；
- 必要 metadata 完整；
- 输出 schema 正确；
- 非空且数值可解析；
- NaN/Inf/重复 ID/异常列检查；
- 样本和 metadata 对齐；
- 运行无未处理 error；
- 结果属于当前 run。

方法级 QC 必须在 MethodContract 中明确，不允许只检查文件存在。

EvidenceItem 必须包含：

- evidence_item_id
- run_id
- subquestion_ids
- dataset_lock_refs
- task_run_refs
- artifact_refs
- qc_report_refs
- method_id/version
- result_summary_structured
- effect_size_or_metric
- uncertainty
- direction
- evidence_level
- scope
- limitations
- negative_or_null_result
- review_status

规则：

1. QC fail 不得生成 approved EvidenceItem。
2. QC warn 只能生成 needs_review EvidenceItem。
3. 结果为空或不支持假设时，生成 negative/null EvidenceItem，不得丢弃。
4. EvidenceItem 必须引用当前 run artifact 和 QC。
5. LLM 只能读取 EvidenceItem 的结构化摘要，不能直接读取任意旧报告作为证据。

Claim 必须包含：

- claim_id
- run_id
- text
- claim_level
- supports_subquestion_ids
- evidence_item_refs
- scope
- confidence_or_support_grade
- limitations
- contradicting_evidence_refs
- status

规则：

- 无 EvidenceItem 不得生成 Claim；
- Claim level 不得超过 EvidencePlan、MethodContract 和 EvidenceItem 中最低 ceiling；
- Claim 必须保留反证、阴性证据和限制；
- Claim 生成后由 deterministic validator 校验引用和 ceiling；
- LLM 生成 Claim 时必须返回 JSON，并记录 prompt、模型和 response hash。

测试：

- 程序 exit 0 但科学 QC fail 时不能生成 approved EvidenceItem；
- failed QC artifact 不能支持 Claim；
- 无 evidence refs 的 Claim 被拒绝；
- claim ceiling 越级被拒绝；
- 阴性结果保留；
- 其他 run 的 evidence 不能引用；
- 修改 artifact 后 evidence 失效；
- 每个 Claim 可反向追溯到 dataset、method、task、execution、artifact 和 QC。

建议测试：
  tests/test_v5_scientific_qc.py
  tests/test_v5_evidence_builder.py
  tests/test_v5_claim_builder.py

运行：
  python -m unittest tests.test_v5_scientific_qc tests.test_v5_evidence_builder tests.test_v5_claim_builder -v
  python -m unittest discover tests -v

只生成：
  docs/v5_real_api_mvp_stage8_evidence_summary.md
```

### Prompt 8 验收

- QC 不再等于文件存在；
- EvidenceItem 来自真实 TaskRun；
- Claim 有真实 evidence refs；
- 阴性和失败结果不丢失；
- 每个 Claim 可完整反向追溯。

---

# Prompt 9：问题对齐审核、最终报告和状态门禁

```text
读取前序总结。

目标：让 Question Alignment Auditor 审核真实 EvidenceItem 和 Claim，并修复状态机与报告状态冲突。

实现要求：

1. Alignment Auditor 输入必须是当前 run 的：
   - ResearchSpec
   - SubQuestion[]
   - ScopeBundle
   - EvidencePlan
   - EvidenceItem[]
   - Claim[]
   - QCReport[]
   - DatasetLock[]
2. 禁止以 evidence_item_refs=[]、claims=[] 生成“已审核”报告。
3. 无 Claim 时可以生成 alignment report，但 final_decision 必须是 needs_review 或 reject，且不得进入 REPORT_APPROVED。
4. 审核内容：
   - 每个 SubQuestion 是否被 Claim 覆盖；
   - Claim 是否回答该 SubQuestion，而不只是引用了 ID；
   - species/tissue/context/condition/modality 是否 scope 一致；
   - Claim level 是否越级；
   - 是否引用 failed/warn/placeholder/其他 run evidence；
   - 是否遗漏阴性、失败和矛盾证据；
   - 所选方法是否能回答对应问题；
   - 是否存在不可解决的歧义。
5. 语义对齐可使用受限 LLM，但必须：
   - 同时有 deterministic 引用检查；
   - 返回结构化 JSON；
   - 记录 API call；
   - 不允许 LLM 自动 approve 自己生成的 Claim；
   - 最终 decision 由规则和人工 Gate 决定。
6. 状态规则：
   - alignment approve → REPORT_DRAFT_READY
   - alignment needs_review/reject → HUMAN_REVIEW_REQUIRED
   - 不得直接进入 REPORT_APPROVED 或 COMPLETED
7. FinalReport canonical JSON 必须包含：
   - 原始用户问题；
   - 规范化研究计划；
   - 子问题与覆盖情况；
   - API 检索策略和资源；
   - 锁定数据集及理由；
   - 方法选择、替代方法和参数；
   - task DAG；
   - TaskRun、Artifact、QC；
   - EvidenceItem；
   - Claim；
   - 阴性/失败/矛盾结果；
   - limitations；
   - alignment report；
   - reproducibility manifest；
   - human approvals。
8. HTML 和 Markdown 报告只从 canonical JSON 渲染。
9. 实现 Gate 4：
   - review_report
   - approve_report
   - reject_report
10. 只有 alignment=approve 且 Gate 4 approval 存在时：
    - REPORT_APPROVED
    - COMPLETED
11. 最终报告必须明确区分：
    - supported findings
    - unsupported findings
    - unresolved questions
    - recommended next steps
12. 不得将“无足够证据”转换成积极结论。

测试：

- 空 Evidence/Claim 不能完成；
- alignment needs_review 时 state 不能 REPORT_APPROVED；
- 其他 run 的 claim 被拒绝；
- scope drift 被发现；
- 引用了 ID 但语义不回答问题时 needs_review；
- 阴性证据遗漏被发现；
- Gate 4 未批准不能 COMPLETED；
- canonical JSON、HTML、Markdown 的 claim IDs 一致；
- 报告每个 Claim 可点击/查询到方法、参数、数据和 QC。

建议测试：
  tests/test_v5_alignment_real_chain.py
  tests/test_v5_report_gate.py
  tests/test_v5_report_traceability.py

运行：
  python -m unittest tests.test_v5_alignment_real_chain tests.test_v5_report_gate tests.test_v5_report_traceability -v
  python -m unittest discover tests -v

只生成：
  docs/v5_real_api_mvp_stage9_report_summary.md
```

### Prompt 9 验收

- Alignment 使用真实 Claim/Evidence；
- needs_review 不会被写成 report ready；
- 报告从 canonical JSON 渲染；
- 每个 Claim 可追溯；
- 最终完成必须人工签出。

---

# Prompt 10：完整 CLI MVP、人工审核视图和端到端流程

```text
读取前序总结。

目标：提供一套最小、统一、可操作的 CLI，使用户在 API 配置完成后可以输入需求，按 Gate 审核，一步一步得到最终结果。

只保留以下 v5 用户命令作为权威入口：

1. tc-lite v5 doctor
2. tc-lite v5 run --project <id> --question "..." [--approval-mode manual]
3. tc-lite v5 status --project <id> --run <run_id>
4. tc-lite v5 review --project <id> --run <run_id> --gate <plan|datasets|workflow|report>
5. tc-lite v5 approve --project <id> --run <run_id> --gate <...> --actor <name> --comment "..."
6. tc-lite v5 reject --project <id> --run <run_id> --gate <...> --actor <name> --reason "..."
7. tc-lite v5 resume --project <id> --run <run_id>
8. tc-lite v5 audit --project <id> --run <run_id> [--task <task_id>] [--claim <claim_id>]
9. tc-lite v5 reproduce --project <id> --run <run_id> --dry-run
10. tc-lite v5 export --project <id> --run <run_id>

行为：

- run 创建 run 并运行到第一个人工 Gate；
- approve 后可显式 resume；
- status 显示当前阶段、阻断原因、下一步操作；
- review 以人类可读表格显示对象，同时给出 JSON path；
- audit 可按 run/task/claim 反向展示完整 lineage；
- reproduce --dry-run 验证输入、方法、环境和 checksum，不执行；
- export 只打包当前 run 必要的 canonical objects、配置快照、方法 contract、环境、API audit、数据引用、任务、QC、证据、报告和复现说明；
- 不导出 API key；
- 不导出其他 run 或遗留 demo 数据。

人工审核显示至少包括：

Gate 1：
- 原始问题
- 规范化问题
- 子问题
- scope
- 假设
- open questions
- claim ceiling

Gate 2：
- 候选数据集
- metadata 来源
- scope 匹配
- 样本和分组
- analysis readiness
- 排除理由

Gate 3：
- 子问题
- 锁定数据集
- 方法及版本
- 参数
- 替代方法
- QC
- 失败条件

Gate 4：
- EvidenceItem
- Claim
- 反证/阴性证据
- limitations
- alignment decision
- 复现信息

不要求在本阶段建设复杂 Web UI。可以生成一个静态 audit HTML 作为可选视图，但 CLI + canonical files 必须完整可用。

端到端测试必须覆盖：

场景 A：
- Provider 可用；
- 研究计划批准；
- 找到 analysis-ready 数据；
- 锁定；
- 工作流批准；
- 执行和 QC 通过；
- 生成 Evidence/Claim；
- alignment approve；
- 人工批准报告；
- 状态 COMPLETED。

场景 B：
- 无 API key；
- 状态 BLOCKED；
- 不生成候选数据、Claim 或报告。

场景 C：
- 找到数据但缺关键 metadata；
- 无法锁定；
- 不生成 workflow。

场景 D：
- 方法不兼容；
- 生成明确 unsupported/needs_review；
- 不执行。

场景 E：
- 执行成功但 QC fail；
- 不生成 approved Claim；
- 不完成报告。

场景 F：
- 同一项目两个 run；
- 无任何对象交叉引用。

测试应使用 fake Provider + 小型中性 fixture，另提供可选真实 API smoke。

建议测试：
  tests/test_v5_cli_flow.py
  tests/test_v5_e2e_mvp.py
  tests/test_v5_audit_cli.py
  tests/test_v5_export.py

运行：
  python -m unittest tests.test_v5_cli_flow tests.test_v5_e2e_mvp tests.test_v5_audit_cli tests.test_v5_export -v
  python -m unittest discover tests -v

只生成：
  docs/v5_real_api_mvp_stage10_cli_summary.md
```

### Prompt 10 验收

- API 配置后有一个统一入口；
- 默认每个 Gate 停止等待人工；
- audit 命令能解释“怎么拆、为什么选、用了什么方法、结果从哪里来”；
- 端到端正向和失败场景全部覆盖；
- 无复杂 UI 依赖。

---

# Prompt 11：安装包、最终安全审计和 MVP 验收

```text
执行最终验收。除修复明确 bug 外，不新增功能。

目标：验证源码目录和安装后的 wheel 都能运行同一条完整 MVP 链，并确认无业务预设、无生产占位、无跨 run 污染、无越级 Claim、无未批准执行。

检查：

1. 架构：
   - 是否只有一个生产 pipeline；
   - 是否只有一个 state/event store；
   - 是否只有一个 task compiler；
   - 旧 runner 是否仅为 compatibility/dev path；
   - Codex worker/MCP/memory/container 是否不在默认链。

2. 无预设：
   - production code、默认 config、默认 prompt、CLI 中无领域特异研究主题；
   - test fixture 不被生产加载；
   - 默认不读取遗留 demo。

3. API：
   - 真实 Provider 可配置；
   - 缺 key 时 BLOCKED；
   - 无 mock fallback；
   - request/response 可审计；
   - secrets 已脱敏。

4. 数据：
   - DISCOVERED 不等于 ANALYSIS_READY；
   - 只有人工 LOCKED 数据能执行；
   - 数据字段有 source provenance；
   - input checksum 改变后 lock/task 失效。

5. 方法：
   - 只有 registered method；
   - 方法选择和拒绝理由完整；
   - TaskPacket 含参数、seed、QC、失败条件和 claim ceiling；
   - 无全局无关 post-analysis。

6. 执行：
   - 无 shell=True；
   - 路径和 symlink 安全；
   - 只写当前 run；
   - stdout/stderr/environment/checksum 完整；
   - 可 dry-run reproduce。

7. 证据：
   - QC fail 不生成 approved EvidenceItem；
   - 无 EvidenceItem 不生成 Claim；
   - Claim 不能超过 ceiling；
   - 阴性和失败证据未遗漏；
   - Claim 可追溯至数据、方法、任务、执行、artifact 和 QC。

8. 状态和人工 Gate：
   - 四个 Gate 均有 approval record；
   - needs_review 不会进入 COMPLETED；
   - alignment approve + Gate 4 才能完成。

9. 打包：
   - build wheel；
   - 临时环境安装；
   - tc-lite v5 doctor；
   - 所有 canonical 子包存在；
   - 不包含 API key、用户数据、遗留 demo 大文件和其他 run。

10. 测试：
    - 运行全部新增 test module；
    - 运行 python -m unittest discover tests -v；
    - 运行安装后 CLI smoke；
    - 可选 live API smoke，若无环境变量明确 skip；
    - 记录所有失败，不伪造通过。

11. 生成一个最小中性演示 run：
    - 使用 tests fixture 或用户输入的本地小数据；
    - 不带任何疾病、组织、物种或通路预设；
    - 完整经历 4 个 Gate；
    - 导出 audit 和 reproduce 包；
    - 确认导出只包含当前 run。

只生成：
  docs/v5_real_api_auditable_mvp_final_audit.md

报告结构：

# v5 Real API Auditable MVP Final Audit
## Executive decision
## Supported MVP scope
## Unsupported scope
## Architecture verification
## No-preset verification
## API verification
## Run-isolation verification
## Dataset-lock verification
## Method and task traceability
## Execution reproducibility
## Scientific QC verification
## Evidence and claim verification
## Human-gate verification
## Security verification
## Packaging verification
## Unit and integration test results
## Live API smoke results
## Known limitations
## Remaining work outside MVP
## Recommendation: merge / revise / hold

只有以下条件全部满足时才能 Recommendation: merge：

- 全量测试无本次新增失败；
- wheel 安装后主流程可运行；
- API 缺失无假数据；
- 无 locked dataset 不执行；
- 无 EvidenceItem 不生成 Claim；
- needs_review 不完成；
- 两个 run 无交叉引用；
- audit 和 reproduce 信息完整；
- 生产代码无业务预设。
```

---

# 七、最终验收清单

完成全部 Prompt 后，使用以下清单人工验收：

## 用户输入与计划

- [ ] 任意新用户问题不会继承旧项目主题；
- [ ] ResearchSpec 字段来自用户或标为 unknown；
- [ ] 每个问题拆解有 DecisionRecord；
- [ ] open questions 可见；
- [ ] Gate 1 前不检索资源。

## 真实 API

- [ ] LLM Provider 可真实调用；
- [ ] NCBI/Europe PMC Provider 可真实调用；
- [ ] API request/response 有 hash 和审计记录；
- [ ] secret 不进入日志；
- [ ] API 失败不生成替代结果。

## 数据选择

- [ ] 搜索到不等于 verified；
- [ ] metadata 字段有来源；
- [ ] scope、分组、样本量、格式和下载可用性被检查；
- [ ] 数据由人工锁定；
- [ ] 无锁定数据不执行。

## 方法和任务

- [ ] 方法来自注册表；
- [ ] 方法选择理由和替代方案可见；
- [ ] 每个 task 对应子问题和数据集；
- [ ] 参数、seed、QC、输出和失败条件完整；
- [ ] Gate 3 前不执行。

## 运行与复现

- [ ] 每个 run 独立目录；
- [ ] 无跨 run 隐式复用；
- [ ] 输入输出 checksum 完整；
- [ ] 软件环境和方法版本完整；
- [ ] reproduce --dry-run 能验证依赖和 checksum；
- [ ] 无 shell=True 和路径绕过。

## 科学证据链

- [ ] QC 是方法级而非文件存在；
- [ ] EvidenceItem 来自当前 TaskRun；
- [ ] Claim 只引用通过审核的 EvidenceItem；
- [ ] 阴性/失败/矛盾证据保留；
- [ ] claim ceiling 不越级；
- [ ] Alignment 确实检查是否回答原问题。

## 最终报告

- [ ] canonical JSON 是事实源；
- [ ] HTML/Markdown 只是渲染；
- [ ] 报告列出数据、方法、参数、QC、证据、限制和复现信息；
- [ ] needs_review 不被标为完成；
- [ ] Gate 4 签出后才 COMPLETED；
- [ ] 每个 Claim 可反向追溯到原始数据和执行记录。

---

# 八、MVP 外明确暂缓的内容

为保持架构最简，以下内容不作为本轮 merge 条件：

- 多用户和复杂权限系统；
- 云端队列与分布式 worker；
- PostgreSQL/MinIO 生产化；
- Kubernetes；
- 长期 Agent memory；
- 自动代码修改；
- 自动 wet-lab protocol；
- 无人工审核的全自动发布；
- 对所有组学模态和所有研究设计的通用支持。

这些内容只能在本 MVP 的 run isolation、Dataset Lock、Method Registry、Scientific QC、Evidence/Claim 和 Human Gate 全部稳定后单独立项。
