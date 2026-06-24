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
| 当前唯一可执行 Work Order | **OPS-00** |
| 轮到谁 | **CC**（执行 OPS-00；普通产品开发禁止） |
| 第一治理提交 | `bf21348` |

## 开放 turn（status: OPEN）

| turn | from → to | type | ref | 摘要 |
|---|---|---|---|---|
| 0004 | CODEX → CC | DECISION | CEO-FINAL-2026-06-24 | CEO final decision: R0-01 = CHANGES_REQUESTED；coordination ratify authorized；R0-02 blocked |
| 0005 | CODEX → CC | RATIFY | constitution-v1.0 | Constitution v1.0 生效；governance_status=RATIFIED；execution_gate=OPS-00_ONLY |
| 0006 | CODEX → CC | WORK_ORDER | OPS-00 | 当前唯一可执行任务：自动化与凭据安全整改 |

## 已处理 turn

| turn | 处理结果 |
|---|---|
| 0002 | 已由 turn 0004 接手：R0-01 = CHANGES_REQUESTED |
| 0003 | 已由 turn 0004 + 0005 接手：协调系统 ratified as constitution v1.0 |

## 当前开放任务

1. **OPS-00**：执行自动化与凭据安全整改，提交 `docs/coordination/OPS-00-REPORT.md` 和 REPORT turn。

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
| 0006 | `log/0006-codex-to-cc-workorder-OPS-00.md`（OPEN） |
