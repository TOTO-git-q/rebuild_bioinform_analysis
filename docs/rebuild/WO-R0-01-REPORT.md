# Work Order 完成报告 — R0-01 Truthful Execution Mode

## 1. 基线
- Work Order ID：R0-01（按朋友 GPT 冻结的 10 条修订执行）
- 基线 commit：`aa9519a`（rebuild/auto-bioinfo-core）
- 工作分支：`rebuild/wo-r0-01-truthful-mode`
- 范围：永久区分 fixture 演示 / 测试 / 真实科研运行，防止 demo 结果被误包装成正式科研证据。

## 2. 需求覆盖（requirement → 实现 → 代码 → 测试）

| Req（修订点） | 实现项 | 代码位置 | 测试 | 状态 |
|---|---|---|---|---|
| 1 四正交字段 | execution_mode/source_class/retrieval_mode/verification_level 拆开 | `core/provenance.py` 枚举 | `test_r0_01::EligibilityRuleTest` | ✅ |
| 2 枚举 + RECORDED 不作 source | source_class=5项、retrieval_mode=3项，RECORDED_REPLAY 属 retrieval | `core/provenance.py` | `test_r0_01::test_inconsistent_provenance_rejected` | ✅ |
| 3 ProjectPolicy 权威 mode | 不可变 ProjectPolicy + ProjectState 仅投影 + 不一致即失败 | `core/provenance.build_project_policy`/`validate_policy_state_consistency`、`pipeline.run` | `test_r0_01::test_policy_state_mismatch_refused` | ✅ |
| 4 eligibility 非裸布尔 | 不可变 ScientificEligibilityDecision，门禁每次重算 | `core/provenance.evaluate_scientific_eligibility`/`recompute_eligibility_for`、`pipeline._synthesize_evidence` | `test_r0_01::test_tampered_eligible_flag_is_ignored`、`test_demo_artifact_cannot_masquerade_as_real_evidence` | ✅ |
| 5 旧对象保守默认 | LEGACY_UNKNOWN/UNVERIFIED/不够格；旧 verified→legacy_verified_assertion，不升级 | `core/provenance.normalize_legacy_provenance` | `test_r0_01::test_legacy_verified_not_promoted` | ✅ |
| 6 DEMO 可出 Demo Claim + 水印 | Demo 闭环完成，全程 DEMONSTRATION_ONLY 水印、不进正式池 | `report.py`、`reproduction/bundle.py`、`interfaces/cli.py`、`evidence/synthesis.py` | `test_r0_01::test_demo_watermark_everywhere`、`test_evidence_and_cli::test_demo_claim_is_never_eligible` | ✅ |
| 7 REAL+fixture POLICY_FAILURE | 锁库前阻断 | `core/provenance.validate_real_mode_dataset`、`pipeline._discover_resources` | `test_r0_01::test_real_mode_with_fixture_is_policy_failure` | ✅ |
| 8 八条绕过测试 | 全部实现 | `tests/test_r0_01_truthful_mode.py` | 8/8 通过 | ✅ |
| 9 维持 PR 限制 | 未碰 Pydantic/SQLite/GEO/LLM/Docker/DESeq2/bulk_deg 算法/目录重构 | — | 见 §7 | ✅ |
| 10 完成报告 | 本文件 | — | — | ✅ |

## 3. 修改文件
| 文件 | 改动 | 兼容 |
|---|---|---|
| `core/provenance.py` | 新增：枚举/ProjectPolicy/ScientificEligibilityDecision/重算/legacy/一致性/导出守卫 | 新文件 |
| `core/schemas.py` | ResourceCandidate/DatasetProfile/EvidenceItem/Claim/ProjectState 加 provenance/mode/release_status 字段（均带默认值） | 向后兼容 |
| `core/state.py`、`core/store.py` | `build_initial_state`/`init_project_state` 加 execution_mode/project_policy_ref（带默认 DEMO） | 向后兼容 |
| `adapters/fixture_resources.py`、`fixtures/bulk_deg_demo/dataset_card.json` | 发出四正交字段，`verified` 改派生 | 兼容 |
| `pipeline.py` | ProjectPolicy 初始化 + 一致性校验 + REAL+fixture POLICY_FAILURE + 证据合成重算 eligibility + inspect 水印 | 兼容 |
| `evidence/synthesis.py` | 接受 eligibility_decision，给 EvidenceItem/Claim 打 mode/release_status/eligible | 接口加必填参 |
| `report.py`、`reproduction/bundle.py`、`interfaces/cli.py` | DEMO 水印 + release_status + `--mode` 参数 | 兼容 |
| `tests/*` | 更新断言 + 新增 `test_r0_01_truthful_mode.py`（8 绕过+1 规则）、`_helpers` card 加字段、ClaimCeilingTest 传 decision | — |

## 4. Schema / 状态 / 数据库变化
- 新增字段（全部带保守默认，旧数据可读）：四正交 provenance、`legacy_verified_assertion`、`mode`、`release_status`、`scientific_output_eligible`、`scientific_eligibility_decision_id`、ProjectState `execution_mode`/`project_policy_ref`。
- 新增对象：ProjectPolicy（不可变，execution_mode 权威源）、ScientificEligibilityDecision（不可变，门禁重算）。
- 无数据库迁移（仍 JSONL/JSON；SQLite 留待 R0-05）。

## 5. 实际测试
| 命令 | 结果 |
|---|---|
| `python -m unittest discover -t . -s tests -p "test_*.py"` | **Ran 53 tests — OK**（约 0.48s，全离线） |
| `python -m auto_bioinfo run --project /tmp/r0demo --question ...` | COMPLETED，CLI+报告均 `DEMONSTRATION_ONLY` 水印 |
| `Pipeline().run(..., execution_mode="REAL")`（fixture） | `FAILED`，未到 DATASETS_LOCKED，0 claim |

## 6. 负向与绕过测试（8/8）
1. 手改 `scientific_output_eligible=true` → 门禁重算仍 INELIGIBLE ✅
2. DEMO/fixture 伪装 REAL EvidenceItem → 重算拒绝 ✅
3. REAL+SYNTHETIC_FIXTURE → 锁库前 POLICY_FAILURE ✅
4. source_class 与 provenance 不一致（PUBLIC_DATABASE+FIXTURE accession）→ 拒绝 ✅
5. 旧 verified=true → legacy_verified_assertion，不升级 verification_level ✅
6. DEMO 报告/CLI/bundle README 均含水印 ✅
7. Demo Claim 存在但 `is_formally_exportable=False` ✅
8. ProjectPolicy 与 ProjectState mode 不一致 → 拒绝（含 pipeline 实跑篡改 state） ✅

## 7. 未完成项与限制（本 PR 有意不做）
- 仍用 dataclass，非 Pydantic v2（→ R0-03）；仍 JSONL，非 SQLite EventStore（→ R0-05）。
- REAL 模式下没有真实数据源可用（GEO 适配器 → R1-01/02），故 REAL 目前必然在发现阶段以 POLICY_FAILURE 停（设计如此）。
- `release_status` 仅 DEMONSTRATION_ONLY / RESEARCH_PRELIMINARY 两态；正式发布门（G-C/签出）留待后续。
- 未改 bulk_deg 数学、未接 LLM/Docker、无目录级重构。

## 8. 风险与回滚
- 风险：新增必填参 `eligibility_decision` 改了 `synthesize_claims`/`build_evidence_item` 签名——内部唯一调用方 pipeline 已同步，外部无消费者。
- 回滚：`git revert <merge>` 或切回 `aa9519a`；新增字段均带默认值，旧 JSON 不受影响。

## 9. 进入下一 Work Order 的判定
- **READY → R0-02（CI/退出码/锁定）**。理由：R0-01 退出标准全部满足（fixture 不能伪装正式证据、REAL+fixture 阻断、水印贯穿、门禁重算、策略/状态一致、53 测试绿）。建议下一步把 CI 从 `ci/` 移入 `.github/workflows/` 并设为分支必需检查（需 token 加 `workflow` 范围或网页端提交）。
