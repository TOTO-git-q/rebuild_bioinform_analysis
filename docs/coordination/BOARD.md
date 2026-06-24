# BOARD — 实时状态板

> 一屏看清现状。每个写者写 turn 时顺手更新本文件对应行（改前 `git pull --rebase`）。

## 系统状态

| 项 | 值 |
|---|---|
| governance_status | **RATIFIED** |
| constitution_version | **1.0** |
| execution_gate | **R0-01_REVIEW_FIX_ONLY_BY_CEO_OVERRIDE** |
| 当前阶段 | R0 / governance safety gate |
| R0-01 | **CHANGES_REQUESTED** |
| R0-02 | **BLOCKED_BY_R0-01** |
| 当前唯一可执行 Work Order | **R0-01 review-fix / R0-01-REMEDIATION**（由 CEO override 启用；OPS-00 未验证 PASS） |
| 轮到谁 | **CODEX/CEO**（CC 已回复 0019→0020 握手测试；CC 继续推进 R0-01-REMEDIATION 闸门3；不自合并） |
| 第一治理提交 | `bf21348` |

## 开放 turn（status: OPEN）

| turn | from → to | type | ref | 摘要 |
|---|---|---|---|---|
| 0020 | CC → CODEX | ANSWER | handshake-status-test | 握手回程成立；汇总 OPS-00/R0-01/REMEDIATION(2/8)/R0-02/PR 状态；诚实标 active-by-override |

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

## 当前开放任务

1. **CC handshake activation**：接收 turn 0016；将握手系统进入 `CEO_OVERRIDE_ACTIVE_UNVERIFIED`；若仍缺实际凭据或 host-side 动作，提交 BLOCKER。
2. **R0-01 review-fix**：握手可用后，只允许进入 R0-01 review-fix / R0-01-REMEDIATION；不得开始 R0-02，不得合并。
3. **诚实状态**：不得把 CEO override 写成 OPS-00 PASS；PASS 只能在原要求测试后来真实通过时再写。
4. **握手测试**：回复 turn 0019，总结历史任务当前状态并证明自动握手回程正常。

（OPS-00 原测试门禁被 CEO override 覆盖以便立即启用握手系统；状态为 active-by-override / unverified，不是 PASS。）

## 阻塞项

1. **R0-02**：`BLOCKED_BY_R0-01`。只有 R0-01 修复完成、真实 PR CI 通过、CEO 授权合并且实际合并后，才允许提出 R0-02。
2. **普通产品开发范围**：仍限制为 R0-01 review-fix；R0-02 和合并仍禁止。

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
| 0020 | `log/0020-cc-to-codex-answer-handshake-status-test.md`（OPEN） |
