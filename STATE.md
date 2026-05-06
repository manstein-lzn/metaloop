# MetaLoop 当前状态

最后更新：2026-05-06

## 一句话状态

MetaLoop 当前是可用的本地 Alpha，已经落地极简 v3 主路径，并进入 v3.5 Spec Discipline + Workflow Discipline：`Co-Design -> MissionSpec -> MissionCapsule -> GoalContract -> 普通 Codex agent goal-style runtime -> ExecutionReport -> VerificationResult -> SoftReviewDecision -> repair/redesign/complete`。

架构理论层已经收敛为 Mission Capsule Constitution，且已落地 Mission Capsule v1 主路径：`MissionSpec -> MissionCapsule -> GoalContract -> runtime evidence/attempt/closure ledger` 可用；ITC/SCP/SKS/AMP 仍作为 Capsule 周边支持层和 backlog。

产品入口层已开始从 one-shot CLI 过渡到 long-running shell：默认 `metaloop` 现在进入第一版 Rich prompt-loop shell，并通过 `@openai/codex-sdk` 启动持久 Codex UserAgent thread。这个 agent 先理解当前项目、和用户对话，再输出受控的 MetaLoop action。

## 当前架构决策

- MetaLoop 负责 Co-Design、MissionSpec、GoalContract、VerificationResult、证据和审计。
- Codex 负责探索、写代码、调试、测试和长任务推进。
- Codex `/goal complete` 或 Codex 自述完成不能等同于 MetaLoop verified completion。
- MetaLoop 不内建递归，不自动启动子 MetaLoop。
- 多 MetaLoop 编排交给用户或未来 Orchestrator。
- 最终面向人的默认入口应升级为 long-running TUI shell：用户运行 `metaloop` 后留在一个持续会话中完成 design/run/status/verify/resume/revise，而不是记忆多个一次性命令。第一版 prompt-loop shell 已落地，后续继续打磨状态流和 revision flow。
- 已新增专门对接用户的 UserAgent / InterfaceAgent v1。默认是 Codex SDK-backed UserAgent：Python shell 启动 `src/metaloop/codex_sdk_bridge.mjs`，Node bridge 使用 `@openai/codex-sdk` 创建/保留 thread；Codex 理解当前项目和用户输入，输出 `ProposedAction`；shell 负责确认并调用底层 `design/run/status/verify/resume`。`codex exec` UserAgent 保留为 `--user-agent exec` 兼容模式，本地规则 UserAgent 只保留为 `--user-agent local` 调试模式。
- 旧的 brainstormer/planner/worker/reviewer/scheduler 多 Agent pipeline 保留为 `--mode rigorous` 或显式 `--worker` 诊断路径。
- v3 MVP 不实现完整 SKS/SCP/ITC/AMP 协议栈；这些文档保留为原则和 backlog。
- 不可代码化验收必须显式分类为 soft review、final human acceptance 或 limitations，不能伪装成 `completed_verified`。
- human acceptance 只发生在内部工作完成后的最终用户确认阶段，不是运行中 reviewer/scheduler 的 agent 路由。
- 内部 reviewer 只做运行路由：complete、ask_worker_to_fix、ask_architect_to_rethink、ask_planner_to_replan、ask_brainstormer_for_options、fail。
- 聊天历史不是 operational memory。MetaLoop 的当前状态来自结构化文件；历史学习应来自 Git-backed attempt history。
- LLM 不需要回滚工作区也能读取历史尝试：使用 `git log`、`git show <commit>`、`git diff <commitA>..<commitB>`、`git show <commit>:path` 即可只读检查历史版本。
- 后续应把重要尝试记录为结构化 commit message，并可选写入 `.metaloop/attempts/<attempt_id>.json`，作为 Context Compiler 的历史证据来源。
- `docs/mission_capsule_constitution.md` 是后续任意阶段开发的宪法级参考。实现可以分阶段简化，但不能违反其中的不变量。

## 当前实现能力

### 已有 Alpha 能力

- `metaloop design`：Co-Design v2，默认 Codex co-designer，Rich 交互，resume；流程为 requirement discovery -> brainstorm expansion -> human design review -> interactive refinement -> contract lock。用户确认 `approve` / `lock` / `完成` / `确认` 后才写出 locked MissionSpec 和 Capsule/GoalContract 预览；非交互/JSON 模式只有在 reviewer 通过且 brainstorm 无任务特定 unresolved decisions 时才允许自动锁定。
- Co-Design Agent availability invariant：只要用户选择或默认进入 Codex co-designer / brainstormer / answerer，Codex agent 不可用、无 final message、输出 JSON 无效或 brainstorm 输出不可用时必须直接失败并展示原因；不得静默回落到 rule backend。Rule backend 只允许用户显式选择或非交互脚本兼容路径使用。
- Co-Design for Verification v1：文件型交付物会优先生成 `file_exists` / `file_contains` / `schema` / `command` 等可检查验收；不可代码化要求会进入 `llm_review` 或最终 `manual` human acceptance；工程、算法研究、Codex skill、深度研究任务会写入 `context.domain_profile_id`。
- Co-Design Spec Discipline v1：MissionSpecReviewer 会保守检查 `scope_too_broad`、`missing_non_goals`、`missing_evidence_path`、`weak_acceptance`、`unclear_authority`、`missing_tradeoff_review`、`needs_decomposition`，体现 agree-before-build 和 brainstorming gate；高风险/明显宽泛任务才 blocking，普通轻量任务不会因缺 non-goals 被阻断。
- Co-Design Contract Quality Gate v1：`file_exists` / `schema` / `file_contains` 等 path-based hard validators 必须指向具体 repo path，不能把自然语言 deliverable/prose/行为短语当 `validation_target`；自动推断会从 “Create docs/guide.md ...” 中抽取 `docs/guide.md`，但会拒绝 `tabs/newlines`、`input/output` 这类概念对。目录 target 必须显式写成 `src/` 这种尾随 `/` 形式；无扩展 `foo/bar` 默认非法。contract lock 前无条件阻断 blocking review findings 和未被用户显式接受的任务特定 unresolved decisions，非 `--strict-review` 路径也不能写出 locked MissionSpec / design Capsule / GoalContract；runtime validator 也会拒绝 invalid path target，防止历史/手写 MissionSpec 伪造 artifact 后通过验收。
- `metaloop run`：发现/指定 mission 且未显式指定 worker 时，默认走 goal-style 单 Codex agent runtime，并保留 MissionSpec 文件中的 `run_id` 作为稳定 contract/capsule id；直接 intent 或显式 `--worker` 仍走经典 Kernel 并分配新的执行 run id。
- `metaloop verify`：当 workspace 存在 `.metaloop/run.json` 时，验证会优先使用最新 goal runtime 写出的 `.metaloop/mission.json` 和 ExecutionReport，避免用户拿原始 `metaloop.mission.json` 验证时遇到历史 run id mismatch。
- `metaloop list/show/resume`：SQLite runs/events/checkpoints。
- `metaloop status`：读取 workspace 的 MissionSpec、MissionCapsule、run manifest、VerificationResult 和 Codex events，显示 mission/run/capsule/verification 状态与下一步建议。
- `metaloop` / `metaloop shell`：第一版 long-running Rich prompt-loop shell。启动后读取 `.metaloop/` 结构化状态，展示 design、mission、capsule/run、verification、redesign、attempt history overview，然后调用 SDK-backed UserAgent 做启动对话/项目理解；循环接收自然语言或显式 action，确认后调用现有 `design/run/status/verify/resume` 命令路径。
- `CodexSdkUserAgent` v1：新增 `src/metaloop/user_agent.py` 和 `src/metaloop/codex_sdk_bridge.mjs`。默认 shell 通过 Node bridge 使用 `@openai/codex-sdk` 创建持久 thread，同一 shell 会话复用历史，并把 thread id 持久化到 `.metaloop/user_agent_thread.json`，重启 shell 后通过 `resumeThread(threadId)` 继续。Codex 需要时读取 README、manifest、Git 历史和关键文件来理解现存项目；返回严格 `ProposedAction` JSON，支持 `start_design`、`resume_design`、`run_current_mission`、`verify_current_run`、`show_status`、`resume_run`、`collect_feedback`、`propose_revision`、`apply_redesign`、`quit`。用户说“不满意/修改/重设计”时只收集 feedback / 指向 revision，不直接修改 locked contract；`redesign_required` 状态下“继续”不会变成普通 worker rerun。
- `CodexExecUserAgent` 保留为 `metaloop shell --user-agent exec` 兼容路径；`UserAgent` 本地规则映射仍存在，但只作为 `metaloop shell --user-agent local` 的 deterministic/debug fallback；默认路径不使用它伪装智能。
- `metaloop shell --reset-user-agent-thread`：只删除当前 workspace 的 `.metaloop/user_agent_thread.json` 并退出，相当于下次启动一个新的 user-facing Codex thread；不会删除 MissionSpec、Capsule、run、verification 或 attempt history。
- Goal-Style Resume v1：`metaloop resume --mode goal` 读取 `.metaloop/run.json` 和结构化 artifacts，terminal success 会跳过；缺失 ExecutionReport、failed/blocked verification、failed capsule closure 会明确说明原因并重跑 goal runtime。
- Repair / Redesign Capsule Semantics v1.5：`ask_worker_to_fix` 只做 implementation repair，不改 locked contract；repair prompt/VerificationResult 记录 `repair_attempt_index`、root cause/hypothesis discipline 和 failed fix summary；重复 worker repair 到第三次请求前会转 `redesign_required`。`ask_architect_to_rethink` / `ask_planner_to_replan` / `ask_brainstormer_for_options` 会生成包含结构化 `contract_delta` 的 `.metaloop/redesign_proposal.json`，Capsule 进入 `redesign_required`，status/resume 阻止它被当成普通 worker rerun。
- DomainProfile Evidence Obligations v1：engineering、algorithm_research、codex_skill_creation、deep_research 都带 evidence obligations；软 obligation 进入 evidence/report hints，工程 bugfix/public behavior 缺 regression/build/test evidence 会作为 required evidence failure。
- Prompt Pack v1：关键 prompt 模板已外置为 `prompts/co_design/*.md` 和 `prompts/run/*.md`，带 version/purpose/input_schema/output_schema/failure_policy/id/stage/required_variables metadata；当前 Co-Design brainstorm、Co-Design discovery/interviewer、run redesign focused route runtime、run soft reviewer 已接入 prompt pack。
- Prompt Compiler v3.6 Phase 0/1/2/3/4/5：已新增严格 `metaloop.prompt_pack` loader/compiler，prompt pack 补齐 id/stage/required_variables，hardcoded/runtime prompt builders 已有语义护栏测试；Phase 2 已将 `_build_codex_brainstorm_prompt` / `CodexCoDesignBrainstormer` 迁移到 `prompts/co_design/brainstorm.md`；Phase 3 已将 `_build_codex_interviewer_prompt` / `CodexCoDesignInterviewer` 迁移到 `prompts/co_design/discovery.md`；Phase 4 已将 `build_focused_route_prompt` 迁移到 `prompts/run/redesign.md`，保留 contract-level redesign、no edit、locked contract 禁令和 VerificationResult 注入；Phase 5 已将 `build_soft_review_prompt` 迁移到 `prompts/run/soft_reviewer.md`，保留 hard-validator authority、route enum、human-acceptance boundary、实际 `SoftReviewDecision` schema 注入和 MissionSpec/GoalContract/VerificationResult 注入。已迁移 prompt pack render failure 均不回退 hardcoded prompt。
- Codex exec adapter：JSONL 事件解析、output-schema fallback、`--no-output-schema`。
- Validators：file_exists、file_contains、command、schema。
- Rich CLI：mission 选择、状态输出、summary、review/failure panels。
- `metaloop run` 可见进度流：终端会保留阶段日志，包括 contract 编译、结构化 artifact、Codex turn/command、初始验收、reviewer route、repair attempt、最终验收；`--json` 仍保持纯 JSON。

### 计划中的产品形态升级

- Long-running TUI shell v1：已新增默认 `metaloop` 入口和 `metaloop shell`，启动后显示当前 workspace 的 mission/capsule/run/verification/redesign/attempt history，并允许用户持续交互。后续需要从 prompt-loop 升级更完整的状态流/命令面板。
- User-facing Agent v1：已新增 Codex SDK-backed 交互 agent，负责把“开始设计”“继续上次任务”“这次结果不满意”“现在卡在哪”这类自然语言转换为结构化 action。Codex SDK 不可用时 fail-fast，不静默回落到规则假智能。
- CLI 子命令继续保留：`metaloop design` / `run` / `status` / `verify` / `resume` 仍作为脚本、调试和 CI 入口。
- TUI 和 UserAgent 不创建平行状态系统；它们必须读写现有 `.metaloop/` structured artifacts。
- UserAgent 不能直接修改 locked MissionSpec、MissionCapsule 或 GoalContract；涉及范围、验收、权限变化时必须进入 revise/redesign 流程。
- Codex agent 不可用时必须 fail-fast，不允许静默降级为看似智能的规则问答。

### 已完成 v3 极简骨架

- `src/metaloop/capsule.py`
- `MissionCapsule`
- `DomainProfile`
- `VerificationPlan`
- `EvidencePlan`
- `EvidenceRecord`
- `AttemptRecord`
- `LifecycleState`
- `ClosureOutcome`
- `MissionSpec -> MissionCapsule -> GoalContract` 兼容编译路径
- `src/metaloop/goal.py`
- `GoalContract`
- `ExecutionReport`
- `VerificationResult`
- `compile_goal_contract`
- `render_goal_objective`
- `verify_mission`
- `metaloop compile`
- `metaloop verify`
- `metaloop status` structured inspect UX
- goal-style `metaloop resume --mode goal` structured resume
- `src/metaloop/goal_runtime.py`
- `CodexExecGoalRuntimeAdapter`
- `SoftReviewDecision`
- `RuleSoftReviewer`
- `CodexSoftReviewer`
- `RedesignProposal`
- `RedesignProposal.contract_delta`
- repair loop：reviewer 路由到 `ask_worker_to_fix` 时，默认 goal runtime 会给 Codex 一次 implementation-level repair prompt，然后重新验收；repair 不允许改变 locked Mission Capsule contract。第二次 repair prompt 会要求 root cause/hypothesis，第三次 worker repair 请求转 redesign gate。
- redesign proposal：reviewer 路由到 `ask_architect_to_rethink` / `ask_planner_to_replan` / `ask_brainstormer_for_options` 时，MetaLoop 会调用 focused route agent 产出 redesign guidance，写出 `.metaloop/redesign_proposal.json`，并把 Capsule 转到 `redesign_required`；v1 不自动改 MissionSpec / GoalContract / acceptance。
- goal runtime 会把 ExecutionReport、VerificationResult、SoftReviewDecision、AttemptRecord 和最终 closure decision 写回 `.metaloop/mission_capsule.json`。
- goal runtime 会额外写出 `.metaloop/attempts/<attempt_id>.json`，记录 git snapshot、changed files、validation、reviewer decision、failure/lesson，作为 Git-backed attempt history 的机器可读入口；当前不会自动 commit。attempt changed files 会过滤 `.metaloop/`、`metaloop.mission.json`、`__pycache__/`、`.pyc/.pyo` 等运行噪声。
- Goal prompt 已做保守压缩：运行时发送 compact MissionCapsule summary、完整 GoalContract 和最小 ExecutionReport 字段契约，而不是完整 Capsule JSON 加完整 Pydantic JSON Schema；locked contract、report path、mission_id 对齐等关键约束保持不变。
- 缺失或无效的必需 evidence 不再被归类为 `completed_with_limitations`；会进入 `failed`，避免把不可验收结果伪装成完成。
- `.metaloop/` 结构化当前运行文件：
  - `.metaloop/mission.json`
  - `.metaloop/design_transcript.jsonl`
  - `.metaloop/design_draft.md`
  - `.metaloop/design_review.md`
  - `.metaloop/design_decisions.json`
  - `.metaloop/design_lock.json`
  - `.metaloop/design_capsule.json`
  - `.metaloop/design_goal_contract.json`
  - `.metaloop/mission_capsule.json`
  - `.metaloop/goal_contract.json`
  - `.metaloop/goal_prompt.md`
  - `.metaloop/execution_report.json`
  - `.metaloop/verification_result.json`
  - `.metaloop/redesign_proposal.json`
  - `.metaloop/attempts/<attempt_id>.json`
  - `.metaloop/run.json`
  - `.metaloop/runs/<run_id>/codex_events.jsonl`

当前测试：

```bash
.venv/bin/pytest -q
# 228 passed
```

## 重要文档

- `docs/mission_capsule_constitution.md`：宪法层，定义 Mission Capsule、生命周期、权限、证据、验收、DomainProfile、AttemptRecord、repair/redesign/decomposition 边界。
- `docs/minimal_v3_codex_goal_architecture.md`：当前权威极简 v3 架构。
- `docs/metaloop_v3_5_spec_workflow_discipline.md`：v3.5 Spec Discipline + Workflow Discipline 增量说明。
- `docs/architecture_v3_goal_runtime.md`：v3 goal runtime 背景和验收模型。
- `DEVELOPMENT_PLAN.md`：近期开发计划。
- `ROADMAP.md`：产品路线。
- `README.md`：当前使用入口。
- `docs/codex-sdk集成文档.md`：Codex 集成文档。
- `docs/agent_message_protocol.md`：backlog/principle。
- `docs/structured_context_protocol.md`：backlog/principle。
- `docs/structured_knowledge_system.md`：backlog/principle。
- `docs/intent_transmission_contract.md`：backlog/principle。
- `docs/guided_autonomy_principle.md`：backlog/principle。

## 当前 CLI

常用：

```bash
metaloop
metaloop shell
metaloop design
metaloop run
metaloop compile
metaloop verify
metaloop status
metaloop design --resume
metaloop resume
metaloop list
metaloop show <run_id>
```

诊断：

```bash
metaloop compile --json
metaloop verify --json
metaloop run --json
metaloop show <run_id> --events
```

## 当前限制

- Codex CLI `0.128.0` 中 `/goal` 是交互式 TUI 功能；`codex --help` 和 `codex exec --help` 尚未暴露独立非交互式 `goal` 子命令。
- 因此当前 goal runtime 使用普通 `codex exec` 承载 GoalContract；未来 Codex 暴露稳定 `/goal` API/CLI 后替换 adapter。
- `metaloop verify` 已能做 hard validator / ExecutionReport / soft-final-human 分类。
- Co-Design v2 的 brainstorm/refinement 是设计期治理，不替代运行期验收；非交互模式只在无 blocking review findings、无未确认任务特定 unresolved decisions 时自动 lock，人工设计审查价值主要在交互终端中体现。
- goal-style resume v1 不是 Codex thread-level continuation；它是 structured resume：读取 `.metaloop/` 文件判断状态，然后跳过、重跑或提示修复。未来 Codex 暴露 thread continuation API 后再替换 adapter。
- redesign_required 不是 implementation failure；status/resume 会提示回到 design/redesign，而不是盲目启动 worker repair。
- shell/UserAgent v1 还不会 apply RedesignProposal；它只把反馈归类为 revision/redesign action 并守住 locked contract 边界。
- SDK-backed shell UserAgent 已把 thread id 持久化到 `.metaloop/user_agent_thread.json` 并支持跨 shell resume；可用 `metaloop shell --reset-user-agent-thread` 显式 reset/forget thread。
- 运行默认 shell 需要 Node 18+ 和根目录 `npm install` 安装 `@openai/codex-sdk`。

## 下一步

1. 将 RedesignProposal 应用为显式 Capsule revision 的流程做完整，包括用户确认和新 MissionSpec 生成。
2. 打磨 long-running TUI shell v2：更完整状态流、命令面板、attempt/history 视图、revise/redesign 入口。
3. 升级 Codex SDK-backed UserAgent：把 tool/action confirmation UX 做顺，并增加更清晰的 thread 状态展示。
4. 按 Prompt Compiler 迁移顺序继续逐步接入 runtime：下一步评估 repair；主 goal prompt 暂缓。
5. 继续扩大 Co-Design v2 reviewer/brainstormer 的 domain-profile 特化检查，但不引入完整 SKS/SCP/ITC/AMP。
6. 打磨 structured resume 的 verify-only / repair-only 分支，减少不必要重跑。
7. 增加可选的 attempt commit workflow；默认仍不自动 commit。
8. 在 Codex 暴露非交互式 `/goal` API/CLI 或 thread continuation API 后替换 `CodexExecGoalRuntimeAdapter` 的传输层。

## 不要做

- 不要在 Kernel 内递归启动子 MetaLoop。
- 不要把 Codex 自报完成当作 MetaLoop verified completion。
- 不要把完整聊天史当 operational memory。
- 不要默认把仓库/文档/日志全文塞给 LLM。
- 不要立刻实现完整 SKS/SCP/ITC/AMP；先落地最小 Mission Capsule v1。
- 不要默认使用多 Agent role pipeline 跑普通任务。
- 不要默认使用 `danger-full-access`。
- 不要把 runtime 全量切到 prompt md；目前只迁移了 Co-Design brainstorm、discovery/interviewer、redesign focused route 和 soft_reviewer，Prompt Compiler 后续接入必须分阶段迁移，且 repair / 主 goal prompt 暂缓。
