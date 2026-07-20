# MetaLoop v3.1 Roadmap

最后更新：2026-07-20

## Alpha Optimization

```text
Frame -> Work -> Reconcile -> Adapt -> Prove
  |        |        |          |        |
Contract  Attempt  Git delta  Decision  Evaluation
```

v3.1 保留 v3 final SQLite schema 和 fail-closed lifecycle，增加 derived Recovery、
content-preserving commit promotion、组合式 begin/finish，以及 risk-proportional Skill
默认。现有 schema-version 3 数据库无需迁移。

## Product Invariants

- Project documents are architecture-content truth。
- Git is workspace-change truth。
- SQLite is protocol-state truth。
- ContractRevision is task-boundary truth。
- Agent is semantic-judgment truth。
- Attempt is execution truth。
- Evaluation is completion truth。
- RecoveryView is derived, never a new fact source。

## Alpha Phase

先让原 alpha Agent 在同一研究项目继续推进，记录每个阶段的显式协议命令数、Task/
Attempt churn、promotion Task 数、authority wait、被门禁捕获的真实问题，以及协议耗时
占比。只有重复证据才能进入下一轮 core 变化。

## 后续候选切片

- 更清晰的 ahead delta 展示和 reconcile ergonomics；
- 有界大仓库扫描的增量优化，不牺牲 unknown fail-closed；
- host hook 的最小适配层和更多 safe points；
- 基于真实 Evidence 的重复工作提示，但不宣称机械语义判重。

Semantic memory、scheduler、daemon、watcher、agent pool、transcript store、vector memory
和 project-management surface 不在路线内。
