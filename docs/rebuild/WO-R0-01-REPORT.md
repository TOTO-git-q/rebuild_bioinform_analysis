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

---

# R0-01-REMEDIATION（CEO 复审反馈 turn 0007 的 8 闸门 + 9 绕过测试）

> 状态：进行中（CEO override turn 0016 启用，`execution_gate=R0-01_REVIEW_FIX_ONLY`）。逐项给绕过测试名 + 真实结果，测试数量不作为验收本身。**不自合并，等 CEO 验收。**

## 闸门进度

| # | 闸门（turn 0007） | 状态 | 绕过测试 / 代码 |
|---|---|---|---|
| 1 | 唯一 authoritative eligibility gate（inspect/report/bundle/CLI formal export 全部重核验，Claim 布尔仅作缓存展示） | **DONE（本步）** | `provenance.authoritative_release`；测试见下 |
| 2 | decision integrity validation（重算 decision id、核 policy_id/version、evaluated_input_refs、input hashes、Claim/EvidenceItem 引用的 decision_id） | **DONE（本步）** | `provenance.verify_decision_integrity` / `decision_is_authoritatively_eligible`；测试见下 |
| 3 | ProjectPolicy 完整性校验（content_hash/project_policy_id 重算、project_id 与 state 一致、execution_mode 合法、project_policy_ref 不缺、policy+state 同时篡改也检出） | **DONE（本步）** | `provenance.verify_project_policy_integrity`；测试见下 |
| 4 | demo export vs `export --formal`（不合格非零退出码且不产出正式导出物，不只告警） | **DONE（本步）** | `cli export --formal` / `bundle.build_reproduction_bundle(formal=True)`；测试见下 |
| 5 | REAL 锁定门补全（≥FILES_CHECKSUM_VERIFIED、checksum 非空且一致、RECORDED_REPLAY 不单独授权、Manifest 存四要素） | **DONE（本步）** | `provenance.validate_real_mode_lock` / `pipeline._lock_datasets`；测试见下 |
| 6 | legacy 项目明确行为（一次性迁移 DEMO+LEGACY_UNKNOWN+UNVERIFIED 或 MIGRATION_REQUIRED，不裸抛 PipelineError） | TODO | — |
| 7 | `validate_provenance` 真正结构化核验（不止 accession 前缀） | TODO | — |
| 8 | bundle README 随实际 source_class 生成文案（REAL 不得显示 committed fixture） | TODO | — |

## 本步（闸门 5）真实结果

需求（turn 0007 闸门 5）：REAL 锁定门补全。一个 REAL 运行只有在数据集**真正经过校验**时才允许锁定（`DATASETS_LOCKED`）：①`verification_level` 须 ≥ `FILES_CHECKSUM_VERIFIED`；②`file_checksums` 非空且与实际物化文件**逐一一致**；③`RECORDED_REPLAY` 检索模式**不得单独**授权 REAL 锁定；④锁定后的 `DatasetManifest` 须持久化四要素（source_class / retrieval_mode / verification_level / file_checksums）。

requirement → 代码 → 测试：
- `auto_bioinfo/core/provenance.py`
  - 新增纯函数 `validate_real_mode_lock(profile, execution_mode, *, file_checksums, recomputed_checksums=None)`：非 REAL 模式恒返回 `[]`（DEMO/TEST 锁定不变）；REAL 模式逐项核验上述①②③，并在给出 `recomputed_checksums`（实际物化文件重新计算的摘要）时核对每条记录 checksum 与真实文件一致、无缺失/多余文件。复用既有常量 `_MIN_VERIFICATION_FOR_LOCK = "FILES_CHECKSUM_VERIFIED"`（此前定义但未接线，本步落地）。
- `auto_bioinfo/pipeline.py::_lock_datasets`
  - 锁定前取 `execution_mode`，对每个物化文件用 `compute_file_sha256` **独立重算**摘要 `recomputed`，与记录 `checksums` 一并送入 `validate_real_mode_lock`；任一失败 → 写 `policy_failure`（`failure_class=POLICY_FAILURE`）+ 推进 `FAILED` 后 `return`（与 `_discover_resources` 的 POLICY_FAILURE 路径一致），**绝不以未验证数据锁定 REAL**。
  - 锁定 manifest 新增三字段 `source_class` / `retrieval_mode` / `verification_level`（连同既有 `file_checksums` 构成四要素），使锁定决策所依赖的 provenance 随产物落盘可审计。

关键安全属性：REAL 锁定是发现期 `validate_real_mode_dataset`（拒绝 SYNTHETIC_FIXTURE）之外的**锁定期纵深防御**——即便某条 REAL 候选绕过发现期检查到达锁定步，只要其 verification 不足、检索仅为录制回放、checksum 为空或与磁盘文件不符，锁定即以 POLICY_FAILURE 中止，流水线不会进入 `DATASETS_LOCKED`。（现行 fixture 适配器下 REAL 仍会在更早的发现期即 POLICY_FAILURE，本门为面向真实数据源接入后的前置保障。）

绕过测试（`tests/test_r0_01_truthful_mode.py::RealModeLockGateBypassTest`，7 条全过）：
1. `test_real_lock_requires_files_checksum_verified` — REAL + `verification_level=METADATA_VERIFIED` → 报 verification_level 不足 ✅
2. `test_real_lock_rejects_recorded_replay` — REAL + `retrieval_mode=RECORDED_REPLAY` → 拒绝（录制回放不单独授权）✅
3. `test_real_lock_requires_nonempty_checksums` — 空 `file_checksums` / checksum 为空串 → 拒绝 ✅
4. `test_real_lock_detects_checksum_mismatch` — 记录 checksum 与实际文件摘要不符 → 报 mismatch ✅
5. `test_real_lock_detects_missing_or_extra_file` — 记录有 checksum 但无对应文件 / 多出未记录的文件 → 双向拒绝 ✅
6. `test_genuine_real_lock_passes` — REAL + `FILES_CHECKSUM_VERIFIED` + `LIVE` + checksum 一致 → 通过（`[]`）✅
7. `test_demo_lock_unaffected_and_manifest_records_four_elements` — 非 REAL 门为 no-op；真实 DEMO 跑通后读 `dataset_manifest` 断言四要素（source_class/retrieval_mode/verification_level/file_checksums）齐备 ✅

全量：`python3 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 79 tests, OK**（72 基线 + 7 闸门5，全离线确定性，约 0.64s）。

> 闸门进度：已完成闸门 1、2、3、4、5 → **5/8**。下一步闸门 6：legacy 项目明确行为（一次性迁移为 DEMO+LEGACY_UNKNOWN+UNVERIFIED 或标记 MIGRATION_REQUIRED，而非裸抛 `PipelineError`）。

## 本步（闸门 4）真实结果

需求（turn 0021 §4）：正式区分 demo export 与 formal export。普通 demo bundle 仍可生成但始终带 `DEMONSTRATION_ONLY`；新增明确正式导出门 `export --formal`；不合格时**返回非零退出码且不得生成正式导出物**，不要只打印警告后返回成功。

requirement → 代码 → 测试：
- `auto_bioinfo/reproduction/bundle.py`
  - 新增 `compute_project_release(project_dir)`：不构建任何 bundle，仅经唯一 authoritative gate（持久化 `ScientificEligibilityDecision` + 活动 `ProjectPolicy` + claims/evidence）复算 release，供 CLI 在**写任何产物之前**做闸控。
  - 新增异常 `FormalExportRefused`：携带 release（含 `release_status` 与 `reasons`）。
  - `build_reproduction_bundle(project_dir, *, formal=False)`：当 `formal=True` 时先 `compute_project_release` 闸控，**不合格则在 rmtree/mkdir 之前抛 `FormalExportRefused`**——确保 demo 项目永不产出 formal 导出物（防御纵深）。manifest 增加 `export_type` 字段（`FORMAL` / `DEMONSTRATION`）。
- `auto_bioinfo/interfaces/cli.py`
  - `export` 子命令新增 `--formal` 开关。`export --formal` 捕获 `FormalExportRefused` → 打印 `❌ FORMAL EXPORT REFUSED …`（含原因）并 **`return 1`（非零）**，不产出任何 formal 产物；合格才构建并 `return 0`。
  - 不带 `--formal` 的 `export` 行为不变：始终生成带 `DEMONSTRATION_ONLY` 水印的 demo bundle。

关键安全属性：formal 闸控发生在任何文件写入之前；即便攻击者翻转 Claim/EvidenceItem 的缓存 `scientific_output_eligible` 布尔（闸门 1 已使其仅为展示缓存），`compute_project_release` 仍判 `DEMONSTRATION_ONLY`，formal 导出被拒、退出码非零、磁盘无 formal 产物。

绕过测试（`tests/test_r0_01_truthful_mode.py::FormalExportGateBypassTest`，3 条全过；其中第 1 条即 turn 0021 要求的「`export --formal` 对 Demo 返回非零且不生成正式导出物」）：
1. `test_formal_export_refused_for_demo_returns_nonzero_and_no_artifact` — DEMO 项目（先删去 run 写出的 demo bundle）`export --formal` → 退出码 1、打印 REFUSED、磁盘无 `reproduction_bundle/` ✅
2. `test_build_formal_bundle_raises_before_writing_for_demo` — 直接 `build_reproduction_bundle(formal=True)` 对 DEMO 抛 `FormalExportRefused`，且目录未被重建；`compute_project_release` 判不合格 ✅
3. `test_plain_export_still_emits_demonstration_bundle` — 不带 `--formal` 的 `export` 退出码 0、输出含 `DEMONSTRATION_ONLY`、manifest `export_type=DEMONSTRATION` 且不合格 ✅

全量：`python3 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 72 tests, OK**（69 基线 + 3 闸门4，全离线确定性，约 0.6s）。

> 闸门进度：已完成闸门 1、2、3、4 → **4/8**。下一步闸门 5：REAL 数据锁定门补全（≥`FILES_CHECKSUM_VERIFIED`、`file_checksums` 非空且与实际文件一致、`RECORDED_REPLAY` 不单独授权 REAL 锁定、`DatasetManifest` 须存 source_class/retrieval_mode/verification_level/输入校验值）。

## 本步（闸门 3）真实结果

代码：`auto_bioinfo/core/provenance.py::verify_project_policy_integrity(policy, state)`
- ProjectPolicy 视为**不可变对象**：不再只比对 policy/state 两个投影是否"一致"（旧 `validate_policy_state_consistency`），而是从 policy 自身载荷**重算完整性**：
  ①`_recompute_policy_content_hash` 按 `build_project_policy` 同一规范体重算 `content_hash` 并比对；
  ②`_recompute_policy_id` 按 (project_id, execution_mode, policy_version) 重算 `project_policy_id` 并比对；
  ③`execution_mode` 必须是合法枚举；
  ④`policy.project_id` 必须与 `ProjectState.project_id` 一致；
  ⑤`ProjectState.project_policy_ref` 不得缺失且须指向该 policy。
  末尾并入旧一致性检查（execution_mode 投影一致 + ref 指向），去重，使本门成为其严格超集。
- 关键安全属性：攻击者把 `execution_mode` 在 **policy 与 state 两个文件**同时改成 REAL、却无法重新派生 policy 的 hash/id（需项目自身哈希函数）→ content_hash + project_policy_id 双失配被抓。
- 接线：`pipeline.run` 启动/恢复时由 `verify_project_policy_integrity` 取代原 `validate_policy_state_consistency`，任一失配抛 `PipelineError`，绝不以 REAL 运行。

绕过测试（`tests/test_r0_01_truthful_mode.py::ProjectPolicyIntegrityBypassTest`，6 条全过）：
1. `test_untampered_policy_passes_integrity` — 合法 policy 完整性通过 ✅
2. `test_tampered_execution_mode_breaks_hash_and_id` — 仅改 policy.execution_mode（hash/id 未重算）→ content_hash + id 双失配 ✅
3. `test_both_policy_and_state_tampered_still_detected` — policy 与 state 同时改 REAL 并把 ref 指回旧 id → 仍因 hash/id 失配被检出（CEO 核心要求项）✅
4. `test_missing_policy_ref_is_rejected` — `project_policy_ref` 缺失 → 拒绝 ✅
5. `test_project_id_mismatch_is_rejected` — policy.project_id 与 state.project_id 不一致 → 拒绝 ✅
6. `test_pipeline_rejects_tampered_policy_on_resume` — 端到端：落盘后同时篡改 `project_policy.json` 与 `project_state.json` 的 mode，再 resume → `PipelineError`，不以 REAL 运行 ✅

全量：`python3 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 69 tests, OK**（63 基线 + 6 闸门3，全离线确定性）。

> 闸门进度：已完成闸门 1、2、3 → **3/8**。下一步闸门 4：正式区分 demo export 与 `export --formal`（不合格返回非零退出码且不产出正式导出物，不只打印警告）。

## 本步（闸门 2）真实结果

代码：`auto_bioinfo/core/provenance.py`
- 抽出单一裁定真值源 `_eligibility_reason_codes()`（fresh 评估与完整性复核共用，防止被篡改的 `decision` 字段与事实不一致）。
- 新增 `verify_decision_integrity(decision, *, policy, expected_input_refs, expected_input_hashes, referencing_decision_id)`：①用决策自身事实重算 decision id 并比对存储 id；②重算 verdict/reason_codes/release_status（verdict 不入 id 哈希，故翻转 verdict 在此被抓）；③核 policy_id/version；④核 evaluated_input_refs/hashes；⑤核 Claim/EvidenceItem 反向引用 id。
- 新增 `decision_is_authoritatively_eligible(...)`：完整性通过**且**重算 verdict=ELIGIBLE 才返回 True；从不信任缓存的 `scientific_output_eligible`。

绕过测试（`tests/test_r0_01_truthful_mode.py::DecisionIntegrityBypassTest`，6 条全过）：
1. `test_untampered_decision_passes_integrity` — 合法 REAL 决策完整性通过 ✅
2. `test_flipped_verdict_is_rejected` — 仅翻转 `decision`+`release_status`（id 不变）被 verdict 重算抓出，非授权 ✅
3. `test_tampered_fact_breaks_decision_id` — 改 source_class 不重算 id → id mismatch ✅
4. `test_tampered_decision_id_is_rejected` — 直接改 decision id → 拒绝 ✅
5. `test_policy_binding_mismatch_is_rejected` — decision 绑定的 policy_id/version 与 active policy 不符 → 拒绝 ✅
6. `test_wrong_back_reference_is_rejected` — Claim/EvidenceItem 引用的 decision_id 指向他者 → 拒绝 ✅

全量：`python -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 59 tests, OK**（53 基线 + 6 新增，全离线确定性）。

## 本步（闸门 1）真实结果

代码：单一权威资格门 `auto_bioinfo/core/provenance.py::authoritative_release(decision, *, policy, claims, evidence_items)`
- 释放资格只从**持久化的 `ScientificEligibilityDecision` + 活动 `ProjectPolicy`** 复算：①无决策 → `DEMONSTRATION_ONLY`（reason `NO_ELIGIBILITY_DECISION`）；②决策须过 `verify_decision_integrity`（闸门2，含 policy 绑定）**且** 重算 verdict=ELIGIBLE（`decision_is_authoritatively_eligible`）；③任何"自称合格"的 Claim/EvidenceItem 必须引用该权威 decision id，指向他者 → 强制 `DEMONSTRATION_ONLY`（reason `OBJECT_REFERENCES_FOREIGN_DECISION`）。
- **彻底不信任** Claim/EvidenceItem 上缓存的 `scientific_output_eligible`，仅作展示缓存。
- 四个输出面统一改走此门：`pipeline.inspect`、`report.build_final_report`、`reproduction.bundle.build_reproduction_bundle`（CLI `inspect`/`export`/`_print_summary` 经由前三者继承）。原先三处各自 `c.get("scientific_output_eligible")` 的弱判定全部移除。

绕过测试（`tests/test_r0_01_truthful_mode.py::AuthoritativeEligibilityGateBypassTest`，4 条全过）：
1. `test_tampered_claim_flag_does_not_release_inspect_report_bundle` — DEMO 项目落盘后把所有 Claim+EvidenceItem 的 `scientific_output_eligible` 篡改为 true，`inspect` / `report` / `bundle` 三面仍判 `DEMONSTRATION_ONLY` 且水印/banner 不变 ✅（核心 CEO 要求项）
2. `test_no_persisted_decision_is_demonstration_only` — 无持久化决策 → `DEMONSTRATION_ONLY` ✅
3. `test_claim_referencing_foreign_decision_forces_demo` — 决策本身合格，但 Claim 自称合格却引用他者 decision id → 强制 demo ✅
4. `test_authoritative_release_passes_for_genuine_eligible_decision` — 真实合格 REAL 决策 + Claim 正确引用 → 放行 `RESEARCH_PRELIMINARY` ✅

全量：`python3 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 63 tests, OK**（53 基线 + 6 闸门2 + 4 闸门1，全离线确定性）。

> 闸门进度更新为 **2/8 → 3/8**（闸门 1、2 完成）。下一步闸门 3：`ProjectPolicy` 完整性校验（content_hash/project_policy_id 重算、project_id 与 state 一致、execution_mode 合法、project_policy_ref 不缺、policy+state 同时篡改也检出）。
