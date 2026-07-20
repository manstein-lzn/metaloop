# MetaLoop Roadmap

最后更新：2026-07-20

## 已完成：V2 Durable Work Graph

- SQLite canonical store 和 schema migration 基础。
- Task graph、immutable ContractRevision、recoverable Attempt。
- content-bound Evaluation/Review acceptance chain。
- CAS、dependency DAG、duplicate fingerprint 和 legacy migration。
- bounded freshness-checked RecoveryView。
- canonical core 到 self-contained Skill 的生成发布。
- v1 correctness fix、重新验证迁移和 v2 fail-closed 兼容边界。
- adversarial hardening：evidence freshness、mixed authority、event isolation、
  atomic migration、terminal lifecycle、bounded recovery、dependency freshness 和
  `ready_to_accept`。
- v2-aware status、observe、dashboard 和 projections。

## 下一阶段：真实使用反馈

当前不预设 v3 功能。只记录真实试用中反复出现的问题：

- RecoveryView 缺失了哪些恢复信息，哪些信息又过量。
- Attempt 边界是否容易由 agent 稳定判断。
- fingerprint 是否需要任务类型相关的 normalization extension。
- 多 thread 同 Task 是否需要更强 lease，而不只是 CAS 和 append-only records。
- supersession-resolved current decisions 的 20 条恢复窗口是否足够。
- legacy import 在真实历史数据中还有哪些不可绑定形式。
- 用户是否真的需要 routable work units 与 v2 Task graph 的更深集成。

只有同类失败在真实任务中反复出现，才新增代码机制。

## 明确不做

- 后台 scheduler、daemon、watcher 或 agent pool。
- 聊天 transcript 存储、向量 memory 或第二个 agent brain。
- deadline、priority、资源排期、团队看板等项目管理能力。
- 让 root JSON、Markdown 或 dashboard 成为第二份真相。
- 为每个推理模式新增 schema/module。
