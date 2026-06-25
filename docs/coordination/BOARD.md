# BOARD — 实时状态板

> 一屏看清现状。每个写者写 turn 时顺手更新本文件对应行（改前 `git pull --rebase`）。

## 系统状态

| 项 | 值 |
|---|---|
| governance_status | **RATIFIED** |
| constitution_version | **1.0** |
| execution_gate | **WP-01_ACTIVE** |
| 当前阶段 | WP-01 / repository skeleton, development environment and quality gates |
| R0-01 | **MERGED** |
| R0-02 | **NOT_STARTED**（WP 路线已启动；当前为 WP-01） |
| 当前唯一可执行 Work Order | **WP-01：仓库骨架、开发环境与质量门** |
| 轮到谁 | **CC**（执行 WP-01；完成后提交 PR + REPORT，等待 Codex 独立审核） |
| 第一治理提交 | `bf21348` |

## 开放 turn（status: OPEN）

| turn | from → to | type | ref | 摘要 |
|---|---|---|---|---|
| 0039 | CODEX → CC | DECISION | architecture-baseline-and-wp-route | 冻结 D-01～D-06 架构基线与 WP 路线；长期合并授权生效；硬停点仍需 CEO |
| 0043 | CODEX → CC | DECISION | WP-00-pr2-merged | PR #2 已合并，merge commit `1fd8844c3f4f50d04d64ad962aaaa69b48d0764a`；WP-00 = MERGED；按 turn 0044 启动 WP-01 |
| 0044 | CODEX → CC | WORK_ORDER | WP-01 | 启动 WP-01：仓库骨架、开发环境与质量门；仅限 WP-01，完成后提交 PR + REPORT |

## 已处理 turn

| turn | 处理结果 |
|---|---|
| 0002 | 已由 turn 0004 接手：R0-01 = CHANGES_REQUESTED |
| 0003 | 已由 turn 0004 + 0005 接手：协调系统 ratified as constitution v1.0 |
| 0004 | CC 已据此执行：承认 ratify、启动 OPS-00 |
| 0005 | CC 已承认宪法 v1.0 并遵守 OPS-00_ONLY |
| 0006 | CC 侧 OPS-00 完成并报告（turn 0010）；剩余 .3/.7 阻塞于 owner（turn 0008） |
| 0007 | 已由 turn 0009 ANSWER 回复 |
| 0008 | 已由 turn 0011 DECISION 接手：原 owner-control 请求为 CHANGES_REQUESTED |
| 0009 | 已转达 CEO；R0-01 review-fix 需等 OPS-00 PASS |
| 0010 | 已由 turn 0011 DECISION 接手：OPS-00 remains NOT_PASS |
| 0011 | 已由 turn 0013 REPORT 接手：接受裁定，Git broker + 13 项证据落地 |
| 0012 | 已由 turn 0014 DECISION 接手：owner controls v2 = APPROVE_WITH_CONDITIONS |
| 0013 | 已由 turn 0014 DECISION 接手：实现接受，PASS 仍需 GitHub App/ruleset/在场测试 |
| 0014 | 已由 turn 0016 DECISION 覆盖：CEO 降低门禁并要求立即进入握手系统 active 状态 |
| 0015 | 已由 turn 0016 DECISION 接手：CEO 覆盖原 owner-control 卡点 |
| 0017 | 已由 Codex 转达 CEO：CC 接受 override，握手 active-by-override，开始 R0-01-REMEDIATION |
| 0018 | 已由 turn 0019 接手：CC 报告自主 loop 已激活；0019 要求补充完整任务状态与回程测试 |
| 0019 | 已由 turn 0020 ANSWER 回复：握手回程测试通过 + 全量任务状态汇总 |
| 0020 | 已由 turn 0021 接手：CEO 追加 R0-01 review-context / plan-memory 留言；CC 继续 R0-01-REMEDIATION 并回报 |
| 0021 | 已由 turn 0022 ANSWER 回复：确认锚点 + 计划记忆 + R0-01-REMEDIATION 进展（2/8, 59 tests OK, f50be1a, 无 PR） |
| 0022 | 已由 turn 0023 DECISION 接手：收到回执，host 重启后继续 R0-01-REMEDIATION Gate 1 |
| 0023 | 已由 turn 0024 REPORT 接手：CC ack CONTINUE，闸门 4（formal export 门）完成，4/8，72 tests OK，SHA 88f8b0e，无 PR |
| 0024 | 续报：闸门 5（REAL 锁定门）由 turn 0025 完成，5/8 |
| 0025 | 续报：闸门 6（legacy 项目明确行为）由 turn 0026 完成，6/8 |
| 0026 | 续报：闸门 7（validate_provenance 结构化核验）由 turn 0027 完成，7/8 |
| 0027 | 续报：闸门 8（bundle README 随 source_class 生成）由 turn 0028 完成，**8/8 全闸门收口 + 真实 PR #1** |
| 0028 | 已由 turn 0029 DECISION 接手：PR #1 = CHANGES_REQUESTED，只修复 3 个 R0-01 blockers |
| 0029 | 已由 turn 0030 REPORT 接手：3 个 blocker review-fix 完成，新 head `c2d5556`，111 测试绿，PR #1 仍 OPEN/未合并 |
| 0030 | 已由 turn 0031 DECISION 接手：独立复核仍为 CHANGES_REQUESTED，只剩 Blocker 2 forged decision 绕过未闭合 |
| 0031 | 已由 turn 0032 REPORT 接手：Blocker 2 修复（生产 gate 派生真实 expected refs/hash），新 head `67e99a0`，113 测试绿，等 Codex 重新独立审核 |
| 0032 | 已由 turn 0033 DECISION 接手：独立复核通过，建议 `APPROVE_MERGE_RECOMMENDED`，等待 CEO 合并裁定 |
| 0033 | 已由 turn 0034 DECISION 接手：CEO 明确 `MERGE_AUTHORIZED`，仅允许合并 PR #1 已审核 head `67e99a0` |
| 0034 | 已由 turn 0035 BLOCKER 接手：CEO 授权有效，但合并执行人按宪法属 Codex；CC 不自合并，等 Codex 机械合并或 CEO 修宪 |
| 0035 | 已由 turn 0036 DECISION 接手：Codex 已机械合并 PR #1，merge commit `b3c1311c706e98f45eec9f962a55837a3b0a8095` |
| 0036 | 已由 turn 0037 DECISION 接手：R0-01 合并后状态归一，R0-02 仍未启动 |
| 0037 | 已由 turn 0038 ACK 接手：CC 确认收到合并后状态，无实现动作，R0-02 未启动 |
| 0038 | 已由 turn 0039/0040 接手：CEO 冻结架构基线并启动 WP-00 |
| 0040 | 已由 turn 0041 REPORT 接手：WP-00 仅文档审计交付，head `c25b22b0`，PR #2 OPEN，113 测试绿，未改业务代码/未启动 WP-01 |
| 0041 | 已由 turn 0042 DECISION 接手：WP-00 独立复核通过，PR #2 merge 受 GitHub integration 403 权限阻塞 |
| 0042 | 已由 turn 0043 DECISION 接手：PR #2 已合并，merge commit `1fd8844c3f4f50d04d64ad962aaaa69b48d0764a`；合并权限阻塞解除 |

## 当前开放任务

1. **WP-01**：已由 turn 0044 派发；范围为仓库骨架、开发环境与质量门，完成后提交 PR + REPORT。
2. **WP-02**：紧邻下一包；**未启动**，等 WP-01 合并并记录 merge SHA 后再派发。
3. **诚实状态**：不得把 CEO override 写成 OPS-00 PASS；PASS 只能在原要求测试后来真实通过时再写。
4. **后续报告**：CC 完成 WP-01 后提交 REPORT，含分支/PR/SHA/产物/测试结果/硬停点确认。

（OPS-00 原测试门禁被 CEO override 覆盖以便立即启用握手系统；状态为 active-by-override / unverified，不是 PASS。）

## 阻塞项

1. **硬停点**：真实人类来源数据、外部 LLM/服务、付费服务、公开发布、破坏性迁移/不可逆删除、扩大机器人凭据权限，均必须停下等 CEO。
2. **WP-01 权限注意**：若 workflow/CI 相关 push 因权限被拒，CC 必须写 BLOCKER；不得自行扩大机器人凭据权限。
3. **当前范围**：仅 WP-01 工程骨架与质量门；不得启动 WP-02，不得加入业务/科学分析逻辑。

## 最近 turn 索引

| turn | 文件 |
|---|---|
| 0001 | `log/0001-codex-to-cc-workorder-R0-01.md`（DONE） |
| 0002 | `log/0002-cc-to-codex-report-R0-01.md`（OPEN，已由 0004 接手） |
| 0003 | `log/0003-cc-to-codex-proposal-coordination-system.md`（OPEN，已由 0004/0005 接手） |
| 0004 | `log/0004-codex-to-cc-decision-ceo-final.md`（OPEN） |
| 0005 | `log/0005-codex-to-cc-ratify-constitution-v1.0.md`（OPEN） |
| 0006 | `log/0006-codex-to-cc-workorder-OPS-00.md`（已由 0010 接手） |
| 0007 | `log/0007-codex-to-cc-question-R0-01-review-fix.md`（已由 0009 接手） |
| 0008 | `log/0008-cc-to-codex-blocker-OPS-00-owner.md`（OPEN） |
| 0009 | `log/0009-cc-to-codex-answer-R0-01-review-fix.md`（OPEN，已转达） |
| 0010 | `log/0010-cc-to-codex-report-OPS-00.md`（OPEN，已由 0011 接手） |
| 0011 | `log/0011-codex-to-cc-decision-OPS-00-owner-controls.md`（已由 0013 接手） |
| 0012 | `log/0012-cc-to-codex-blocker-OPS-00-owner-v2.md`（OPEN，已由 0014 接手） |
| 0013 | `log/0013-cc-to-codex-report-OPS-00-controls.md`（OPEN，已由 0014 接手） |
| 0014 | `log/0014-codex-to-cc-decision-OPS-00-owner-controls-v2.md`（OPEN，已由 0016 覆盖） |
| 0015 | `log/0015-cc-to-codex-answer-OPS-00-controls-v2.md`（OPEN，已由 0016 接手） |
| 0016 | `log/0016-codex-to-cc-decision-CEO-override-handshake-active.md`（OPEN） |
| 0017 | `log/0017-cc-to-codex-answer-CEO-override-active.md`（OPEN，已转达） |
| 0018 | `log/0018-cc-to-codex-report-autonomous-loop-active.md`（OPEN，已由 0019 接手） |
| 0019 | `log/0019-codex-to-cc-question-handshake-status-test.md`（已由 0020 接手） |
| 0020 | `log/0020-cc-to-codex-answer-handshake-status-test.md`（OPEN，已由 0021 接手） |
| 0021 | `log/0021-codex-to-cc-decision-R0-01-review-context.md`（已由 0022 接手） |
| 0022 | `log/0022-cc-to-codex-answer-R0-01-review-context.md`（OPEN，已由 0023 接手） |
| 0023 | `log/0023-codex-to-cc-decision-resume-R0-01-remediation.md`（已由 0024 接手） |
| 0024 | `log/0024-cc-to-codex-report-R0-01-gate4-formal-export.md`（OPEN，续报于 0025） |
| 0025 | `log/0025-cc-to-codex-report-R0-01-gate5-real-lock.md`（OPEN） |
| 0026 | `log/0026-cc-to-codex-report-R0-01-gate6-legacy-behavior.md`（OPEN，续报于 0027） |
| 0027 | `log/0027-cc-to-codex-report-R0-01-gate7-structural-provenance.md`（OPEN，续报于 0028） |
| 0028 | `log/0028-cc-to-codex-report-R0-01-gate8-and-pr.md`（OPEN，已由 0029 接手） |
| 0029 | `log/0029-codex-to-cc-decision-R0-01-pr1-changes-requested.md`（已由 0030 接手） |
| 0030 | `log/0030-cc-to-codex-report-R0-01-pr1-review-fix.md`（OPEN，已由 0031 接手） |
| 0031 | `log/0031-codex-to-cc-decision-R0-01-pr1-review-fix-changes-requested.md`（OPEN，已由 0032 接手） |
| 0032 | `log/0032-cc-to-codex-report-R0-01-pr1-blocker2-fix.md`（OPEN，已由 0033 接手） |
| 0033 | `log/0033-codex-to-cc-decision-R0-01-pr1-review-pass-await-ceo.md`（OPEN，已由 0034 接手） |
| 0034 | `log/0034-codex-to-cc-decision-R0-01-pr1-merge-authorized.md`（OPEN，已由 0035 接手） |
| 0035 | `log/0035-cc-to-codex-blocker-R0-01-pr1-merge-authority.md`（OPEN，已由 0036 接手） |
| 0036 | `log/0036-codex-to-cc-decision-R0-01-pr1-merged.md`（OPEN，已由 0037 接手） |
| 0037 | `log/0037-codex-to-cc-decision-R0-01-post-merge-state.md`（已由 0038 接手） |
| 0038 | `log/0038-cc-to-codex-ack-R0-01-post-merge-state.md`（DONE，纯确认；已由 0039/0040 接手） |
| 0039 | `log/0039-codex-to-cc-decision-architecture-baseline-wp-route.md`（OPEN） |
| 0040 | `log/0040-codex-to-cc-workorder-WP-00.md`（已由 0041 接手） |
| 0041 | `log/0041-cc-to-codex-report-WP-00.md`（OPEN，已由 0042 接手） |
| 0042 | `log/0042-codex-to-cc-decision-WP-00-pr2-reviewed-merge-blocked.md`（OPEN，已由 0043 接手：PR #2 merged） |
| 0043 | `log/0043-codex-to-cc-decision-WP-00-pr2-merged.md`（OPEN，WP-00 merged，merge commit `1fd8844c3f4f50d04d64ad962aaaa69b48d0764a`） |
| 0044 | `log/0044-codex-to-cc-workorder-WP-01.md`（OPEN，WP-01 WORK_ORDER） |
