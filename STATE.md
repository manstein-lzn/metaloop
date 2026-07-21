# MetaLoop v3.2 当前状态

最后更新：2026-07-22

## 一句话状态

MetaLoop v3.2 是 **minimal / orthogonal / event-triggered / Git-backed / SQLite-canonical**
外环控制系统：Git 证明 workspace 机械变化，SQLite 保存 durable target、current state、
feedback、authority 和 recovery；fresh-context Review 只在语义风险无法完全机械判定时出现。

## 已实现

- Git repository/worktree identity 与 Python 3.12 标准库 WorkspaceStamp。
- clean、staged、unstaged、untracked、deleted、renamed、binary、重复编辑和 scan limit
  的确定性状态摘要。
- Project、Task graph、ContractRevision、Attempt、Checkpoint、Evidence、DecisionEvent、
  Evaluation、Review overlay 和 RecoveryView final schema。
- baseline stamp、显式 `claim/defer/assign/conflict` reconcile、CAS、one-worktree one open
  Attempt、exact replay retry reason。
- stable input、managed output、allowed paths、显式 change kind 和 redesign migration plan
  统一在 Contract execution scope。
- live WorkspaceStamp 与所有内容绑定在 seal、verify、review、accept、integrity 重检。
- `Frame -> Work -> Reconcile -> Adapt -> Prove` 与条件式 Progressive Design。
- 同步 host safe point；无 scheduler、daemon、watcher、transcript、vector memory 或管理 UI。
- canonical source 自动生成 self-contained Skill，portable kernel 仅为 bootstrap。
- RecoveryView 真正 live-derived；无需先写 resume annotation 即可开始 Attempt。
- WorkspaceStamp 记录 HEAD tree、parent OIDs 和 isolated-index materialized tree；exact
  direct commit promotion 不再需要 promotion Task。
- `task begin` 与 `attempt finish` 把普通路径压缩为两个显式协议操作，仍复用同一
  canonical lifecycle。
- 测试失败、review follow-up、Contract 修订和 commit 保持在原 Task；外部 authority
  仅对 Contract 明确声明的语义结论生效。
- Contract v1.1 规范化 Tier 1-3 assurance；旧 v3 Contract v1.0 继续按 legacy 语义读取。
- Tier 3 reviewer authority 由内核派生，unresolved trigger 对当前 acceptance target sticky；
  降级必须由新 ContractRevision 绑定旧 Contract 的 approved Evaluation。
- `acceptance_head_id` 在完成前就是唯一 active Evaluation head；Review 和 accept 不能引用
  stale parent 或 sibling chain。
- active head 使用统一 control projection，给出唯一 `next_transition`；verification、Review
  和 Contract replacement 都参与 Task CAS。verification 只绑定当前 Contract 的 latest
  sealed Attempt，authority 固定按 reviewer -> reserved user 满足。
- non-approved、out-of-order、duplicate 或 extra historical Review 不重写历史；统一投影为
  `start_repair_attempt`，新 Attempt 清除 malformed active head。
- Tier 3 Review report、fresh context、Contract、Attempt、Evidence 和 parent Evaluation
  直接进入 Review content hash，不使用未绑定 DecisionEvent sidecar。
- Tier 3 降级逐 trigger 检查规范化 proof；只有映射了稳定
  `validator_id/resolves_trigger_ids` 的 passing executable validator，或 host-verified
  structured Review 可以解除对应 trigger。
- context provenance 区分 `host/verified`、`manual/unverified` 和 `unavailable`；CLI
  `--context-id` 不再被误当作 host attestation。
- Workspace observation 同时隔离临时 index 和 object directory，真实 Git metadata 在
  stamp/status/recovery 前后保持不变。
- `observe --format full|brief` 保持兼容；brief 增加 control status、ordered authority、
  typed transition、blocker、trigger proofs、assurance 和 next action。

## Alpha 复测重点

1. 普通局部修复是否只需 `begin`、一次编辑和 `finish`。
2. commit 后是否保持 fresh/aligned 且没有 clean-head promotion Task。
3. validator 失败、review 修改和 Contract 修订是否留在同一 Task。
4. Tier 2 的完整机械证明是否避免不必要 reviewer。
5. Tier 3 fresh-context Review 是否发现 Worker 与其测试共享的遗漏。
6. active Evaluation head 的 typed next transition 是否在恢复后可直接执行。
7. 用户是否只在真实例外和明确保留的最终决策上被中断。
8. Tier 0 通过外部试用记录校准，Tier 1-3 通过 SQLite 和用户反馈校准。

## 稳定边界

- GitHub/remote repository 不是运行依赖。
- Git 不判断语义正确性；SQLite 不复制项目架构正文。
- declared paths 不是 sandbox；强制隔离由 host hook、sandbox 或 wrapper 提供。
- 不从 prose 推断 repair、redesign、pivot 或 ownership。
- 不建立第二个 Task ontology 或 active compatibility path。
- 默认信任 Agent 是合作的；context provenance 用于认知去相关，不是敌对认证。
- 内核执行已声明 assurance，但不推断项目特定 semantic trigger。

## 验证

```bash
python3 tools/sync_skill_core.py
python3 tools/check_skill_core_sync.py
python3 tools/check_core_import_boundary.py
python3 tools/check_v3_surface.py
pytest -q
git diff --check
```
