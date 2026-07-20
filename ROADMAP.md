# MetaLoop v3 Roadmap

最后更新：2026-07-20

## Final Clean Cut

```text
Frame -> Work -> Reconcile -> Adapt -> Prove
  |        |        |          |        |
Contract  Attempt  Git delta  Decision  Evaluation
```

v3 vertical slice 包含 Git workspace adapter、WorkspaceStamp、final SQLite schema、
checkpoint alignment、fail-closed lifecycle、active CLI、self-contained Skill、installed-path
smoke tests 和 surface audit。

## Product Invariants

- Project documents are architecture-content truth。
- Git is workspace-change truth。
- SQLite is protocol-state truth。
- ContractRevision is task-boundary truth。
- Agent is semantic-judgment truth。
- Attempt is execution truth。
- Evaluation is completion truth。
- RecoveryView is derived, never a new fact source。

## Dogfood Phase

真实任务重点验证 context compaction、Task pause/resume、repair child、Git reconcile、
stable/managed refs、separate worktree identity 和 host safe point。只有重复失败才能进入
下一轮 core 变化。

## 后续候选切片

- 更清晰的 ahead delta 展示和 reconcile ergonomics；
- 有界大仓库扫描的增量优化，不牺牲 unknown fail-closed；
- host hook 的最小适配层和更多 safe points；
- 基于真实 Evidence 的重复工作提示，但不宣称机械语义判重。

Semantic memory、scheduler、daemon、watcher、agent pool、transcript store、vector memory
和 project-management surface 不在路线内。
