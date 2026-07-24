# MetaLoop v3.4 当前状态

最后更新：2026-07-23

## 一句话状态

MetaLoop v3.4 是 **minimal / orthogonal / event-triggered / implementation-first / Git-backed / SQLite-canonical**
外环控制系统：Git 证明 workspace 机械变化，SQLite 保存 durable target、current state、
feedback、authority 和 recovery；fresh-context Review 只在语义风险无法完全机械判定时出现。
普通局部修改、文档同步和测试修复默认不进入 MetaLoop，直接使用 Git + 项目 verifier。

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
- `attempt finish` 自动 claim 当前 Attempt delta，并可从 checkpoint、Evidence、sealed
  Attempt 或 Evaluation 幂等恢复；defer/assign 是例外，不再逐文件登记普通代码。
- 最新 terminal same-Task Attempt 的 non-conflicted workspace 可被下一 Attempt 自动继承；
  immutable start record 保存 source baseline、checkpoint、adopted hashes 与逐路径
  provenance；新 Contract scope 在 Attempt 创建前校验全部 carried paths。
- `protocol_activity` 从现有记录派生 counts 和 routine warning，不增加遥测表或状态写入。
- `task begin` 的 create/contract/select/start 使用嵌套 savepoint 保持原子；即使库调用者
  捕获内部异常，Contract 或 validator 输入错误也不会留下空 Task。新 Contract 的 user
  authority 只能来自 assurance final decision。
- Tier 1 可由 title、plan 和 `--check` 自动生成最小 Contract；只有 Tier 2/3 需要完整
  Contract JSON。
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
- Tier 3 Review report、可选 context label、Contract、Attempt、Evidence 和 parent Evaluation
  直接进入 Review content hash，不使用未绑定 DecisionEvent sidecar。
- Tier 3 降级逐 trigger 检查 approved structured reviewer report 的
  `resolved_trigger_ids`；普通 passing validator 不自动解除 trigger。
- context 只作为可选诊断 metadata；不要求 host attestation、independence 证明或
  `METALOOP_HOST_CONTEXT_ID`。
- 项目 verifier 与测试拥有技术正确性，MetaLoop 只记录完成证明、恢复状态和必要 Review，
  不复制项目 schema 或领域语义。
- 后续 Tier 0 Git 修改不会让默认 Project status 把历史 completed Task 判为 integrity
  failure；显式 Task integrity 仍可复核旧封存结果与当前文件。
- integrity 派生为 `valid`、active-work `not_yet_reconciled` 或真实 `violated`；兼容
  `passed` boolean 保留，所有 lifecycle gate 仍要求 aligned。
- brief/RecoveryView 只派生当前 `active_chain`；等待 reviewer 时同时提供无权威、无持久化的
  最小 `review_handoff`，避免 Agent 手工拼装 claim、trigger、Evidence 和 report template。
- checkpoint 可保存一个非权威 `external_ref` locator 与 checkpoint identity；外部系统继续
  拥有 epoch、liveness、metrics 和 completion truth，MetaLoop 不调度或监控。
- Workspace observation 同时隔离临时 index 和 object directory，真实 Git metadata 在
  stamp/status/recovery 前后保持不变。
- `observe --format full|brief` 保持兼容；brief 增加 control status、ordered authority、
  typed transition、blocker、trigger proofs、assurance 和 next action。

## Alpha 复测重点

1. 普通局部修复是否只需 `begin`、一次编辑和可重复的 `finish`。
2. commit 后是否保持 fresh/aligned 且没有 clean-head promotion Task。
3. validator 失败、review 修改和 Contract 修订是否留在同一 Task。
4. Tier 2 的完整机械证明是否避免不必要 reviewer。
5. Tier 3 fresh-context Review 是否发现 Worker 与其测试共享的遗漏。
6. active Evaluation head 的 typed next transition 是否在恢复后可直接执行。
7. 用户是否只在真实例外和明确保留的最终决策上被中断。
8. Tier 0 通过外部试用记录校准，Tier 1-3 通过 SQLite 和用户反馈校准。
9. aborted、rejected 或 stale sealed work 是否无需还原文件即可自动继承。
10. implementation work 是否保持 Tier 0/1，只有最终正式主张才触发 reviewer。
11. active Attempt 的普通 ahead 是否显示 `not_yet_reconciled` 而非误报损坏。
12. reviewer 是否直接使用派生 handoff，且外部运行引用是否只降低恢复定位成本。

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
