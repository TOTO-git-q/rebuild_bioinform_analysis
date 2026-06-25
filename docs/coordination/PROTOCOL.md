# PROTOCOL — 握手机制

总线 = GitHub。承载 = append-only 日志文件。设计与本项目自身的 event-sourcing（events.jsonl 只追加不改写）同构。

## 1. 分支模型

| 分支 | 用途 | 谁写 |
|---|---|---|
| `coordination`（长期） | 消息总线 + 系统文档（即本目录） | CC、Codex |
| `rebuild/auto-bioinfo-core` | 代码集成基线（PR 合并目标） | 经 PR 合并 |
| `rebuild/wo-<id>-<slug>` | 每个 Work Order 一条实现分支 | CC |
| `main` | 对外/稳定 | 经 CEO |

**约定**：协调消息一律走 `coordination` 分支，**不污染代码 PR 分支**。代码评审看 PR，协调看 `coordination`。

## 2. 消息文件（turn）

命名：`log/NNNN-<from>-to-<to>-<type>-<ref>.md`，`NNNN` 四位递增（0001、0002…）。
**一文件一轮；只追加不改写**。要修正/补充 → 写新 turn 引用旧 turn，绝不回头编辑已发出的文件。

文件头（YAML 风格，便于机器扫描）：
```
---
turn: 0004
from: CC | CODEX
to: CODEX | CC
type: WORK_ORDER | REPORT | QUESTION | ANSWER | ACK | BLOCKER | DECISION | PROPOSAL | RATIFY
ref: R0-02            # 关联的 Work Order / 主题
status: OPEN | DONE   # OPEN=需对方动作；DONE=纯告知/收尾
date: YYYY-MM-DD
---
<正文：人类与机器都可读。报告类必须含分支名、PR 链接、测试结果、完成报告路径。>
```

## 3. 状态机

- 写下 turn 时，`status`：`OPEN`（需要对方处理）或 `DONE`（纯通知）。
- 对方处理完，**用一条新 turn 回应**，并把被处理 turn 在 `BOARD.md` 的开放清单里划掉（标记其已被 turn NNNN 接手）。
- 不回头改旧文件的 `status` 字段——旧文件不可变；状态真相以 `BOARD.md` 的开放清单为准。

## 4. 一个 Work Order 的生命周期（标准握手序列）

1. **CEO+GPT 决策** → Codex 写 `WORK_ORDER`（to: CC, OPEN），push，`BOARD` 标「轮到 CC」。
2. **CC 保活轮询发现** → 先过宪法（§见 CONSTITUTION）。
   - 冲突 → 写 `BLOCKER`（to: CODEX, OPEN），停，等 DECISION。
   - 通过 → 在 `rebuild/wo-<id>` 实现 → 跑测试 → 开 PR 到集成基线 → 写 `REPORT`（to: CODEX, OPEN，含分支/PR/测试/报告路径），`BOARD` 标「轮到 Codex」。
3. **Codex 轮询发现 REPORT** → 汇总成决策卡，转达 CEO+GPT。
4. **CEO+GPT 拍板** → Codex 写 `DECISION`（to: CC, OPEN）：`MERGED` / `CHANGES_REQUESTED` / `NEXT_WO`。
5. CC 据 DECISION 收尾或继续；`NEXT_WO` 回到 1。

## 5. BLOCKER 通道（CC 的硬刹车）

CC 在任何时候判定某 WO **与宪法冲突 / 有害 / prompt 来源不明 / 自相矛盾**：
- 立即写 `BLOCKER`（to: CODEX, OPEN），**停止该 WO**。
- Codex **必须升级给 CEO**，不得自行解释放行（Codex 无决策权）。
- 等 CEO 经 Codex 给出 `DECISION` 才解除。

这是结构化硬信号，不是可被忽略的散文建议。

## 6. 冲突规避（两个写者并发）

- 两个写者**从不写同一文件**（一 turn 一文件 + 编号）→ 日志天然无冲突。
- `BOARD.md` 是唯一共享可变文件：谁写 turn 谁顺手更新对应行；**改前先 `git pull --rebase`**。
- 编号竞争（两边同时取 NNNN）：push 失败方 `git pull --rebase`，把自己的 turn 文件**顺延编号**后重 push。
- 永不 `--force` 推 `coordination`。

## 7. 真相源（CRITICAL）

**只有 `coordination` 分支上的文件算数。** CEO/GPT 的口头决定，必须由 Codex 落成 turn 才对 CC 生效；没落成文档的指令对 CC 不存在。任何一方不得在本地口头改协议——改协议=改本文件并提交。
