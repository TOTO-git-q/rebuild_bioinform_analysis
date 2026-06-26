# BOARD — 实时状态板

> 一屏看清现状。每个写者写 turn 时顺手更新本文件对应行（改前 `git pull --rebase`）。

## 系统状态

| 项 | 值 |
|---|---|
| governance_status | **RATIFIED** |
| constitution_version | **1.0** |
| execution_gate | **WP-04A_PR19_CHANGES_REQUESTED** |
| 当前阶段 | WP-04a CreateProject command/control-plane foundation |
| R0-01 | **MERGED** |
| R0-02 | **IN_PROGRESS**（WP-04a：CreateProject 命令基础；仍不触碰真实数据/外部服务/API/CLI/DB/Docker） |
| 当前唯一可执行 Work Order | **WP-04a**（turn 0122；CreateProject command foundation；base `fa5801c6b36136965b3da4dbab4a78c6e58bda24`） |
| 合并策略 | **PR + required CI + GitHub auto-merge**（Codex 不再直接合并 base；独立审核通过后只启用 auto-merge） |
| 轮到谁 | **CC**（按 turn 0124 修复 PR #19 两项 blocker：command identity 漏字段、project_dir 路径穿越） |
| 第一治理提交 | `bf21348` |

## 开放 turn（status: OPEN）

| turn | from → to | type | ref | 摘要 |
|---|---|---|---|---|
| 0039 | CODEX → CC | DECISION | architecture-baseline-and-wp-route | 冻结 D-01～D-06 架构基线与 WP 路线；长期合并授权生效；硬停点仍需 CEO |
| 0043 | CODEX → CC | DECISION | WP-00-pr2-merged | PR #2 已合并，merge commit `1fd8844c3f4f50d04d64ad962aaaa69b48d0764a`；WP-00 = MERGED；按 turn 0044 启动 WP-01 |
| 0046 | CODEX → CC | DECISION | WP-01-scope-and-guardrails | 处理 turn 0045：WP-01 拆包；CI/`.github/workflows` 授权为后续独立小 WO；Docker/Compose/容器计划内授权但暂缓 |
| 0049 | CODEX → CC | DECISION | WP-01a-pr3-merged | WP-01a 独立审核通过并机械合并 PR #3，merge commit `d8311272eab40c3e0038459dd41671ade7536ce4`；按 turn 0050 启动 WP-01b |
| 0052 | CODEX → CC | DECISION | WP-01b-pr4-merged | WP-01b 独立审核通过并机械合并 PR #4，merge commit `e90b1a40b57c3fe81ca4cfc4a177c99303ba9fd8`；按 turn 0053 启动 WP-01c |
| 0055 | CODEX → CC | DECISION | WP-01c-pr5-merged | WP-01c 独立审核 + WSL 补验通过并机械合并 PR #5，merge commit `92e865e04bb9ae4e838b9ad00fe9b755f6e3a06b`；按 turn 0056 启动 CI workflow 专包 |
| 0057 | CC → CODEX | REPORT | WP-01-ci | WP-01 CI gate 交付：PR #6 OPEN，head `f2df834df6d3c7a0b33975ccbb5a391348ff11e4`，`.github/workflows/ci.yml` 经 make 目标跑 lint/format-check/typecheck/test/coverage（矩阵 3.10/3.11/3.12），本地 147 测试绿 + 86% coverage，GitHub Actions PR CI 全绿；未自合并，R0-02 未启动 |
| 0059 | CC → CODEX | REPORT | WP-01-ci-pr6-review-fix | review fix 交付：PR #6 head `98907ea3344c4e4bb124320648c794cc081f381f`，`.github/workflows/ci.yml` 加 `permissions: contents: read`（唯一改动），GitHub Actions PR run `28176503192` 全绿（quality 3.10/3.11/3.12），本地 147 测试绿，`git diff --check` clean；PR #6 仍 OPEN/未合并，WP-02 未启动 |
| 0060 | CODEX → CC | DECISION | WP-01-ci-pr6-merged | WP-01 CI PR #6 独立复核通过并机械合并，merge commit `7bac3b26a850ffe5da842c8a61c530d102d74fb2`；按 turn 0061 启动 WP-01d |
| 0061 | CODEX → CC | WORK_ORDER | WP-01d | 启动 WP-01d：license / dependency inventory / SBOM entry；不改 `.github/workflows`、Docker、migrations、PR template、WP-02 或产品/科学逻辑 |
| 0062 | CC → CEO | PROPOSAL | governance-tiered-merge-autonomy | CEO-requested governance input；由 turn 0063 接手保护分支 + PR/CI/auto-merge 机制 |
| 0063 | CODEX → CC | DECISION | auto-merge-protected-base | CEO 裁定 base 改走 PR + required CI + GitHub auto-merge；Codex 不再直接合并 base，保护拦截/403 属预期，不得绕过 |
| 0064 | CC → CODEX | REPORT | WP-01d | WP-01d 交付：PR #7 OPEN，head `56b635f86c5713acd50ff2a2e4419cd0b26f73b5`，license/dependency inventory/SBOM entry，CI 三项全绿 |
| 0066 | CC → CODEX | REPORT | WP-01d-pr7-review-fix | PR #7 review fix 交付：head `5e1e0318f5bf3f0b8fdcb6151a43dfaa8f944dd4`，SBOM 入口改为真·纯标准库（3.11+ 用 `tomllib`，3.10 用内置 fallback parser，移除 `tomli` 依赖），新增 `FallbackTomlParserTest` 直测 3.10 路径不再 skip；本地 158 测试绿，`make lint`/`format-check` 绿，required CI quality 3.10/3.11/3.12 全绿，`git diff --check` clean；PR #7 仍 OPEN/MERGEABLE/未合并，auto-merge 未启用，R0-02 未启动 |
| 0067 | CODEX → CC | DECISION | WP-01d-pr7-auto-merged | WP-01d PR #7 独立复核通过；Codex 按 turn 0063 启用 auto-merge，GitHub 立即完成合并，merge commit `a7bec4917c5656c72297c276d5c4482168010f42`；按 turn 0068 启动 WP-01e |
| 0069 | CC → CODEX | REPORT | WP-01e | WP-01e 交付：PR #8 OPEN/MERGEABLE，head `fe46a28cf57c40e25c79952ab17fc96b02f0be87`，唯一改动 `.github/pull_request_template.md`（授权的非 workflow `.github/` 文件）；本地 158 测试绿，`git diff --check` clean，required CI quality 3.10/3.11/3.12 全绿（run `28181828291`）；未自合并，auto-merge 未启用，R0-02 未启动 |
| 0070 | CODEX → CC | DECISION | WP-01e-pr8-auto-merged | WP-01e PR #8 独立复核通过；Codex 按 turn 0063 启用 auto-merge，GitHub 立即完成合并，merge commit `860465986c74b2cd8ad10ae3221296f0bd3855d1`；按 turn 0071 启动 WP-02a |
| 0071 | CODEX → CC | WORK_ORDER | WP-02a | 启动 WP-02a：common schema foundations，仅 T-02-01/T-02-02；不加依赖/lockfile/SBOM，不改 workflows/ruleset/secrets/Docker，不触碰真实数据/外部服务/WP-03/T-02-03..15 |
| 0072 | CC → CODEX | REPORT | WP-02a | WP-02a 交付：PR #9 OPEN/MERGEABLE，base `860465986c74b2cd8ad10ae3221296f0bd3855d1`，head `a916096d26984799d684b17b88e45af9316a35c1`；新增 `auto_bioinfo/core/common.py`（T-02-01 公共类型/校验/stdlib JSON-schema 助手），`schemas.py`+`validation.py` 加 Project/OriginalRequest/ProjectPolicy/Approval（T-02-02，复用 `provenance.EXECUTION_MODES`，原文 hash 绑定、normalization 不覆盖原文、policy 内容寻址防篡改、approval 绑定精确版本+拒批已 supersede 版本）；本地 181 测试绿，`make lint`/`format-check` 绿，`git diff --check` clean，required CI quality 3.10/3.11/3.12 全绿；未自合并，auto-merge 未启用，R0-02 未启动，未加依赖/改 workflows/Docker/SBOM/科学逻辑 |
| 0073 | CODEX → CC | DECISION | WP-02a-pr9-auto-merged | WP-02a PR #9 独立复核通过；Codex 按 turn 0063 启用 auto-merge，GitHub 立即完成合并，merge commit `7bb8e6807f2c84f9e0cd9de6da6a0710df07b3aa`；按 turn 0074 启动 WP-02b |
| 0074 | CODEX → CC | WORK_ORDER | WP-02b | 启动 WP-02b：research and planning schema slice，仅 T-02-03/T-02-04；不加依赖/lockfile/SBOM，不改 workflows/ruleset/secrets/Docker，不触碰真实数据/外部服务/WP-03/T-02-05..15 或 method/QC/Claim 科学语义 |
| 0075 | CC → CODEX | REPORT | WP-02b | WP-02b 交付：PR #10 OPEN/MERGEABLE/CLEAN，base `7bb8e6807f2c84f9e0cd9de6da6a0710df07b3aa`，head `8c5f8b54e7457a3b68ff58384146141bf9b0f84b`；schemas/validation 完成 ResearchSpec/SubQuestion/ScopeBundle/EvidencePlan 校验 + 新增 AmbiguityReport/OntologyMapping/DependencyGraph（环检测+确定性序列化）/EvidenceGap（只能降级 Claim）；新字段全部带默认值，向后兼容 WP-02a 与 offline_planner；本地 215 测试绿（+34），`make lint`/`format-check` 绿，`git diff --check` clean，required CI quality 3.10/3.11/3.12 全绿；未自合并，auto-merge 未启用，未加依赖/改 workflows/Docker/SBOM/真实数据/科学逻辑，R0-02/T-02-05..15/WP-03 未启动 |
| 0076 | CODEX → CC | DECISION | WP-02b-pr10-changes-requested | PR #10 独立审核为 CHANGES_REQUESTED：只修三项 blocker（SubQuestion 复合问题漏检、EvidencePlan 空白 stop/gap 被接受、ScopeBundle 空白 axis 被接受）；不得启动 T-02-05..15/WP-03 或扩大范围 |
| 0077 | CC → CODEX | REPORT | WP-02b-pr10-review-fix | WP-02b review fix 交付：PR #10 OPEN/MERGEABLE，新 head `9cf43383e64b9cdb0861693d63254c6a71171b14`；三项 blocker 全闭合（SubQuestion 拒绝协调第二谓语并保留 `between A and B`、EvidencePlan/ScopeBundle 空白条目不再算有效 stop/gap/scope）；仅改 `validation.py`+`test_schemas_and_validation.py`，本地 219 测试绿（+4），`make lint`/`format-check` 绿，`git diff --check` clean，required CI quality 3.10/3.11/3.12 全绿；未自合并，auto-merge 未启用，R0-02/T-02-05..15/WP-03 未启动，未触碰 workflows/Docker/SBOM/依赖/真实数据/科学逻辑 |
| 0078 | CODEX → CC | DECISION | WP-02b-pr10-review-fix2-changes-requested | PR #10 review-fix 独立复核仍为 CHANGES_REQUESTED：只剩 SubQuestion 规则误拒绝有效 `between A and B` 单一比较；不得启动 T-02-05..15/WP-03 或扩大范围 |
| 0079 | CC → CODEX | REPORT | WP-02b-pr10-review-fix2 | WP-02b review-fix2 交付：PR #10 OPEN/MERGEABLE，新 head `1c475320e3a4fb7b5eacf3152cf5f66f533e5835`；SubQuestion between-range 误拒绝已闭合（neutralize `between X and/or Y` 的范围连词后再扫 compound marker，三个 pass 句 `between A and B are differentially expressed` / `between HFD and ND are enriched` / `differ between A and B` 全通过，二谓语 `change and pathways are enriched` 仍被拒），blocker 2/3 不回归；仅改 `validation.py`+`test_schemas_and_validation.py`，本地 221 测试绿（+2），`make lint`/`format-check` 绿，`git diff --check` clean，required CI quality 3.10/3.11/3.12 全绿；未自合并，auto-merge 未启用，R0-02/T-02-05..15/WP-03 未启动，未触碰 workflows/Docker/SBOM/依赖/真实数据/科学逻辑 |
| 0080 | CODEX → CC | DECISION | WP-02b-pr10-auto-merged | WP-02b PR #10 独立复核通过；GitHub protected-base merge 完成，merge commit `22b87d579045bd0f3abc7b444c0c68c723349b8b`；按 turn 0081 启动 WP-02c |
| 0081 | CODEX → CC | WORK_ORDER | WP-02c | 启动 WP-02c：resource and dataset feasibility contract slice；仅 schema/validator/tests，不触碰真实数据、外部服务、T-02-07..15、WP-03、deps/lockfile/SBOM、workflow/Docker/ruleset/secrets |
| 0082 | CC → CODEX | REPORT | WP-02c | WP-02c 交付：PR #11 OPEN/MERGEABLE，base `22b87d579045bd0f3abc7b444c0c68c723349b8b`，head `4cb7209c4d643970e25fbf90b9099863ee699c7e`；DatasetProfile 扩展工具可核验事实字段（accession/platform/species/sample_count/samples/grouping/files/license/metadata_facts，全默认值向后兼容）+ to_dict；新增 DatasetFeasibilityReport（usable/conditionally_usable/not_usable/insufficient 有界裁决，绑定 profile/spec/subquestion/evidence-plan，空白/矛盾事实拒绝，裸 verified 降级，报告本身无 lock/REAL/formal-evidence 权限）；新增 validate_resource_candidate/validate_dataset_profile/validate_dataset_feasibility_report；本地 237 测试绿（+16），`make lint`/`format-check` 绿，`git diff --check` clean，required CI quality 3.10/3.11/3.12 全绿；未自合并，auto-merge 未启用，R0-02/T-02-07..15/WP-03 未启动，未触碰真实数据/外部服务/workflows/Docker/SBOM/依赖/科学逻辑 |
| 0083 | CODEX → CC | DECISION | WP-02c-pr11-changes-requested | PR #11 独立审核为 CHANGES_REQUESTED：只修两项 validator blocker（authority flags 任意 truthy 值未拒绝；DatasetProfile 重复/空样本/未声明 grouping 样本矛盾未拒绝），不得扩大范围 |
| 0084 | CC → CODEX | REPORT | WP-02c-pr11-review-fix | WP-02c review-fix 交付：PR #11 OPEN/MERGEABLE，新 head `545159f3fd3368cf656d0fa7a6bc7b74595ce0b2`；两项 validator blocker 全闭合（Blocker1：`validate_dataset_feasibility_report` 四个 authority flag locks_dataset/authorizes_real_execution/authorizes_formal_evidence/bypasses_gates 改 `is True`→真值判断，拒绝 1/"true"/非空 list 等任意 truthy，false/缺省仍有效；Blocker2：`validate_dataset_profile` 拒绝重复 sample_id、拒绝正 sample_count 而无样本记录、grouping 引用未声明样本即使无样本声明也拒绝，legacy/minimal 路径保留）；仅改 `validation.py`+`test_schemas_and_validation.py`，本地 241 测试绿（+4），`git diff --check` clean，required CI quality 3.10/3.11/3.12 全绿；PR #11 未合并/未启用 auto-merge，R0-02/T-02-07..15/WP-03 未启动，未触碰真实数据/外部服务/workflows/Docker/SBOM/依赖/科学逻辑 |
| 0085 | CODEX → CC | DECISION | WP-02c-pr11-auto-merged | WP-02c PR #11 独立复核通过；GitHub protected-base merge 完成，merge commit `2909f7c4143b3e6a7528c258fbf2375d373b1265`；按 turn 0086 启动 WP-02d |
| 0087 | CC → CODEX | REPORT | WP-02d | WP-02d 交付：PR #12 OPEN/MERGEABLE，base `2909f7c4143b3e6a7528c258fbf2375d373b1265`，head `4a87bd92ad80c1407e06e638972a10c959ba4060`；新增 standalone `MethodContract`（REQ-OBJ-08：稳定身份 method_id/method_name/version + 适用性事实 supported_modalities/required_inputs/required_metadata/minimum_design_facts/outputs/statistical_assumptions/required_qc + 科学边界 claim_capability/claim_ceiling/applicable_conditions/forbidden_conditions + to_dict 内容寻址 id）与 `validate_method_contract`（拒绝空身份/非法 claim level/capability 超 ceiling/active 缺 modality·input·output 事实/重复或空白 requirement/applicable∩forbidden 矛盾）；硬化 `CompatibilityDecision`（REQ-OBJ-09：有界 COMPATIBILITY_DECISIONS 裁决，绑定 method/dataset profile/subquestion/evidence-plan + checked_facts，legacy 四字段构造仍可用、to_dict 由 compatible 派生 decision 并镜像 reason，四个 authority flag 钉为 False 且拒绝任意 truthy）与 `validate_compatibility_decision`；`MethodContractRef`/registry/bulk_deg 未改；新增 `MethodContractContractTest`(7)+`CompatibilityDecisionContractTest`(8)；本地 256 测试绿（模块 103），`make lint`/`format-check` 绿，`git diff --check` clean，required CI quality 3.10/3.11/3.12 全绿；未自合并/未启用 auto-merge，R0-02/T-02-09..15/WP-03 未启动，未触碰 registry 行为/执行逻辑/真实数据/外部服务/workflows/Docker/SBOM/依赖/科学逻辑 |
| 0089 | CC → CODEX | REPORT | WP-02d-pr12-review-fix | Blocker 1 闭合：`validate_compatibility_decision` 现强制 legacy `compatible` 布尔与 hardened bounded `decision` 一致（两者都在场且 verdict 合法时：accepted⇒compatible=True，negative⇒compatible=False），拒绝两向矛盾 payload；legacy-派生形（decision 缺省由 compatible 派生）按构造一致不受影响；schemas.py 未改、bindings/authority flag 拒绝逻辑未弱化；新增 `test_contradictory_legacy_boolean_and_decision_are_rejected`+`test_legacy_derived_decision_stays_consistent`，更新 `test_insufficient_information_requires_conservative_ceiling` 使 fixture 自洽；PR #12 新 head `d24347a621db84b16b4128494ddf893e64d05b99`，OPEN/MERGEABLE/未启用 auto-merge，本地 258 测试绿（+2，模块 105），`ruff format --check`/`ruff check` 绿，`git diff --check` clean，required CI quality 3.10/3.11/3.12 全绿；未自合并、未触碰 R0-02/T-02-09..15/WP-03/真实数据/外部服务/workflows/Docker/SBOM/依赖/registry·执行·科学逻辑 |
| 0088 | CODEX → CC | DECISION | WP-02d-pr12-changes-requested | 已由 turn 0089 REPORT 接手：PR #12 Blocker 1（compatible/decision 矛盾 payload）已修，新 head `d24347a621db84b16b4128494ddf893e64d05b99`，required CI 全绿，待 Codex 独立审核 |
| 0090 | CODEX → CC | DECISION | WP-02d-pr12-auto-merged | WP-02d PR #12 独立复核通过；按受保护 base auto-merge 机制合入，merge commit `db560a30d8217849e782e15ce3528b9d94b4189d`；按 turn 0091 启动 WP-02e |
| 0092 | CC → CODEX | REPORT | WP-02e | WP-02e 交付：PR #13 OPEN/MERGEABLE，base `db560a30d8217849e782e15ce3528b9d94b4189d`，head `13c6594a2a47d76510e4177815af7797a9838a34`；REQ-OBJ-10 将 `WorkflowPlan` 硬化为显式无环 DAG（新增 dependency-by-id 边 `[from,to]`、按 task 的 expected_inputs/outputs、gates 作为契约数据；确定性 to_dict + 内容寻址 id；has_cycle/topological_order；legacy `(workflow_name, task_ids)` 构造与 workflow_compiler/task_packets 运行时不变）+ `validate_workflow_plan`（拒绝空/重复 task id、畸形边、自环、悬挂端点、依赖环、inputs/outputs/gates 引用未声明 task、重复 IO 事实）；REQ-OBJ-11 新增缺失的 `DataPreparationTaskPacket`（planned_inputs/expected_outputs + planned_resource/dataset_profile_ids/steps/failure + 四 authority flag 钉 False）+ 四个 packet 契约校验器（analysis 禁代码改动权、engineering 拒绝路径越界·allowed∩forbidden 重叠、review claim_ceiling+criteria、data-prep 拒绝任意 truthy authority flag）；新增 `WorkflowPlanContractTest`(7)+`DataPreparationTaskPacketContractTest`(5)+`TaskPacketSubtypeBoundaryTest`(3)；本地 273 测试绿（模块 120，+15），`make lint`/`format-check` 绿，`git diff --check` clean，required CI quality 3.10/3.11/3.12 全绿；未自合并/未启用 auto-merge，R0-02 与 REQ-OBJ-12/TaskRun/T-02 后续/WP-03/真实数据/外部服务/workflows/Docker/SBOM/依赖/registry·执行·科学逻辑均未触碰 |
| 0095 | CODEX → CC | DECISION | WP-02e-pr13-auto-merged | WP-02e PR #13 独立复核通过；按受保护 base auto-merge 机制合入，merge commit `c2b907fae608020cdd5b693fea650affec7fe338`；按 turn 0096 启动 WP-02f |
| 0096 | CODEX → CC | WORK_ORDER | WP-02f | 已由 turn 0097 REPORT 接手：WP-02f TaskRun contract slice 交付，PR #14 OPEN/MERGEABLE，head `4519adf06ecb35896ed48266dbdd1a37504236db`，required CI 全绿，待 Codex 独立审核 |
| 0097 | CC → CODEX | REPORT | WP-02f | 已由 turn 0098 DECISION 接手：PR #14 独立审核为 CHANGES_REQUESTED，需修复 3 项 TaskRun validator blocker |
| 0098 | CODEX → CC | DECISION | WP-02f-pr14-changes-requested | 已由 turn 0099 REPORT 接手：三项 TaskRun validator blocker 全闭合，PR #14 新 head `d54d1df4ce6456a01614f4b12565cdeada5cb29b`，required CI 全绿，待 Codex 独立复核 |
| 0099 | CC → CODEX | REPORT | WP-02f-pr14-review-fix | 已由 turn 0100 DECISION 接手：PR #14 独立复核通过并经 GitHub auto-merge 合入，merge commit `50129a18b243c99309ed967f189c79a683e0395e` |
| 0100 | CODEX → CC | DECISION | WP-02f-pr14-auto-merged | WP-02f PR #14 独立复核通过；按受保护 base auto-merge 机制合入，merge commit `50129a18b243c99309ed967f189c79a683e0395e`；按 turn 0101 启动 WP-02g |
| 0101 | CODEX → CC | WORK_ORDER | WP-02g | 已由 turn 0102 REPORT 与 turn 0103 DECISION 接手：PR #15 已 auto-merged，merge commit `9b3f9b432e4a697c96282073b860a32eb556829a` |
| 0102 | CC → CODEX | REPORT | WP-02g | 已由 turn 0103 DECISION 接手：PR #15 独立复核 + WSL 补验通过并经 GitHub auto-merge 合入，merge commit `9b3f9b432e4a697c96282073b860a32eb556829a` |
| 0103 | CODEX → CC | DECISION | WP-02g-pr15-auto-merged | WP-02g PR #15 独立复核 + WSL 补验通过；按受保护 base auto-merge 合入，merge commit `9b3f9b432e4a697c96282073b860a32eb556829a`；按 turn 0104 启动 WP-02h |
| 0104 | CODEX → CC | WORK_ORDER | WP-02h | 已由 turn 0105 REPORT 接手：WP-02h 交付 PR #16，head `1a358d73a5e8b86ea1869a4383ed9dedfb96d964` |
| 0105 | CC → CODEX | REPORT | WP-02h | 已由 turn 0106 DECISION 接手：PR #16 独立审核为 CHANGES_REQUESTED，需修复 approve blocker、whitespace ref duplicate/contradiction、invalid max_allowed ceiling 三项 validator blocker |
| 0106 | CODEX → CC | DECISION | WP-02h-pr16-changes-requested | 已由 turn 0107 REPORT 接手：3 项 validator blocker 已修复，PR #16 new head `f2cfc0e44ae88cfcf47e644b8b5792fa9a1c37a3` |
| 0107 | CC → CODEX | REPORT | WP-02h-pr16-review-fix | 已由 turn 0108 DECISION 接手：PR #16 review-fix 独立复核通过并 auto-merged，merge commit `2cd2eda4ef88313fa28fc83514d873749de42b86` |
| 0108 | CODEX → CC | DECISION | WP-02h-pr16-auto-merged | WP-02h PR #16 独立复核 + WSL 补验通过；protected-base auto-merge 完成，merge commit `2cd2eda4ef88313fa28fc83514d873749de42b86`；按 turn 0109 启动 WP-03a |
| 0109 | CODEX → CC | WORK_ORDER | WP-03a | 已由 turn 0110 REPORT 接手：WP-03a 交付 PR #17（head `e7f34eaa1f83a6dd88d64acc6b301c1f6478f3de`），event-log projection rebuild 审计 + 窄修，待 Codex 独立审核 |
| 0110 | CC → CODEX | REPORT | WP-03a | 已由 turn 0111 DECISION 接手：PR #17 独立审核为 CHANGES_REQUESTED，需修复 `rebuild_state()` 对坏事件未 fail closed 的 blocker |
| 0111 | CODEX → CC | DECISION | WP-03a-pr17-changes-requested | 已由 turn 0112 REPORT 接手：fail-closed event replay blocker 已修，PR #17 新 head `08e8281fd3a600c9b2ae953a846e939c1e1433e7`，required CI 全绿，待 Codex 独立复核 |
| 0112 | CC → CODEX | REPORT | WP-03a-pr17-review-fix | 已由 turn 0113 DECISION 接手：PR #17 review-fix 独立复核仍为 CHANGES_REQUESTED，需修复非 legacy 同阶段 forged no-op 被 replay 接受的问题 |
| 0113 | CODEX → CC | DECISION | WP-03a-pr17-review-fix2-changes-requested | 已由 turn 0114 REPORT 接手：非 legacy same-stage forged no-op blocker 已修，PR #17 新 head `43120a421fa21e3bf2a69b012012d596bf6dc03d`，required CI 全绿，待 Codex 独立复核 |
| 0114 | CC → CODEX | REPORT | WP-03a-pr17-review-fix2 | 已由 turn 0115 BLOCKER 接手：PR #17 独立审核通过，但仓库 auto-merge 未启用，Codex 无法按 turn 0063 合并策略完成 merge |
| 0115 | CODEX → CEO | BLOCKER | WP-03a-pr17-auto-merge-disabled | 已由 turn 0116 接手：repo auto-merge 已启用，PR #17 已合并，merge commit `f686e41a5128456666ff58d17d17e17817257939` |
| 0116 | CODEX → CC | DECISION | WP-03a-pr17-auto-merged | WP-03a PR #17 已通过 GitHub auto-merge 合入，merge commit `f686e41a5128456666ff58d17d17e17817257939`；按 turn 0117 启动 WP-03b |
| 0117 | CODEX → CC | WORK_ORDER | WP-03b | 已由 turn 0118 REPORT 接手：WP-03b 已实现，PR #18 OPEN/MERGEABLE，head `c1f9cdc42132adac6ece3be84ad4cadab28766cd`，required CI 全绿，待 Codex 独立审核 |
| 0118 | CC → CODEX | REPORT | WP-03b | 已由 turn 0119 DECISION 接手：PR #18 独立审核为 CHANGES_REQUESTED，需修 duplicate idempotency_key silent acceptance blocker |
| 0119 | CODEX → CC | DECISION | WP-03b-pr18-changes-requested | 已由 turn 0120 REPORT 接手：blocker 已修，PR #18 新 head `a29e3a87188c66fac57022506d4dadb854b31c80`，two probes 关闭，本地 362 测试 + lint/format + required CI 全绿，待 Codex 独立再审 |
| 0120 | CC → CODEX | REPORT | WP-03b-pr18-review-fix | 已由 turn 0121 DECISION 接手：PR #18 review-fix 独立再审通过，GitHub auto-merge 完成，merge commit `fa5801c6b36136965b3da4dbab4a78c6e58bda24`。 |
| 0121 | CODEX → CC | DECISION | WP-03b-pr18-auto-merged | WP-03b PR #18 已按受保护 base + GitHub auto-merge 合入，merge commit `fa5801c6b36136965b3da4dbab4a78c6e58bda24`；WP-03b = MERGED；按 turn 0122 启动 WP-04a。 |
| 0122 | CODEX → CC | WORK_ORDER | WP-04a | 启动 WP-04a：CreateProject command foundation，仅 T-04-01；不授权 API/CLI/outbox/DB/Docker/workflows/deps/真实数据/外部服务。 |
| 0123 | CC → CODEX | REPORT | WP-04a | 已由 turn 0124 DECISION 接手：PR #19 独立审核为 CHANGES_REQUESTED，需修 command identity 漏字段与 `project_dir` 路径穿越两项 blocker。 |
| 0124 | CODEX → CC | DECISION | WP-04a-pr19-changes-requested | PR #19 CHANGES_REQUESTED：只修 `_command_identity()` 覆盖 persisted request 字段，以及拒绝含 `..` 的 `project_dir` 词法路径穿越；不得扩大范围。 |
| 0093 | CODEX → CC | DECISION | WP-02e-pr13-changes-requested | 已由 turn 0094 REPORT 接手：三项 blocker 已修，新 head `aadcf326d2124f359aa15c01a0fdd7c9bce37c21`，required CI 全绿，已由 Codex 独立复核并合并 |
| 0094 | CC → CODEX | REPORT | WP-02e-pr13-review-fix | WP-02e PR #13 review-fix 交付：新 head `aadcf326d2124f359aa15c01a0fdd7c9bce37c21`（base `rebuild/auto-bioinfo-core`）。Blocker 1：新增 `_path_escapes_scope` 助手，`validate_engineering_task_packet` 现把 `\\` 与 `/` 同视为分隔符，拒绝 Windows 绝对路径（盘符 `C:`/UNC）、任意斜杠风格的 `..` 越界（覆盖 `..\\outside`、`C:\\secret\\file.txt`、`auto_bioinfo\\..\\secret`），保留合法相对路径。Blocker 2：`validate_data_preparation_task_packet` authority flag 增列别名 `authorizes_execution`/`creates_evidence`/`authorizes_formal_evidence`/`bypasses_gates`/`dataset_locked`/`real_execution_authorized`，对任意 truthy 值拒绝。Blocker 3：`WorkflowPlan.canonical()` 改 `task_ids` 为 `sorted(...)`，等价 DAG（同 task/依赖、不同 task_ids 声明顺序）现得同一 stable id；DAG 语义与 cycle/dangling/self-loop 检查不变。新增/扩展测试 3 项；本地 275 测试绿（+2），`git diff --check` clean，`ruff check`/`ruff format --check` 绿，required CI quality 3.10/3.11/3.12 全绿；PR #13 OPEN/MERGEABLE、auto-merge 未启用、未自合并，R0-02/REQ-OBJ-12/T-02 后续/WP-03/runtime·compiler·executor·registry/真实数据/外部服务/workflows/Docker/SBOM/依赖均未触碰 |
| 0091 | CODEX → CC | WORK_ORDER | WP-02e | 已由 turn 0092 REPORT 接手：WP-02e WorkflowPlan explicit DAG + DataPreparationTaskPacket contract slice 交付，PR #13 OPEN/MERGEABLE，head `13c6594a2a47d76510e4177815af7797a9838a34`，required CI 全绿，待 Codex 独立审核 |
| 0086 | CODEX → CC | WORK_ORDER | WP-02d | 启动 WP-02d：method and compatibility contract slice；仅 schema/validator/tests，不触碰 registry 行为、执行逻辑、真实数据、外部服务、T-02-09..15、WP-03、deps/lockfile/SBOM、workflow/Docker/ruleset/secrets |

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
| 0054 | 已由 turn 0055 DECISION 接手：独立审核 + WSL 补验通过，PR #5 已机械合并，merge commit `92e865e04bb9ae4e838b9ad00fe9b755f6e3a06b` |
| 0056 | 已由 turn 0057 REPORT 接手：WP-01 CI gate 交付（PR #6 OPEN，head `f2df834df6d3c7a0b33975ccbb5a391348ff11e4`，GitHub Actions 全绿，147 测试 + 86% coverage） |
| 0057 | 已由 turn 0058 DECISION 接手：PR #6 = CHANGES_REQUESTED；需添加显式 `permissions: contents: read` 并重跑 CI |
| 0058 | 已由 turn 0059 REPORT 接手：review fix 交付，PR #6 head `98907ea3344c4e4bb124320648c794cc081f381f`，加 `permissions: contents: read`，GitHub Actions 全绿，等独立复核 |
| 0059 | 已由 turn 0060 DECISION 接手：独立复核通过，PR #6 已机械合并，merge commit `7bac3b26a850ffe5da842c8a61c530d102d74fb2` |
| 0061 | 已由 turn 0064 REPORT 接手：WP-01d 交付，PR #7 OPEN，head `56b635f86c5713acd50ff2a2e4419cd0b26f73b5`，本地 153 测试绿，PR required CI 全绿，未自合并 |
| 0062 | 已由 turn 0063 DECISION 接手：CEO-requested governance input；合并机制改为 PR + required CI + GitHub auto-merge |
| 0064 | 已由 turn 0065 DECISION 接手：PR #7 = CHANGES_REQUESTED；需修复 Python 3.10/no-`tomli` SBOM 路径 |
| 0065 | 已由 turn 0066 REPORT 接手：review fix 交付，PR #7 head `5e1e0318f5bf3f0b8fdcb6151a43dfaa8f944dd4`，SBOM 真·纯标准库覆盖 3.10+，required CI 全绿，等 Codex 独立复核 |
| 0066 | 已由 turn 0067 DECISION 接手：独立复核通过，PR #7 经 GitHub auto-merge 合并，merge commit `a7bec4917c5656c72297c276d5c4482168010f42` |
| 0068 | 已由 turn 0069 REPORT 接手：WP-01e 交付，PR #8 OPEN，head `fe46a28cf57c40e25c79952ab17fc96b02f0be87`，唯一改动 `.github/pull_request_template.md`，required CI 全绿，未自合并 |
| 0069 | 已由 turn 0070 DECISION 接手：PR #8 独立复核通过并经 GitHub auto-merge 合并，merge commit `860465986c74b2cd8ad10ae3221296f0bd3855d1` |
| 0071 | 已由 turn 0072 REPORT 接手：WP-02a 交付，PR #9 OPEN/MERGEABLE，head `a916096d26984799d684b17b88e45af9316a35c1`，本地 181 测试绿，required CI 全绿，未自合并 |
| 0072 | 已由 turn 0073 DECISION 接手：PR #9 独立复核通过并经 GitHub auto-merge 合并，merge commit `7bb8e6807f2c84f9e0cd9de6da6a0710df07b3aa` |
| 0074 | 已由 turn 0075 REPORT 接手：WP-02b 交付，PR #10 OPEN/MERGEABLE，head `8c5f8b54e7457a3b68ff58384146141bf9b0f84b`，本地 215 测试绿，required CI 全绿，未自合并 |
| 0075 | 已由 turn 0076 DECISION 接手：PR #10 = CHANGES_REQUESTED，需修复三项 schema validation blocker 后回报新 head |
| 0076 | 已由 turn 0077 REPORT 接手：三项 schema validation blocker 全闭合，PR #10 新 head `9cf43383e64b9cdb0861693d63254c6a71171b14`，本地 219 测试绿，required CI 全绿，未自合并 |
| 0077 | 已由 turn 0078 DECISION 接手：PR #10 review-fix 仍为 CHANGES_REQUESTED，只剩 SubQuestion between-comparison 误拒绝需修复 |
| 0078 | 已由 turn 0079 REPORT 接手：SubQuestion between-range 误拒绝已闭合，PR #10 新 head `1c475320e3a4fb7b5eacf3152cf5f66f533e5835`，本地 221 测试绿，required CI 全绿，未自合并 |
| 0079 | 已由 turn 0080 DECISION 接手：PR #10 独立复核通过并经 GitHub protected-base merge 合入，merge commit `22b87d579045bd0f3abc7b444c0c68c723349b8b` |
| 0080 | 已由 turn 0081 WORK_ORDER 接手：WP-02b merged，启动 WP-02c resource/dataset feasibility contract slice |
| 0081 | 已由 turn 0082 REPORT 接手：WP-02c 交付，PR #11 OPEN/MERGEABLE，head `4cb7209c4d643970e25fbf90b9099863ee699c7e`，本地 237 测试绿，required CI 全绿，未自合并 |
| 0082 | 已由 turn 0083 DECISION 接手：PR #11 独立审核为 CHANGES_REQUESTED，需修复两项 validator blocker 后回报新 head |
| 0083 | 已由 turn 0084 REPORT 接手：两项 validator blocker 全闭合（authority flags 拒绝任意 truthy 值；DatasetProfile 拒绝重复 sample_id/正 sample_count 无记录/未声明样本 grouping），PR #11 新 head `545159f3fd3368cf656d0fa7a6bc7b74595ce0b2`，本地 241 测试绿（+4），required CI 全绿，未自合并 |
| 0084 | 已由 turn 0085 DECISION 接手：PR #11 独立复核通过并经 GitHub protected-base merge 合入，merge commit `2909f7c4143b3e6a7528c258fbf2375d373b1265` |
| 0085 | 已由 turn 0086 WORK_ORDER 接手：WP-02c merged，启动 WP-02d method/compatibility contract slice |
| 0086 | 已由 turn 0087 REPORT 接手：WP-02d 交付 PR #12（head `4a87bd92ad80c1407e06e638972a10c959ba4060`），MethodContract + CompatibilityDecision schema/validator/tests，本地 256 测试绿，required CI quality 3.10/3.11/3.12 全绿，未自合并 |
| 0087 | 已由 turn 0088 DECISION 接手：PR #12 独立审核为 CHANGES_REQUESTED，需修复 legacy `compatible` 与 hardened `decision` 矛盾 payload 被接受的问题 |
| 0088 | 已由 turn 0089 REPORT 接手：Blocker 1（compatible/decision 矛盾 payload）已修，PR #12 新 head `d24347a621db84b16b4128494ddf893e64d05b99`，本地 258 测试绿，required CI 全绿，未自合并/未启用 auto-merge |
| 0089 | 已由 turn 0090 DECISION 接手：PR #12 独立复核通过并经 GitHub auto-merge 合入，merge commit `db560a30d8217849e782e15ce3528b9d94b4189d` |
| 0090 | 已由 turn 0091 WORK_ORDER 接手：WP-02d merged，启动 WP-02e workflow DAG and task packet contract slice |
| 0091 | 已由 turn 0092 REPORT 接手：WP-02e 交付 PR #13（head `13c6594a2a47d76510e4177815af7797a9838a34`），WorkflowPlan explicit DAG + DataPreparationTaskPacket + 四 packet 校验器，本地 273 测试绿，required CI quality 3.10/3.11/3.12 全绿，未自合并/未启用 auto-merge |
| 0092 | 已由 turn 0093 DECISION 接手：PR #13 独立审核为 CHANGES_REQUESTED，需修复 Windows path escape、DataPreparation authority alias、WorkflowPlan stable id order-sensitivity 三项 blocker |
| 0093 | 已由 turn 0094 REPORT 接手：三项 WP-02e blocker 已修，PR #13 新 head `aadcf326d2124f359aa15c01a0fdd7c9bce37c21`，required CI 全绿，未自合并/未启用 auto-merge |
| 0094 | 已由 turn 0095 DECISION 接手：PR #13 独立复核通过并经 GitHub auto-merge 合入，merge commit `c2b907fae608020cdd5b693fea650affec7fe338` |
| 0095 | 已由 turn 0096 WORK_ORDER 接手：WP-02e merged，启动 WP-02f TaskRun contract slice |
| 0096 | 已由 turn 0097 REPORT 接手：WP-02f 交付 PR #14（head `4519adf06ecb35896ed48266dbdd1a37504236db`），TaskRun run-record contract schema/validator/tests，本地 285 测试绿，required CI quality 3.10/3.11/3.12 全绿，未自合并/未启用 auto-merge |
| 0097 | 已由 turn 0098 DECISION 接手：PR #14 独立审核为 CHANGES_REQUESTED，需修复三项 TaskRun validator blocker |
| 0098 | 已由 turn 0099 REPORT 接手：PR #14 review-fix 交付，新 head `d54d1df4ce6456a01614f4b12565cdeada5cb29b`，三项 TaskRun validator blocker 已闭合，required CI 全绿，待 Codex 独立复核 |
| 0099 | 已由 turn 0100 DECISION 接手：PR #14 独立复核通过并 auto-merged，merge commit `50129a18b243c99309ed967f189c79a683e0395e` |
| 0100 | 已由 turn 0101 WORK_ORDER 接手：WP-02f merged，启动 WP-02g Artifact/QC/Evidence contract slice |
| 0101 | 已由 turn 0102 REPORT 接手：WP-02g 交付 PR #15（head `939b0f1da52b4c20c8dd5ed63ab78a4f042c75f0`），ArtifactManifest/QCReport/EvidenceItem schema+validator hardening + 24 新测试，本地 311 测试绿，required CI quality 3.10/3.11/3.12 全绿，未自合并/未启用 auto-merge |
| 0102 | 已由 turn 0103 DECISION 接手：PR #15 独立复核 + WSL 补验通过并经 GitHub auto-merge 合入，merge commit `9b3f9b432e4a697c96282073b860a32eb556829a` |
| 0103 | 已由 turn 0104 WORK_ORDER 接手：启动 WP-02h Claim/Alignment/Report/Bundle contract slice |
| 0104 | 已由 turn 0105 REPORT 接手：WP-02h 交付 PR #16（head `1a358d73a5e8b86ea1869a4383ed9dedfb96d964`），Claim/QuestionAlignmentReport/FinalReportManifest/ReproductionBundleManifest schema+validator hardening + 23 新测试，本地 334 测试绿，required CI quality 3.10/3.11/3.12 全绿，未自合并/未启用 auto-merge |
| 0105 | 已由 turn 0106 DECISION 接手：PR #16 独立审核为 CHANGES_REQUESTED，需修复 3 项 validator blocker 后回报新 head |
| 0106 | 已由 turn 0107 REPORT 接手：3 项 validator blocker 已修复，PR #16 new head `f2cfc0e44ae88cfcf47e644b8b5792fa9a1c37a3`，本地 339 测试 + required CI 全绿 |
| 0107 | 已由 turn 0108 DECISION 接手：PR #16 独立复核 + WSL 补验通过并经 GitHub auto-merge 合入，merge commit `2cd2eda4ef88313fa28fc83514d873749de42b86` |
| 0108 | 已由 turn 0109 WORK_ORDER 接手：WP-02h merged，启动 WP-03a event log/projection/idempotency audit and split |
| 0109 | 已由 turn 0110 REPORT 接手：WP-03a 交付 PR #17（head `e7f34eaa1f83a6dd88d64acc6b301c1f6478f3de`），event-log projection rebuild 审计 + `rebuild_state`/`load_state` 窄修 + `ProjectionRebuildTest`(6)，本地 345 测试绿，required CI quality 3.10/3.11/3.12 全绿，未自合并/未启用 auto-merge |
| 0110 | 已由 turn 0111 DECISION 接手：PR #17 独立审核为 CHANGES_REQUESTED，需修复坏事件 replay 未 fail closed 的 blocker |
| 0111 | 已由 turn 0112 REPORT 接手：fail-closed event replay blocker 已修，PR #17 新 head `08e8281fd3a600c9b2ae953a846e939c1e1433e7`，本地 350 测试 + required CI quality 3.10/3.11/3.12 全绿，未自合并/未启用 auto-merge |
| 0112 | 已由 turn 0113 DECISION 接手：PR #17 review-fix 独立复核仍为 CHANGES_REQUESTED，需修复非 legacy 同阶段 forged no-op 被 replay 接受的问题 |
| 0113 | 已由 turn 0114 REPORT 接手：非 legacy same-stage forged no-op blocker 已修，PR #17 新 head `43120a421fa21e3bf2a69b012012d596bf6dc03d`，本地 351 测试 + required CI quality 3.10/3.11/3.12 全绿，未自合并/未启用 auto-merge |
| 0114 | 已由 turn 0115 BLOCKER 接手：PR #17 独立审核通过，但仓库未启用 auto-merge，Codex 无法按既定策略合并 |
| 0115 | 已由 turn 0116 DECISION 接手：repo `allow_auto_merge=true` 后，PR #17 已经 GitHub auto-merge 合入，merge commit `f686e41a5128456666ff58d17d17e17817257939` |
| 0116 | 已由 turn 0117 WORK_ORDER 接手：WP-03a merged，启动 WP-03b event-log idempotency key + transition/snapshot consistency hardening |
| 0117 | 已由 turn 0118 REPORT 接手：WP-03b 交付 PR #18（head `c1f9cdc42132adac6ece3be84ad4cadab28766cd`），events.py idempotency_key + store.py append_event 幂等 + verify_projection 漂移检测 + 9 新测试，本地 360 测试 + lint/format-check + required CI quality 3.10/3.11/3.12 全绿，未自合并/OPEN/MERGEABLE |
| 0118 | 已由 turn 0119 DECISION 接手：WP-03b PR #18 独立审核为 CHANGES_REQUESTED，需修复 duplicate idempotency_key silent acceptance blocker |
| 0119 | 已由 turn 0120 REPORT 接手：CC 修复 blocker，PR #18 新 head `a29e3a87188c66fac57022506d4dadb854b31c80`，two probes 关闭，本地 362 测试 + lint/format + required CI 全绿，待 Codex 独立再审 |
| 0120 | 已由 turn 0121 DECISION 接手：PR #18 独立再审通过并经 GitHub auto-merge 合入，merge commit `fa5801c6b36136965b3da4dbab4a78c6e58bda24`。 |
| 0121 | 已由 turn 0122 WORK_ORDER 接手：WP-03b merged，启动 WP-04a CreateProject command foundation。 |
| 0122 | 已由 turn 0123 REPORT 接手：WP-04a 交付 PR #19，head `b16ad2c8ff31441f2f9b8ab94044d1435c3feae6`，新增 `auto_bioinfo/control_plane/`（CreateProject 命令：verbatim OriginalRequest + 版本化 ProjectPolicy 绑定 + PROJECT_STATE_INITIALIZED 事件 + 命令级幂等/同键冲突 fail-closed），无改动既有模块，本地 372 测试 + lint/format-check + required CI quality 3.10/3.11/3.12 全绿，`git diff --check` clean，OPEN/MERGEABLE，未自合并/未启用 auto-merge |
| 0123 | 已由 turn 0124 DECISION 接手：PR #19 独立审核为 CHANGES_REQUESTED；需修 command identity 漏掉 `submitter/attachments/user_constraints` 与 `project_dir` 路径穿越两项 blocker。 |
## 当前开放任务

1. **WP-04a PR #19 review-fix**：turn 0124 已派回 CC；只修两项 blocker：`_command_identity()` 必须覆盖 persisted request 字段（`submitter/attachments/user_constraints` 等），`project_dir` 必须拒绝含 `..` 的词法路径穿越。修复后回报新 head。
2. **WP-04 后续 T-04-02..12**：项目查询/list/timeline、状态机 registry、审批生命周期、A0-A3 gate、HTTP/CLI/OpenAPI/auth 等均等 WP-04a 合并后拆成独立小 WO。
3. **WP-03 deferred register / Docker**：PostgreSQL event store、outbox/broker/queue、multi-writer locking、Docker/Compose/container images 继续暂缓，只有后续独立 WO 明确授权时才可做。

（OPS-00 原测试门禁被 CEO override 覆盖以便立即启用握手系统；状态为 active-by-override / unverified，不是 PASS。）
## 阻塞项

1. **硬停点**：真实人类来源数据、外部 LLM/服务、付费服务、公开发布、破坏性迁移/不可逆删除、扩大机器人凭据权限，均必须停下等 CEO。
2. **CI 权限注意**：`.github/workflows` 已获 CEO 授权用于后续独立 CI WO；若实际 push 因 workflow 权限被拒，CC 必须写 BLOCKER，不得自行扩大凭据权限。
3. **Docker 注意**：Docker / Compose / Dockerfile 已属 D-03 计划内授权，但当前暂缓；只有后续独立 WO 明确写明时才可执行。
4. **当前范围**：WP-04a 仅限 CreateProject command foundation / T-04-01；不得扩大到 HTTP API、CLI、OpenAPI、auth、Approval lifecycle、A0-A3 evaluator、async operation、outbox、DB、Docker、deps、workflow、真实数据或外部服务。
5. **合并策略**：`rebuild/auto-bioinfo-core` 按受保护 base 处理；Codex 独立审核通过后只能启用 `gh pr merge <PR> --auto --merge`，不得直接 push/硬合 base，不得绕过 required CI。
6. **当前合并 blocker**：无。若后续 auto-merge 被保护规则/权限拦截，按 turn 0063 写回 BLOCKER，不得绕过。
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
| 0054 | `log/0054-cc-to-codex-report-WP-01c.md`（OPEN，已由 0055 接手：PR #5 reviewed and merged） |
| 0055 | `log/0055-codex-to-cc-decision-WP-01c-pr5-merged.md`（OPEN，WP-01c merged，merge commit `92e865e04bb9ae4e838b9ad00fe9b755f6e3a06b`） |
| 0056 | `log/0056-codex-to-cc-workorder-WP-01-ci.md`（OPEN，已由 0057 接手） |
| 0057 | `log/0057-cc-to-codex-report-WP-01-ci.md`（OPEN，WP-01 CI REPORT，PR #6，GitHub Actions 全绿） |
| 0058 | `log/0058-codex-to-cc-decision-WP-01-ci-pr6-changes-requested.md`（OPEN，已由 0059 接手：PR #6 CHANGES_REQUESTED → review fix 已交付） |
| 0059 | `log/0059-cc-to-codex-report-WP-01-ci-pr6-review-fix.md`（OPEN，WP-01 CI review fix REPORT，PR #6 head `98907ea3`，GitHub Actions 全绿） |
| 0060 | `log/0060-codex-to-cc-decision-WP-01-ci-pr6-merged.md`（OPEN，WP-01 CI PR #6 merged，merge commit `7bac3b26a850ffe5da842c8a61c530d102d74fb2`） |
| 0061 | `log/0061-codex-to-cc-workorder-WP-01d.md`（OPEN，已由 0064 接手：启动 WP-01d license / dependency inventory / SBOM entry） |
| 0062 | `log/0062-cc-to-ceo-proposal-tiered-merge-autonomy.md`（OPEN，CEO-requested governance input；auto-merge 机制由 0063 接手） |
| 0063 | `log/0063-codex-to-cc-decision-auto-merge-protected-base.md`（OPEN，base 保护 + PR/CI/auto-merge 合并机制裁定） |
| 0064 | `log/0064-cc-to-codex-report-WP-01d.md`（OPEN，WP-01d REPORT，PR #7 head `56b635f86c5713acd50ff2a2e4419cd0b26f73b5`） |
| 0065 | `log/0065-codex-to-cc-decision-WP-01d-pr7-changes-requested.md`（OPEN，PR #7 CHANGES_REQUESTED：修复 Python 3.10/no-`tomli` SBOM 路径；已由 0066 接手） |
| 0066 | `log/0066-cc-to-codex-report-WP-01d-pr7-review-fix.md`（OPEN，WP-01d PR #7 review fix REPORT，head `5e1e0318f5bf3f0b8fdcb6151a43dfaa8f944dd4`，required CI 全绿） |
| 0067 | `log/0067-codex-to-cc-decision-WP-01d-pr7-auto-merged.md`（OPEN，WP-01d PR #7 auto-merged，merge commit `a7bec4917c5656c72297c276d5c4482168010f42`） |
| 0068 | `log/0068-codex-to-cc-workorder-WP-01e.md`（OPEN，已由 0069 接手：启动 WP-01e PR / change template） |
| 0069 | `log/0069-cc-to-codex-report-WP-01e.md`（OPEN，已由 0070 接手：PR #8 auto-merged） |
| 0070 | `log/0070-codex-to-cc-decision-WP-01e-pr8-auto-merged.md`（OPEN，WP-01e PR #8 auto-merged，merge commit `860465986c74b2cd8ad10ae3221296f0bd3855d1`） |
| 0071 | `log/0071-codex-to-cc-workorder-WP-02a.md`（OPEN，已由 0072 接手：启动 WP-02a common schema foundations） |
| 0072 | `log/0072-cc-to-codex-report-WP-02a.md`（OPEN，已由 0073 接手：PR #9 auto-merged） |
| 0073 | `log/0073-codex-to-cc-decision-WP-02a-pr9-auto-merged.md`（OPEN，WP-02a PR #9 auto-merged，merge commit `7bb8e6807f2c84f9e0cd9de6da6a0710df07b3aa`） |
| 0074 | `log/0074-codex-to-cc-workorder-WP-02b.md`（OPEN，已由 0075 接手：启动 WP-02b research and planning schema slice） |
| 0075 | `log/0075-cc-to-codex-report-WP-02b.md`（OPEN，已由 0076 接手：PR #10 CHANGES_REQUESTED） |
| 0076 | `log/0076-codex-to-cc-decision-WP-02b-pr10-changes-requested.md`（OPEN，要求修复三项 schema validation blocker；已由 0077 接手） |
| 0077 | `log/0077-cc-to-codex-report-WP-02b-pr10-review-fix.md`（OPEN，已由 0078 接手：PR #10 review-fix 仍 CHANGES_REQUESTED） |
| 0078 | `log/0078-codex-to-cc-decision-WP-02b-pr10-review-fix2-changes-requested.md`（OPEN，已由 0079 接手：要求修复 SubQuestion between-comparison 误拒绝） |
| 0079 | `log/0079-cc-to-codex-report-WP-02b-pr10-review-fix2.md`（OPEN，已由 0080 接手：PR #10 auto-merged） |
| 0080 | `log/0080-codex-to-cc-decision-WP-02b-pr10-auto-merged.md`（OPEN，WP-02b PR #10 merged，merge commit `22b87d579045bd0f3abc7b444c0c68c723349b8b`） |
| 0081 | `log/0081-codex-to-cc-workorder-WP-02c.md`（OPEN，启动 WP-02c resource/dataset feasibility contract slice） |
| 0082 | `log/0082-cc-to-codex-report-WP-02c.md`（OPEN，已由 0083 接手：PR #11 CHANGES_REQUESTED） |
| 0083 | `log/0083-codex-to-cc-decision-WP-02c-pr11-changes-requested.md`（OPEN，已由 0084 接手：两项 validator blocker 已闭合，PR #11 新 head `545159f`） |
| 0084 | `log/0084-cc-to-codex-report-WP-02c-pr11-review-fix.md`（OPEN，已由 0085 接手：PR #11 auto-merged） |
| 0085 | `log/0085-codex-to-cc-decision-WP-02c-pr11-auto-merged.md`（OPEN，WP-02c PR #11 merged，merge commit `2909f7c4143b3e6a7528c258fbf2375d373b1265`） |
| 0086 | `log/0086-codex-to-cc-workorder-WP-02d.md`（OPEN，已由 0087 接手：WP-02d 交付 PR #12） |
| 0087 | `log/0087-cc-to-codex-report-WP-02d.md`（OPEN，WP-02d 交付 PR #12，head `4a87bd92ad80c1407e06e638972a10c959ba4060`，本地 256 测试绿 + required CI 全绿，待 Codex 审核） |
| 0088 | `log/0088-codex-to-cc-decision-WP-02d-pr12-changes-requested.md`（OPEN，已由 0089 接手：Blocker 1 已修，PR #12 新 head `d24347a621db84b16b4128494ddf893e64d05b99`） |
| 0089 | `log/0089-cc-to-codex-report-WP-02d-pr12-review-fix.md`（OPEN，WP-02d PR #12 review-fix：Blocker 1 闭合，新 head `d24347a621db84b16b4128494ddf893e64d05b99`，本地 258 测试绿 + required CI 全绿，未自合并，待 Codex 审核） |
| 0090 | `log/0090-codex-to-cc-decision-WP-02d-pr12-auto-merged.md`（OPEN，WP-02d PR #12 auto-merged，merge commit `db560a30d8217849e782e15ce3528b9d94b4189d`） |
| 0091 | `log/0091-codex-to-cc-workorder-WP-02e.md`（OPEN，已由 0092 接手：WP-02e 交付 PR #13） |
| 0092 | `log/0092-cc-to-codex-report-WP-02e.md`（OPEN，WP-02e 交付 PR #13，head `13c6594a2a47d76510e4177815af7797a9838a34`，本地 273 测试绿 + required CI quality 3.10/3.11/3.12 全绿，未自合并/未启用 auto-merge，待 Codex 审核） |
| 0093 | `log/0093-codex-to-cc-decision-WP-02e-pr13-changes-requested.md`（OPEN，已由 0094 接手：三项 blocker 已修，PR #13 新 head `aadcf326d2124f359aa15c01a0fdd7c9bce37c21`） |
| 0094 | `log/0094-cc-to-codex-report-WP-02e-pr13-review-fix.md`（OPEN，WP-02e PR #13 review-fix：三项 blocker 闭合，新 head `aadcf326d2124f359aa15c01a0fdd7c9bce37c21`，required CI 全绿，已由 Codex 审核） |
| 0095 | `log/0095-codex-to-cc-decision-WP-02e-pr13-auto-merged.md`（OPEN，WP-02e PR #13 auto-merged，merge commit `c2b907fae608020cdd5b693fea650affec7fe338`） |
| 0096 | `log/0096-codex-to-cc-workorder-WP-02f.md`（OPEN，已由 0097 接手：WP-02f 交付 PR #14） |
| 0097 | `log/0097-cc-to-codex-report-WP-02f.md`（OPEN，已由 0098 接手：PR #14 CHANGES_REQUESTED） |
| 0098 | `log/0098-codex-to-cc-decision-WP-02f-pr14-changes-requested.md`（OPEN，已由 0099 接手：三项 blocker 已修，PR #14 新 head `d54d1df4ce6456a01614f4b12565cdeada5cb29b`） |
| 0099 | `log/0099-cc-to-codex-report-WP-02f-pr14-review-fix.md`（OPEN，已由 0100 接手：PR #14 auto-merged） |
| 0100 | `log/0100-codex-to-cc-decision-WP-02f-pr14-auto-merged.md`（OPEN，WP-02f PR #14 auto-merged，merge commit `50129a18b243c99309ed967f189c79a683e0395e`） |
| 0101 | `log/0101-codex-to-cc-workorder-WP-02g.md`（OPEN，已由 0102 接手：WP-02g 交付 PR #15，head `939b0f1da52b4c20c8dd5ed63ab78a4f042c75f0`） |
| 0102 | `log/0102-cc-to-codex-report-WP-02g.md`（OPEN，WP-02g Artifact/QC/Evidence contract slice 交付 PR #15，已由 0103 接手：PR #15 auto-merged） |
| 0103 | `log/0103-codex-to-cc-decision-WP-02g-pr15-auto-merged.md`（OPEN，WP-02g PR #15 auto-merged，merge commit `9b3f9b432e4a697c96282073b860a32eb556829a`） |
| 0104 | `log/0104-codex-to-cc-workorder-WP-02h.md`（OPEN，已由 0105 接手：WP-02h 交付 PR #16，head `1a358d73a5e8b86ea1869a4383ed9dedfb96d964`） |
| 0105 | `log/0105-cc-to-codex-report-WP-02h.md`（OPEN，已由 0106 接手：PR #16 CHANGES_REQUESTED） |
| 0106 | `log/0106-codex-to-cc-decision-WP-02h-pr16-changes-requested.md`（OPEN，已由 0107 接手：3 项 blocker 已修复，new head `f2cfc0e4`） |
| 0107 | `log/0107-cc-to-codex-report-WP-02h-pr16-review-fix.md`（OPEN，已由 0108 接手：PR #16 auto-merged） |
| 0108 | `log/0108-codex-to-cc-decision-WP-02h-pr16-auto-merged.md`（OPEN，WP-02h PR #16 auto-merged，merge commit `2cd2eda4ef88313fa28fc83514d873749de42b86`） |
| 0109 | `log/0109-codex-to-cc-workorder-WP-03a.md`（OPEN，启动 WP-03a event log/projection/idempotency audit and split） |
| 0110 | `log/0110-cc-to-codex-report-WP-03a.md`（OPEN，已由 0111 接手：PR #17 CHANGES_REQUESTED） |
| 0111 | `log/0111-codex-to-cc-decision-WP-03a-pr17-changes-requested.md`（OPEN，要求修复 PR #17 fail-closed event replay blocker） |
| 0112 | `log/0112-cc-to-codex-report-WP-03a-pr17-review-fix.md`（OPEN，已由 0113 接手：PR #17 review-fix 仍 CHANGES_REQUESTED） |
| 0113 | `log/0113-codex-to-cc-decision-WP-03a-pr17-review-fix2-changes-requested.md`（OPEN，已由 0114 接手：要求修复非 legacy same-stage forged no-op replay blocker） |
| 0114 | `log/0114-cc-to-codex-report-WP-03a-pr17-review-fix2.md`（OPEN，已由 0115 接手：PR #17 approved but auto-merge disabled） |
| 0115 | `log/0115-codex-to-ceo-blocker-WP-03a-pr17-auto-merge-disabled.md`（OPEN，已由 0116 接手：auto-merge enabled + PR #17 merged） |
| 0116 | `log/0116-codex-to-cc-decision-WP-03a-pr17-auto-merged.md`（OPEN，WP-03a PR #17 auto-merged，merge commit `f686e41a5128456666ff58d17d17e17817257939`） |
| 0117 | `log/0117-codex-to-cc-workorder-WP-03b.md`（OPEN，已由 0118 接手：WP-03b 交付 PR #18，待 Codex 独立审核） |
| 0118 | `log/0118-cc-to-codex-report-WP-03b.md`（OPEN，已由 0119 接手：PR #18 CHANGES_REQUESTED） |
| 0119 | `log/0119-codex-to-cc-decision-WP-03b-pr18-changes-requested.md`（OPEN，已由 0120 接手：blocker 已修，PR #18 新 head `a29e3a8`） |
| 0120 | `log/0120-cc-to-codex-report-WP-03b-pr18-review-fix.md`（OPEN，已由 0121 DECISION 接手：PR #18 auto-merged） |
| 0121 | `log/0121-codex-to-cc-decision-WP-03b-pr18-auto-merged.md`（OPEN，WP-03b PR #18 auto-merged，merge commit `fa5801c6b36136965b3da4dbab4a78c6e58bda24`） |
| 0122 | `log/0122-codex-to-cc-workorder-WP-04a.md`（OPEN，已由 0123 接手：WP-04a 交付 PR #19，待 Codex 独立审核） |
| 0123 | `log/0123-cc-to-codex-report-WP-04a.md`（OPEN，已由 0124 DECISION 接手：PR #19 CHANGES_REQUESTED） |
| 0124 | `log/0124-codex-to-cc-decision-WP-04a-pr19-changes-requested.md`（OPEN，要求修复 command identity 漏字段 + project_dir 路径穿越） |
