# MetaLoop Roadmap

最后更新：2026-05-08

本文记录产品路线。当前实现主线是极简 v3：

```text
MissionSpec -> GoalContract -> Codex goal runtime -> ExecutionReport -> VerificationResult
```

宪法层详见 `docs/mission_capsule_constitution.md`。当前实现层详见 `docs/minimal_v3_codex_goal_architecture.md`。

## 0. 产品原则

MetaLoop 的价值不是替 Codex 写代码，而是：

- 更好地定义任务。
- 更清楚地表达边界。
- 更可靠地验收结果。
- 更完整地记录证据。

Codex 保留 coding agent 的主动性：搜索、阅读、修改、运行、调试。MetaLoop 不微观管理 Codex 的工具选择。

2026-05-08 之后的产品方向是 skill-first，但不是 prompt-only：`$metaloop` skill 负责入口、对齐、设计纪律和 action 建议；skill-bundled kernel、MetaLoop CLI、schemas、validators 和 `.metaloop/` artifacts 负责确定性检查和状态；hooks、sandbox 或 wrapper runtime 只在真实任务证明必要时提供更强不可绕过约束。

## v2.9 Skill-First Lightweight Protocol

状态：v1.2 self-contained skill package 已新增。

目标：把 MetaLoop 的入口变轻，让 Codex 可以通过可一键部署的 `$metaloop` skill 进入深度 design、capsule、verify、repair/redesign/resume 纪律，同时不把强约束只放在 prompt 中。

已实现：

- `skills/metaloop/SKILL.md`
- `skills/metaloop/agents/openai.yaml`
- `skills/metaloop/references/lightweight_protocol.md`
- `skills/metaloop/scripts/metaloop_kernel.py`
- README 文档入口
- skill package 边界测试
- design gate：intent-only 不能 lock；必须有 rationale、non-goal、acceptance 和硬验证路径，除非显式 manual-only
- minimal run wrapper：命令式执行写入 `.metaloop/execution_report.json`
- schema checks：verify 读取 capsule/report 时做结构校验，缺 report 不能完成
- locked VerificationSpec：Mission Capsule 内锁定 structured completion contract
- generic extension：支持 `file_exists`、`command`、`forbidden_path`、`json_metric_gate`
- extension hash audit：验证阶段检测 VerificationSpec 执行后篡改

验收：

- Skill 明确声明自己是入口和对齐层，不是不可绕过的 runtime。
- Skill 指向 CLI/schema/validators 作为检查和状态来源。
- Skill 内置 lightweight kernel，目标环境不必先安装完整 MetaLoop package 才能使用核心协议。
- Skill 不创建第二套状态系统。
- Skill 不允许 worker 静默修改 locked contract。

## v3.0 Minimal Goal Governance

状态：主路径已落地，Goal-Style Resume v1 和 Status Inspect UX v1 已实现。

目标：把默认执行路径从重型多 Agent pipeline 收敛为单个 Codex goal-style runtime，加上 MetaLoop 独立验收。

已完成：

- `GoalContract`
- `ExecutionReport`
- `VerificationResult`
- MissionSpec to GoalContract compiler
- Codex-facing goal objective renderer
- `metaloop compile`
- `metaloop verify`
- `CodexExecGoalRuntimeAdapter`
- `metaloop run` auto 模式对 mission 默认走 goal-style runtime
- `.metaloop/` 结构化运行文件
- `SoftReviewDecision`
- 内部 reviewer route schema
- `ask_worker_to_fix` 一步 repair loop
- focused architect/planner/brainstormer guidance routes
- `RedesignProposal`
- Repair / Redesign Capsule Semantics v1
- `metaloop status` structured inspect UX
- goal-style `metaloop resume --mode goal` structured resume
- goal mode 保留 MissionSpec `run_id` 作为稳定 contract/capsule id；`metaloop verify` 会在存在 `.metaloop/run.json` 时验证最新 runtime mission，避免原 mission 文件与 ExecutionReport id mismatch。
- goal prompt 保守压缩为 compact MissionCapsule summary + 完整 GoalContract + 最小 ExecutionReport 字段契约，降低小任务 token 开销。
- 旧 role pipeline 可通过 `--mode rigorous` 或显式 `--worker` 使用

待完成：

- RedesignProposal 应用为 Capsule revision 的用户确认流程
- 更细粒度的 goal runtime resume 分支：verify-only / repair-only / rerun
- Codex 暴露非交互式 `/goal` API/CLI 后替换当前 `codex exec` 传输层

验收：

- `metaloop design && metaloop run` 是主路径。
- 默认 run 只启动一个 Codex runtime。
- Codex 完成后必须产生 ExecutionReport。
- MetaLoop 必须再运行 VerificationResult 分类。
- hard validator 失败不能进入 `completed_verified`。
- manual/llm_review 不能伪装成 hard verified；final human acceptance 不参与内部 agent 路由。

## v3.1 Mission Capsule v1

状态：理论已收敛，v1 主路径已实现；Repair / Redesign Capsule Semantics v1 已实现，Capsule revision 应用流程继续推进。

目标：把当前 `MissionSpec -> GoalContract` 主线演进为 Mission Capsule v1，但不引入完整 SKS/SCP/ITC/AMP 协议栈。

v1 Capsule 范围：

- 已实现：identity
- 已实现：mission charter
- 已实现：authority contract
- 已实现：acceptance contract / verification plan
- 已实现：domain profile id
- 已实现：reference set
- 已实现：evidence ledger
- 已实现：attempt history
- 已实现：`.metaloop/attempts/<attempt_id>.json` git-aware attempt history artifact
- 已实现：attempt changed files 噪声过滤，排除 `.metaloop/`、`metaloop.mission.json`、`__pycache__/`、`.pyc/.pyo`
- 已实现：decision ledger
- 已实现：lifecycle state
- 已实现：closure outcome
- 已实现：把 runtime evidence、attempt、review、closure decision 自动写入 Capsule ledger
- 已实现：`metaloop design` 结束时写出 Capsule/GoalContract contract 预览 `.metaloop/design_capsule.json` 和 `.metaloop/design_goal_contract.json`
- 已实现：implementation repair 与 contract-level redesign 分离
- 已实现：design route 写出 `.metaloop/redesign_proposal.json`
- 已实现：Capsule 可进入 `redesign_required`
- 剩余：把 RedesignProposal 应用为显式 Capsule revision，并支持用户确认后的 revised MissionSpec
- 剩余：可选 attempt commit workflow；默认不自动 commit

优先 DomainProfile：

- `engineering_development`
- `algorithm_research`
- `codex_skill_creation`
- `deep_research`

验收：

- locked intent / acceptance 不能被 executor 弱化。
- permissions 不能无记录扩张。
- evidence / attempts append-only。
- completion 必须引用当前有效 evidence。
- repair 不能改变 normative contract。
- redesign 必须显式 Capsule revision。
- v1 redesign 只生成 proposal，不自动改 MissionSpec、acceptance、scope 或 authority。
- status/resume 不能把 `redesign_required` 当成普通 implementation rerun。
- child Capsule 只能继承明确委托的权限。

## v3.2 Product CLI

状态：v1 已实现，继续 polish；下一阶段产品形态要从 one-shot CLI 过渡到 long-running TUI shell。

目标：让自用路径稳定、少参数、可恢复。

目标命令：

```bash
metaloop design
metaloop run
metaloop status
metaloop verify
```

保留诊断命令：

```bash
metaloop compile
metaloop list
metaloop show
metaloop resume
```

Status Inspect UX v1:

- `metaloop status` 读取 MissionSpec、MissionCapsule、run manifest、VerificationResult 和 Codex events。
- plain 输出给出 mission/run/capsule/verification 摘要与 `next_action`。
- JSON 输出保留结构化字段，适合脚本和未来 UI。

Goal-Style Resume v1:

- resume 不是 Codex thread-level continuation。
- resume 是 structured resume：读取 `.metaloop/` 文件判断是否 terminal success、缺少 ExecutionReport、failed/blocked verification、failed capsule closure 或 incomplete manifest。
- terminal success 不重跑；需要继续时明确说明原因并重跑 goal runtime。
- 后续 Codex 如提供 thread continuation API，再替换 adapter。

## v3.2.5 Long-Running TUI Shell

状态：v1 prompt-loop 已实现，继续打磨。

目标：用户打开 `metaloop` 后长期停留在一个 TUI 会话中完成设计、运行、验收、修复、状态检查和后续迭代，而不是记住一组离散命令。

核心判断：

- 当前 `metaloop design` / `metaloop run` / `metaloop status` / `metaloop verify` 是正确的底层能力，但不是最终产品体验。
- 最终自用形态应类似一个项目级控制台：启动一次，持续交互，随时知道当前 workspace 的 design/run/capsule/verification 状态。
- CLI 子命令仍保留，作为脚本、调试和 CI 入口；TUI shell 是面向人的默认入口。

目标入口：

```bash
metaloop
```

已实现 v1：

- `metaloop` 空命令进入 shell；保留 `metaloop shell` 显式入口。
- 启动时读取现有 `.metaloop/` structured artifacts，不创建平行状态系统。
- 默认启动 Codex SDK-backed UserAgent，通过 `@openai/codex-sdk` 保持 Codex thread，并把 thread id 持久化到 `.metaloop/user_agent_thread.json` 支持跨 shell resume，让 Codex 理解现存项目并输出受控 `ProposedAction`；`metaloop shell --reset-user-agent-thread` 可忘掉该对话历史；`codex exec` 只作为 `--user-agent exec` 兼容路径，本地规则 agent 只作为 `--user-agent local` 调试路径。
- Rich overview 展示 design、mission、run、verification、redesign、attempt history 和 next action。
- 支持自然语言或显式 action 输入，确认后调用现有 `design/run/status/verify/resume` CLI/runtime 路径。
- 用户反馈“不满意/修改/重设计”会被归类为 feedback/revision，不直接修改 locked MissionSpec、MissionCapsule 或 GoalContract。
- `redesign_required` 状态下，“继续”不会被映射为普通 worker rerun。

TUI shell 应提供：

- 当前 workspace 总览：mission、capsule、run、verification、redesign、attempt history。
- 用户自然语言输入区：用户可以说“开始设计”“继续上次任务”“这次结果我不满意”“帮我看现在卡在哪”。
- 状态流：Codex、reviewer、verification、repair/redesign route 的当前动作必须持续可见。
- 命令面板：保留显式 action，例如 design、run、verify、status、resume、revise、quit。
- 任务队列/历史：展示最近 attempts、ExecutionReport、VerificationResult、RedesignProposal。
- 中断恢复：TUI 重启后从 `.metaloop/` 结构化状态恢复。

非目标：

- 不把 TUI 做成隐藏所有结构的黑盒。
- 不移除脚本友好的 CLI 子命令。
- 不在 TUI 内引入递归 MetaLoop 编排。

验收：

- 用户在一个新 repo 中运行 `metaloop`，无需记忆命令即可被引导完成 design -> run -> verify。
- 用户中途退出后重新运行 `metaloop`，能看到当前状态并继续。
- 用户不满意结果时，TUI 能引导进入 feedback/revise/redesign 流程，而不是只显示 completed。

## v3.2.6 User-Facing Agent

状态：v1 Codex SDK-backed action proposal 已实现，thread id 持久化、跨 shell resume、reset/forget thread 已实现。

目标：增加一个专门面向用户的 agent，作为 MetaLoop 的交互层。它不直接替代 worker/reviewer，也不直接绕过结构化状态，而是负责理解用户意图、解释当前状态、建议下一步，并把用户自然语言转成明确的 MetaLoop action。

角色命名暂定：

```text
UserAgent / ConciergeAgent / InterfaceAgent
```

已实现 v1：

- `src/metaloop/user_agent.py`
- `CodexSdkUserAgent` 接收用户文本和 workspace status，通过 `src/metaloop/codex_sdk_bridge.mjs` 调用 `@openai/codex-sdk`。它复用/恢复 Codex thread，允许 Codex 读取当前项目的 README、manifest、Git 历史和关键文件后返回 `ProposedAction`。
- 支持 `start_design`、`resume_design`、`run_current_mission`、`verify_current_run`、`show_status`、`resume_run`、`collect_feedback`、`propose_revision`、`apply_redesign`、`quit`。
- shell 负责确认并执行底层 `design/run/status/verify/resume`；CodexSdkUserAgent 不直接执行 MetaLoop action。
- 本地规则映射只作为显式 local/debug mode，不伪装为默认智能体验。

职责：

- 解释当前 workspace 状态：读取 `.metaloop/` artifacts，告诉用户现在处于 design、running、verified、blocked、redesign_required 还是 pending human acceptance。
- 降低命令记忆成本：用户不需要记住 `metaloop design --resume` 或 `metaloop resume --mode goal`，UserAgent 根据状态选择 action。
- 引导 Co-Design：用用户能读懂的方式推进需求压榨、方案展示、确认和锁定。
- 引导 run 后反馈：当用户说“不满意”“继续优化”“结果不对”时，UserAgent 不直接让 worker 乱改，而是生成结构化 feedback/revision intent，进入 revise/redesign/repair 路径。
- 做边界解释：说明哪些事情是 MetaLoop 验收，哪些是 Codex 执行，哪些需要用户最终确认。

权限边界：

- UserAgent 不能直接修改 locked MissionSpec、MissionCapsule、GoalContract。
- UserAgent 不能把用户一句“继续”自动解释为扩大权限或弱化验收。
- UserAgent 的输出必须落到结构化 action，例如 `start_design`、`resume_design`、`run_current_mission`、`verify_current_run`、`collect_feedback`、`propose_revision`、`show_status`。
- Codex 不可用时直接报错；不得静默回落到假智能规则。

建议数据结构：

```text
UserTurn -> UserIntent -> ProposedAction -> TUI Confirmation -> MetaLoop Command/Runtime Call
```

验收：

- 用户可以用自然语言完成常见路径，而不需要知道具体子命令。
- UserAgent 的每次建议都能解释“为什么现在建议这个 action”。
- 所有 action 都能映射到现有结构化状态和 CLI/runtime API，不引入平行状态系统。

## v3.3 Co-Design v2 for Verification

状态：v2 主路径已实现，继续打磨 domain-profile 细化。

目标：Co-Design 不只是写任务描述，也不只是 agent 追问用户；它要先发现需求，再让 agent 主动扩展方案空间，最后由用户审核并锁定可执行 GoalContract 和可验收 VerificationPlan。

重点：

- 已实现：自动识别 hard validators。
- 已实现：自动标注 soft review / final human acceptance。
- 已实现：对文件型交付物优先生成可机器验收标准。
- 已实现：对工程、算法研究、Codex skill、深度研究任务写入 `domain_profile_id`。
- 已实现：reviewer 检查文件型交付物是否缺少 hard validators、manual 是否滥用、domain profile 是否缺失或不匹配。
- 已实现：Contract Quality Gate v1，path-based hard validators 必须是具体 repo path，不能是自然语言句子或 `tabs/newlines` 这类行为短语；Co-Design 自动补 `file_exists` 时只使用强 path token，不再把整句 deliverable 或概念对当 target。
- 已实现：runtime validator 防线，`file_exists` / `file_contains` / `schema` 对 invalid path target 直接失败；即使 worker 创建了同名无意义 artifact，也不能进入 `completed_verified`。
- 已实现：brainstorm expansion，主动提出方案选项、取舍、风险、MVP/V1/后续路线和待确认决策。
- 已实现：non-interactive unresolved gate。非交互/JSON design 如果 brainstorm 仍有任务特定 unresolved decisions，拒绝写出 locked MissionSpec；通用 non-goal 提醒作为 risk/overlooked point，不再制造虚假的 blocking unresolved。
- 已实现：Codex co-designer / brainstormer / answerer 不可用时直接失败；不得静默回落到 rule backend。Rule backend 只作为显式选择或非交互兼容路径。
- 已实现：human design review markdown / CLI Rich 展示。
- 已实现：interactive refinement，用户可继续质疑、补充、否定、选择，并用 `approve` / `lock` / `完成` / `确认` 显式结束。
- 已实现：contract lock 后才写出 locked MissionSpec、design Capsule 和 design GoalContract。
- 已实现：contract lock 前无条件阻断 blocking reviewer findings；非 `--strict-review`/非交互兼容路径也不能锁定 invalid contract。
- 已实现：Co-Design v2 过程 artifact：`.metaloop/design_transcript.jsonl`、`.metaloop/design_draft.md`、`.metaloop/design_review.md`、`.metaloop/design_decisions.json`、`.metaloop/design_lock.json`。
- 保持：产品体验类要求可保留最终用户确认标记；这不参与内部 agent 路由。

## v3.4 Rigorous Mode

状态：保留，不作为默认。

旧的：

```text
brainstormer -> planner -> worker -> reviewer -> scheduler
```

将作为高成本模式存在：

```bash
metaloop run --mode rigorous
```

适用场景：

- 高风险修改。
- 需要多轮独立审查。
- 需要复盘多 Agent 协作实验。

## v3.5 Spec Discipline + Workflow Discipline

状态：v1 已实现，不引入 OpenSpec CLI 或 Superpowers runtime，不改变默认 CLI 主路径。

目标：吸收 agree-before-build、brainstorming gate 和 systematic debugging 的纪律，但只落到 MetaLoop 现有 MissionSpec/Capsule/GoalContract/VerificationResult 边界。

已完成：

- MissionSpecReviewer 新增保守 findings：`scope_too_broad`、`missing_non_goals`、`missing_evidence_path`、`weak_acceptance`、`unclear_authority`、`missing_tradeoff_review`、`needs_decomposition`。
- `RedesignProposal.contract_delta` 结构化记录 added/removed scope、non-goals、acceptance、authority、evidence delta；status JSON/plain 输出 delta 摘要。
- repair prompt/VerificationResult 记录 `repair_attempt_index`、root cause/hypothesis discipline、failed fix summary；重复 repair 到第三次 worker-fix 请求前转 redesign gate。
- DomainProfile evidence obligations 已落地到 profile、EvidencePlan hints 和 VerificationResult domain checks；工程 bugfix/public behavior 缺 regression/build/test evidence 会 failed。
- Prompt Pack v1 文件已外置到 `prompts/co_design/` 和 `prompts/run/`，每个文件带 metadata。

待完成：

- RedesignProposal 应用为显式 Capsule revision 的确认流程。
- 更丰富的 structured status UI 展示 delta 详情。

## v3.6 Prompt Compiler

状态：Phase 0/1/2/3/4/5 已落地；runtime 仅迁移了 Co-Design brainstorm、discovery/interviewer、run redesign focused route 和 run soft reviewer。

目标：把 prompt 从审计层逐步升级为可版本化、可测试、可编译的上下文源，同时保持 MetaLoop structured state 是最终 work order 的核心输入。

已完成：

- Phase 0：当前 hardcoded runtime prompt builders 增加语义基线测试，不做全文 snapshot。
- Phase 1：新增只读 `metaloop.prompt_pack` loader/compiler，支持 prompt md front matter、严格 `{{var_name}}` 替换、required variables、fail-fast 和 sha256。
- Phase 2：`_build_codex_brainstorm_prompt` / `CodexCoDesignBrainstormer` 使用 `prompts/co_design/brainstorm.md` 编译 runtime prompt；Python 注入 MissionSpec、CoDesignDraft、MissionSpecReview 的 fenced JSON；prompt pack 渲染失败不回退 hardcoded prompt。
- Phase 3：`_build_codex_interviewer_prompt` / `CodexCoDesignInterviewer` 使用 `prompts/co_design/discovery.md` 编译 runtime prompt；Python 注入 `patch_mode`、`patch_mode_instruction`、CoDesignDraft 的 fenced JSON；prompt pack 渲染失败不回退 hardcoded prompt。
- Phase 4：`build_focused_route_prompt` 使用 `prompts/run/redesign.md` 编译 runtime prompt；Python 注入 route/role、MissionSpec、MissionCapsule、VerificationResult、SoftReviewDecision 的 fenced JSON；prompt pack 渲染失败不回退 hardcoded prompt。
- Phase 5：`build_soft_review_prompt` 使用 `prompts/run/soft_reviewer.md` 编译 runtime prompt；Python 注入 MissionSpec、GoalContract、VerificationResult 和实际 `SoftReviewDecision.model_json_schema(by_alias=True)` 的 fenced JSON；prompt pack 渲染失败不回退 hardcoded prompt，`CodexSoftReviewer.review` 会返回 failed low-confidence review。
- Prompt Pack metadata 补齐 `id`、`stage`、`required_variables`。
- 新增 `docs/prompt_compiler_v3_6_plan.md` 记录三层模型、迁移顺序、风险与护栏。

明确边界：

- runtime 仍主要由 Python builder 拼 prompt；当前例外只有 Co-Design brainstorm、discovery/interviewer、redesign focused route 和 soft_reviewer。
- 不迁移主 goal prompt。
- 不迁移 repair / 主 goal prompt，直到后续阶段按测试护栏逐个接入。

下一步迁移顺序：

```text
repair
```

主 goal prompt 暂缓，等待低风险 prompt 家族验证 compiler 路径稳定后再评估。

## Backlog / Principles

以下文档分为宪法层和扩展原则层：

- `docs/mission_capsule_constitution.md`
- `docs/agent_message_protocol.md`
- `docs/structured_context_protocol.md`
- `docs/structured_knowledge_system.md`
- `docs/intent_transmission_contract.md`
- `docs/guided_autonomy_principle.md`

它们的实际引入原则：

```text
先证明主线瓶颈，再引入最小必要抽象。
```

Mission Capsule Constitution 是宪法层，必须遵守；但 full SKS/SCP/ITC/AMP 是扩展治理层，不做大而全的协议栈，不默认建设完整知识库，不默认约束 Codex 工具清单。

## 已完成历史里程碑

### Kernel Foundation

- Python package / CLI。
- Pydantic runtime schema。
- SQLite events/checkpoints。
- Policy engine。
- Tool registry。
- Dummy runner。
- Structured terminal states。

### Codex Worker Preview

- Codex exec adapter。
- Codex worker backend。
- Codex role agents。
- output-schema fallback。
- Rich CLI run status。

### Co-Design Alpha

- Co-Design v2：requirement discovery -> brainstorm expansion -> human design review -> interactive refinement -> contract lock。
- Codex co-designer / brainstormer。
- 多轮 reviewer gate 与 refinement。
- resume 与 design transcript。
- mission auto-discovery。

这些能力保留，但不再定义默认 v3 执行架构。
