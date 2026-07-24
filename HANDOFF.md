# MetaLoop v3.4 Handoff

最后更新：2026-07-23

## 快速恢复

1. `README.md`
2. `STATE.md`
3. `AGENTS.md`
4. `docs/metaloop_v3_2_reliability_upgrade_spec.md`
5. `docs/metaloop_final_architecture_upgrade_spec.md`
6. `docs/metaloop_v3_trial_guide.md`
7. `skills/metaloop/SKILL.md`
8. `git status`、最近提交和 `observe --format brief`

## 主路径

```text
routine: $metaloop -> task begin --check <project verifier> -> Work -> resumable attempt finish -> accepted
governed: Frame -> Attempt/checkpoints -> Evidence -> verify -> accept
high assurance: governed -> fresh-context structured Review -> accept
both: one SQLite ontology + live-derived RecoveryView + exact Git alignment
control: verify -> reviewer -> reserved user -> accept; terminal failure -> repair Attempt
```

普通局部修改、文档同步和测试修复默认走 Git + 项目 verifier，不创建 MetaLoop Task。
只有持久恢复、任务切换、正式封存或真实语义 Review 才进入上面的 durable path。

## 开发纪律

- Git 是运行前提；remote 和 clean worktree 不是运行前提。
- `.metaloop/metaloop.db` 是 protocol truth；projection 可重建。
- lifecycle gates 都要检查 WorkspaceStamp alignment。
- ahead 必须 claim/defer/assign/conflict；不猜 ownership。
- exact direct commit promotion 可保持 aligned；reset/amend/branch switch、额外内容和
  dirty post-commit 是 conflicted；Git failure/scan limit 是 unknown。
- managed outputs 必须是 exact Evidence；stable inputs 漂移 fail closed。
- one worktree 只允许一个 open mutating Attempt。
- Contract v1.1 assurance 由内核规范化，Tier 3 自动需要 reviewer。
- `task begin` 的 create/contract/select/start 通过嵌套 savepoint 保持单事务语义；输入
  校验或 Attempt start 失败不能遗留空 Task。
- `attempt finish` 自动 reconcile current-Attempt delta、绑定 managed Evidence、seal、verify，
  并可在部分完成后重复执行；普通路径不逐文件 claim。
- 最新 terminal same-Task Attempt 的 non-conflicted workspace 自动成为下一 Attempt baseline，
  并从 source baseline/checkpoint 到 adopted workspace 保存逐路径 provenance；当前 Contract
  scope 在 Attempt 创建前重新校验 carried paths。
- Review 只能扩展 active Evaluation head；accept 只能消费 active head。
- active head transition 递增 Task CAS；旧 Attempt、乱序 authority 和 terminal Review 不能
  重新成为 acceptance 候选，历史坏链通过新 Attempt 恢复。
- Tier 3 report 必须 hash-bound 且为结构化 Review；context label 只用于诊断，不是接受门禁。
- Tier 3 trigger 降级需要 approved Review report 逐项列出 `resolved_trigger_ids`；普通
  validator 不自动解除风险记忆。
- user authority 只能在 Contract assurance 中作为最终决策声明，不能通过 validator 或
  resource gate 旁路进入 Evaluation chain。
- 项目 verifier 负责技术正确性，MetaLoop 只负责完成证明和恢复，不复制领域检查。
- integrity 将 active Attempt 的普通 ahead 投影为 `not_yet_reconciled`，只有结构、identity、
  hash、Evidence、stable input、conflict 或 closed-claim drift 才是 `violated`。
- brief/recovery 只显示当前 active Evaluation lineage；`review:reviewer` 时自动派生最小
  `review_handoff`，不新增 packet 状态或命令。
- 可选 external locator 只用于恢复定位；进度、存活和完成仍由外部 manifest 负责。
- 子 Task 不会隐式完成 parent；approved active chain 才能 accept。

## 验证

```bash
python3 tools/sync_skill_core.py
python3 tools/check_skill_core_sync.py
python3 tools/check_core_import_boundary.py
python3 tools/check_v3_surface.py
pytest -q
git diff --check
```

下一步让原 alpha Agent 继续真实任务，优先验证 Tier 1 操作数、finish 重试、workspace
自动继承、Tier 2 reviewer false
positive、Tier 3 finding yield、context recovery 重复工作和不必要用户中断。
