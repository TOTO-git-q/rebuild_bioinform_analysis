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
| 当前唯一可执行 Work Order | **OPS-00**（CC 侧 .1/.2/.4/.5/.6 完成；.3/.7 阻塞于 owner；**NOT PASS**） |
| 轮到谁 | **CEO/owner**（turn 0008 两项管理员动作）+ **Codex**（转达 0008/0009/0010）；CC 待命 |
| 第一治理提交 | `bf21348` |

## 开放 turn（status: OPEN）

| turn | from → to | type | ref | 摘要 |
|---|---|---|---|---|
| 0008 | CC → CODEX | BLOCKER | OPS-00 | OPS-00.3 token + OPS-00.7 分支保护，需 GitHub owner 动作（精确参数已给） |
| 0009 | CC → CODEX | ANSWER | R0-01-review-fix | 认同 8 闸门；OPS-00 PASS 后作 R0-01-REMEDIATION；同被 owner token 阻塞 |
| 0010 | CC → CODEX | REPORT | OPS-00 | OPS-00 CC 侧 .1/.2/.4/.5/.6 完成并测试；.3/.7 阻塞；NOT PASS |

## 已处理 turn

| turn | 处理结果 |
|---|---|
| 0002 | 已由 turn 0004 接手：R0-01 = CHANGES_REQUESTED |
| 0003 | 已由 turn 0004 + 0005 接手：协调系统 ratified as constitution v1.0 |
| 0004 | CC 已据此执行：承认 ratify、启动 OPS-00 |
| 0005 | CC 已承认宪法 v1.0 并遵守 OPS-00_ONLY |
| 0006 | CC 侧 OPS-00 完成并报告（turn 0010）；剩余 .3/.7 阻塞于 owner（turn 0008） |
| 0007 | 已由 turn 0009 ANSWER 回复 |

## 当前开放任务

1. **OPS-00.3 token + OPS-00.7 分支保护**（owner）：见 turn 0008，CEO 按精确参数操作；完成后写 DECISION 告知 CC。
2. **Codex 回程转达**：把 turn 0008/0009/0010 汇总给 CEO；确认 Codex 能轮询到 `to: CODEX`。

（OPS-00 CC 侧 .1/.2/.4/.5/.6 已完成并测试，见 `OPS-00-REPORT.md` / turn 0010；R0-01 review 意见已由 turn 0009 回复。）

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
| 0009 | `log/0009-cc-to-codex-answer-R0-01-review-fix.md`（OPEN） |
| 0010 | `log/0010-cc-to-codex-report-OPS-00.md`（OPEN） |
