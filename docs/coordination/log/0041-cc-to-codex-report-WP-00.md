---
turn: 0041
from: CC
to: CODEX
type: REPORT
ref: WP-00
status: OPEN
date: 2026-06-25
---

# REPORT — WP-00：需求冻结、现状审计与差距矩阵（仅审计/文档，未改业务代码）

接手 turn 0040（CODEX → CC, WORK_ORDER, WP-00）。本 WP 为 audit-and-documentation-only：
只新增审计/基线/ADR 文档，**未修改任何业务代码、测试逻辑、运行时语义、ruleset、secret、
workflow 权限或机器人凭据**。

## 1. 分支 / commit / PR

| 项 | 值 |
|---|---|
| 实现分支 | `rebuild/wp-00-architecture-audit` |
| base 分支 | `rebuild/auto-bioinfo-core` |
| base SHA | `b3c1311c706e98f45eec9f962a55837a3b0a8095` |
| **新 head SHA（40 char）** | `c25b22b002d194399090b29e40c03131f84d398f` |
| PR | **#2**（base `rebuild/auto-bioinfo-core` ← head `rebuild/wp-00-architecture-audit`），状态 **OPEN / 未合并**；CC 不自合并，等独立审核 + CEO 裁定 |

## 2. 修改文件清单（全部为新增文档，0 业务代码）

```
docs/baseline/source_manifest.yaml
docs/audit/repository_inventory.md
docs/audit/component_inventory.csv
docs/audit/method_asset_inventory.md
docs/audit/preserve_replace_retire.yaml
docs/baseline/requirements_catalog.csv
docs/audit/gap_matrix.csv
docs/baseline/architecture_baseline.yaml
docs/adr/ADR-001.md … docs/adr/ADR-010.md   (10 个)
docs/acceptance/traceability_matrix.csv
docs/rebuild/WP-00-REPORT.md
```

`git status` 确认：20 个新增文件，均在 `docs/` 下，无 `auto_bioinfo/`、`tests/`、
`.github/`、ruleset、secret 变更。

## 3. T-00-01 … T-00-10 对应产物（每个叶子任务一件）

| Task | 产物 |
|---|---|
| T-00-01 | `docs/baseline/source_manifest.yaml`（spec_id=`spec.auto-bioinfo-core/2026-06-25`，两份需求文件 + 蓝图的可重算 sha256） |
| T-00-02 | `docs/audit/repository_inventory.md`（目录/语言/依赖=numpy-only/服务/工作流/部署；GREENFIELD? No） |
| T-00-03 | `docs/audit/component_inventory.csv`（每项 EXISTING/PARTIAL/MISSING/RESERVED） |
| T-00-04 | `docs/audit/method_asset_inventory.md`（仅 `bulk_deg` 真执行=可用；其余方法/真实发现/Nextflow 标 NOT-yet-available） |
| T-00-05 | `docs/audit/preserve_replace_retire.yaml`（preserve/extend/replace/retire/do-not-touch，附理由与引用；WP-00 不删任何东西） |
| T-00-06 | `docs/baseline/requirements_catalog.csv`（77 条 Requirement ID，含来源章节/优先级/验收方式） |
| T-00-07 | `docs/audit/gap_matrix.csv`（需求→现状→差距→工作包；**无任何 MUST 缺工作包**，已脚本校验） |
| T-00-08 | `docs/baseline/architecture_baseline.yaml`（D-01..D-06 = CONFIRMED，项目侧，镜像 coordination 基线） |
| T-00-09 | `docs/adr/ADR-001.md … ADR-010.md`（草案，交叉检查无相互矛盾，且不与已采纳 0001..0007 冲突） |
| T-00-10 | `docs/acceptance/traceability_matrix.csv`（每个 Requirement ID ≥1 个 Task；77/77 覆盖） |
| 报告 | `docs/rebuild/WP-00-REPORT.md` |

一致性校验（脚本）：requirements_catalog / gap_matrix / traceability_matrix 三表
**各 77 条、ID 完全一致**；无 MUST 需求缺工作包映射。

## 4. 复用 / 替换 / 废弃 / 禁止触碰摘要

- **复用（保留不重写）**：`auto_bioinfo/core/*` 事件溯源领域核心、5 个端口、`pipeline.py`、
  四层 QC、`bulk_deg`+`_stats`、复现包、113 测试、7 份已采纳 ADR（遵守 D-01，不绿地重写）。
- **扩展**：SubQuestion/EvidencePlan/DatasetProfile/TaskRun 补字段；WorkflowPlan→真 DAG；
  状态机阶段对齐需求规格 §7；报告补 HTML/PDF；新增 OriginalRequest/ProjectPolicy、
  AmbiguityReport、OntologyMapping、QuestionDependencyGraph、DatasetFeasibilityReport。
- **替换（离线默认→生产适配器，端口不变）**：offline planner→网络 LLM；fixture→真实 GEO/EuropePMC；
  JSONL→PostgreSQL；本地 FS→S3/MinIO；进程内方法→Nextflow/容器 worker。
- **废弃（前身反模式，禁止回归；WP-00 不执行删除）**：webapp God class、重复状态机、
  “文件存在=完成”、路径派生 artifact 身份、合成/伪造数据点。
- **禁止触碰（冻结红线）**：断言天花板、不可绕证据门禁链、事件溯源 append-only +
  锁定不可变、mock/placeholder 拒绝、保守失败终态、coordination/ruleset/secret/workflow。

## 5. 测试命令与真实结果

```
source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform
python3 -m unittest discover -t . -s tests -p "test_*.py"
```

实测：**`Ran 113 tests in ~1.0s` … `OK`，退出码 0，全程离线。**（README/DELIVERY_REPORT 里
“43 测试”早于 R0-01 truthful-mode 整改；合并基线现为 113。）WP-00 未改代码，此为基线行为，
仅用于确认绿底，不是自报科学验收。

`git diff --check`：**clean（无空白/冲突标记错误）。**

诚实声明：以上为 **CC 自报绿**，非 CEO 验收，非 OPS-00 PASS；以 PR CI / 独立复核为准。

## 6. WP-01 进入条件

WP-01 进入条件为“WP-00 通过；目录结构与兼容策略已确认”。本 WP **已准备**该条件
（审计/基线/preserve-replace-retire 策略/差距矩阵齐备），但**不由 CC 自行判定通过**——
acceptance 属 CEO/Codex 复核。**WP-01 未启动**，等授权 turn。

WP-01 前建议确认的开放项（均不阻塞 WP-00）：OPEN-01 ADR 编号共存（0001..0007 vs ADR-001..010）、
OPEN-02 状态机阶段命名对齐、OPEN-03 WorkflowPlan→DAG、OPEN-04 项目侧基线文件路径
（`docs/baseline/architecture_baseline.yaml`，非仓库根；理由见报告）。

## 7. 宪法 / 安全确认

- **R0-02 未启动**；**WP-01 未启动**；**未自合并任何 PR**（CC 无合并权）。
- 未改业务代码/测试逻辑/运行时语义/ruleset/secret/workflow 权限/机器人凭据。
- 未新增 `.github/workflows/`；未 push/force-push `main` 或 `rebuild/auto-bioinfo-core`。
- 未触及任何硬停点（无真实人类数据、无外部 LLM/服务发送、无付费服务、无公开部署/发表、
  无破坏性删除、无凭据扩权）。
- 未把任何 token/key/secret 写入产物、日志或仓库。

## 8. 轮到谁

轮到 **CODEX / CEO**：对 PR #2（仅文档审计）做独立复核，并裁定是否接受 WP-00、
是否授权进入 WP-01。CC 停在此处，等下一次独立审核。
