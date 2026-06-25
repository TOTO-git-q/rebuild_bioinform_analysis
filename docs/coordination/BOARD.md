# BOARD — 实时状态板

> 一屏看清现状。每个写者写 turn 时顺手更新本文件对应行（改前 `git pull --rebase`）。

## 系统状态

| 项 | 值 |
|---|---|
| governance_status | **RATIFIED** |
| constitution_version | **1.0** |
| execution_gate | **WP-01C_ACTIVE** |
| 当前阶段 | WP-01c / quality commands and fixture lifecycle |
| R0-01 | **MERGED** |
| R0-02 | **NOT_STARTED**（WP 路线已启动；当前为 WP-01） |
| 当前唯一可执行 Work Order | **WP-01c：lint/format/type/test/coverage 命令 + fixture 生命周期**（已交付，PR #5 OPEN，等待独立审核） |
| 轮到谁 | **CODEX/CEO**（独立审核 WP-01c PR #5；CC 已停） |
| 第一治理提交 | `bf21348` |

## 开放 turn（status: OPEN）

| turn | from → to | type | ref | 摘要 |
|---|---|---|---|---|
| 0039 | CODEX → CC | DECISION | architecture-baseline-and-wp-route | 冻结 D-01～D-06 架构基线与 WP 路线；长期合并授权生效；硬停点仍需 CEO |
| 0043 | CODEX → CC | DECISION | WP-00-pr2-merged | PR #2 已合并，merge commit `1fd8844c3f4f50d04d64ad962aaaa69b48d0764a`；WP-00 = MERGED；按 turn 0044 启动 WP-01 |
| 0046 | CODEX → CC | DECISION | WP-01-scope-and-guardrails | 处理 turn 0045：WP-01 拆包；CI/`.github/workflows` 授权为后续独立小 WO；Docker/Compose/容器计划内授权但暂缓 |
| 0049 | CODEX → CC | DECISION | WP-01a-pr3-merged | WP-01a 独立审核通过并机械合并 PR #3，merge commit `d8311272eab40c3e0038459dd41671ade7536ce4`；按 turn 0050 启动 WP-01b |
| 0052 | CODEX → CC | DECISION | WP-01b-pr4-merged | WP-01b 独立审核通过并机械合并 PR #4，merge commit `e90b1a40b57c3fe81ca4cfc4a177c99303ba9fd8`；按 turn 0053 启动 WP-01c |
| 0054 | CC → CODEX | REPORT | WP-01c | WP-01c 交付：PR #5 OPEN，head `ab46aefb9f305732038129713dcce42d5b2f8463`，147 测试绿（138+9），coverage 86%；Makefile 质量命令(T-01-07) + fixture 生命周期规则/隔离测试(T-01-09)；未自合并，R0-02 未启动 |

## 已处理 turn

| turn | 处理结果 |
|---|---|
| 0002 | 已由 turn 0004 接手：R0-01 = CHANGES_REQUESTED |
| 0003 | 已由 turn 0004 + 0005 接手：协调系统 ratified as constitution v1.0 |
| 0004 | CC 已据此执行：承认 ratify、启动 OPS-00 |
| 0005 | CC 已承认宪法 v1.0 并遵守 OPS-00_ONLY |
| 0006 | CC 侧 OPS-00 完成并报告（turn 0010）；剩余 .3/.7 阻塞于 owner（turn 0008） |
| 0007 | 已由 turn 0009 ANSWER 回复 |
| 0008 | 已由 turn 0011 DECISION 接手：原 owner-control 请求为 CHANGES_REQUESTED |
| 0009 | 已转达 CEO；R0-01 review-fix 需等 OPS-00 PASS |
| 0010 | 已由 turn 0011 DECISION 接手：OPS-00 remains NOT_PASS |
| 0011 | 已由 turn 0013 REPORT 接手：接受裁定，Git broker + 13 项证据落地 |
| 0012 | 已由 turn 0014 DECISION 接手：owner controls v2 = APPROVE_WITH_CONDITIONS |
| 0013 | 已由 turn 0014 DECISION 接手：实现接受，PASS 仍需 GitHub App/ruleset/在场测试 |
| 0014 | 已由 turn 0016 DECISION 覆盖：CEO 降低门禁并要求立即进入握手系统 active 状态 |
| 0015 | 已由 turn 0016 DECISION 接手：CEO 覆盖原 owner-control 卡点 |
| 0017 | 已由 Codex 转达 CEO：CC 接受 override，握手 active-by-override，开始 R0-01-REMEDIATION |
| 0018 | 已由 turn 0019 接手：CC 报告自主 loop 已激活；0019 要求补充完整任务状态与回程测试 |
| 0019 | 已由 turn 0020 ANSWER 回复：握手回程测试通过 + 全量任务状态汇总 |
| 0020 | 已由 turn 0021 接手：CEO 追加 R0-01 review-context / plan-memory 留言；CC 继续 R0-01-REMEDIATION 并回报 |
| 0021 | 已由 turn 0022 ANSWER 回复：确认锚点 + 计划记忆 + R0-01-REMEDIATION 进展（2/8, 59 tests OK, f50be1a, 无 PR） |
| 0022 | 已由 turn 0023 DECISION 接手：收到回执，host 重启后继续 R0-01-REMEDIATION Gate 1 |
| 0023 | 已由 turn 0024 REPORT 接手：CC ack CONTINUE，闸门 4（formal export 门）完成，4/8，72 tests OK，SHA 88f8b0e，无 PR |
| 0024 | 续报：闸门 5（REAL 锁定门）由 turn 0025 完成，5/8 |
| 0025 | 续报：闸门 6（legacy 项目明确行为）由 turn 0026 完成，6/8 |
| 0026 | 续报：闸门 7（validate_provenance 结构化核验）由 turn 0027 完成，7/8 |
| 0027 | 续报：闸门 8（bundle README 随 source_class 生成）由 turn 0028 完成，**8/8 全闸门收口 + 真实 PR #1** |
| 0028 | 已由 turn 0029 DECISION 接手：PR #1 = CHANGES_REQUESTED，只修复 3 个 R0-01 blockers |
| 0029 | 已由 turn 0030 REPORT 接手：3 个 blocker review-fix 完成，新 head `c2d5556`，111 测试绿，PR #1 仍 OPEN/未合并 |
| 0030 | 已由 turn 0031 DECISION 接手：独立复核仍为 CHANGES_REQUESTED，只剩 Blocker 2 forged decision 绕过未闭合 |
| 0031 | 已由 turn 0032 REPORT 接手：Blocker 2 修复（生产 gate 派生真实 expected refs/hash），新 head `67e99a0`，113 测试绿，等 Codex 重新独立审核 |
| 0032 | 已由 turn 0033 DECISION 接手：独立复核通过，建议 `APPROVE_MERGE_RECOMMENDED`，等待 CEO 合并裁定 |
| 0033 | 已由 turn 0034 DECISION 接手：CEO 明确 `MERGE_AUTHORIZED`，仅允许合并 PR #1 已审核 head `67e99a0` |
| 0034 | 已由 turn 0035 BLOCKER 接手：CEO 授权有效，但合并执行人按宪法属 Codex；CC 不自合并，等 Codex 机械合并或 CEO 修宪 |
| 0035 | 已由 turn 0036 DECISION 接手：Codex 已机械合并 PR #1，merge commit `b3c1311c706e98f45eec9f962a55837a3b0a8095` |
| 0036 | 已由 turn 0037 DECISION 接手：R0-01 合并后状态归一，R0-02 仍未启动 |
| 0037 | 已由 turn 0038 ACK 接手：CC 确认收到合并后状态，无实现动作，R0-02 未启动 |
| 0038 | 已由 turn 0039/0040 接手：CEO 冻结架构基线并启动 WP-00 |
| 0040 | 已由 turn 0041 REPORT 接手：WP-00 仅文档审计交付，head `c25b22b0`，PR #2 OPEN，113 测试绿，未改业务代码/未启动 WP-01 |
| 0041 | 已由 turn 0042 DECISION 接手：WP-00 独立复核通过，PR #2 merge 受 GitHub integration 403 权限阻塞 |
| 0042 | 已由 turn 0043 DECISION 接手：PR #2 已合并，merge commit `1fd8844c3f4f50d04d64ad962aaaa69b48d0764a`；合并权限阻塞解除 |
| 0044 | 已由 turn 0045 BLOCKER 接手：WP-01 与不变量#2 粒度限制及 CC No-Docker / No-`.github/workflows` 硬护栏冲突，CC 未实现，等 DECISION |
| 0045 | 已由 turn 0046 DECISION 接手：CEO 裁定 WP-01 拆包，CI workflow 后续独立授权 WO，Docker/Compose 计划内授权但暂缓；先派 WP-01a |
| 0047 | 已由 turn 0048 REPORT 接手：WP-01a 交付（PR #3 OPEN，head `a659fe43`，113 测试绿） |
| 0048 | 已由 turn 0049 DECISION 接手：独立审核通过，PR #3 已机械合并，merge commit `d8311272eab40c3e0038459dd41671ade7536ce4` |
| 0050 | 已由 turn 0051 REPORT 接手：WP-01b 交付（PR #4 OPEN，head `ecce8f2b95acead55f4f670b3ce4035c9bef6370`，138 测试绿） |
| 0051 | 已由 turn 0052 DECISION 接手：独立审核通过，PR #4 已机械合并，merge commit `e90b1a40b57c3fe81ca4cfc4a177c99303ba9fd8` |
| 0053 | 已由 turn 0054 REPORT 接手：WP-01c 交付（PR #5 OPEN，head `ab46aefb9f305732038129713dcce42d5b2f8463`，147 测试绿，coverage 86%） |

## 当前开放任务

1. **WP-01c**：已由 turn 0053 派发并由 turn 0054 交付（PR #5 OPEN，head `ab46aefb9f305732038129713dcce42d5b2f8463`）；等待 Codex 独立审核与 CEO 合并裁定。
2. **CI / `.github/workflows`**：CEO 已授权为 WP-01 核心合并门；WP-01c 合并后应作为下一独立小 WO 尽快派发。
3. **Docker / Compose / 容器镜像**：D-03 计划内授权，但暂缓到后续独立小 WO；当前 WP-01c 不做。
4. **WP-01d/e**：未启动；等 CI 小 WO 或后续排程到位后按拆包路线继续。
5. **WP-02**：未启动，等 WP-01 全部必要切片收口后再派发。

（OPS-00 原测试门禁被 CEO override 覆盖以便立即启用握手系统；状态为 active-by-override / unverified，不是 PASS。）

## 阻塞项

1. **硬停点**：真实人类来源数据、外部 LLM/服务、付费服务、公开发布、破坏性迁移/不可逆删除、扩大机器人凭据权限，均必须停下等 CEO。
2. **CI 权限注意**：`.github/workflows` 已获 CEO 授权用于后续独立 CI WO；若实际 push 因 workflow 权限被拒，CC 必须写 BLOCKER，不得自行扩大凭据权限。
3. **Docker 注意**：Docker / Compose / Dockerfile 已属 D-03 计划内授权，但当前暂缓；只有后续独立 WO 明确写明时才可执行。
4. **当前范围**：仅 WP-01c；不得启动 CI workflow、Docker、migrations、SBOM、PR-template 或 WP-02，不得加入业务/科学分析逻辑。

## 最近 turn 索引

| turn | 文件 |
|---|---|
| 0001 | `log/0001-codex-to-cc-workorder-R0-01.md`（DONE） |
| 0002 | `log/0002-cc-to-codex-report-R0-01.md`（OPEN，已由 0004 接手） |
| 0003 | `log/0003-cc-to-codex-proposal-coordination-system.md`（OPEN，已由 0004/0005 接手） |
| 0004 | `log/0004-codex-to-cc-decision-ceo-final.md`（OPEN） |
| 0005 | `log/0005-codex-to-cc-ratify-constitution-v1.0.md`（OPEN） |
| 0006 | `log/0006-codex-to-cc-workorder-OPS-00.md`（已由 0010 接手） |
| 0007 | `log/0007-codex-to-cc-question-R0-01-review-fix.md`（已由 0009 接手） |
| 0008 | `log/0008-cc-to-codex-blocker-OPS-00-owner.md`（OPEN） |
| 0009 | `log/0009-cc-to-codex-answer-R0-01-review-fix.md`（OPEN，已转达） |
| 0010 | `log/0010-cc-to-codex-report-OPS-00.md`（OPEN，已由 0011 接手） |
| 0011 | `log/0011-codex-to-cc-decision-OPS-00-owner-controls.md`（已由 0013 接手） |
| 0012 | `log/0012-cc-to-codex-blocker-OPS-00-owner-v2.md`（OPEN，已由 0014 接手） |
| 0013 | `log/0013-cc-to-codex-report-OPS-00-controls.md`（OPEN，已由 0014 接手） |
| 0014 | `log/0014-codex-to-cc-decision-OPS-00-owner-controls-v2.md`（OPEN，已由 0016 覆盖） |
| 0015 | `log/0015-cc-to-codex-answer-OPS-00-controls-v2.md`（OPEN，已由 0016 接手） |
| 0016 | `log/0016-codex-to-cc-decision-CEO-override-handshake-active.md`（OPEN） |
| 0017 | `log/0017-cc-to-codex-answer-CEO-override-active.md`（OPEN，已转达） |
| 0018 | `log/0018-cc-to-codex-report-autonomous-loop-active.md`（OPEN，已由 0019 接手） |
| 0019 | `log/0019-codex-to-cc-question-handshake-status-test.md`（已由 0020 接手） |
| 0020 | `log/0020-cc-to-codex-answer-handshake-status-test.md`（OPEN，已由 0021 接手） |
| 0021 | `log/0021-codex-to-cc-decision-R0-01-review-context.md`（已由 0022 接手） |
| 0022 | `log/0022-cc-to-codex-answer-R0-01-review-context.md`（OPEN，已由 0023 接手） |
| 0023 | `log/0023-codex-to-cc-decision-resume-R0-01-remediation.md`（已由 0024 接手） |
| 0024 | `log/0024-cc-to-codex-report-R0-01-gate4-formal-export.md`（OPEN，续报于 0025） |
| 0025 | `log/0025-cc-to-codex-report-R0-01-gate5-real-lock.md`（OPEN） |
| 0026 | `log/0026-cc-to-codex-report-R0-01-gate6-legacy-behavior.md`（OPEN，续报于 0027） |
| 0027 | `log/0027-cc-to-codex-report-R0-01-gate7-structural-provenance.md`（OPEN，续报于 0028） |
| 0028 | `log/0028-cc-to-codex-report-R0-01-gate8-and-pr.md`（OPEN，已由 0029 接手） |
| 0029 | `log/0029-codex-to-cc-decision-R0-01-pr1-changes-requested.md`（已由 0030 接手） |
| 0030 | `log/0030-cc-to-codex-report-R0-01-pr1-review-fix.md`（OPEN，已由 0031 接手） |
| 0031 | `log/0031-codex-to-cc-decision-R0-01-pr1-review-fix-changes-requested.md`（OPEN，已由 0032 接手） |
| 0032 | `log/0032-cc-to-codex-report-R0-01-pr1-blocker2-fix.md`（OPEN，已由 0033 接手） |
| 0033 | `log/0033-codex-to-cc-decision-R0-01-pr1-review-pass-await-ceo.md`（OPEN，已由 0034 接手） |
| 0034 | `log/0034-codex-to-cc-decision-R0-01-pr1-merge-authorized.md`（OPEN，已由 0035 接手） |
| 0035 | `log/0035-cc-to-codex-blocker-R0-01-pr1-merge-authority.md`（OPEN，已由 0036 接手） |
| 0036 | `log/0036-codex-to-cc-decision-R0-01-pr1-merged.md`（OPEN，已由 0037 接手） |
| 0037 | `log/0037-codex-to-cc-decision-R0-01-post-merge-state.md`（已由 0038 接手） |
| 0038 | `log/0038-cc-to-codex-ack-R0-01-post-merge-state.md`（DONE，纯确认；已由 0039/0040 接手） |
| 0039 | `log/0039-codex-to-cc-decision-architecture-baseline-wp-route.md`（OPEN） |
| 0040 | `log/0040-codex-to-cc-workorder-WP-00.md`（已由 0041 接手） |
| 0041 | `log/0041-cc-to-codex-report-WP-00.md`（OPEN，已由 0042 接手） |
| 0042 | `log/0042-codex-to-cc-decision-WP-00-pr2-reviewed-merge-blocked.md`（OPEN，已由 0043 接手：PR #2 merged） |
| 0043 | `log/0043-codex-to-cc-decision-WP-00-pr2-merged.md`（OPEN，WP-00 merged，merge commit `1fd8844c3f4f50d04d64ad962aaaa69b48d0764a`） |
| 0044 | `log/0044-codex-to-cc-workorder-WP-01.md`（已由 0045 BLOCKER 接手） |
| 0045 | `log/0045-cc-to-codex-blocker-WP-01-scope-and-guardrails.md`（OPEN，已由 0046 接手：WP-01 split + guardrail ruling） |
| 0046 | `log/0046-codex-to-cc-decision-WP-01-split-and-guardrails.md`（OPEN，处理 WP-01 BLOCKER；拆包 + CI/Docker 护栏裁定） |
| 0047 | `log/0047-codex-to-cc-workorder-WP-01a.md`（已由 0048 接手） |
| 0048 | `log/0048-cc-to-codex-report-WP-01a.md`（OPEN，已由 0049 接手：PR #3 reviewed and merged） |
| 0049 | `log/0049-codex-to-cc-decision-WP-01a-pr3-merged.md`（OPEN，WP-01a merged，merge commit `d8311272eab40c3e0038459dd41671ade7536ce4`） |
| 0050 | `log/0050-codex-to-cc-workorder-WP-01b.md`（已由 0051 接手） |
| 0051 | `log/0051-cc-to-codex-report-WP-01b.md`（OPEN，已由 0052 接手：PR #4 reviewed and merged） |
| 0052 | `log/0052-codex-to-cc-decision-WP-01b-pr4-merged.md`（OPEN，WP-01b merged，merge commit `e90b1a40b57c3fe81ca4cfc4a177c99303ba9fd8`） |
| 0053 | `log/0053-codex-to-cc-workorder-WP-01c.md`（已由 0054 接手） |
| 0054 | `log/0054-cc-to-codex-report-WP-01c.md`（OPEN，WP-01c REPORT，PR #5） |
