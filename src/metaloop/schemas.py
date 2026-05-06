from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    PROPOSED_NEXT_TASK = "proposed_next_task"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED_BY_POLICY = "blocked_by_policy"
    BLOCKED_BY_AUTH = "blocked_by_auth"


class Route(str, Enum):
    NEXT_STEP = "next_step"
    RETRY_WORKER = "retry_worker"
    REPLAN = "replan"
    REBRAINSTORM = "rebrainstorm"
    PROPOSE_NEXT_TASK = "propose_next_task"
    AWAIT_AUTH = "await_auth"
    FAIL = "fail"
    COMPLETE = "complete"


class FailureType(str, Enum):
    NONE = "none"
    ARTIFACT_ERROR = "artifact_error"
    STRATEGY_ERROR = "strategy_error"
    POLICY_BLOCK = "policy_block"
    BUDGET_EXCEEDED = "budget_exceeded"
    WORKER_ERROR = "worker_error"


class AcceptanceCriteria(BaseModel):
    id: str = Field(default_factory=lambda: new_id("criteria"))
    description: str
    validation_type: Literal["command", "schema", "file_exists", "file_contains", "manual", "llm_review"] = "manual"
    validation_target: str | None = None
    required: bool = True


class Budget(BaseModel):
    max_tokens: int | None = None
    max_usd: float = 2.0
    max_tool_calls: int | None = None
    max_wall_time_seconds: int = 1800
    max_step_retries: int = 3
    max_replan_count: int = 2


class BudgetUsage(BaseModel):
    tokens: int = 0
    usd: float = 0.0
    tool_calls: int = 0
    step_retries: dict[str, int] = Field(default_factory=dict)
    replan_count: int = 0

    def retry_count_for(self, step_id: str) -> int:
        return self.step_retries.get(step_id, 0)


class PolicyScope(BaseModel):
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    requires_human_auth_for: list[str] = Field(default_factory=list)
    workspace_root: str = "."
    risk_level: RiskLevel = RiskLevel.MEDIUM


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
    run_id: str = Field(default_factory=lambda: new_id("run"))
    intent: str
    context: dict[str, Any] = Field(default_factory=dict)
    deliverables: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriteria]
    agents: list[AgentSpec] = Field(default_factory=list)
    scheduler_policy: SchedulerPolicy = Field(default_factory=SchedulerPolicy)
    budget: Budget = Field(default_factory=Budget)
    policy: PolicyScope = Field(default_factory=PolicyScope)
    locked: bool = False

    @model_validator(mode="after")
    def criteria_required(self) -> MissionSpec:
        if not self.acceptance_criteria:
            raise ValueError("MissionSpec requires at least one acceptance criterion")
        return self


class PlanStep(BaseModel):
    step_id: str = Field(default_factory=lambda: new_id("step"))
    title: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    max_retries: int = 3


class TaskPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: new_id("plan"))
    selected_strategy: str
    steps: list[PlanStep]

    @model_validator(mode="after")
    def steps_required(self) -> TaskPlan:
        if not self.steps:
            raise ValueError("TaskPlan requires at least one step")
        return self


class Artifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: new_id("artifact"))
    kind: Literal["file", "json", "text", "command_output", "url"]
    uri: str | None = None
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StepResult(BaseModel):
    step_id: str
    status: StepStatus
    artifacts: list[Artifact] = Field(default_factory=list)
    error_log: str | None = None
    tokens_used: int = 0
    tool_calls_used: int = 0


class ReviewResult(BaseModel):
    step_id: str
    passed: bool
    failure_type: FailureType = FailureType.NONE
    route: Route
    notes: str = ""


class NextTaskProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: new_id("proposal"))
    source_run_id: str
    source_step_id: str | None = None
    reason: str
    suggested_intent: str
    required_context: dict[str, Any] = Field(default_factory=dict)
    expected_artifacts: list[str] = Field(default_factory=list)
    suggested_acceptance_criteria: list[AcceptanceCriteria] = Field(default_factory=list)
    blocking: bool = True
    notes: str = ""


class FailureReport(BaseModel):
    run_id: str
    failed_node: str
    failed_step_id: str | None = None
    error_type: str
    message: str
    recoverable: bool = False
    recommended_next_step: str | None = None
    created_at: str = Field(default_factory=utc_now)


class SystemEvent(BaseModel):
    run_id: str
    event_id: str = Field(default_factory=lambda: new_id("event"))
    event_type: str
    node: str | None = None
    step_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class KernelState(BaseModel):
    mission: MissionSpec
    status: RunStatus = RunStatus.PENDING
    strategy: str | None = None
    plan: TaskPlan | None = None
    current_step_index: int = 0
    step_results: list[StepResult] = Field(default_factory=list)
    review_results: list[ReviewResult] = Field(default_factory=list)
    events: list[SystemEvent] = Field(default_factory=list)
    budget_usage: BudgetUsage = Field(default_factory=BudgetUsage)
    next_task_proposal: NextTaskProposal | None = None
    failure_report: FailureReport | None = None

    @property
    def current_step(self) -> PlanStep | None:
        if self.plan is None:
            return None
        if self.current_step_index >= len(self.plan.steps):
            return None
        return self.plan.steps[self.current_step_index]

    def add_event(
        self,
        event_type: str,
        *,
        node: str | None = None,
        step_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> SystemEvent:
        event = SystemEvent(
            run_id=self.mission.run_id,
            event_type=event_type,
            node=node,
            step_id=step_id,
            payload=payload or {},
        )
        self.events.append(event)
        return event
