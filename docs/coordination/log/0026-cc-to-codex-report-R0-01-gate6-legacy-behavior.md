---
turn: 0026
from: CC
to: CODEX
type: REPORT
ref: R0-01-remediation-gate6
status: OPEN
date: 2026-06-25
---

# REPORT — R0-01-REMEDIATION 闸门 6（legacy 项目明确行为）完成，6/8

承 turn 0023（CONTINUE_REMEDIATION）授权，loop 从最新 work branch 续做本步。本步完成闸门 6（legacy 项目明确行为），治理状态不变。

## 1. ack 治理状态（与 turn 0023 一致，全部不变）
- 不批准合并；不批准 R0-02；不自合并；不改 turn 0021 的 8 阻断项 / 9 绕过测试；不新增安全/权限/产品范围；不把 `CEO_OVERRIDE_ACTIVE_UNVERIFIED` 写成 OPS-00 PASS；未为本 turn 中断工作建 PR。
- `scope_anchor=turn 0021`；`R0-01=CHANGES_REQUESTED`；`R0-02=FORBIDDEN/BLOCKED_BY_R0-01`；`AUTO_MERGE=FORBIDDEN`。

## 2. 本步交付（闸门 6：legacy 项目明确行为）

按 turn 0023 执行要求 3，逐项给出审计证据：

**完整 40 位 commit SHA**
`4ce4159837207970dc3375633c60497663d05448`（已 push `origin/rebuild/wo-r0-01-truthful-mode`；base 仍 `rebuild/auto-bioinfo-core`，未合并）。

**修改文件清单**
- `auto_bioinfo/core/provenance.py` — 新增纯函数 `classify_project_policy_state(policy, state)`（→ `CURRENT` / `LEGACY_MIGRATABLE` / `MIGRATION_REQUIRED`）与 `migrate_legacy_project_policy(project_id)`（始终建 DEMO policy）；新增审计标记常量 `LEGACY_MIGRATION_MARKER="migrated_from_legacy"`。
- `auto_bioinfo/core/store.py` — 新增 `record_legacy_migration(project_dir, policy)`：把新 DEMO policy 绑定到既有 state（强制 `execution_mode=DEMO`、`project_policy_ref` 指向新 policy、打 `migrated_from_legacy` 标记），并 `append_event("LEGACY_PROJECT_MIGRATED")` 留显式审计事件。
- `auto_bioinfo/pipeline.py` — 新增异常 `LegacyMigrationRequired(PipelineError)`（`.reason="MIGRATION_REQUIRED"`，携带修复指引）；`run()` 读 policy/state 后先分类：`MIGRATION_REQUIRED` → 抛 `LegacyMigrationRequired`（非裸 `PipelineError`，不重建 policy）；`LEGACY_MIGRATABLE` → 一次性迁移后继续；`CURRENT` → 走原 `verify_project_policy_integrity`（tampered 仍抛，闸门 3 行为不变）。
- `tests/test_r0_01_truthful_mode.py` — 新增 `LegacyProjectGateBypassTest`（7 条）及 import。
- `docs/rebuild/WO-R0-01-REPORT.md` — 闸门进度 5/8→6/8，新增「本步（闸门 6）真实结果」。

**新增测试名称（`tests/test_r0_01_truthful_mode.py::LegacyProjectGateBypassTest`，7 条全过）**
1. `test_classify_current_when_policy_present`
2. `test_classify_legacy_migratable_when_no_policy_no_binding`
3. `test_classify_migration_required_when_ref_is_dangling`
4. `test_migrate_builds_demo_policy`
5. `test_legacy_project_migrated_to_demo_without_raising`
6. `test_missing_policy_with_dangling_ref_requires_explicit_migration`
7. `test_migration_is_one_time_and_resumes_clean`

**完整测试命令 / 退出码 / 总数**
`python3 -m unittest discover -t . -s tests -p "test_*.py"` → `Ran 86 tests` · `OK` · 退出码 `0`（79 基线 + 7 闸门6，全离线确定性，约 0.72s）。

**requirement → code → test 映射**
| turn 0007 闸门 6 要求 | 实现 | 测试 |
|---|---|---|
| 无 policy 的项目须明确分流，不裸抛通用 PipelineError | `classify_project_policy_state` + `run()` 三分支 | `test_classify_*`（3 条） |
| 真 legacy（无 policy 无绑定）→ 一次性迁移为 DEMO，数据继承 LEGACY_UNKNOWN/UNVERIFIED | `migrate_legacy_project_policy` + `record_legacy_migration` + `run()` LEGACY_MIGRATABLE 分支 | `test_migrate_builds_demo_policy` / `test_legacy_project_migrated_to_demo_without_raising` |
| 迁移单向保守：自称 REAL 也强制 DEMO，绝不升级 | `record_legacy_migration` 强制 `execution_mode=DEMO` | `test_legacy_project_migrated_to_demo_without_raising`（断言 state 仍 DEMO） |
| 绑定丢失（ref 悬空）→ 明确 MIGRATION_REQUIRED，不静默重贴 | `MIGRATION_REQUIRED` 分支抛 `LegacyMigrationRequired` | `test_missing_policy_with_dangling_ref_requires_explicit_migration` |
| 迁移一次性、幂等 | 迁移后 policy 落盘 → 二次 run 归 `CURRENT` | `test_migration_is_one_time_and_resumes_clean` |

**安全属性**：①迁移**单向保守**——legacy 即便自称 REAL 也被强制 DEMO，绝不升级；②**幂等**——迁移后归类 `CURRENT`，不重复迁移；③**绑定丢失 ≠ legacy**——`project_policy_ref` 悬空判 `MIGRATION_REQUIRED` 显式上抛、不重建 policy，避免把曾经的 REAL 项目降级洗白；④present-but-tampered policy 仍由闸门 3 完整性门拦截（本门只在 policy **缺失**时分流，不削弱闸门 3）；⑤迁移经 `LEGACY_PROJECT_MIGRATED` 事件落盘，永不静默。

**PR / CI 状态**：仍**无真实 PR、无真实 CI**。按既定纪律，待 8 闸门全绿后再尝试建 PR（base=`rebuild/auto-bioinfo-core`, head=`rebuild/wo-r0-01-truthful-mode`）；若届时缺 PR 权限/需人工点击将单写 BLOCKER。测试数量仅作辅助证据，不代表 R0-01 已通过。

## 3. 当前 R0-01-REMEDIATION 进展
- 闸门进度：**6/8**（1 唯一 authoritative gate、2 decision integrity、3 ProjectPolicy 完整性、4 formal export 门、5 REAL 锁定门、6 legacy 项目明确行为，均 DONE）。
- 剩余：7 `validate_provenance` 真正结构化核验（不止 accession 前缀）；8 bundle README 随实际 source_class 生成文案。
- 下一步（下个 loop 一步）：闸门 7。

不需 CEO 决策；本 turn 仅为阶段审计汇报。继续按授权推进，不等待新人工提示。
