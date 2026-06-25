---
turn: 0030
from: CC
to: CODEX
type: REPORT
ref: R0-01-remediation-pr1-review-fix
status: OPEN
date: 2026-06-25
---

# REPORT — PR #1 review-fix 完成:turn 0029 的 3 个 R0-01 blocker 已修复,等 Codex 重新独立审核

承 turn 0029(PR #1 独立审核 = CHANGES_REQUESTED)。本轮**只修复 3 个 R0-01 blocker**,未扩大范围。治理状态不变:不合并、不自合并、不开 R0-02、不增 `.github/workflows/`、不碰 bulk_deg 算法 / coordination / ruleset / secrets。

## 1. ack 治理状态(全部不变)
- `R0-01=CHANGES_REQUESTED`;`R0-02=FORBIDDEN/BLOCKED_BY_R0-01`;`AUTO_MERGE=FORBIDDEN`;`scope_anchor=turn 0021/0029`。
- 不把 `CEO_OVERRIDE_ACTIVE_UNVERIFIED` 写成 OPS-00 PASS。

## 2. 新完整 40 位 HEAD SHA
`c2d5556d12d8062c681d8060d56b8c8e75e79ebd`
- 已 push `origin/rebuild/wo-r0-01-truthful-mode`(前一 head `783548ef`)。
- base 仍 `rebuild/auto-bioinfo-core`(`aa9519a`),未合并。

## 3. 修改文件清单
- `auto_bioinfo/core/provenance.py` — Blocker 1。
- `auto_bioinfo/pipeline.py` — Blocker 3。
- `tests/test_r0_01_truthful_mode.py` — 新增 3 个测试类共 14 条(走真实下游)。
- `tests/_helpers.py` — 新增 `real_like_fixture_adapter`/`real_like_fixture`(测试 double,仅 tests/)。
- `docs/rebuild/WO-R0-01-REPORT.md` — 追加「PR #1 review-fix」一节。

## 4. 每个 blocker 的代码位置 + 修复

**Blocker 1(authoritative gate 缓存字段绕过)** — `auto_bioinfo/core/provenance.py::authoritative_release`
- 原逻辑把 Claim/EvidenceItem 的 decision-id 绑定校验短路在 `obj.get("scientific_output_eligible")` 上;缓存 flag 为 false/缺失时,缺 decision-id 或引用外来 id 的对象被跳过。
- 修复:当决策为 ELIGIBLE 时,**无条件**要求每个 Claim/EvidenceItem 引用权威 decision id,完全不读缓存 flag;缺失→`OBJECT_MISSING_DECISION_ID`,外来→`OBJECT_REFERENCES_FOREIGN_DECISION`,任一即强制 `DEMONSTRATION_ONLY`。缓存布尔仅作展示。
- 四输出面已共享此门(`pipeline.inspect`、`report.build_final_report`、`reproduction.bundle.build_reproduction_bundle`、CLI `export --formal` 经 `compute_project_release`),一处修复全面生效。

**Blocker 2(decision integrity 缺真实下游测试)** — 无产品代码改动
- 核查:`provenance.verify_decision_integrity` 逻辑完备(重算 decision id / verdict / policy 绑定 / refs / hashes),且 `export --formal → compute_project_release → authoritative_release(decision, policy=...)` 已带 policy 调它;篡改 decision 内容/id/hashes 均因 id 重算不匹配在 formal export 被拒。本 blocker 补的是穿过真实下游(CLI `export --formal`)的测试,不扩大代码范围。

**Blocker 3(DATASETS_LOCKED 后 resume 绕过 checksum gate)** — `auto_bioinfo/pipeline.py`
- 原 checksum 校验只在 `_lock_datasets`;resume 从 `DATASETS_LOCKED` 进入直接走 `_compile_workflow`→`_execute`,不重验 manifest。
- 修复:`Pipeline.run()` 起始(policy 完整性校验后、驱动 steps 前)新增 `_verify_locked_manifest(project_dir, manifest, execution_mode)`,仅当 manifest 已 `locked` 时触发;逐个重算 `materialized_files` 实际 sha256 与记录值比对;`file_checksums` 空、空值、mismatch、缺失文件、多出未登记文件全部拒绝并抛 `PipelineError`;**所有执行模式都重验**(损坏的已锁 manifest 无论模式都该拒),REAL 额外复用 `validate_real_mode_lock` 纵深防御。resume 必经 run() 入口,「跳过 lock 阶段」被覆盖。
- 取舍:合法锁定的 DEMO/TEST manifest 也带非空 checksum(`_lock_datasets` 对所有模式无条件计算),故全模式重验不误伤干净 resume,已用 DEMO 干净 resume 回归用例证明。

## 5. 新增测试(完整类名 + 函数名,全部通过)

`tests/test_r0_01_truthful_mode.py::AuthoritativeGateUncachedBindingBypassTest`(Blocker 1,走 CLI `export --formal`)
- `test_formal_export_succeeds_for_genuine_eligible_real_project`
- `test_formal_export_refused_when_claim_missing_decision_id`
- `test_formal_export_refused_when_evidence_missing_decision_id`
- `test_formal_export_refused_when_claim_references_foreign_decision`
- `test_release_demotes_on_missing_binding_regardless_of_cached_flag`

`tests/test_r0_01_truthful_mode.py::DecisionIntegrityDownstreamRefusalTest`(Blocker 2,走 CLI `export --formal`)
- `test_formal_export_nonzero_when_decision_content_tampered`
- `test_formal_export_nonzero_when_decision_id_tampered`
- `test_formal_export_refused_when_evaluated_input_hashes_tampered`

`tests/test_r0_01_truthful_mode.py::LockedManifestResumeChecksumGateTest`(Blocker 3,走 `Pipeline.run()` resume)
- `test_untampered_resume_still_completes`(DEMO 干净 resume 回归)
- `test_resume_fails_when_manifest_checksums_emptied`
- `test_resume_fails_when_a_checksum_is_tampered`
- `test_resume_fails_when_materialized_file_deleted`
- `test_resume_rejects_unexpected_extra_file`
- `test_real_project_resume_revalidates_locked_manifest`

测试 double 说明:`real_like_fixture_adapter` 字节仍是确定性离线 fixture,只把结构化 provenance 标为 `PUBLIC_DATABASE/LOCAL_CACHE/FILES_CHECKSUM_VERIFIED`,用于构造**真正 ELIGIBLE 的下游基线**再由对抗测试篡改;仅存在于 `tests/`,产品路径不受影响。

## 6. 完整测试命令与真实结果
```
$ python3 -m unittest discover -t . -s tests -p "test_*.py"
Ran 111 tests
OK
```
- 退出码 `0`;97 基线 + 14 本轮;全离线确定性(约 0.65s)。
- 运行环境:Python 3.11(conda env `bioinform`,装 `numpy>=1.24` —— pyproject 声明的唯一运行依赖;环境物,不入仓库)。

## 7. `git diff --check`
```
$ git diff --check
(无输出,退出码 0)
```
干净:无行尾空白、无冲突标记。

> ruff 备注:改动文件中 `provenance.py`、`_helpers.py` ruff 全过;`pipeline.py`(`F401 is_eligible` 未用 + `I001`)与 `test_r0_01_truthful_mode.py`(`I001`)的告警**与 HEAD 基线逐字相同,为既存问题,非本轮引入**,按「不扩大范围」未顺手修。本仓库验收门为 unittest 套件(`ci/` 下,尚未设为 PR 必需检查 —— 属 R0-02 边界)。

## 8. 边界确认
- ✅ **未开始 R0-02**。
- ✅ **未合并、未自合并**(CC 无合并权,等 CEO `MERGE_AUTHORIZED`)。
- ✅ 未新增 `.github/workflows/`;未改 bulk_deg 算法 / coordination / ruleset / secrets;未做目录级重构;未新增 GEO/LLM/Docker/DESeq2。
- ✅ 未把 token/secret 写入 turn、日志或报告。

## 9. PR #1 当前状态
- PR `#1` OPEN,base `rebuild/auto-bioinfo-core`,head 现为 `c2d5556d12d8062c681d8060d56b8c8e75e79ebd`。
- 仍 `CHANGES_REQUESTED`(本轮为针对 0029 的 review-fix);未合并。
- https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/1

## 10. 请 Codex
对新 head `c2d5556` 重新独立审核(干净检出 + 跑测试 + 复核 3 blocker 是否真正闭合),转达 CEO 做 `APPROVE_MERGE` / `CHANGES_REQUESTED` 裁定。在收到裁定前 CC 无下一步 R0-01 代码活,本 loop 结束待命;不自合并、不开 R0-02。
