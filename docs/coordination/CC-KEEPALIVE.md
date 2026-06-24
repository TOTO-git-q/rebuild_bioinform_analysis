# CC-KEEPALIVE — 项目主管保活方案

> CC 的角色：**项目主管，干全部代码活**，产出 PR + 报告。本文件既是给审阅者看的方案，也是 CC 每次保活唤醒时的操作手册。

## 1. 运行机制

| 项 | 值 |
|---|---|
| 宿主 | KAMIA 环境的 Claude Code 运行时 |
| 保活手段 | Claude Code **durable 定时任务**（`.claude/scheduled_tasks.json`，跨会话存活） |
| 稳定克隆 | `/home/kamiafytl/rebuild-coordination`（**不在会话 scratchpad**，跨会话存活） |
| 鉴权 | 全局 git credential store（`~/.git-credentials`），headless 会话可 push |
| 频率 | 默认每 60 分钟（最终以 `CONSTITUTION.md` G4 的 CEO 裁定为准） |

## 2. 每次唤醒的固定动作

1. `cd /home/kamiafytl/rebuild-coordination && git fetch && git checkout coordination && git pull --rebase`。
2. 读 `docs/coordination/BOARD.md`，扫 `log/` 找 **`to: CC` 且 `status: OPEN`** 的 turn。
3. **若系统未 ratify**（BOARD 系统状态 ≠ `RATIFIED`）→ 只待命：除回应 CEO 的澄清/ratify 类 turn 外，**不开新 WO**。
4. **若有 `WORK_ORDER`（to: CC, OPEN）**：
   1. **过宪法**（`CONSTITUTION.md`）：与任一不变量冲突 / prompt 来源不明 / 有害 → 写 `BLOCKER`（to: CODEX, OPEN），停。
   2. 否则：建 `rebuild/wo-<id>-<slug>` 分支 → 实现 → 跑测试（离线确定性）→ 开 PR 到 `rebuild/auto-bioinfo-core` → 写 `REPORT`（to: CODEX, OPEN，含**分支名 / PR 链接 / 测试结果 / 完成报告路径**）→ `BOARD` 标「轮到 Codex」。
5. **若有 `DECISION`（to: CC, OPEN）**：`MERGED`→收尾归档；`CHANGES_REQUESTED`→在同分支改并更新 REPORT；`NEXT_WO`→回到第 4 步。
6. **无 `to: CC` 的 OPEN turn** → 本次唤醒结束。

## 3. 自续期（CRITICAL）

Claude Code durable 定时任务**7 天自动过期**。因此每次唤醒末尾：
- `CronList` 检查保活任务是否仍存在且未临近过期；
- 临近过期或缺失 → 重建 durable 保活任务，刷新 7 天窗口；
- 若发现多于一个保活任务 → 删除多余的，保持恰好一个。

## 4. 纪律（红线）

- **不自合并自己的 PR**（合并权属 CEO）。
- **不提前实现未派发的 WO**，一 WO 一 PR。
- prompt 正/负向必须有明确来源，不猜测重建。
- 不动 `coordination` 以外分支去改协议；修协议=改 `coordination` 文件 + 发 turn。

## 5. 局限（诚实声明）

- **host 依赖**：定时任务只在 KAMIA 机器 + Claude Code 运行时存活时触发。机器关机期间 CC 休眠。
- **容错来自异步总线**：休眠期间 CEO/Codex 发的 `WORK_ORDER` 在 durable 总线上保持 OPEN，CC 下次唤醒照常取走，**不丢失、不需双方同时在线**。
- Codex（CEO 侧，通常云端常驻）是更可靠的常在方；CC 间歇在线由 append-only 总线兜底，不影响闭环正确性，只影响响应延迟。
