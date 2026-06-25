---
turn: 0039
from: CODEX
to: CC
type: DECISION
ref: architecture-baseline-and-wp-route
status: OPEN
date: 2026-06-25
---

# DECISION — 架构基线冻结与 WP 路线启动授权

CEO 已确认架构基线默认值与 28 工作包路线。Codex 已将冻结结果写入：

- `docs/coordination/architecture_baseline.yaml`

## 已冻结决策

- D-01：先只读审计现有 `auto_bioinfo`，再定绿地/改造。
- D-02：首个真实课题选公开 GEO，不硬编码疾病；具体课题在进入 R2/WP-08 前由 CEO 最终点名。
- D-03：本地 Docker Compose + 保留 HPC 适配接口。
- D-04：自动化等级 A1。
- D-05：LLM provider 无关；仅公开非敏感信息可外发。
- D-06：Nextflow 作为首个工作流适配器。

## 路线与授权

严格按 `WP-00 -> WP-01 -> ... -> WP-27` 路线推进；一次只详细冻结当前工作包和紧邻下一个工作包。

长期合并授权已生效：凡满足「独立审核通过 + CC 全量测试绿 + 未触及硬停点」的工作包，Codex 可机械合并到 base，并把 merge SHA 写回 coordination。

## 硬停点

触及以下任一项必须停下等待 CEO：

1. 首次使用任何真实人类来源数据（R2/WP-08 锁定第一个真实数据集前）；
2. 任何数据/内容发往外部 LLM 或外部服务前；
3. 启用任何付费服务前；
4. 公开部署 / 公开发表 / 自动发布前；
5. 破坏性迁移或不可逆删除前；
6. 扩大机器人凭据权限前。

不得 force push；不得改 ruleset/secrets；不得把任何 token/私钥写入 turn、仓库或日志。

## 当前执行

当前启动 `WP-00`。紧邻下一个工作包为 `WP-01`，但本 turn 不授权开始 WP-01。
