# auto-bioinfo — 自动生信系统核心闭环（轻量离线版）

把一句**自然语言科研问题**转换成**结构化研究规约 → 可执行分析任务 → 经四层质量控制的计算证据 → 受证据边界约束的科学结论 → 可复现包**的最小可运行闭环。

本仓库是对历史系统 `targetcompass_lite` 的**重建**：以其已经相当干净的 `canonical/` 控制平面为领域核心、清理反模式、并补上它一直缺失的"控制平面 ↔ 真实分析"适配器（原作者称之为 Phase 2，从未写过），从而让闭环**真正端到端跑通**——不是 metadata-only 的空角色，而是在一份提交进仓库的离线 fixture 上跑一次**真实的差异表达分析**。

- **轻量、离线、确定性**：运行期只依赖 `numpy`；默认测试不联网、不调付费 LLM、可重复。
- **预留生产端口**：PostgreSQL 事件库 / MinIO 对象存储 / Nextflow 工作流 / 网络 LLM 都以 `Protocol` 端口预留接口（见 `auto_bioinfo/ports/`），本次不实现，可平滑升级而不改领域核心。
- **科学护栏内建**：断言天花板（claim ceiling）、四层 QC 门、mock 数据硬隔离、原问题对照审计、内容校验和谱系、保守失败终态。

> ⚠️ 仓库内 `auto_bioinfo/fixtures/` 是**合成的离线 fixture**，已诚实标注，**不是真实生物数据**；它只用于参考运行与测试。生产运行必须通过真实、可审计的资源发现适配器获取数据集。

## 快速开始（端到端）

```bash
pip install -e .                      # 只装 numpy
# 跑一次完整闭环：自然语言问题 → 复现包
bioauto run --project ./runs/demo \
  --question "Which genes are differentially expressed in tissue_x between condition_a and condition_b?"

bioauto inspect  --project ./runs/demo          # 看阶段/Claim/对齐结论
bioauto validate --project ./runs/demo          # 事件回放=状态 + 复现包逐文件校验和比对
bioauto export   --project ./runs/demo          # 定位/重建复现包
```

`run` 走完的阶段（来自不可变事件日志）：

```
INTAKE → QUESTION_RESOLVED → SCOPE_RESOLVED → EVIDENCE_PLANNED → RESOURCES_DISCOVERED
→ DATASETS_LOCKED → WORKFLOW_COMPILED → TASKS_READY → TASKS_RUNNING → QC_COMPLETED
→ EVIDENCE_SYNTHESIZED → ALIGNMENT_AUDITED → REPORT_READY → REPRODUCTION_BUNDLE_READY → COMPLETED
```

产物落在 `./runs/demo/`：`state/`（事件日志 + 状态投影 + 各阶段对象 + Claim/Evidence/QC 账本 + 报告）与 `reproduction_bundle/`（输入/输出/参数/环境/QC/Claim + `checksums.sha256` + `run_order.md` + `comparison_spec.json`）。

## 运行测试

```bash
python -m unittest discover -t . -s tests -p "test_*.py" -v
```

43 个测试，全部离线确定性：状态机/非法迁移、schema 与护栏、统计与 bulk_deg 确定性、四层 QC 门、证据/Claim 天花板、原问题对照（含越级与跑题被拦截）、复现包逐字节比对与篡改检测、失败路径（样本不足→合法终态、mock 数据被拦、缺问题报错）、一条完整端到端。

## 架构（六边形 / 端口-适配器）

```
auto_bioinfo/
├─ core/          领域核心（复用并清理后的 canonical）：schema / 状态机 / 事件溯源 store /
│                 稳定ID / 校验护栏 / 带校验和的 artifact 登记 + 证据准入闸门 /
│                 task packets / 工作流编译 / agent 交接契约 / 原问题对照审计器
├─ ports/         端口 Protocol（含 RESERVED 的 Postgres/MinIO/Nextflow/网络LLM 预留位）
├─ adapters/      离线适配器：确定性 planner（替代 LLM）、fixture 资源
├─ methods/       注册方法：bulk_deg（numpy-only 真实 DEG）+ MethodContract + 兼容性判定
├─ quality/       四层 QC 引擎（执行/数据/统计/生物学）
├─ evidence/      EvidenceItem 提取 + Claim 合成（天花板封顶，保留阴性结果）
├─ execution/     运行/QC/证据/Claim 的 append-only JSONL 账本 + 对象持久化
├─ reproduction/  复现包构建 + 比对
├─ pipeline.py    唯一生产编排入口（run 即 resume，按阶段守卫、幂等可恢复）
├─ report.py      受约束报告（只渲染已合成的 Claim，绝不新增/升级结论）
├─ interfaces/    CLI（run/resume/inspect/export/validate）
└─ fixtures/      提交的离线合成数据集（诚实标注为 fixture）
```

依赖方向恒向内：`adapters → ports → core`；LLM/数据库/对象存储/执行引擎都在端口之外，替换实现不改领域状态机。

## 设计红线（与需求规格一致）

- **证据链单调不可绕**：QC 通过 → EvidenceItem → Claim → 原问题对照；未过 QC 的产物不得成为正式证据。
- **断言天花板**：RNA 差异表达只到 `association`，绝不自动升级为蛋白/分泌/因果；越级在 Claim 生成与对照审计两处被拦。
- **保守失败**：数据不足/方法不适用时进入 `INSUFFICIENT_DATA` / `METHOD_NOT_APPLICABLE` 等合法终态，而不是硬凑结果。
- **不伪造**：禁止生成不存在的 accession；verified 数据集不得来自 mock/placeholder 源；复现包离线干净重跑应 `BITWISE_IDENTICAL`。

## 文档

- `docs/rebuild/EXISTING_SYSTEM_AUDIT.md` — 现有系统审计
- `docs/rebuild/TARGET_ARCHITECTURE.md` — 目标架构
- `docs/rebuild/MIGRATION_MAP.md` — 迁移地图（复用/适配/重构/退役）
- `docs/adr/` — 关键架构决策记录
- `DELIVERY_REPORT.md` — 本次交付报告（已实现/未实现/下一步）
