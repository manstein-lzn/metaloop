# MetaLoop v3 当前状态

最后更新：2026-07-20

## 一句话状态

MetaLoop v3 是 **Skill-only / Git-backed / SQLite-canonical** durable work protocol：
Git 证明 workspace 机械变化，SQLite 保存 Task history、evidence、authority 和 recovery。

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

## 试用重点

1. context compaction 后 RecoveryView 是否足以恢复下一步与 changed paths。
2. Task switch、repair child、dependency 和 one-worktree 规则是否自然。
3. ahead/conflicted/unknown diagnostics 是否让 reconcile 可执行。
4. Progressive Design 的收益是否超过额外设计负担。
5. managed outputs、stable inputs 和线性 authority chain 是否阻止误验收。
6. clean target 安装和 long-task dogfood 的实际摩擦。

## 稳定边界

- GitHub/remote repository 不是运行依赖。
- Git 不判断语义正确性；SQLite 不复制项目架构正文。
- declared paths 不是 sandbox；强制隔离由 host hook、sandbox 或 wrapper 提供。
- 不从 prose 推断 repair、redesign、pivot 或 ownership。
- 不建立第二个 Task ontology 或 active compatibility path。

## 验证

```bash
python3 tools/sync_skill_core.py
python3 tools/check_skill_core_sync.py
python3 tools/check_core_import_boundary.py
python3 tools/check_v3_surface.py
pytest -q
git diff --check
```
