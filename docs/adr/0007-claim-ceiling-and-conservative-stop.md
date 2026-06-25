# ADR-0007：断言天花板与保守失败终态

- 状态：已采纳
- 决策：①每个项目有 claim_ceiling（本切片 = `association`）；RNA 差异表达只能支撑 association 级 Claim，绝不自动升级为蛋白/分泌/机制/因果。天花板取"方法能力 ∧ 项目上限"的最小值，在 Claim 生成与对照审计两处强制。②数据不足/方法不适用/结论不稳定时进入合法非成功终态（INSUFFICIENT_DATA/METHOD_NOT_APPLICABLE/INCONCLUSIVE/CONFLICTING_EVIDENCE），而不是抛异常或硬凑结果。③阴性/零结果必须在 EvidenceItem/报告中保留。
- 理由：直接落实需求规格的"保守失败""证据优先于故事""不得越级表达"。
- 后果：CLI/pipeline 在终态正常返回（非崩溃），调用方据 `current_stage` 判断结局。
