# MetaLoop Handoff

最后更新：2026-07-20

## 快速恢复

新 session 应先读取：

1. `README.md`
2. `STATE.md`
3. `ROADMAP.md`
4. `docs/metaloop_task_history_architecture_review.md`
5. `docs/metaloop_v2_trial_guide.md`
6. `skills/metaloop/SKILL.md`
7. `git status` 与最近提交

当前产品叙事是统一的：MetaLoop 是 Codex 的轻量开发治理协议；深度设计与 Progressive
Design 属于 Skill 的智能纪律，项目文档拥有具体架构认知，v2 SQLite work graph 拥有
Task、Attempt、证据、验证、决策与恢复真相。

## 当前主路径

```text
$metaloop Skill
  -> deep design / Progressive Design
  -> thin portable kernel
  -> vendored canonical metaloop_core
  -> .metaloop/metaloop.db
  -> Project / Task / ContractRevision / Attempt / Evaluation / DecisionEvent
  -> freshness-checked RecoveryView and read-only projections
```

旧 Mission Capsule 只作为 v1 read/migration input。旧 engineering governance 在迁移时
规范化进 V2 ContractRevision；v2 初始化后，v1 mutable commands 必须 fail closed。

## 开发纪律

- 修改 canonical core 后运行 `python3 tools/sync_skill_core.py`。
- `skills/metaloop/scripts/metaloop_kernel.py` 必须保持薄启动器。
- 不在 Skill 和 core 中硬编码项目任务、数据集、指标或业务规则。
- 不从自由文本机械推断 repair/redesign 等语义决策。
- v2 mutation 必须显式指定 Task/Attempt/Evaluation，并使用 Task state version。
- sealed Attempt、Evaluation、DecisionEvent 和 ContractRevision 必须保持不可变与内容绑定。
- evidence 在 seal、verify、review、accept 前必须重新校验。
- RecoveryView stale 时先刷新，再恢复昂贵工作。
- parent Recovery 必须因 dependency head 变化而 stale。
- 子 Task 完成不能隐式完成父 Task。
- approved chain 显示 `ready_to_accept` 时不得再创建重复 Attempt。
- governance stable inputs 漂移时 fail closed；managed outputs 必须是 exact Attempt evidence。

## 验证

```bash
python3 tools/sync_skill_core.py
python3 tools/check_skill_core_sync.py
python3 tools/check_core_import_boundary.py
.venv/bin/pytest -q
git diff --check
```

## 安装

仓库 Skill 位于 `skills/metaloop/`，安装目标为
`${CODEX_HOME:-$HOME/.codex}/skills/metaloop`。发布时替换整个 Skill，不单独复制文件。
安装与 v2 smoke test 见 `docs/codex_install_metaloop_skill.md`。

## 下一步

直接用真实任务试用：

```text
Use $metaloop. 我想完成 <真实开发任务>。
```

重点记录上下文压缩恢复、Task/Attempt 边界、任务切换、repair branch、重复判定、
Progressive Design 负担和 governance 价值。只有同类失败重复出现后才调整架构。
