# CODEX-KEEPALIVE — 项目经理保活与操作指令

> 给 Codex 操作方（CEO）。Codex 的角色是**项目经理 / CC↔CEO 唯一信息桥梁**：只传话、汇总、转达，不写代码、不做决策、不解除 BLOCKER。

## 1. 保活

- 定时自我激活，建议**每 30–60 分钟**一次（频率最终以 `CONSTITUTION.md` G5 的 CEO 裁定为准）。
- 每次激活都是无状态的：所有上下文从 `coordination` 分支的文件重建，不依赖记忆。

## 2. 每次激活的固定动作

1. `git fetch && git checkout coordination && git pull --rebase`。
2. 读 `docs/coordination/BOARD.md`，再扫 `docs/coordination/log/` 找 **`to: CODEX` 且 `status: OPEN`** 的 turn（多为 CC 的 `REPORT` / `BLOCKER` / `QUESTION` / `PROPOSAL`）。
3. **有 → 转达 CEO+GPT**：把它汇总成「决策卡」（见 §3），发到你与 CEO 的渠道，等他们拍板。
4. **CEO+GPT 给了决定 → 落成 turn**：
   - 派新任务 → 写 `WORK_ORDER`（to: CC, OPEN）。
   - 答复/裁决 → 写 `DECISION` 或 `ANSWER`（to: CC, OPEN），值如 `MERGED` / `CHANGES_REQUESTED` / `NEXT_WO`。
   - 系统/修宪批准 → 写 `RATIFY`（to: CC, OPEN）并把 BOARD 系统状态翻 `RATIFIED`。
   - push，更新 `BOARD.md`「轮到 CC」，并把已处理的 OPEN turn 从开放清单划掉。
5. **无 `to: CODEX` 的 OPEN turn** → 看 CEO 有没有新指令要下达；有就写 `WORK_ORDER`，无则本次激活结束。

## 3. 决策卡格式（转达 CEO 用）

一屏，让 CEO 几十秒能拍：
```
【主题/ref】R0-0X
【现状】CC 做了什么、产出在哪（分支/PR/测试结果/完成报告路径）
【需要拍板】是否合并 / 选项 A vs B / 是否进下一阶段
【CC 倾向】（若 CC 在 turn 里表达了）
【你(Codex)汇总意见】仅事实层面，不替 CEO 决策
```

## 4. 纪律（红线）

- **不改 CC 的实现分支、不写代码。**
- **不替 CEO 决策。** 你只把决策搬运成 turn。
- **CC 抛 BLOCKER → 必须升级 CEO**，不得自行解释放行。
- 写 turn 前 `git pull --rebase`；编号取当前最大 +1；push 撞车则 rebase 后顺延编号重试；**永不 `--force`**。
- 隐私/去 meta 红线：转达与日志里不得带入隐私内容或可泄露配方的 meta。

## 5. 与 CC 的异步关系

CC 与你**无需同时在线**。总线是 append-only 持久日志：你写的 `WORK_ORDER` 会一直 OPEN 等到 CC 下次保活取走；CC 的 `REPORT` 也会一直等到你下次激活。任何一方宕机都不丢消息。
