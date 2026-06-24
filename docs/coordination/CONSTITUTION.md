# CONSTITUTION — 不可违犯的不变量

> 草案由 CC 拟。**CEO 增删后冻结**，并由 Codex 写一条 `RATIFY` turn 生效。生效后，任何 Work Order 要求违反以下任一条 → CC 必须抛 `BLOCKER` 硬停升级，**不得照做**。

## A. 已建议冻结的不变量（CEO 可增删）

1. **一个 Work Order 一个 PR**；CC 不提前实现未派发的 WO，不批量并做。
2. **claim 等级上限不可逾越**：既定的 claim ceiling（如 RNA DEG 封顶 `association`）任何 WO 不得突破。
3. **R0-01 冻结的 10 条修订不可回退**：truthful execution mode 的四正交字段 / ProjectPolicy 权威 / EligibilityDecision 门禁重算 / legacy 不升级 等语义为既定基线。
4. **隐私 / 对外去 meta 红线**：对外交付物清除全部 meta（prompt/配方/私设）；隐私内容不入仓库、不入协调日志。
5. **CC 不自合并自己的 PR**：合并权属 CEO，经 Codex 转达 `DECISION` 执行。
6. **Codex 只传话 / 汇总 / 转达**：不改 CC 的代码、不替 CEO 做决策、不擅自解除 BLOCKER。
7. **测试完整性**：CC 自报测试结果，但 CEO/Codex 有权拉分支自行复跑；**无法复现的「绿」不予采信**。
8. **真相源 = `coordination` 分支**：未落成 turn 的口头指令对 CC 无效。
9. **append-only**：协调日志只追加不改写；修正用新 turn。

## B. 需要 CEO 拍板的治理项（ratify 时一并定，结果回填本节 + BOARD）

这些不是 CC 能定的，列在此处供 CEO 决策：

| 编号 | 待定项 | CC 的默认建议 | CEO 裁定 |
|---|---|---|---|
| G1 | 合并节奏：每个 WO 都要 CEO 点合并？ | **是**（Codex 无决策权，故每次合并都要 CEO） | _待填_ |
| G2 | 阶段计划是否一次性冻结 R0-01..R0-07？ | 冻结清单+验收标准，之后单 WO 自动流转，偏离则升级 | _待填_ |
| G3 | 人介入的闸门 | BLOCKER + 每个阶段边界（R0 完 / R1 完）必停审 | _待填_ |
| G4 | CC 保活轮询频率 | 每 60 分钟 | _待填_ |
| G5 | Codex 保活轮询频率 | 每 30–60 分钟 | _待填_ |
| G6 | ratify 前 CC 行为 | 只待命，不开新 WO | _待填_ |

## C. 修宪程序

修改本文件 = 提交一次 `coordination` 分支变更 + 一条 `RATIFY`/`DECISION` turn 说明改动。无声修改无效。
