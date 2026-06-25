# ADR-0006：真实方法用 numpy-only 确定性实现，默认测试离线

- 状态：已采纳
- 背景：垂直切片需"至少一个真正执行的小型分析，而非 metadata-only 角色"；环境有 numpy 无 scipy；需求要求默认测试离线确定性、可用提交的 fixture。
- 决策：`bulk_deg` 用 numpy 实现 CPM/log2 + Welch t 检验 + BH FDR；t 分布尾概率用**有出处的正则不完全 Beta 函数（Numerical Recipes betacf/betai 连分式）**计算，对齐 scipy.stats 到 ~1e-10，而**不**引入 scipy。测试用标准库 unittest（零额外安装即可跑）。
- 理由：①numpy-only 让第三方零摩擦复现；②不"自造统计"——不完全 Beta 是公认参考算法，并以已知 t 临界值校验；③避免 scipy 重型构建依赖。
- 后果：真实生物方法（limma/edgeR/scanpy/Nextflow）作为未来 AnalysisMethodPort 适配器接入，本次不引入以保离线确定性。
