# MetaLoop 开发计划

最后更新：2026-05-03

## 当前方向

MetaLoop v3 MVP 只实现一条主线：

```text
MissionSpec -> GoalContract -> Codex goal runtime -> ExecutionReport -> VerificationResult -> SoftReviewDecision -> optional worker repair -> final VerificationResult
```

核心边界：

- MetaLoop 负责 Co-Design、MissionSpec、GoalContract、验收、证据和审计。
- Codex 负责代码探索、实现、调试、测试和长任务推进。
- MetaLoop 不默认运行多 Agent role pipeline。
- MetaLoop 不给 Codex 设计细粒度工具清单。
- MetaLoop 不把 Codex 认为完成等同于 Mission verified。

权威设计见：

- `docs/mission_capsule_constitution.md`
- `docs/minimal_v3_codex_goal_architecture.md`
- `docs/architecture_v3_goal_runtime.md`

其中 `docs/mission_capsule_constitution.md` 是宪法层：后续任意实现阶段可以简化，但不能违反其中关于 Mission Capsule、权限、证据、验收、上下文、attempt history、repair/redesign/decomposition 的不变量。

## 已完成

- Mission Capsule v1 schema 首版：
  - `MissionCapsule`
  - `DomainProfile`
  - `VerificationPlan`
  - `EvidencePlan`
  - `EvidenceRecord`
  - `AttemptRecord`
  - `LifecycleState`
  - `ClosureOutcome`
  - `MissionSpec -> MissionCapsule -> GoalContract` 兼容编译路径
  - goal runtime 写出 `.metaloop/mission_capsule.json`
- `GoalContract`
- `ExecutionReport`
- `VerificationResult`
- `MissionSpec -> GoalContract` 编译
- Codex-facing goal objective 渲染
- `metaloop compile`
- `metaloop verify`
- `metaloop status`
- goal-style `metaloop resume --mode goal`
- `src/metaloop/goal_runtime.py`
- `CodexExecGoalRuntimeAdapter`
- `SoftReviewDecision`
- `RuleSoftReviewer`
- `CodexSoftReviewer`
- reviewer route schema：
  - `complete`
  - `ask_worker_to_fix`
  - `ask_architect_to_rethink`
  - `ask_planner_to_replan`
  - `ask_brainstormer_for_options`
  - `fail`
- worker repair loop：`ask_worker_to_fix` 会触发一次 Codex repair，然后重新验收。
- focused route agents：`ask_architect_to_rethink` / `ask_planner_to_replan` / `ask_brainstormer_for_options` 会先调用对应 focused agent 产出修复指导，再交给 Codex worker 修复。
- `metaloop run` 在 auto 模式下对 mission 默认走 goal-style 单 Codex agent runtime
- 旧多 Agent role pipeline 保留为 `--mode rigorous` 或显式 `--worker`
- `.metaloop/` 结构化运行文件：
  - `mission.json`
  - `goal_contract.json`
  - `goal_prompt.md`
  - `execution_report.json`
  - `verification_result.json`
  - `run.json`
  - `runs/<run_id>/codex_events.jsonl`
- hard validator 与 ExecutionReport 交叉验收
- 不可代码化验收的显式分类：
  - `completed_pending_human_acceptance`
  - `completed_with_soft_acceptance`
  - `completed_with_limitations`

## 当前最高优先级

### Phase 0：Mission Capsule v1 Schema

状态：schema 首版已完成，继续做 runtime ledger 集成和 CLI 打磨。

目标：把理论收敛后的 Mission Capsule Constitution 转化为最小可实现 schema，不引入完整 SKS/SCP/ITC/AMP。

交付：

- 已完成：`MissionCapsule`
- 已完成：`DomainProfile`
- 已完成：`VerificationPlan`
- 已完成：`EvidencePlan`
- 已完成：`EvidenceRecord`
- 已完成：`AttemptRecord`
- 已完成：`LifecycleState`
- 已完成：`ClosureOutcome`
- 已完成：`MissionSpec -> MissionCapsule -> GoalContract` 兼容编译路径
- 剩余：把 ExecutionReport / VerificationResult / SoftReviewDecision / repair attempt 写入 Capsule ledger

验收：

- 已覆盖：locked intent / acceptance 不能被 executor 弱化。
- 已覆盖：permissions 不能无记录扩张。
- 已覆盖：evidence 和 attempts append-only。
- 已覆盖：repair 不能改变 Capsule normative contract。
- 已覆盖：redesign 必须显式 Capsule revision。
- 已覆盖：current v3 `metaloop design && metaloop run` 主线保持可用。

### Phase 1：Resume Polish

目标：让 goal-style runtime 的恢复体验更细。

交付：

- 区分恢复阶段：仅 verify、soft review、repair、重新执行。
- `.metaloop/run.json` 作为恢复入口已经可用，继续增强策略选择。

验收：

- 中断后可以根据 `.metaloop/run.json` 和 `verification_result.json` 选择最小恢复动作。
- 缺少 ExecutionReport、Codex 失败、final human acceptance pending 都能清楚恢复或报告。

### Phase 2：Codex Goal Adapter Replacement Point

约束保持不变：

- 当前 Codex CLI `0.128.0` 没有非交互式 `codex goal` 子命令。
- `/goal` 当前是交互式 TUI 功能。
- 因此 adapter 必须保持可替换：
  - 有稳定 `/goal` API 时使用真正 goal runtime。
  - 暂时可用单次 `codex exec` 承载 GoalContract。

已完成当前替代实现：`CodexExecGoalRuntimeAdapter`。

后续只替换 adapter 传输层，不改变 MissionSpec / GoalContract / ExecutionReport / VerificationResult。

### Phase 3：CLI 收敛

目标：用户只需要：

```bash
metaloop design
metaloop run
metaloop status
metaloop verify
```

剩余交付：

- `metaloop compile` 保留为诊断命令。

验收：

- 新用户在一个 git workspace 中执行 `metaloop design && metaloop run` 即可跑通。
- `run` 时有实时状态输出。
- 断开后可恢复或至少可明确显示最近状态。

### Phase 4：Co-Design 面向 GoalContract 优化

目标：Co-Design 直接产出适合 Codex goal runtime 的 MissionSpec。

交付：

- Co-Design reviewer 增加 GoalContract readiness 检查。
- 引导用户把验收拆成：
  - hard validators
  - soft review
  - evidence
  - final human acceptance
- human acceptance 不参与运行中的 agent 路由；reviewer/scheduler 只能决定 complete、返工、架构重想、重新规划、补充探索或 fail。

验收：

- `metaloop design` 结束后生成的 mission 可直接 compile。
- 文件型交付物优先生成 file_exists/file_contains/command/schema 验收。
- 无法自动验收的内容被明确标注，不伪装成 verified。

## Backlog，不属于 v3 MVP

以下内容保留为原则和后续研究，不进入当前 MVP 实现：

- full Agent Message Protocol
- full Structured Context Protocol
- full Structured Knowledge System
- full Intent Transmission Contract
- generic WorkerBackend ecosystem
- recursive MetaLoop spawning
- 默认多 Agent rigorous pipeline
- explicit Codex tool allowlist
- 完整权限隔离知识库
- 静态 RAG 系统

触发条件：只有当 `MissionSpec -> GoalContract -> Codex -> VerificationResult` 主线出现明确瓶颈时，才引入其中最小必要部分。

## 不做

- 不在 Kernel 内递归启动子 MetaLoop。
- 不把不可代码化验收标记为 `completed_verified`。
- 不默认使用 `danger-full-access`。
- 不把聊天历史当 operational memory。
- 不用大而全架构替代当前可运行主线。
- 不实现 full SKS/SCP/ITC/AMP 后再交付 Capsule v1；先落地最小 Capsule。
