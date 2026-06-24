# 交付报告（auto-bioinfo 核心闭环重建）

> 本次交付 = **审计 + 干净核心骨架 + 一条真正端到端跑通的垂直切片 + 离线测试 + CI + 复现包**。轻量离线核心，重型基础设施以端口预留。

## 1. 对旧系统的复用 / 重构 / 退役（详见 `docs/rebuild/MIGRATION_MAP.md`）

- **直接复用为 `auto_bioinfo/core/`**：旧 `canonical/` 子包（纯标准库、自包含、护栏齐备）——schema/状态机/事件溯源 store/稳定 ID/校验护栏/带校验和的 artifact 登记+证据准入闸门/task packets/工作流编译/交接契约/对照审计。已清理见 ADR-0002。
- **通过适配器复用（本次未接入）**：v4 真实科学模块（deg/enrichment/genetic/scrna/evidence_db/reporting）——留待 AnalysisMethodPort/ResourceDiscoveryPort 接入；bulk_deg 本次改用 numpy 干净重写以保离线确定性（ADR-0006）。
- **退役**：`webapp.py`(4282 行 God class)、`cli.py`(113 命令单点)、重复状态机（run_state/orchestrator/work_order_dag/task_registry）、`external_agent_adapter` 合成肌少症计划 + `engineering_closure` 合成 attempt（伪造数据反模式）、`work_order_dag.py:113/126` 文件存在判完成。
- **历史/测试参考**：`mock_runner`、`local_demo_runner`、`external_agent_import`。

## 2. 新架构与关键 ADR

六边形/端口-适配器，依赖恒向内。见 `docs/rebuild/TARGET_ARCHITECTURE.md` 与 `docs/adr/`：
0001 轻量离线优先 · 0002 复用 canonical · 0003 事件溯源+锁定不可变 · 0004 端口预留 Postgres/MinIO/Nextflow/LLM · 0005 不可绕过证据门禁链 · 0006 numpy 确定性方法 · 0007 断言天花板与保守失败。

## 3. 已实现的端到端路径

一句自然语言问题 → 完整 22 阶段状态机走到 `COMPLETED`：

```
INTAKE→QUESTION_RESOLVED→SCOPE_RESOLVED→EVIDENCE_PLANNED→RESOURCES_DISCOVERED→DATASETS_LOCKED
→WORKFLOW_COMPILED→TASKS_READY→TASKS_RUNNING→QC_COMPLETED→EVIDENCE_SYNTHESIZED→ALIGNMENT_AUDITED
→REPORT_READY→REPRODUCTION_BUNDLE_READY→COMPLETED
```

其中 `TASKS_RUNNING` 是**真实执行**（bulk_deg 在提交的 fixture 上真算 DEG），不是 metadata-only 角色。

## 4. 目录与核心领域对象

见 `README.md` §架构。核心对象（`auto_bioinfo/core/schemas.py`）：ResearchSpec / SubQuestion / ScopeBundle / EvidencePlan / ResourceCandidate / DatasetProfile / DatasetManifest / CompatibilityDecision / WorkflowPlan / Analysis·Review·EngineeringTaskPacket / TaskRun / ArtifactManifest / QCReport / EvidenceItem / Claim / QuestionAlignmentReport / FinalReportManifest / ProjectEvent / ProjectState。

## 5. 运行命令

```bash
pip install -e .
bioauto run --project ./runs/demo --question "Which genes are differentially expressed in tissue_x between condition_a and condition_b?"
bioauto inspect  --project ./runs/demo
bioauto validate --project ./runs/demo
bioauto export   --project ./runs/demo
```

## 6. 测试命令与实际结果

```bash
python -m unittest discover -t . -s tests -p "test_*.py" -v
```

**实测：43 个测试全部通过（OK），耗时约 0.35s，全程离线、不联网、无付费 LLM。** 覆盖：状态机/非法迁移/事件重建、schema 与护栏、统计正确性（对齐已知 t 临界值）与 bulk_deg 确定性、四层 QC 门（含统计层伪重复 FAIL）、证据/Claim 天花板（项目上限压过方法能力）、原问题对照（approve + 越级 reject + scope drift reject）、复现包逐字节比对 + 篡改检测、失败路径（样本不足→合法终态、mock 数据被拦、缺问题报错）、一条完整端到端 + Claim 可追溯到 QC 通过的带校验和 artifact、resume 幂等、CLI run/validate/inspect。

## 7. 示例产物位置（运行后）

- `runs/demo/state/events.jsonl`、`project_state.json` —— 事件日志 + 状态投影
- `runs/demo/state/objects/*.json` —— 各阶段结构化对象
- `runs/demo/state/{task_runs,qc_reports,evidence_items,claims}.jsonl` —— 账本
- `runs/demo/state/reports/report.md` + `report.json` —— 受约束报告
- `runs/demo/reproduction_bundle/` —— 复现包（inputs/outputs/parameters/environment/qc_rules/claims + `checksums.sha256` + `run_order.md` + `comparison_spec.json`）

## 8. 未实现部分与原因

- **真实公共库发现/核验**（GEO/Europe PMC/注释源）：需联网，与离线默认测试冲突 → 留 ResourceDiscoveryPort，本次用提交 fixture。
- **sc/snRNA donor-level 路线、跨数据集复现综合**：范围控制，本切片先做 bulk DEG 一条。
- **PostgreSQL/MinIO/Nextflow/队列/Docker Compose、安全硬化、可观测性、多用户**：v1.0 的生产化项，本次以端口预留，见 ADR-0001/0004。
- **真实 LLM 规划**：用离线确定性 planner 替代以保测试离线 → 留 PlannerPort。

## 9. 下一阶段最小工作清单

1. 实现 ResourceDiscoveryPort 的 GEO 适配器（带录制 fixture 的离线回放 + 真实 HTTP 两套），打通真实 `DATASETS_LOCKED` 前核验。
2. 实现 PlannerPort 的网络 LLM 适配器（provider-agnostic），输出仍过 schema+天花板校验。
3. 接入第二个 MethodContract：scrna_pseudobulk donor-level DEG（AnalysisMethodPort），并补差异丰度 + 跨数据集一致性。
4. EventStorePort 的 PostgreSQL 适配器 + outbox（替换 JSONL，领域不变）。
5. clean-room 容器复现 smoke（在干净容器重跑复现包并比对）。

## 10. 新增提交摘要

单次提交（分支 `rebuild/auto-bioinfo-core`）：新增 `auto_bioinfo/`（核心+端口+适配器+方法+QC+证据+复现+CLI+fixtures）、`tests/`（43 测试）、`docs/rebuild/`（审计/目标架构/迁移地图）、`docs/adr/`（7 份 ADR）、`pyproject.toml`、`ci/ci.yml（见 ci/README.md，启用即移入 .github/workflows/）`、`README.md`、本报告、`.gitignore`。未改动仓库内原有的需求文档与 zip 素材（作为只读需求来源保留）。

---

## 附：需求规格 §13「最小验收 20 条」自评

满足：1 自然语言提问 ✓、2 可验证 ResearchSpec ✓、3 拆 SubQuestion ✓、4 每子问题 EvidencePlan ✓、5 通过工具找并核验数据（fixture 适配器，真实联网留端口）◑、6 可行性/兼容性判定 ✓、7 锁定数据集+样本+校验和 ✓、8 按 MethodContract 选方法 ✓、9 编译可执行任务（线性 DAG）✓、10 隔离目录执行 + 完整 TaskRun ✓、11 产物登记为带校验和 Artifact ✓、12 四层 QC ✓、13 仅过门控结果进 EvidenceItem ✓、14 Claim 不越级 ✓、15 对照审计能发现越级/跑题 ✓、16 输出正/负/未回答项 ✓、17 复现包 ✓、18 第三方按复现包重跑可比较（`validate` BITWISE_IDENTICAL）✓、19 图表/结论可追溯到数据+参数+运行 ✓、20 数据不足以合法终态结束 ✓。

打折项：5（真实公共库联网发现未实现，用诚实标注的离线 fixture 代替，已留端口）。
