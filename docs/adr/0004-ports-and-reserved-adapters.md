# ADR-0004：端口-适配器，预留 Postgres/MinIO/Nextflow/LLM

- 状态：已采纳
- 决策：领域核心只依赖 `auto_bioinfo/ports` 中的 `Protocol`（结构化类型）。本次提供离线默认适配器；Postgres 事件库、MinIO 对象存储、Nextflow 执行器、网络 LLM 网关均以注释 `RESERVED` 在端口处留位，本次不实现。
- 端口清单：PlannerPort（LLM 替身=离线确定性规划）、ResourceDiscoveryPort（=提交的 fixture）、AnalysisMethodPort（=numpy bulk_deg）、ObjectStorePort（=本地文件系统）、EventStorePort（=JSONL）。
- 理由：用 Protocol 而非基类，适配器无需 import/继承核心，依赖箭头恒向内；满足"替换基础设施实现不改领域状态机"。
- 后果：升级到生产基础设施 = 新增实现这些 Protocol 的适配器并在装配处注入，核心零改动。
