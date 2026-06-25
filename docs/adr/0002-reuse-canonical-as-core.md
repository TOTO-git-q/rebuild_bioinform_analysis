# ADR-0002：以 canonical/ 为领域核心清理改造，而非绿地重写

- 状态：已采纳
- 背景：历史系统 targetcompass_lite 约 3.8 万行；其中 `canonical/` 子包（约 4600 行）已是一次干净的"规范化控制平面"重构：纯标准库、完全自包含（唯一外部依赖是 stdlib 的 fnmatch）、事件溯源、稳定 ID、断言天花板、mock 隔离、对照审计齐备。
- 决策：把 `canonical/` 搬入 `auto_bioinfo/core/` 作为领域核心，清理反模式并补字段，**不绿地重写**。
- 理由：canonical 离目标"干净六边形核心"最近且经过测试；重写会丢失已验证的护栏细节、徒增工程量与风险。
- 已做清理：删除耦合 TargetCompass 报告命名且带悬空导入（`from .nextflow_execution import ...`）的 `report_manifest.py`，改写干净的 `report.py`/`reproduction/`；状态机扩展复现/完成阶段 + 合法非成功终态；schema 按需求规格补 ResearchSpec/EvidenceItem/DatasetManifest 字段；运行目录段 `v5/` → `state/`。
- 后果：core 保留 `schema_version="v5.canonical/0.1"` 常量以维持兼容；后续可统一升版。
