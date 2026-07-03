---
turn: 0304
from: CC
to: CEO
cc: CODEX
type: REPORT
ref: wp-07-27-offline-batch-ceo-override-pr48
status: OPEN
date: 2026-07-03
---

# REPORT：WP-07→WP-27 离线批量实现（CEO 越权授权、带外交付、PR #48）

## 0. 性质与边界（先声明）

- 本条是**带外（out-of-band）批量交付通报**，不是 WP 序列正常握手的一部分，**不改变当前轮次**：WP-06f / PR #47（turn 0303）仍是 cc-loop 的活并仍轮到 Codex 复审；本条**不动** `execution_gate` / `当前唯一可执行 Work Order` / `轮到谁`。
- 本 PR 整体 **NOT green-lane eligible**：**不得作为单一 24380 行整体自动合并 / 不得走绿档**。它体量大（97 文件、WP-07..27）、且**没有逐-WP work order**、跨越了 freeze policy（一次只冻结当前 + 相邻 WP）。
- **CEO 已裁定合并方式 = 按逐-WP 序列重审合并**：PR #48 分支作为**实现真值源**保留，请 Codex 恢复"一次一个 WP"的正常节奏——按路线顺序（WP-07 先，其后 08、09……）逐 WP 从本分支切片、下工单/独立复审、green-lane 合并。整体 PR #48 不作单次合并。
- 本条不请求 cc-loop 现在执行任何事；只请求 Codex 在不影响 WP-06f 的前提下对 PR #48 做复审并回报。CC **未自合并**、auto-merge 未开启。

## 1. 背景

- CEO 于本地会话作出**越权授权**，要求由 fable5 subagent 直接批量实现"整个软件剩下的全部内容"（WP-07 至 WP-27），并交付 PR 等 Codex 验证后合并。
- 实现由 Claude **Fable 5** 完成：1 个 WP-07 三分片 + 4 条并行车道（WP-08/09/10、WP-11..15、WP-18..22、WP-23/24/25/27）+ 1 个收尾 agent（WP-16/17/26 端到端路线 + 验收），全部在隔离 git worktree、off `rebuild/auto-bioinfo-core`。CC 逐段集成并独立跑全量门禁。

## 2. 交付物

- **PR #48** → `TOTO-git-q/rebuild_bioinform_analysis`
  - 分支 `rebuild/wp-07-27-offline`
  - head `82eb7da4222aef4e0d8eac7444696de617aedee2`，base `rebuild/auto-bioinfo-core` at `29a79a621b8fd383b97ddc78ca0b7708946983c5`
  - 97 文件、+24380 行、43 新模块、28 新测试文件、12 新文档；逐-WP/逐-车道 clean commit
- 范围：WP-07 planning（`planning/`）；WP-08/09/10 资源闭环（`resources/`、`adapters/offline_search.py`）；WP-11..15 方法/工作流/执行（`methods/`、`workflow/`、`execution/`）；WP-18..22 QC/证据/报告/复现（`quality/`、`evidence/`、`reporting/`、`reproduction/`）；WP-23/24/25/27 安全/可观测/失败恢复/发布交接（`security/`、`observability/`、`ops/`、`docs/rebuild/`）；WP-16/17/26 离线端到端 bulk RNA-seq 路线 + sc/snRNA donor 路线 + 验收/对抗/需求覆盖矩阵（`routes/`）。
- **复用 PR #46 可复用离线工具层**：`adapters/public_bio_tools.py`（离线 query-planner、deny-by-default、丢弃敏感字段、绝不检索）+ `adapters/capability_registry.py` 已并入并在两条路线的资源发现步骤**实际调用**（作为硬工具/能力闸）。**仅取纯增量部分**；PR #46 早于 WP-06e 的 `scope_resolver.py`/`intake/__init__`/`test_intake_scope_resolver` **未取**，以免回退基线上更新的 WP-06e scope resolver。

## 3. 纪律与验证（on `rebuild/auto-bioinfo-core` base）

- 全离线/确定性/inert：无真实 network/data/compute/credential/wall-clock/subprocess/container/付费服务/持久化/事件总线；所有"真实"阶段用 fake adapter + 录制 fixture（符合落地计划"CI 不调用真实 API"、"fake adapter 契约测试"）。产出 draft 皆空 `created_at`，字节级可复现。
- 复用已冻结 `core/schemas.py` 契约与验证器；**未改** `core/schemas.py` / `core/validation.py`。无核心等价物的 value/orchestration 类型保持车道本地，已在交付报告标注供后续 consolidation。
- 全量套件：**1872 tests OK**（本地 `make lint` / `make format-check` / `git diff --check` 全绿；`make typecheck` advisory，新模块零新错误）。required CI（quality 3.10/3.11/3.12）：**全部 SUCCESS，PR #48 OPEN / MERGEABLE / CLEAN、非 draft、未开 auto-merge**。
- **未触任何硬停点**：真实数据/联网/付费/部署一律没开；PR 全为离线代码。

## 4. 已记录的覆盖缺口（离线收尾范围之外、未接 runner）

T-16-07 绘图、T-16-08 gene-set score、T-16-09 富集、T-16-10 surface/secretome、T-16-14 benchmark、T-17-05 注释重建、T-17-09 differential abundance；T-26-10 worker-crash recovery 为 `partial`（WP-25 单测覆盖，未经路线重驱）。全部记于 `auto_bioinfo/routes/requirement_coverage.py::build_requirement_coverage_matrix()`。

## 5. 请求

1. **执行 CEO 裁定（逐-WP 序列重审合并）**：请 Codex 在 WP-06f / PR #47 收口后，恢复正常"一次一个 WP"节奏，以 `rebuild/wp-07-27-offline`（head `82eb7da4222aef4e0d8eac7444696de617aedee2`）为实现真值源，按路线顺序 **WP-07 → WP-08 → …→ WP-27** 逐 WP 切片：每个 WP 由 Codex 下工单 / 独立复审 / green-lane 合并进 `rebuild/auto-bioinfo-core`，切片 diff 严格限定在该 WP 授权文件内（吸取 turn 0302 的 out-of-scope 教训）。整体 PR #48 **不作单次合并**，仅作切片来源与全绿基线证明。
2. **Codex review-only 先行复核（不影响 WP-06f）**：独立复核 exact head `82eb7da4222aef4e0d8eac7444696de617aedee2` 的 required CI、全量套件、离线/inert 边界（无 network/subprocess import、无真实数据/accession、materialize/execute 无法浮现、claim-ceiling 未被抬高、egress/RBAC deny-by-default 不可绕过），并指出跨车道接口缝隙或车道本地类型（应否 consolidation 进 `core`）以便逐-WP 切片时校正。
3. 本条**不影响** WP-06f / PR #47（turn 0303）当前握手 —— 那条仍轮到 Codex；本批量切片在 WP-06f 收口后启动。
