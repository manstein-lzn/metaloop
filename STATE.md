# MetaLoop 当前状态

最后更新：2026-07-20

## 一句话状态

MetaLoop v2 已实现为 **Skill-only / SQLite-backed Durable Work Graph**。
新任务使用 `.metaloop/metaloop.db`；旧 v1 artifact 流程只在 v2 初始化前兼容，
并可通过重新验证后原子迁移。

## 已实现

- Project、Task、parent/dependency DAG 和显式 execution scope。
- immutable ContractRevision，mutable lifecycle 已移出合同。
- open/sealed/aborted Attempt、append-only action/checkpoint/evidence。
- Task `state_version` compare-and-swap 和单 open Attempt 唯一约束。
- Attempt fingerprint、`retry_of_attempt_id` 和 `retry_reason`。
- content-bound automated Evaluation、independent Review 和 user authority chain。
- 唯一 `acceptance_head_ref` 和 fail-closed completion resolver。
- verified artifact binding，文件变化会使旧 Evaluation 无法完成 Task。
- Attempt evidence 在 seal/verify/accept 三处重验；默认 Task 的 evidence drift
  会使 integrity 失败。
- 混合 reviewer/user 手工 gates 会持久化全部 required authorities，缺一不可。
- task/project scoped DecisionEvent 和单调 event sequence。
- DecisionEvent 主体隔离、查询/导出和 supersession-resolved current decisions。
- bounded RecoveryView，机械分类 `fresh | stale | incomplete`，并绑定依赖 heads、
  acceptance chain 与 current project/task decisions。
- thread Task assignment/focus stack，default Task 仅用于导航。
- repair Task 的 `spawned_by_event_id`、可移除 dependency 和 thread assignment 查询。
- legacy import 先重新验证 v1 内容和 validators，再以单事务导入；不可信批准为
  `legacy_unbound`。
- v2 workspace 禁止 v1 mutable writes；`event append` 显式路由到 v2 Task。
- `ready_to_accept` 明确阻止通过后再次启动重复 Attempt。
- rebuildable `.metaloop/v2/` JSON/Markdown projections。
- v2-aware status、observe 和只读 dashboard。
- v1 ReviewResult 绑定 ExecutionReport identity/hash，旧 review 不再跨执行复用。
- canonical `src/metaloop_core` 生成到 Skill，portable kernel 已变为薄启动器。

## 产品边界

- Codex 负责理解、设计、编码、运行、诊断和策略。
- MetaLoop 负责身份、合同、证据链、恢复、验证和审计。
- SQLite 负责事务真相，不负责 agent 调度。
- 不保存聊天 transcript，不引入向量库、daemon、watcher 或 agent pool。
- 不承诺完全识别语义重复；内核只硬检测精确 replay。
- 不增加 deadline、priority、看板等项目管理产品面。

## 当前试用重点

1. 上下文压缩发生在 open Attempt 中时，RecoveryView 是否足够恢复。
2. 同一 project 多 Task 切换是否保持低心智负担。
3. fingerprint 是否误报或漏掉用户实际关心的重复工作。
4. DecisionEvent 和 resume projection 的信息密度是否合适。
5. SQLite writer conflict 和显式 Task scope 是否符合真实 multi-thread 使用。

## 验证命令

```bash
python3 tools/sync_skill_core.py
python3 tools/check_skill_core_sync.py
python3 tools/check_core_import_boundary.py
.venv/bin/pytest -q
git diff --check
```

不要在真实反馈前继续扩展 scheduler、自动路由或复杂 project-management 状态。
