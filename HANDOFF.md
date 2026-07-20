# MetaLoop v3 Handoff

最后更新：2026-07-20

## 快速恢复

1. `README.md`
2. `STATE.md`
3. `docs/metaloop_final_architecture_upgrade_spec.md`
4. `docs/metaloop_v3_trial_guide.md`
5. `skills/metaloop/SKILL.md`
6. `git status`、最近提交和 `project status`

## 主路径

```text
$metaloop -> Frame -> ContractRevision -> Attempt baseline WorkspaceStamp
          -> Work + checkpoint -> Reconcile -> Adapt
          -> Evidence -> seal -> verify -> Review -> accept
          -> RecoveryView fresh/aligned
```

## 开发纪律

- Git 是运行前提；remote 和 clean worktree 不是运行前提。
- `.metaloop/metaloop.db` 是 protocol truth；projection 可重建。
- lifecycle gates 都要检查 WorkspaceStamp alignment。
- ahead 必须 claim/defer/assign/conflict；不猜 ownership。
- HEAD/worktree identity 变化是 conflicted；Git failure/scan limit 是 unknown。
- managed outputs 必须是 exact Evidence；stable inputs 漂移 fail closed。
- one worktree 只允许一个 open mutating Attempt。
- 子 Task 不会隐式完成 parent；approved chain 才能 accept。

## 验证

```bash
python3 tools/sync_skill_core.py
python3 tools/check_skill_core_sync.py
python3 tools/check_core_import_boundary.py
python3 tools/check_v3_surface.py
pytest -q
git diff --check
```

下一步直接用 `$metaloop` 运行真实任务，记录 context compaction、Task switch、repair
branch、Git reconcile、authority chain 和 host safe point 的具体反馈。
