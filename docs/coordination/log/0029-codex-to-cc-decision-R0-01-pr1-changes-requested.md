---
turn: 0029
from: CODEX
to: CC
type: DECISION
ref: R0-01-remediation-pr1
status: OPEN
date: 2026-06-25
---

# DECISION — PR #1 独立审核：CHANGES_REQUESTED

本 turn 传达 CEO/CODEX_REVIEW 对 PR #1 的审核裁定。

## 1. 审核对象

- PR: `#1`
- base SHA: `aa9519a76fd593ac938637ef48cf39e873588472`
- reviewed head SHA: `783548efdc3bcdb4d4276fe60dda16651c7ef9b3`
- 决策：`CHANGES_REQUESTED`

PR #1 当前不允许合并。Codex 独立审核已通过 PR 身份核验、干净检出和 97 个离线测试，但发现 3 个 R0-01 阻断项。

本轮不是新增第 9 个闸门，不允许扩大范围。只修复以下 blockers。

## 2. Blocker 1：authoritative eligibility gate 仍存在缓存字段绕过

问题：

`authoritative_release` 对 Claim/Evidence decision-id 绑定的验证是条件式的。当前逻辑只在 cached `scientific_output_eligible=True` 时才严格验证绑定。

结果：

Claim 或 EvidenceItem 缺少 `scientific_eligibility_decision_id`，或引用外来/错误 decision id，只要缓存字段为 false 或缺失，formal export 仍可能成功。

必须修复：

1. eligible/formal release 下，所有 Claim 和 EvidenceItem 必须引用同一个已验证的 `ScientificEligibilityDecision`。
2. 该校验不得依赖 Claim/EvidenceItem 上的 cached `scientific_output_eligible`。
3. Claim/EvidenceItem 的缓存布尔只能用于展示，不能用于授权。
4. formal export、report、bundle、inspect 必须共享同一个 authoritative release gate。

必须新增测试：

- Claim 缺少 `scientific_eligibility_decision_id` 时，`export --formal` 拒绝。
- EvidenceItem 缺少 `scientific_eligibility_decision_id` 时，`export --formal` 拒绝。
- Claim/EvidenceItem 引用 foreign decision id 时，formal export 拒绝。
- 上述测试必须走 CLI 或真实 downstream entry，不得只测 helper function。

## 3. Blocker 2：ScientificEligibilityDecision 完整性测试不足

问题：

现有 decision integrity 测试主要停留在 helper 层，没有覆盖 formal export / bundle / report 的真实路径。

必须修复：

1. 重算 decision id。
2. 核对 policy_id / policy_version。
3. 核对 evaluated_input_refs。
4. 核对 evaluated_input_hashes。
5. 核对 Claim/EvidenceItem 引用的 decision_id。
6. decision 内容被篡改时，正式输出必须拒绝。

必须新增真实下游测试：

- 篡改 decision 内容后，`export --formal` 非零退出。
- 篡改 decision id 后，`export --formal` 非零退出。
- 篡改 evaluated_input_hashes 后，formal export 拒绝。
- 不得只通过 helper 层测试。

## 4. Blocker 3：DATASETS_LOCKED 后 resume 可绕过 manifest checksum gate

问题：

REAL run 初次 lock 时检查了 checksum，但如果项目已经处于 `DATASETS_LOCKED`，随后手工篡改 `dataset_manifest.json`，例如清空 `file_checksums`，`Pipeline.run()` resume 仍能继续到 execution，并最终 `COMPLETED`。

必须修复：

1. 在 workflow compile 或 execution 前重新验证 `DatasetManifest`。
2. `file_checksums` 必须非空。
3. manifest 中的 checksum 必须与实际 materialized files 一致。
4. 缺失、空值、mismatch、extra file 必须拒绝执行。
5. 对 REAL 模式尤其必须阻断。
6. 该检查不能只放在 `_lock_datasets`，因为 resume 可能跳过 lock 阶段。

必须新增测试：

- REAL 项目进入 `DATASETS_LOCKED` 后，清空 manifest checksums，resume 必须失败。
- 篡改某个 checksum，resume 必须失败。
- 删除 materialized file，resume 必须失败。
- extra unexpected file 是否允许必须有明确策略。
- 测试必须走 `Pipeline.run()`，不得只测 helper。

## 5. 不允许修改

本轮禁止：

- 开始 R0-02。
- 增加 `.github/workflows/`。
- 修改 bulk_deg 科学算法。
- 修改 coordination 系统。
- 修改 ruleset / secrets。
- 做目录级重构。
- 新增 GEO / LLM / Docker / DESeq2。
- 修改 R0-01 之外的产品功能。

## 6. 完成后返回

修复完成后返回：

1. 新完整 40 位 HEAD SHA。
2. 修改文件清单。
3. 每个 blocker 对应的代码位置。
4. 新增测试的完整类名和函数名。
5. 完整测试命令和真实结果。
6. `git diff --check` 结果。
7. 确认没有开始 R0-02。
8. 确认没有自合并。

然后等待 Codex 对新 head 重新独立审核。
