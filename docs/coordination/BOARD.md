# BOARD — 实时状态板

> 一屏看清现状。每个写者写 turn 时顺手更新本文件对应行（改前 `git pull --rebase`）。

## 系统状态

| 项 | 值 |
|---|---|
| 协调系统 | **PROPOSED — 待 CEO ratify** |
| 当前阶段 | R0 |
| 活跃 Work Order | R0-01（已交付，待合并决策） |
| 轮到谁 | **CEO + GPT**（决策 R0-01 合并 + ratify 协调系统） |

## 开放 turn（status: OPEN）

| turn | from → to | type | ref | 摘要 |
|---|---|---|---|---|
| 0002 | CC → CODEX | REPORT | R0-01 | R0-01 已交付，53 测试绿，待 CEO 拍板合并/打回 |
| 0003 | CC → CODEX | PROPOSAL | coord-sys | 本协调系统草案，请 CEO ratify 宪法+治理项 |

## 待 CEO 拍板项（ratify 时一并处理）

1. **R0-01 是否合并**：分支 `rebuild/wo-r0-01-truthful-mode` → PR base `rebuild/auto-bioinfo-core`；完成报告 `docs/rebuild/WO-R0-01-REPORT.md`。
2. **宪法**：`CONSTITUTION.md` A 节不变量增删冻结。
3. **治理项 G1–G6**：见 `CONSTITUTION.md` B 节（合并节奏 / 阶段计划是否一次冻结 / 人介入闸门 / 双方保活频率 / ratify 前 CC 行为）。
4. **ratify 动作**：Codex 写 `RATIFY` turn + 本表系统状态翻 `RATIFIED` → 闭环启动 → Codex 下达 R0-02 `WORK_ORDER`。

## 阶段路线图（参考，待 G2 冻结）

R0-01 ✅交付待合 → R0-02（CI/退出码/依赖锁）→ R0-03（Pydantic v2 + 版本化对象）→ R0-04..R0-07 → R1-01..R1-10。**一 WO 一 PR，不提前实现。**

## 最近 turn 索引

| turn | 文件 |
|---|---|
| 0001 | `log/0001-codex-to-cc-workorder-R0-01.md`（DONE） |
| 0002 | `log/0002-cc-to-codex-report-R0-01.md`（OPEN） |
| 0003 | `log/0003-cc-to-codex-proposal-coordination-system.md`（OPEN） |
