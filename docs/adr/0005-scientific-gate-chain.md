# ADR-0005：不可绕过的科学证据门禁链 QC→Evidence→Claim→Alignment

- 状态：已采纳
- 决策：证据链单调不可绕：真实执行 → 带校验和的 Artifact → 四层 QC → 证据准入闸门（`validate_artifact_for_evidence`）→ EvidenceItem → Claim → 原问题对照审计。任一环缺失不得进入下一环。
- 强制点：①未过 QC / placeholder / 不存在 / 无校验和的 artifact 进不了证据合成；②Claim 等级被 `validate_claim_ceiling` 封顶，超界抛错；③对照审计检查越级、跑题（scope drift）、阴性结果遗漏、证据可达性，非 `approve` 不出干净报告、转人工。
- 理由：需求把"计划/执行/审核分离、证据优先于故事、保守失败、可追溯"列为核心价值；门禁链是其代码化。
- 测试：越级 claim→对照 reject、scope drift→reject、QC fail→不生成证据、样本不足→合法终态，均有用例。
