# MetaLoop Handoff

最后更新：2026-07-20

MetaLoop v2 已落地。后续 session 应先读取：

1. `README.md`
2. `STATE.md`
3. `docs/metaloop_task_history_architecture_review.md`
4. `docs/metaloop_v2_trial_guide.md`
5. `skills/metaloop/SKILL.md`
6. `git status` 与最近提交

## 当前主路径

```text
$metaloop Skill
  -> thin portable kernel
  -> vendored canonical metaloop_core
  -> .metaloop/metaloop.db
  -> Task / ContractRevision / Attempt / Evaluation / DecisionEvent
  -> RecoveryView and read-only projections
```

## 开发纪律

- 修改 `src/metaloop_core/` 后运行 `python3 tools/sync_skill_core.py`。
- 不直接编辑 `skills/metaloop/lib/metaloop_core/`。
- 新协议语义只进入 canonical core，不进入 thin script。
- 所有 Task mutation 必须 CAS；所有 Evaluation 必须绑定 immutable subject hash。
- v1 compatibility 只在没有 v2 DB 时可写；v2 workspace 中旧写面必须 fail closed
  或显式路由到 Task。
- Legacy review 缺少 execution binding 时必须保留 `legacy_unbound`。
- Dashboard、observe 和 export 保持只读。
- Routing/activation 保持 one-shot，不得演化成 daemon 或 scheduler。

## 必测反例

- old review + new ExecutionReport 不得 completed_verified。
- verified artifact 修改后不得通过旧 acceptance chain。
- stale Task version 必须冲突。
- 同 Task 第二个 open Attempt 必须失败。
- exact fingerprint replay 必须要求 retry reason。
- stale RecoveryView 必须被检测。
- child completion 不得自动完成 parent。
- legacy_unbound 不得授予 v2 completion。
- Attempt evidence drift 必须阻止 verify/accept，并污染默认 Task integrity。
- 混合 reviewer/user gates 必须全部出现在同一 acceptance chain。
- DecisionEvent 的 Attempt/Evaluation 不得跨 Task 或悬空。
- cancelled Task 不得被旧 Evaluation 复活。
- parent Recovery 必须因 dependency head 变化而 stale。
- fresh Recovery 必须仍携带 current project/task decisions。
- approved chain 必须显示 `ready_to_accept`，不得建议重复 Attempt。
- v2 workspace 不得写 v1 event/context/thread/capsule 真相。

## 安装

仓库 Skill 已生成到 `skills/metaloop/`。本机安装时同步整个目录到
`${CODEX_HOME:-$HOME/.codex}/skills/metaloop`，递归清除缓存后比较完整目录，并从
安装路径运行 portable smoke tests。
