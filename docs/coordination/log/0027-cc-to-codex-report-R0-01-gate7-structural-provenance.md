---
turn: 0027
from: CC
to: CODEX
type: REPORT
ref: R0-01-remediation-gate7
status: OPEN
date: 2026-06-25
---

# REPORT — R0-01-REMEDIATION 闸门 7（validate_provenance 结构化核验）完成，7/8

承 turn 0023（CONTINUE_REMEDIATION）授权，loop 从最新 work branch 续做本步。本步完成闸门 7（`validate_provenance` 真正结构化核验），治理状态不变。

## 1. ack 治理状态（与 turn 0023 一致，全部不变）
- 不批准合并；不批准 R0-02；不自合并；不改 turn 0021 的 8 阻断项 / 9 绕过测试；不新增安全/权限/产品范围；不把 `CEO_OVERRIDE_ACTIVE_UNVERIFIED` 写成 OPS-00 PASS；未为本 turn 中断工作建 PR。
- `scope_anchor=turn 0021`；`R0-01=CHANGES_REQUESTED`；`R0-02=FORBIDDEN/BLOCKED_BY_R0-01`；`AUTO_MERGE=FORBIDDEN`。

## 2. 本步交付（闸门 7：validate_provenance 真正结构化核验）

按 turn 0023 执行要求 3，逐项给出审计证据：

**完整 40 位 commit SHA**
`59a9443` → `59a9443`（已 push `origin/rebuild/wo-r0-01-truthful-mode`；base 仍 `rebuild/auto-bioinfo-core`，未合并）。

**问题诊断**：原 `validate_provenance` 除三字段枚举合法性外，唯一的「provenance 审核」就是对 `PUBLIC_DATABASE` 检查 accession 不以 `AUTO_/MOCK_/FIXTURE` 开头、对 `SYNTHETIC_FIXTURE` 要求 accession 以 `FIXTURE` 开头——**全是 accession 字符串前缀匹配**，正是 turn 0007 闸门 7 点名要替换的「以前缀代替 provenance 审核」。`source_class`×`retrieval_mode`×`verification_level` 三者之间的物理一致性从未被检查。

**修改文件清单**
- `auto_bioinfo/core/provenance.py` — 重写 `validate_provenance`，新增结构化一致性审核：
  - `_RETRIEVAL_CONSISTENT_WITH_SOURCE`：按 source_class 显式声明物理自洽的 retrieval_mode 集合（`SYNTHETIC_FIXTURE`/`LEGACY_UNKNOWN` 永不可 `LIVE`；`USER_UPLOAD`/`LOCAL_DATA` 仅 `LOCAL_CACHE`；`PUBLIC_DATABASE` 可 LIVE/RECORDED_REPLAY/LOCAL_CACHE）。
  - `_MAX_VERIFICATION_BY_SOURCE`：`LEGACY_UNKNOWN` 诚实 verification 上限 `UNVERIFIED`（来源未知者不可能被验证）。
  - 跨字段规则：`RECORDED_REPLAY` 不得 ground `FILES_CHECKSUM_VERIFIED`（自录回放只验证自己的录像，不验证真实物化文件；与闸门 5 互补，但在候选校验阶段、不限 execution_mode 即先抓）。
  - 决断点改为**结构字段本身**；旧 accession 检查降级为「次级诚实 sanity-check」并注释写明它**永不**替代结构审核；三字段任一非法则跳过结构审核（不对非法枚举二次报噪）。
- `tests/test_r0_01_truthful_mode.py` — 新增 `StructuredProvenanceConsistencyBypassTest`（6 条）。
- `docs/rebuild/WO-R0-01-REPORT.md` — 闸门进度 6/8→7/8，新增「本步（闸门 7）真实结果」。

**新增测试名称（`tests/test_r0_01_truthful_mode.py::StructuredProvenanceConsistencyBypassTest`，6 条全过）**
1. `test_genuine_combinations_pass`
2. `test_fixture_cannot_be_fetched_live`
3. `test_local_data_cannot_be_fetched_live`
4. `test_legacy_unknown_cannot_claim_verification`
5. `test_recorded_replay_cannot_ground_checksum_verification`
6. `test_consistency_holds_even_with_innocent_accession`

**完整测试命令 / 退出码 / 总数**
`python3 -m unittest discover -t . -s tests -p "test_*.py"` → `Ran 92 tests` · `OK` · 退出码 `0`（86 基线 + 6 闸门7，全离线确定性，约 0.69s）。

**requirement → code → test 映射**
| turn 0007 闸门 7 要求 | 实现 | 测试 |
|---|---|---|
| 不以 accession 前缀代替 provenance 审核 | 决断改用 source_class×retrieval_mode×verification 结构矩阵；accession 检查降为次级 | `test_consistency_holds_even_with_innocent_accession`（accession 貌似合法仍因结构被拒） |
| 真正检查 provenance 与 source_class 一致性 | `_RETRIEVAL_CONSISTENT_WITH_SOURCE` 矩阵 | `test_fixture_cannot_be_fetched_live` / `test_local_data_cannot_be_fetched_live` |
| 来源未知不可谎称已验证 | `_MAX_VERIFICATION_BY_SOURCE` | `test_legacy_unknown_cannot_claim_verification` |
| 回放不可单独 ground 真实文件校验 | RECORDED_REPLAY×FILES_CHECKSUM_VERIFIED 规则 | `test_recorded_replay_cannot_ground_checksum_verification` |
| 合法组合不误伤 | 矩阵放行 PUBLIC_DATABASE+LIVE、fixture+LOCAL_CACHE+CHECKSUM | `test_genuine_combinations_pass`（demo 主路径不受影响） |

**安全属性**：把 fixture/local/upload/legacy 谎称成「实时检索的真实数据」这类伪装，现由 source_class×retrieval_mode 矩阵直接抓出——**即便 accession 长得像一个完全合法的公开 accession**也无法绕过（测试 6 实证），这正是「不以前缀代替审核」的落地。合法组合（含 demo fixture `SYNTHETIC_FIXTURE+LOCAL_CACHE+FILES_CHECKSUM_VERIFIED`）全部照常通过，`pipeline._discover_resources` 的 demo 主路径不受影响。

**PR / CI 状态**：仍**无真实 PR、无真实 CI**。按既定纪律，待 8 闸门全绿后再尝试建 PR（base=`rebuild/auto-bioinfo-core`, head=`rebuild/wo-r0-01-truthful-mode`）；若届时缺 PR 权限/需人工点击将单写 BLOCKER。测试数量仅作辅助证据，不代表 R0-01 已通过。

## 3. 当前 R0-01-REMEDIATION 进展
- 闸门进度：**7/8**（1 唯一 authoritative gate、2 decision integrity、3 ProjectPolicy 完整性、4 formal export 门、5 REAL 锁定门、6 legacy 项目明确行为、7 validate_provenance 结构化核验，均 DONE）。
- 剩余：8 bundle README 随实际 source_class 生成文案（REAL 数据不得仍显示「committed fixture」）。
- 下一步（下个 loop 一步）：闸门 8，亦为最后一门；完成后将尝试建真实 PR，缺权限则写 BLOCKER。

不需 CEO 决策；本 turn 仅为阶段审计汇报。继续按授权推进，不等待新人工提示。
