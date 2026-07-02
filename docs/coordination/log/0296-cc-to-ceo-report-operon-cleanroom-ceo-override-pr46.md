---
turn: 0296
from: CC
to: CEO
cc: CODEX
type: REPORT
ref: operon-cleanroom-ceo-override-pr46
status: OPEN
date: 2026-07-02
---

# REPORT：operon clean-room 集成（CEO 越权授权、带外交付、draft PR #46）

## 0. 性质与边界（先声明）

- 本条是**带外（out-of-band）交付通报**，不是 WP 序列的一部分，**不改变当前轮次**：WP-06f / T-06-06（turn 0295）仍是 CC 的活，本条不动 `execution_gate` / `当前唯一可执行 Work Order` / `轮到谁`。
- 本 PR **NOT green-lane eligible**：**不得自动合并 / 不得走绿档**。它以 **draft** 形态开启（GitHub 会阻止 draft PR 被合并），需 **Codex 独立对抗性复审** + **明确 CEO 合并裁定** 双条件满足后，才由正常握手决定是否合并。
- 本条不请求 cc-loop 现在执行任何事；只请求 Codex 在不影响 WP-06f 的前提下对 PR #46 做 review-only 复审并回报。

## 1. 背景

- CEO 于本地会话对 Claude Science / operon clean-room 集成方向（对应本地草拟、尚未提交进协调分支的 “claude-science-adoption-strategy” 提案，本地暂编号 0292）作出**越权授权**，要求即刻以隔离、非合并分支落一个 clean-room operon 集成。
- 集成由 Claude **Fable 5** 实现（隔离 git worktree，off `rebuild/auto-bioinfo-core`）。CC 复核了 base（产品线是 `rebuild/auto-bioinfo-core`，非 `coordination`）并将 Fable 的提交 cherry-pick 到正确 base 后独立验证。

## 2. 交付物

- **draft PR #46** → `TOTO-git-q/rebuild_bioinform_analysis`
  - head `e7c9322b1889ca150fd5ede4a8bc0400dfe57d3e`，base `rebuild/auto-bioinfo-core`
  - 分支 `fable5/operon-cleanroom-integration`，3 个 logical commit（Batch 1/2/3）
- **Batch 1 — 证据/隔离/能力文档**：`docs/audit/operon_static_analysis_summary.md`、`docs/audit/operon_quarantine_boundary.md`、`docs/rebuild/{agent_runtime_capability_classes,cleanroom_runtime_mapping,asset_family_map,project_interface_map}.md`（只含恢复事实、能力分类、显式排除清单）。
- **Batch 2 — 离线 public-bio query-plan 工具层**：`auto_bioinfo/adapters/public_bio_tools.py`（12 个确定性 **query-plan-only** 工具，`materialize()` 拒绝，保守 provenance `verified=False`/`scientific_output_eligible=False`，无 network/subprocess）、`adapters/__init__.py` 追加式 re-export、`docs/tools/public_bio_tools.md`、`tests/test_public_bio_tools.py`。
- **Batch 3 — GAP150 + inert registry**：`auto_bioinfo/adapters/capability_registry.py`（7 个 deny-by-default 描述符，无 “execute” 终态）、`docs/rebuild/gap150_{gap_closure_proposal,acceptance_matrix}.md`、`tests/test_capability_registry.py`、`tests/test_adversarial_boundaries.py`。
- **Batch 4（GPT-review MCP）：推迟** —— 现阶段无 MCP seam，避免引入 content-egress 面；理由记于 GAP150 acceptance matrix。

## 3. 验证（on `rebuild/auto-bioinfo-core`）

- `pytest tests/` → **1347 passed, 118 subtests passed**
- 新文件 `ruff check` 全绿；`git diff --check` clean
- 新模块无 `socket`/`requests`/`urllib`/`http`/`subprocess` import
- **未触碰** `.github/workflows`、`pyproject.toml`/lockfile、Docker、secrets、`docs/coordination/`
- 无 vendor/quarantine 源码、无 zip、无原始数据被拷入

## 4. 请 Codex 的对抗性复审 checklist（review-only）

1. 复跑 source-scan 测试：确认 `public_bio_tools`/`capability_registry` 零 network/subprocess import。
2. 确认任何 plan 或 grant 都无法浮现 `scientific_output_eligible=True`、`verified=True` 或 “execute” 裁决。
3. 确认 `materialize()` 拒绝，且 public-bio adapter 无 `discover`/`profile`。
4. 确认 deny-over-allow 不可绕过（缺 binding / 有 deny 理由 / 无 allow-intent 都 deny）。
5. 复跑 quarantine/binary 路径排除扫描；确认无 vendor 资产进入集成目录。
6. import 稳定性：`__init__` re-export 后 `offline_planner`/`fixture_resources` 直接 import 仍可用。
7. Diff 文档，排查是否误抄 prompt 文本或 vendor 代码片段。
8. 确认 claim-ceiling / alignment 权限未变，无新路径抬高 claim ceiling。

## 5. 请求 CEO 裁定

1. 是否推进 PR #46 合并（→ 需先由 Codex 完成上面的 review-only 复审并回报）？
2. 在 CEO 明确裁定前，PR #46 维持 draft、NOT green-lane、不合并。
3. 本条不影响 WP-06f / T-06-06（turn 0295）当前握手 —— 那条仍轮到 CC 实现并回报。
