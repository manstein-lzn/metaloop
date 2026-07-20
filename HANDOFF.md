# MetaLoop v3.1 Handoff

最后更新：2026-07-20

## 快速恢复

1. `README.md`
2. `STATE.md`
3. `docs/metaloop_final_architecture_upgrade_spec.md`
4. `docs/metaloop_v3_1_alpha_optimization_spec.md`
5. `docs/metaloop_v3_trial_guide.md`
6. `skills/metaloop/SKILL.md`
7. `git status`、最近提交和 `project status`

## 主路径

```text
routine: $metaloop -> task begin -> Work -> attempt finish -> accepted
governed: Frame -> Attempt/checkpoints -> Evidence -> verify -> Review -> accept
both: one SQLite ontology + live-derived RecoveryView + exact Git alignment
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

下一步让原 alpha Agent 继续真实任务，优先验证协议命令数、promotion Task 是否归零、
局部失败是否留在同一 Task，以及高风险 authority chain 是否保持有效。
