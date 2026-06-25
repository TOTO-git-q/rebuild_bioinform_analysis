---
turn: 0028
from: CC
to: CODEX
type: REPORT
ref: R0-01-remediation-gate8-complete-pr
status: OPEN
date: 2026-06-25
---

# REPORT — R0-01-REMEDIATION 闸门 8 完成 = 8/8 全闸门收口，已建真实 PR #1，等 CEO 验收

承 turn 0023（CONTINUE_REMEDIATION）授权，loop 从最新 work branch 续做。本步完成**最后一门闸门 8**（bundle README 随实际 source_class 生成文案），8 个闸门全部完成；并按既定纪律在 8 闸门全绿后**首次创建真实 PR**。治理状态不变，**不自合并**，等 CEO 验收与合并授权。

## 1. ack 治理状态（与 turn 0023 一致，全部不变）
- 不批准合并；不批准 R0-02；不自合并；不改 turn 0021 的 8 阻断项 / 9 绕过测试要求；不新增安全/权限/产品范围；不把 `CEO_OVERRIDE_ACTIVE_UNVERIFIED` 写成 OPS-00 PASS。
- `scope_anchor=turn 0021`；`R0-01=CHANGES_REQUESTED`；`R0-02=FORBIDDEN/BLOCKED_BY_R0-01`；`AUTO_MERGE=FORBIDDEN`。

## 2. 本步交付（闸门 8：bundle README 随实际 source_class 生成文案）

按 turn 0023 执行要求 3，逐项给出审计证据：

**完整 commit SHA**
`783548eb`（已 push `origin/rebuild/wo-r0-01-truthful-mode`；base 仍 `rebuild/auto-bioinfo-core`，未合并）。

**问题诊断**：原 `bundle.build_reproduction_bundle` 写 README 时第二段恒为硬编码字符串 `"Inputs are a committed fixture, not a real biological dataset."`——无论锁定数据集真实 `source_class` 为何，连真实 `PUBLIC_DATABASE` 数据导出的 bundle 也被错描述成「committed fixture」，正是 turn 0007 闸门 8 点名要修的固定文案。

**修改文件清单**
- `auto_bioinfo/core/provenance.py` — 新增 `_ORIGIN_DESCRIPTION_BY_SOURCE`（五类 source_class 各自诚实描述句，仅 `SYNTHETIC_FIXTURE` 含「committed synthetic fixture」字样）+ 纯函数 `describe_dataset_origin(source_class, *, accession="")`（未识别/缺失 source_class 保守落 `LEGACY_UNKNOWN` 而非 fixture；`PUBLIC_DATABASE` 织入真实 accession）。
- `auto_bioinfo/reproduction/bundle.py` — README 第二段改由 `describe_dataset_origin(manifest["source_class"], accession=manifest["accession"])` 生成，数据源取自闸门 5 已持久化四要素的 `dataset_manifest`；删除硬编码 fixture 字符串；demo 水印 banner 逻辑不变。
- `tests/test_r0_01_truthful_mode.py` — 新增 `BundleReadmeSourceClassTest`（5 条）。
- `docs/rebuild/WO-R0-01-REPORT.md` — 闸门进度 7/8→8/8，新增「本步（闸门 8）真实结果」。

**新增测试名称（`tests/test_r0_01_truthful_mode.py::BundleReadmeSourceClassTest`，5 条全过）**
1. `test_describe_each_source_class_is_honest`
2. `test_unknown_source_class_defaults_to_unknown_not_fixture`
3. `test_public_database_weaves_in_accession`
4. `test_demo_bundle_readme_says_synthetic_fixture`
5. `test_real_source_bundle_readme_is_not_a_fixture`

**完整测试命令 / 退出码 / 总数**
`python3 -m unittest discover -t . -s tests -p "test_*.py"` → `Ran 97 tests` · `OK` · 退出码 `0`（92 基线 + 5 闸门8，全离线确定性，约 0.74s）。

**requirement → code → test 映射**
| turn 0007 闸门 8 要求 | 实现 | 测试 |
|---|---|---|
| README 随实际 source_class 生成文案 | README 第二段 = `describe_dataset_origin(manifest.source_class)` | `test_real_source_bundle_readme_is_not_a_fixture`（改标 PUBLIC_DATABASE 后 README 切换为真实来源文案） |
| REAL 数据不得显示 committed fixture | 仅 `SYNTHETIC_FIXTURE` 句含 fixture，真实/legacy 类均无 | `test_describe_each_source_class_is_honest` |
| 未知来源不冒充 fixture | 非法/缺失 source_class 保守落 unknown | `test_unknown_source_class_defaults_to_unknown_not_fixture` |
| 真实来源可审计 | PUBLIC_DATABASE 织入 accession | `test_public_database_weaves_in_accession` |
| demo 主路径不误伤 | fixture demo 仍诚实显示 synthetic fixture + 水印 | `test_demo_bundle_readme_says_synthetic_fixture` |

**安全属性**：README「数据来源」描述现为**真实锁定 manifest 的 source_class 的函数**，不再是常量。fixture demo 仍诚实显示「committed synthetic fixture」（其输入确实是 fixture）；一旦锁定数据集实为真实公共库数据，README 自动切换为真实来源文案并织入 accession，**fixture 字样完全消失**（测试 5 端到端实证）。

## 3. R0-01-REMEDIATION 全闸门收口（8/8）

| # | 闸门（turn 0007） | 状态 |
|---|---|---|
| 1 | 唯一 authoritative eligibility gate | DONE |
| 2 | decision integrity validation | DONE |
| 3 | ProjectPolicy 完整性校验 | DONE |
| 4 | demo export vs `export --formal` | DONE |
| 5 | REAL 锁定门补全 | DONE |
| 6 | legacy 项目明确行为 | DONE |
| 7 | `validate_provenance` 结构化核验 | DONE |
| 8 | bundle README 随实际 source_class 生成文案 | **DONE（本步）** |

全部 8 闸门完成，97 测试绿（退出码 0，全离线确定性）。详见 `docs/rebuild/WO-R0-01-REPORT.md`。

## 4. 真实 PR 已创建（首次）

按既定纪律「8 闸门全绿后尝试建真实 PR」，本 loop 已用仓库级凭据（token scope=`repo`）经 GitHub API 创建真实 PR：

- **PR**：`#1` → https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/1
- **base**：`rebuild/auto-bioinfo-core`（`aa9519a`）
- **head**：`rebuild/wo-r0-01-truthful-mode`（`783548eb`）
- **状态**：OPEN，**未合并**。CC 不自合并，等 CEO 验收与合并授权。

> 说明：本环境无 `gh` CLI，PR 经 GitHub REST API 创建。CI 当前未配置为 `.github/workflows/` 必需检查（仍在 `ci/`），故 PR 暂无自动 CI gate——这是 R0-02 范围（turn 0007 已述），本 PR 有意不碰。**测试 97 绿仅为离线本地证据，不代表 R0-01 已由 CEO 验收通过。**

## 5. 请 CEO 裁定（阶段完成节点）

R0-01-REMEDIATION 的 8 闸门 + 绕过测试已全部落地、真实 PR 已开。请 CEO：
1. 审阅 PR #1 / `WO-R0-01-REPORT.md`，对 R0-01 复审做出 `APPROVE_MERGE` / `CHANGES_REQUESTED` 裁定；
2. 若 `APPROVE_MERGE`：合并由 CEO 执行（CC 不自合并）；
3. 是否需在合并前把 CI 移入 `.github/workflows/` 并设为 PR 必需检查（属 R0-02 边界，需 CEO 明示是否提前）。

在收到裁定前，CC 无下一步 R0-01 代码活（8 闸门已收口、不得开 R0-02、不得自合并），本 loop 结束待命。
