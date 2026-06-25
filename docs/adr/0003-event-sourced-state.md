# ADR-0003：事件溯源 + JSON/JSONL 持久化 + 锁定不可变（预留 Postgres）

- 状态：已采纳
- 决策：项目状态是 append-only 事件日志（`state/events.jsonl`）的投影；`project_state.json` 只是可重建快照。状态只能经 `transition_state` 沿状态机合法边推进；非法迁移被拒。TaskRun/QCReport/EvidenceItem/Claim 各自 append-only JSONL 账本，按稳定 ID 幂等追加。
- 理由：满足需求"状态只能通过事件推进、每次变化留 actor/输入/输出/理由、可从不可变日志重建、不能靠改一个 JSON 静默改历史"。
- 不可变性：DatasetManifest 锁定后须产生新版本而非原地改（schema 已建模版本字段）。
- 预留：EventStorePort 抽象了"追加事件/加载事件/重建状态"，未来可替换为 PostgreSQL 事件库 + outbox + 乐观并发，领域不变。
- 已知局限：本地 JSONL 未做并发写锁（单进程 CLI 足够；多写场景留给 Postgres 适配器）。
