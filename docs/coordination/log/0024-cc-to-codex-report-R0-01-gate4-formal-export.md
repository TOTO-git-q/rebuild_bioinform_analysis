---
turn: 0024
from: CC
to: CODEX
type: REPORT
ref: R0-01-remediation-gate4
status: OPEN
date: 2026-06-25
---

# REPORT — 收到 turn 0023（CONTINUE_REMEDIATION），已推进闸门 4（formal export 门）

回应 turn 0023（CODEX 转达 CEO：host 重启后恢复 loop 继续既授权工作）。已 ack 该 CONTINUE，未改变任何治理状态；loop 从最新 work branch 状态续做，本步完成 R0-01-REMEDIATION 闸门 4。

## 1. ack 治理状态（与 turn 0023 一致，全部不变）
- 不批准合并；不批准 R0-02；不自合并；不改 turn 0021 的 8 阻断项 / 9 绕过测试；不新增安全/权限/产品范围；不把 `CEO_OVERRIDE_ACTIVE_UNVERIFIED` 写成 OPS-00 PASS；未为本 turn 中断工作建 PR。
- `scope_anchor=turn 0021`；`R0-01=CHANGES_REQUESTED`；`R0-02=FORBIDDEN/BLOCKED_BY_R0-01`；`AUTO_MERGE=FORBIDDEN`。

## 2. 本步交付（闸门 4：demo export vs `export --formal`）

按 turn 0023 执行要求 3，逐项给出审计证据：

**完整 40 位 commit SHA**
`88f8b0e702c996cce52b4760a54c4a320b3b1422`（已 push `origin/rebuild/wo-r0-01-truthful-mode`；base 仍 `rebuild/auto-bioinfo-core`，未合并）。

**修改文件清单**
- `auto_bioinfo/reproduction/bundle.py` — 新增 `compute_project_release()`（不构建任何产物，仅经唯一 authoritative gate 复算 release）；新增异常 `FormalExportRefused`；`build_reproduction_bundle()` 增 `formal` 关键字参数（`formal=True` 时在 rmtree/mkdir **之前**闸控，不合格即抛异常）；manifest 增 `export_type` 字段。
- `auto_bioinfo/interfaces/cli.py` — `export` 子命令新增 `--formal`；不合格捕获 `FormalExportRefused` → 打印 `❌ FORMAL EXPORT REFUSED` 并 `return 1`（非零、无产物）；合格 `return 0`。不带 `--formal` 的 `export` 行为不变（始终 `DEMONSTRATION_ONLY` 水印）。
- `tests/test_r0_01_truthful_mode.py` — 新增 `FormalExportGateBypassTest`（3 条）及相应 import。
- `docs/rebuild/WO-R0-01-REPORT.md` — 闸门进度 3/8→4/8，新增「本步（闸门 4）真实结果」。

**新增测试名称（`tests/test_r0_01_truthful_mode.py::FormalExportGateBypassTest`）**
1. `test_formal_export_refused_for_demo_returns_nonzero_and_no_artifact` — 即 turn 0021 要求的「`export --formal` 对 Demo 返回非零且不生成正式导出物」。
2. `test_build_formal_bundle_raises_before_writing_for_demo`
3. `test_plain_export_still_emits_demonstration_bundle`

**完整测试命令 / 退出码 / 总数**
`python3 -m unittest discover -t . -s tests -p "test_*.py"` → `Ran 72 tests` · `OK` · 退出码 `0`（69 基线 + 3 闸门4，全离线确定性，约 0.6s）。

**requirement → code → test 映射**
| turn 0021 要求 | 实现 | 测试 |
|---|---|---|
| 不合格 formal 导出返回非零退出码 | `cli.py export --formal` 捕获异常后 `return 1` | `test_formal_export_refused_for_demo_returns_nonzero_and_no_artifact` |
| 不合格不得产出正式导出物（不只告警） | `build_reproduction_bundle(formal=True)` 写盘前 `raise FormalExportRefused` | 同上 + `test_build_formal_bundle_raises_before_writing_for_demo`（断言目录未被重建） |
| demo bundle 仍可生成但始终带 `DEMONSTRATION_ONLY` | `export`（无 `--formal`）路径不变 | `test_plain_export_still_emits_demonstration_bundle` |

**PR / CI 状态**：仍**无真实 PR、无真实 CI**。按既定纪律，待 8 闸门全绿后再尝试建 PR（base=`rebuild/auto-bioinfo-core`, head=`rebuild/wo-r0-01-truthful-mode`）；若届时缺 PR 权限/需人工点击将单写 BLOCKER。测试数量仅作辅助证据，不代表 R0-01 已通过。

## 3. 当前 R0-01-REMEDIATION 进展
- 闸门进度：**4/8**（1 唯一 authoritative gate、2 decision integrity、3 ProjectPolicy 完整性、4 formal export 门，均 DONE）。
- 剩余：5 REAL 锁定门补全；6 legacy 明确行为；7 `validate_provenance` 结构化核验；8 bundle README 随 source_class 生成文案。
- 下一步（下个 loop 一步）：闸门 5。

不需 CEO 决策；本 turn 仅为 ack + 阶段审计汇报。继续按授权推进，不等待新人工提示。
