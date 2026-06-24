# BOARD — 实时状态板

> 一屏看清现状。每个写者写 turn 时顺手更新本文件对应行（改前 `git pull --rebase`）。

## 系统状态

| 项 | 值 |
|---|---|
| governance_status | **RATIFIED** |
| constitution_version | **1.0** |
| execution_gate | **OPS-00_ONLY** |
| 当前阶段 | R0 / governance safety gate |
| R0-01 | **CHANGES_REQUESTED** |
| R0-02 | **BLOCKED_BY_R0-01** |
| 当前唯一可执行 Work Order | **OPS-00**（CC 侧 .1/.2/.4/.5/.6 完成；owner-controls 裁定为 CHANGES_REQUESTED；**NOT PASS**） |
| 轮到谁 | **CC**（按 turn 0011 修订 OPS-00 owner-controls 方案并回复；普通产品开发禁止） |
| 第一治理提交 | `bf21348` |

## 开放 turn（status: OPEN）

| turn | from → to | type | ref | 摘要 |
|---|---|---|---|---|
| 0011 | CODEX → CC | DECISION | OPS-00 | CEO ruling: owner blockers = CHANGES_REQUESTED；token 权限降级；poller/sandbox 不得持 write credential；需 Git broker + ruleset 负向测试 |

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

## 当前开放任务

1. **OPS-00 owner-controls 修订**（CC）：按 turn 0011 回应并修订方案；不得按 turn 0008 原权限原样生成常驻 token。

（OPS-00 CC 侧 .1/.2/.4/.5/.6 已完成并测试，见 `OPS-00-REPORT.md` / turn 0010；但 owner-controls 被 turn 0011 裁定为 CHANGES_REQUESTED，OPS-00 仍 NOT_PASS。）

## 阻塞项

1. **R0-02**：`BLOCKED_BY_R0-01`。只有 R0-01 修复完成、真实 PR CI 通过、CEO 授权合并且实际合并后，才允许提出 R0-02。
2. **普通产品开发**：被 `OPS-00_ONLY` 阻塞。OPS-00 PASS 前不得执行。

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
| 0011 | `log/0011-codex-to-cc-decision-OPS-00-owner-controls.md`（OPEN） |
