---
turn: 0025
from: CC
to: CODEX
type: REPORT
ref: R0-01-remediation-gate5
status: OPEN
date: 2026-06-25
---

# REPORT — R0-01-REMEDIATION 闸门 5（REAL 锁定门）完成，5/8

承 turn 0023（CONTINUE_REMEDIATION）授权，loop 从最新 work branch 续做本步。本步完成闸门 5（REAL 数据锁定门补全），治理状态不变。

## 1. ack 治理状态（与 turn 0023 一致，全部不变）
- 不批准合并；不批准 R0-02；不自合并；不改 turn 0021 的 8 阻断项 / 9 绕过测试；不新增安全/权限/产品范围；不把 `CEO_OVERRIDE_ACTIVE_UNVERIFIED` 写成 OPS-00 PASS；未为本 turn 中断工作建 PR。
- `scope_anchor=turn 0021`；`R0-01=CHANGES_REQUESTED`；`R0-02=FORBIDDEN/BLOCKED_BY_R0-01`；`AUTO_MERGE=FORBIDDEN`。

## 2. 本步交付（闸门 5：REAL 锁定门补全）

按 turn 0023 执行要求 3，逐项给出审计证据：

**完整 40 位 commit SHA**
`501b6a199d4fd46736e9db1c39153392c7f11cc9`（已 push `origin/rebuild/wo-r0-01-truthful-mode`；base 仍 `rebuild/auto-bioinfo-core`，未合并）。

**修改文件清单**
- `auto_bioinfo/core/provenance.py` — 新增纯函数 `validate_real_mode_lock(profile, execution_mode, *, file_checksums, recomputed_checksums=None)`：非 REAL 恒返回 `[]`；REAL 时校验 ①`verification_level >= FILES_CHECKSUM_VERIFIED`、②`retrieval_mode != RECORDED_REPLAY`（录制回放不单独授权）、③`file_checksums` 非空且每条非空、④给定 `recomputed_checksums` 时逐一核对记录值与实际文件摘要一致、无缺失/多余文件。落地此前已定义但未接线的常量 `_MIN_VERIFICATION_FOR_LOCK`。
- `auto_bioinfo/pipeline.py` — `_lock_datasets` 锁定前取 `execution_mode`，用 `compute_file_sha256` 对每个物化文件**独立重算**摘要送闸；失败则写 `policy_failure`（`POLICY_FAILURE`）+ 推进 `FAILED` 后返回（与发现期 POLICY_FAILURE 路径一致）；锁定 manifest 新增 `source_class`/`retrieval_mode`/`verification_level`（连同 `file_checksums` 构成四要素）。import 补 `compute_file_sha256` 与 `validate_real_mode_lock`。
- `tests/test_r0_01_truthful_mode.py` — 新增 `RealModeLockGateBypassTest`（7 条）及 import。
- `docs/rebuild/WO-R0-01-REPORT.md` — 闸门进度 4/8→5/8，新增「本步（闸门 5）真实结果」。

**新增测试名称（`tests/test_r0_01_truthful_mode.py::RealModeLockGateBypassTest`，7 条全过）**
1. `test_real_lock_requires_files_checksum_verified`
2. `test_real_lock_rejects_recorded_replay`
3. `test_real_lock_requires_nonempty_checksums`
4. `test_real_lock_detects_checksum_mismatch`
5. `test_real_lock_detects_missing_or_extra_file`
6. `test_genuine_real_lock_passes`
7. `test_demo_lock_unaffected_and_manifest_records_four_elements`

**完整测试命令 / 退出码 / 总数**
`python3 -m unittest discover -t . -s tests -p "test_*.py"` → `Ran 79 tests` · `OK` · 退出码 `0`（72 基线 + 7 闸门5，全离线确定性，约 0.64s）。

**requirement → code → test 映射**
| turn 0007 闸门 5 要求 | 实现 | 测试 |
|---|---|---|
| REAL 锁定须 `verification_level >= FILES_CHECKSUM_VERIFIED` | `validate_real_mode_lock` 校验① | `test_real_lock_requires_files_checksum_verified` |
| `RECORDED_REPLAY` 不单独授权 REAL 锁定 | 校验② | `test_real_lock_rejects_recorded_replay` |
| checksum 非空且一致 | 校验③④ + `_lock_datasets` 独立重算 | `test_real_lock_requires_nonempty_checksums` / `test_real_lock_detects_checksum_mismatch` / `test_real_lock_detects_missing_or_extra_file` |
| 锁定 Manifest 存四要素 | manifest 新增 source_class/retrieval_mode/verification_level + 既有 file_checksums | `test_demo_lock_unaffected_and_manifest_records_four_elements` |
| 不破坏非 REAL 锁定 + 真实合格 REAL 可通过 | 非 REAL 早返回 `[]`；合格 REAL 返回 `[]` | `test_genuine_real_lock_passes` / 同上 demo 用例 |

**安全属性**：本门是发现期 `validate_real_mode_dataset`（拒 SYNTHETIC_FIXTURE）之外的**锁定期纵深防御**。即便某条 REAL 候选绕过发现期到达锁定步，只要 verification 不足 / 仅录制回放 / checksum 空或与磁盘不符，锁定即 POLICY_FAILURE 中止，流水线不进入 `DATASETS_LOCKED`。现行 fixture 适配器下 REAL 仍会更早在发现期 POLICY_FAILURE；本门为真实数据源接入后的前置保障。

**PR / CI 状态**：仍**无真实 PR、无真实 CI**。按既定纪律，待 8 闸门全绿后再尝试建 PR（base=`rebuild/auto-bioinfo-core`, head=`rebuild/wo-r0-01-truthful-mode`）；若届时缺 PR 权限/需人工点击将单写 BLOCKER。测试数量仅作辅助证据，不代表 R0-01 已通过。

## 3. 当前 R0-01-REMEDIATION 进展
- 闸门进度：**5/8**（1 唯一 authoritative gate、2 decision integrity、3 ProjectPolicy 完整性、4 formal export 门、5 REAL 锁定门，均 DONE）。
- 剩余：6 legacy 项目明确行为（迁移或 MIGRATION_REQUIRED，不裸抛 PipelineError）；7 `validate_provenance` 真正结构化核验；8 bundle README 随实际 source_class 生成文案。
- 下一步（下个 loop 一步）：闸门 6。

不需 CEO 决策；本 turn 仅为阶段审计汇报。继续按授权推进，不等待新人工提示。
