# 协调闭环系统（Coordination Loop）

本目录是 `rebuild_bioinform_analysis` 项目的**自动协作总线**。它让「实现方 CC」与「项目经理 Codex」通过 GitHub 文档异步对话，把 CEO 的决策一路传到代码、再把成果一路传回 CEO，全程留痕、可审计、可断点续。

> 这套系统由 CC 草拟。**它本身尚未生效，等 CEO ratify**（见 `BOARD.md` 的系统状态）。在 ratify 前 CC 只待命，不自动开新工作。

## 1. 角色（5 个）

| 角色 | 是谁 | 职责 | 是否碰 git 总线 |
|---|---|---|---|
| **股东** | KAMIA | 启动项目并提供 CC 运行环境，之后不过问 | 否 |
| **CEO** | 朋友 | **全部拍板决策**：方向、合并、是否继续 | 经 Codex 间接 |
| **军师** | GPT Pro（网页） | 辅助 CEO 制定方案与决策 | 经 Codex 间接 |
| **项目经理** | Codex | **CC↔CEO 之间唯一信息桥梁**：传话、汇总、转达，定时保活 | **是（写者）** |
| **项目主管** | CC（Claude Code） | **干全部代码活**，产出 PR + 报告，定时保活 | **是（写者）** |

**总线上只有两个自动写者：CC 与 Codex。** CEO/GPT 坐在 Codex 身后，决策经 Codex 落成文档才对 CC 生效。

## 2. 指令流（一个闭环）

```
GPT Pro + CEO 决策
        │  (Codex 落成 WORK_ORDER / DECISION turn)
        ▼
     Codex ──转达──▶ CC 干活、开 PR、写 REPORT
        ▲                         │
        └────── Codex 汇总 ◀───────┘
        │  (汇报给 CEO+GPT)
        ▼
GPT Pro + CEO 拍板 → 下一轮
```

## 3. 文件索引

| 文件 | 作用 | 谁该读 |
|---|---|---|
| `README.md` | 本文件：角色 + 流程 + 索引 | 所有人入口 |
| `PROTOCOL.md` | 握手机制：分支模型、turn 格式、状态机、冲突规避 | CC + Codex |
| `BOARD.md` | 实时状态板（一屏）：系统状态、当前 WO、轮到谁、待拍板项 | 所有人，每次激活先读 |
| `CONSTITUTION.md` | 不可违犯的不变量（草案，待 CEO ratify/增删） | CEO 拍板，CC/Codex 遵守 |
| `CODEX-KEEPALIVE.md` | Codex 的保活与操作指令 | Codex 操作方（CEO） |
| `CC-KEEPALIVE.md` | CC 的保活方案与机制 | CC 自身 + 审阅者 |
| `log/NNNN-*.md` | append-only 对话日志，一轮一文件，只追加不改写 | CC + Codex |

## 4. 给 CEO 的最短上手路径

1. 读本文件 + `BOARD.md`（30 秒看清现状）。
2. 读 `CONSTITUTION.md`，对不变量增删后冻结。
3. 处理 `BOARD.md`「待 CEO 拍板项」列表（含 R0-01 合并、保活频率、阶段计划是否一次冻结）。
4. 让 Codex 写一条 `RATIFY` turn 并把 `BOARD.md` 系统状态翻成 `RATIFIED` → 闭环正式启动。
