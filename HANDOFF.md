# MetaLoop v3.2 Handoff

最后更新：2026-07-22

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
routine: $metaloop -> task begin -> Work -> attempt finish -> accepted
governed: Frame -> Attempt/checkpoints -> Evidence -> verify -> accept
high assurance: governed -> fresh-context structured Review -> accept
both: one SQLite ontology + live-derived RecoveryView + exact Git alignment
control: verify -> reviewer -> reserved user -> accept; terminal failure -> repair Attempt
```

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
- Review 只能扩展 active Evaluation head；accept 只能消费 active head。
- active head transition 递增 Task CAS；旧 Attempt、乱序 authority 和 terminal Review 不能
  重新成为 acceptance 候选，历史坏链通过新 Attempt 恢复。
- Tier 3 report 必须 hash-bound 且由不同 verified host context 提供；CLI `--context-id`
  只是 manual/unverified 标签。
- Tier 3 trigger 降级需要逐项绑定 mapped executable validator 或 verified Review proof。
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

下一步让原 alpha Agent 继续真实任务，优先验证 Tier 1 操作数、Tier 2 reviewer false
positive、Tier 3 finding yield、context recovery 重复工作和不必要用户中断。
