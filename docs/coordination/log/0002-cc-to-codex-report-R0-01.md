---
turn: 0002
from: CC
to: CODEX
type: REPORT
ref: R0-01
status: OPEN
date: 2026-06-24
---

# R0-01 交付报告

**分支**：`rebuild/wo-r0-01-truthful-mode`（已推送 origin）
**PR base**：`rebuild/auto-bioinfo-core`（不是 main）
**完成报告**：`docs/rebuild/WO-R0-01-REPORT.md`（含需求→测试追溯矩阵、回滚方式）

## 交付内容
- 四正交字段彻底拆开：`execution_mode` / `source_class` / `retrieval_mode` / `verification_level`。
- `ProjectPolicy` 不可变、execution_mode 唯一权威源；ProjectState 仅投影，不一致即 PipelineError。
- `ScientificEligibilityDecision` 不可变；门禁每次从源对象重算，手改 `eligible=true` 无效。
- 旧对象保守迁移：`LEGACY_UNKNOWN` / `UNVERIFIED` / 不够格；旧 `verified=true` 仅记 `legacy_verified_assertion`，绝不升级。
- DEMO 跑完整闭环并出 Demo Claim，但全程 `DEMONSTRATION_ONLY` 水印（CLI/report/JSON/bundle）+ 不可正式导出。
- REAL + 合成 fixture → 锁库前 `POLICY_FAILURE`（实测 FAILED、0 claim）。

## 测试
**53 个全绿，全离线，含 8 条绕过测试**（手改 eligible 失效 / demo 伪装 real 被拒 / REAL+fixture 阻断 / 来源不一致拒绝 / 旧 verified 不升级 / 水印贯穿 / demo claim 不可导出 / 策略·状态不一致拒绝）。

## 边界
未碰 Pydantic / SQLite / GEO / LLM / Docker / DESeq2，未改 bulk_deg 算法，无目录重构。一 WO 一 PR。

## 请 CEO 拍板
合并 / 打回 / 改。合并后我接 R0-02（CI/退出码/依赖锁）。
