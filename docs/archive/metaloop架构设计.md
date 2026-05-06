# MetaLoop 架构设计文档 (v2.2)

## 1. 项目定位

**MetaLoop Kernel** 是一个面向自治智能体的本地化闭环执行单元，也是构建复杂自治系统的基本元。它不是单次 Prompt 脚本，也不是松散的多 Agent 聊天室，而是一个由 Co-Design、结构化契约、多 Agent 协作、反馈调度和硬约束控制共同组成的单任务自治闭环。

MetaLoop 的命名强调两层含义：

- **Meta**：它不只执行任务，还会先生成任务本身的规范、规则、角色和协作协议。
- **Loop**：它像自动控制系统一样，通过执行、审查、反馈、重规划和再执行来逼近目标。

MetaLoop 的目标是解决多智能体系统中的四类常见问题：

1. **需求未收敛就开始执行**：模糊目标被直接送入执行层，导致返工、误解和死循环。
2. **Agent 间纯文本通信失控**：自然语言在多轮传递中丢失约束，产生幻觉累积。
3. **自治执行不可控**：系统可以持续调用工具、消耗预算或触碰高风险操作，但缺少强制刹车机制。
4. **执行过程不可审计**：失败后难以复盘，崩溃后难以恢复，终端输出无法作为可靠事实来源。

MetaLoop 的核心答案是：**Co-Design 收敛单个任务并生成内生规则，Inner Loop 按规则自治执行；所有状态通过结构化契约流转；所有工具调用受策略引擎约束；所有状态跃迁可记录、可恢复、可回放；当任务应被拆分时，Kernel 只产出结构化 `NextTaskProposal`，不直接编排新的 MetaLoop。**

## 2. 核心原则

### 2.1 Co-Design 与执行隔离

MetaLoop 将系统生命周期拆分为两个控制逻辑不同的阶段：

- **Co-Design Loop：需求共创与准入环**  
  允许用户参与，由专业 Agent 主动进行多轮深度访谈，用于澄清需求、压榨上下文、确认边界、定义验收标准，并生成完整 `MissionSpec`。

- **Inner Loop：自治执行与自纠错环**  
  默认不接受需求变更，由状态机、调度器、工具系统和审查器自动推进任务。

Co-Design 结束后，人类默认退出执行协作。更准确的约束是：**内环不接受临时需求变更，但保留取消、暂停、授权、灾难恢复和关键阻塞决策五类控制信号。**

用户如果要改变任务目标，应终止当前 run 并重新进入 Co-Design，而不是在内环中临时改写任务。

### 2.2 结构化契约通信

Agent 之间不依赖自由文本作为事实载体。自由文本可以作为解释、日志或推理材料存在，但状态流转必须落到 Pydantic/TypedDict 可校验对象上。

核心对象包括：

- `MissionSpec`：任务规范，描述目标、边界、验收标准和预算。
- `TaskPlan`：执行计划，描述步骤、依赖和预期产物。
- `StepResult`：步骤结果，描述状态、产物、错误和资源消耗。
- `ReviewResult`：审查结果，描述是否通过、失败类型和下一步路由建议。
- `SystemEvent`：事件记录，描述节点、工具、预算、检查点等运行时事实。

### 2.3 可实现与允许执行分离

MetaLoop 明确区分两个判断：

- **Feasibility Assessor** 判断任务是否能做。
- **Policy Engine** 判断任务是否允许做、是否需要授权、是否超出预算或风险边界。

一个任务可以技术上可行，但因为权限、成本、合规、破坏性操作或用户未授权而被阻断。

### 2.4 本地优先与可审计

MetaLoop 默认不依赖强制云端遥测。日志、状态快照、事件流和运行记录优先保存在本地。Rich TUI 只是观察层，真正的事实来源是结构化事件日志和 checkpoint store。

### 2.5 Kernel 与 Orchestrator 分离

MetaLoop Kernel 专注于把一个任务闭环做好。多个 MetaLoop 的组合、并行、递归和生命周期管理不属于 Kernel 职责，而属于更高层的 Orchestrator。

第一阶段由用户扮演 Orchestrator：

- Kernel 发现任务超出当前闭环边界时，返回 `NextTaskProposal`。
- 用户根据 proposal 手动启动新的 MetaLoop。
- 每个 MetaLoop run 都拥有独立上下文、预算、checkpoint 和结果。
- 等手动组合的边界足够清晰后，再设计独立的 `MetaLoop Orchestrator`。

这是一种协程/生成器式控制流：MetaLoop 不进行无限递归调用，而是在必要时 `yield NextTaskProposal`，把控制权交还给外部编排者。

## 3. 总体架构

```text
User
  |
  v
Co-Design Loop
  |-- Interviewer
  |-- Feasibility Assessor
  |-- Policy Engine
  |-- Gateway Scheduler
  v
MissionSpec locked
  |
  v
Inner Loop
  |-- Brainstormer
  |-- Planner
  |-- Worker
  |-- Artifact Validator
  |-- Strategy Reviewer
  |-- Internal Scheduler
  |
  +--> Tool Registry / Tool Runtime
  +--> Event Bus
  +--> Checkpoint Store
  +--> Budget Guard
  +--> Human Override Channel
  +--> NextTaskProposal
```

MetaLoop 的核心不是某个单独 Agent，而是一组受调度器约束的节点。节点可以调用 LLM，但节点输出必须经过 schema 校验后才能进入全局状态。

## 4. Co-Design Loop：需求共创与准入环

Co-Design Loop 是唯一允许用户参与需求塑形的阶段。它的目标不是立即执行，而是生成足够稳定、可验证、可执行、可自治的 `MissionSpec`。

`MissionSpec` 不只是任务说明。它还必须携带本次 MetaLoop 内部所有 Agent 的职责、约束、协作规则、工具边界、验收标准和调度策略。

### 4.1 Interviewer

Interviewer 负责将用户的自然语言需求转化为结构化任务草案。它不是被动问答机器人，而是 Co-Design 阶段的主导者，需要主动、不设限地追问，直到任务足以进入自治执行。

它需要收集：

- 用户目标和非目标。
- 输入数据、上下文和运行环境。
- 期望产物和交付形式。
- 可接受的成本、时间和工具范围。
- 验收标准。
- 潜在高风险操作。
- 本次任务所需 Agent 角色和职责边界。
- 调度器在何种情况下应该重试、重规划、阻塞或失败退出。

### 4.2 Feasibility Assessor

Feasibility Assessor 负责判断任务是否具备执行条件。

评估维度包括：

- 信息是否完整。
- 工具能力是否覆盖。
- 外部依赖是否可用。
- 验收标准是否可机器验证。
- 是否存在明显不可达目标。
- 是否需要额外凭证、网络、文件或用户授权。

输出不是一句“可行/不可行”，而是结构化的可行性报告。

### 4.3 Policy Engine

Policy Engine 是独立于 LLM 的硬约束模块。它负责在任务进入内环前执行策略检查。

它至少需要处理：

- 高风险工具调用是否需要人工授权。
- 文件系统、网络、数据库、支付、部署等操作边界。
- token、费用、时间、工具调用次数和重规划次数预算。
- 任务是否触碰禁止策略。
- 是否需要从用户处获得显式确认。

### 4.4 Gateway Scheduler

Gateway Scheduler 根据 Interviewer、Feasibility Assessor 和 Policy Engine 的结构化结果路由：

- **继续询问**：需求不完整，回到 Interviewer。
- **拒绝执行**：不可行、不可授权或违反策略，输出失败诊断。
- **请求授权**：任务可行但涉及高风险操作或超预算，需要用户确认。
- **锁定任务**：生成最终 `MissionSpec`，关闭需求变更通道，进入 Inner Loop。

一旦锁定，`MissionSpec` 成为内环的最高契约。Inner Loop 只能围绕它执行、反馈和修正实现路径，不能擅自修改任务目标。

## 5. Inner Loop：自治执行与自纠错环

Inner Loop 的目标是在不接受临时需求变更的前提下，完成 `MissionSpec` 定义的任务，并在失败时进行有限度自纠错。

### 5.1 Brainstormer

Brainstormer 根据 `MissionSpec` 生成候选技术路线。它不直接执行任务，只输出可比较的方案。

输出应包含：

- 方案摘要。
- 适用条件。
- 风险点。
- 预估成本。
- 需要的工具能力。
- 推荐方案及理由。

### 5.2 Planner

Planner 将选定路线转化为 `TaskPlan`。

每个步骤需要包含：

- `step_id`。
- 输入依赖。
- 预期产物。
- 可验证的完成条件。
- 允许使用的工具范围。
- 步骤级预算和重试上限。

### 5.3 Worker

Worker 负责执行具体步骤。它不能绕过 Tool Registry 直接调用外部世界，也不能直接修改全局任务目标。

Worker 的输出必须是 `StepResult`，包括：

- 执行状态。
- 产物引用。
- 错误日志。
- 工具调用记录。
- 资源消耗。

### 5.4 Artifact Validator

Artifact Validator 是非 LLM 优先的产物验证器。它应该尽量使用确定性手段验证产物。

典型验证方式包括：

- 运行测试。
- 校验 JSON Schema。
- 检查文件是否存在。
- 执行静态扫描。
- 调用本地命令验证输出。
- 比对验收标准。

Artifact Validator 只判断产物是否满足明确条件，不负责解释用户意图。

### 5.5 Strategy Reviewer

Strategy Reviewer 负责判断执行方向是否仍然符合 `MissionSpec`。

它处理的问题包括：

- 产物虽然通过测试，但是否偏离用户目标。
- 当前失败是否属于局部错误还是路线错误。
- 是否应该继续重试、回到 Planner，还是回到 Brainstormer。
- 是否已经接近预算或触发风险边界。

### 5.6 Internal Scheduler

Internal Scheduler 根据 `ReviewResult` 和预算状态进行路由：

- **继续下一步**：当前步骤通过。
- **局部重试**：错误可修复，返回 Worker。
- **步骤重规划**：步骤拆解错误，返回 Planner。
- **路线重选**：整体策略错误，返回 Brainstormer。
- **等待授权**：触发 Policy Engine 的授权要求。
- **提出后续任务**：当前任务应被拆分或需要独立闭环时，生成 `NextTaskProposal` 并结束当前 run。
- **失败退出**：达到预算、重试或策略上限。
- **完成任务**：所有验收标准通过。

Scheduler 是 MetaLoop 的反馈控制器。Brainstormer、Planner、Worker 和 Reviewer 都是执行与判断节点，真正决定系统下一步状态迁移的是 Scheduler。

## 6. 核心数据契约

以下为初版 schema 草案。实际代码中可根据 LangGraph 状态模型拆分为 Pydantic Model 与 TypedDict。

```python
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class AcceptanceCriteria(BaseModel):
    id: str
    description: str
    validation_type: Literal["command", "schema", "file_exists", "manual", "llm_review"]
    validation_target: str | None = None
    required: bool = True


class Budget(BaseModel):
    max_tokens: int | None = None  # None means unlimited; explicit ints are hard caps.
    max_usd: float = 2.0
    max_tool_calls: int = 50
    max_wall_time_seconds: int = 1800
    max_step_retries: int = 3
    max_replan_count: int = 2


class PolicyScope(BaseModel):
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    requires_human_auth_for: list[str] = Field(default_factory=list)
    workspace_root: str = "."
    risk_level: RiskLevel = RiskLevel.medium


class AgentSpec(BaseModel):
    name: str
    role: Literal[
        "interviewer",
        "feasibility_assessor",
        "brainstormer",
        "planner",
        "worker",
        "artifact_validator",
        "strategy_reviewer",
        "scheduler",
    ]
    responsibilities: list[str]
    input_contract: str
    output_contract: str
    rules: list[str] = Field(default_factory=list)
    model_profile: str = "codex"


class SchedulerPolicy(BaseModel):
    retry_rules: list[str] = Field(default_factory=list)
    replan_rules: list[str] = Field(default_factory=list)
    rebrainstorm_rules: list[str] = Field(default_factory=list)
    block_rules: list[str] = Field(default_factory=list)
    completion_rules: list[str] = Field(default_factory=list)


class MissionSpec(BaseModel):
    run_id: str
    intent: str
    context: dict[str, Any] = Field(default_factory=dict)
    deliverables: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriteria]
    agents: list[AgentSpec] = Field(default_factory=list)
    scheduler_policy: SchedulerPolicy = Field(default_factory=SchedulerPolicy)
    budget: Budget = Field(default_factory=Budget)
    policy: PolicyScope = Field(default_factory=PolicyScope)
    locked: bool = False


class PlanStep(BaseModel):
    step_id: str
    title: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    max_retries: int = 3


class TaskPlan(BaseModel):
    plan_id: str
    selected_strategy: str
    steps: list[PlanStep]


class Artifact(BaseModel):
    artifact_id: str
    kind: Literal["file", "json", "text", "command_output", "url"]
    uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StepResult(BaseModel):
    step_id: str
    status: Literal["success", "failed", "blocked_by_policy", "blocked_by_auth"]
    artifacts: list[Artifact] = Field(default_factory=list)
    error_log: str | None = None
    tokens_used: int = 0
    tool_calls_used: int = 0


class ReviewResult(BaseModel):
    step_id: str
    passed: bool
    failure_type: Literal["none", "artifact_error", "strategy_error", "policy_block", "budget_exceeded"]
    route: Literal[
        "next_step",
        "retry_worker",
        "replan",
        "rebrainstorm",
        "propose_next_task",
        "await_auth",
        "fail",
        "complete",
    ]
    notes: str = ""


class NextTaskProposal(BaseModel):
    proposal_id: str
    source_run_id: str
    source_step_id: str | None = None
    reason: str
    suggested_intent: str
    required_context: dict[str, Any] = Field(default_factory=dict)
    expected_artifacts: list[str] = Field(default_factory=list)
    suggested_acceptance_criteria: list[AcceptanceCriteria] = Field(default_factory=list)
    blocking: bool = True
    notes: str = ""


class SystemEvent(BaseModel):
    run_id: str
    event_id: str
    event_type: str
    node: str | None = None
    step_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
```

## 7. Tool Registry 与工具运行时

MetaLoop 不应让 Worker 直接调用任意工具。所有工具必须先注册到 Tool Registry。

工具声明应包含：

- 工具名。
- 输入 schema。
- 输出 schema。
- 风险等级。
- 是否需要人工授权。
- 是否允许在内环自动调用。
- 超时设置。
- 资源消耗估算。

MCP 可以作为工具发现和工具调用协议的参考，但 MetaLoop 的权限决策仍由自身的 Policy Engine 执行。

## 8. 组合边界与 NextTaskProposal

MetaLoop Kernel 不直接启动子 MetaLoop。它只负责当前 `MissionSpec` 的闭环执行。

当 Kernel 发现当前任务已经超出本 run 的合理处理边界时，不应该强行硬干，也不应该自行递归创建子 run，而是生成 `NextTaskProposal` 并把控制权交还给外部编排者。

### 8.1 触发条件

Scheduler 可以在以下场景生成 `NextTaskProposal`：

- 当前任务需要独立需求澄清。
- 当前任务应拆分为多个互相独立的闭环。
- 当前 run 的上下文已经过长，继续执行会污染判断。
- 当前步骤需要不同 workspace、预算或工具边界。
- 当前任务的最佳下一步是启动一个新的 MetaLoop，而不是继续在本 run 内重试。

### 8.2 返回协议

`NextTaskProposal` 是 Kernel 的 yield 接口。它不是失败，也不是子任务调用，而是一个结构化的后续任务建议。

外部编排者可以选择：

- 接受 proposal，启动新的 MetaLoop。
- 修改 proposal 后启动新的 MetaLoop。
- 拒绝 proposal，将当前 run 标记为失败或完成。
- 将多个 proposal 合并为一个新任务。

### 8.3 Orchestrator 后置

未来可以新增独立的 `MetaLoop Orchestrator`，负责消费多个 `NextTaskProposal`，并管理多个 MetaLoop 的并行、串行、依赖和验收。

但这不是 Kernel 的第一阶段职责。Kernel 的第一阶段目标是成为稳定、可验证、可恢复的单任务闭环执行单元。

### 8.4 设计收益

- Kernel 保持单一职责。
- 每个 run 拥有干净独立的上下文。
- 避免递归导致的 token 成本黑洞。
- LangGraph 可以保持单层 Flat Graph，调试和观测更简单。
- 未来 Orchestrator 可以基于真实 proposal 流转经验再设计。

## 9. Event Bus 与 Checkpoint Store

### 9.1 Event Bus

Event Bus 记录运行时事实，不依赖终端输出。

必须记录的事件包括：

- run started / completed / failed。
- node started / completed / failed。
- tool called / tool returned / tool failed。
- budget updated。
- checkpoint saved。
- policy blocked。
- human authorization requested / granted / denied。
- next task proposed。
- scheduler routed。

这些事件可以被 Rich TUI、日志文件、测试回放和后续分析共同消费。

### 9.2 Checkpoint Store

Checkpoint Store 保存每次关键状态跃迁后的完整图状态。

最低要求：

- 每个 `run_id` 可恢复。
- 每个 checkpoint 可关联事件。
- 崩溃后能从最近稳定状态继续。
- 失败后能导出 `FailureReport`。

初期可使用 SQLite，本地稳定后再扩展到 Postgres。

## 10. Human Override Channel

内环不接受用户随意修改需求，但必须保留控制信号。

允许的外部控制包括：

- **cancel**：取消当前 run，执行优雅退出。
- **pause**：暂停执行，保存 checkpoint。
- **authorize**：批准某个高风险工具调用或预算扩展。
- **decide**：对阻塞任务作出关键决定，例如在多个不可自动判定的方案中选择一个。
- **resume**：从 checkpoint 继续执行。

这些控制信号不应直接改写 `MissionSpec.intent` 或 `TaskPlan`。如果用户要改变目标，应终止当前 run，回到 Co-Design Loop 创建新的 `MissionSpec`。

## 11. Workspace 安全边界

第一版 MetaLoop 是本地工具，允许改动本地文件，但所有写操作必须限制在明确的 workspace 内。

基础规则：

- `MissionSpec.policy.workspace_root` 是本次 run 的写入根目录。
- Worker 不允许写出 workspace。
- 读取外部文件需要显式声明，写入外部文件默认禁止。
- 系统级目录、用户主目录根部、凭证文件、SSH key、shell profile 等默认高危。
- destructive command 必须经过 Policy Engine 检查，必要时触发 `authorize`。

这个边界不是为了削弱自治，而是为了让自治可持续、可恢复、可信任。

## 12. 技术栈

### 12.1 LangGraph

用于构建有向带环状态图，承载 Co-Design Loop、Inner Loop、Scheduler 和 checkpoint。

关键能力：

- 条件路由。
- 中断与恢复。
- 状态流转。
- checkpoint。
- streaming updates。

### 12.2 Pydantic / TypedDict

用于定义输入输出契约和全局状态结构。

Pydantic 适合外部边界和复杂对象校验，TypedDict 适合 LangGraph 内部状态类型。

### 12.3 Codex SDK

MetaLoop 第一版应优先复用 Codex SDK。Brainstormer、Planner、Worker、Strategy Reviewer 等角色都可以调用 Codex Agent，只是使用不同的 system prompt、输入 schema、输出 schema、工具权限和预算配置。

角色不是由不同模型天然区分，而是由以下内容区分：

- `AgentSpec.role`。
- 角色 prompt。
- 输入输出契约。
- Tool Registry 可见范围。
- Scheduler 对该角色输出的路由解释。

Codex SDK 在 MetaLoop 中不是单纯 Worker，而是可被多个 Agent 角色复用的执行与推理引擎。

### 12.4 Rich TUI

Rich 负责本地终端可视化，但它不是事实来源。TUI 应从 Event Bus 和 LangGraph streaming updates 渲染状态，而不是自行推断系统行为。

### 12.5 SQLite / Postgres

SQLite 适合作为初版本地 checkpoint 和 event log 存储。Postgres 适合多 run、长任务和服务化部署。

### 12.6 Agent Protocol / MCP 的借鉴边界

- Agent Protocol 可借鉴其 `Task`、`Step`、`Artifact` 思想，用于任务流转和产物命名。
- MCP 可借鉴其工具发现、工具调用和结构化交互思想。
- 初版不追求完整兼容二者，优先保持 MetaLoop 的内部状态模型简单、可测试、可控。

## 13. 运行流程示例

```text
[System] run started: run_001
[CoDesign] interviewer collected missing fields: target, deliverable, budget
[CoDesign] feasibility passed: tools available
[Policy] auth required: filesystem_write
[CoDesign] user authorized: filesystem_write
[Gateway] MissionSpec locked

[InnerLoop] brainstormer proposed 2 strategies
[InnerLoop] planner generated 4 steps
[Worker] executing step_001
[Tool] command.run completed
[Validator] step_001 passed
[Reviewer] route: next_step
[Checkpoint] saved after step_001

[Worker] executing step_002
[Validator] failed: test command returned non-zero
[Reviewer] route: retry_worker
[Budget] step retry 1/3

[Worker] executing step_002 retry
[Validator] passed
[Reviewer] route: next_step
[Checkpoint] saved after step_002

[Scheduler] all criteria passed
[System] run completed
```

### 13.1 NextTaskProposal 示例

```text
[Scheduler] step_003 requires an independent closed-loop task
[Reviewer] route: propose_next_task
[System] generated NextTaskProposal: proposal_001
[System] run ended with status: proposed_next_task
[User/Orchestrator] may start a new MetaLoop from proposal_001
```

## 14. 失败处理模型

MetaLoop 的失败不应只是一段错误文本，而应输出结构化 `FailureReport`。

失败报告至少包含：

- run id。
- 最后一个成功 checkpoint。
- 失败节点。
- 失败步骤。
- 错误类型。
- 已消耗预算。
- 已尝试修复动作。
- 是否可恢复。
- 推荐下一步。

失败类型建议分为：

- `invalid_request`：需求不完整或不可达。
- `policy_blocked`：策略禁止执行。
- `auth_denied`：用户拒绝授权。
- `budget_exceeded`：预算耗尽。
- `tool_failure`：工具不可用或调用失败。
- `artifact_validation_failed`：产物验证失败。
- `strategy_failed`：整体路线失败。
- `system_error`：运行时异常。
- `proposed_next_task`：当前 run 正常让出控制权，并产出后续任务建议。

## 15. 落地路线

### Phase 1：契约与状态骨架

- 定义 `MissionSpec`、`AgentSpec`、`TaskPlan`、`StepResult`、`ReviewResult`、`NextTaskProposal`、`SystemEvent`。
- 编写 schema 单元测试。
- 明确状态字段的 owner 和更新规则。

### Phase 2：Dummy Graph

- 使用 LangGraph 搭建 Co-Design Loop 和 Inner Loop。
- 所有节点先用硬编码函数模拟。
- 验证路由、重试、重规划、失败退出和完成路径。

### Phase 3：Event Log 与 Checkpoint

- 接入 SQLite checkpoint。
- 建立本地 event log。
- 支持从 checkpoint 恢复。
- 支持导出失败报告。

### Phase 4：Policy Engine 与 Tool Registry

- 定义工具注册格式。
- 增加风险等级和授权策略。
- 在工具调用前加入策略拦截。
- 实现 workspace 写入边界。
- 实现 cancel / pause / authorize / decide / resume 控制信号。

### Phase 5：NextTaskProposal

- 实现 `NextTaskProposal`。
- 让 Scheduler 在适当场景以 proposal 形式结束当前 run。
- 在 TUI 和日志中明确展示 proposal。
- 用户手动承接 proposal，启动新的 MetaLoop run。

### Phase 6：Rich TUI

- 基于 Event Bus 渲染运行状态。
- 展示当前节点、步骤、预算、事件、checkpoint 和失败诊断。
- 保持 TUI 无业务决策逻辑。

### Phase 7：Codex SDK Integration

- 将 Interviewer、Brainstormer、Planner、Worker、Strategy Reviewer 接入 Codex SDK。
- 所有 LLM 输出必须经过 schema 校验。
- 对 schema 失败、空输出、越权建议和幻觉工具调用设置防御路径。

## 16. 当前版本的架构结论

MetaLoop v2.2 的核心形态是：

**一个本地优先、Co-Design 驱动、契约约束、可恢复、可组合的单任务自治 Agent Kernel。**

它应避免两个极端：

- 不能退化成多个 Agent 自由聊天的脚本。
- 也不能变成完全不可接管的黑箱执行器。

正确的工程边界是：**需求在 Co-Design Loop 中充分收敛，任务在 Inner Loop 中默认自治，复杂任务通过 `NextTaskProposal` 让出控制权，多个 MetaLoop 的组合交给用户或未来 Orchestrator，执行受策略引擎约束，过程由事件和 checkpoint 留痕，异常可以被人类以有限控制信号安全接管。**
