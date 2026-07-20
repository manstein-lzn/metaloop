# MetaLoop v3.1 当前状态

最后更新：2026-07-20

## 一句话状态

MetaLoop v3.1 是 **risk-proportional / Skill-only / Git-backed / SQLite-canonical**
durable work protocol：Git 证明 workspace 机械变化，SQLite 保存 Task history、evidence、
authority 和 recovery。

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

## Alpha 复测重点

1. 普通局部修复是否只需 `begin`、一次编辑和 `finish`。
2. commit 后是否保持 fresh/aligned 且没有 clean-head promotion Task。
3. validator 失败、review 修改和 Contract 修订是否留在同一 Task。
4. reviewer/user authority 是否只出现在语义或正式 acceptance。
5. context compaction、Task switch 和 repair child 是否继续可靠恢复。
6. 高风险阶段的 Evidence、stable inputs 和线性 authority chain 是否保持原保证。

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
