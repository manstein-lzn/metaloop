# MetaLoop Roadmap

最后更新：2026-05-04

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

状态：v1 已实现，继续 polish。

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
