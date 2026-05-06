from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, Field, ValidationError

from metaloop.codex_adapter import CodexExecAdapter, CodexExecOptions, CodexExecResult, map_codex_event_type
from metaloop.schemas import (
    AcceptanceCriteria,
    BudgetUsage,
    FailureType,
    MissionSpec,
    PlanStep,
    ReviewResult,
    Route,
    StepResult,
    StepStatus,
    SystemEvent,
    TaskPlan,
)
from metaloop.validators import ValidationResult
from metaloop.workers import _fallback_reason, _normalize_optional_string


T = TypeVar("T")
EventEmitter = Callable[[str, str | None, str | None, dict | None], SystemEvent]


@dataclass(frozen=True)
class AgentContext:
    run_id: str
    budget_usage: BudgetUsage
    emit_event: EventEmitter


@dataclass(frozen=True)
class AgentCallResult(Generic[T]):
    value: T
    tokens_used: int = 0
    tool_calls_used: int = 0


class RoleAgentError(RuntimeError):
    def __init__(self, node: str, message: str) -> None:
        super().__init__(message)
        self.node = node
        self.message = message


class BrainstormResult(BaseModel):
    selected_strategy: str
    rationale: str = ""
    risks: list[str] = Field(default_factory=list)
    notes: str = ""


class RoleAgentBackend(Protocol):
    def brainstorm(self, context: AgentContext, mission: MissionSpec) -> AgentCallResult[BrainstormResult]:
        ...

    def plan(
        self,
        context: AgentContext,
        mission: MissionSpec,
        strategy: BrainstormResult,
    ) -> AgentCallResult[TaskPlan]:
        ...

    def review(
        self,
        context: AgentContext,
        mission: MissionSpec,
        plan: TaskPlan,
        result: StepResult,
        *,
        retry_count: int,
        is_last_step: bool,
        validation_results: list[ValidationResult],
    ) -> AgentCallResult[ReviewResult]:
        ...


class RuleBasedRoleAgentBackend:
    """Deterministic role agents for tests and offline smoke runs."""

    def brainstorm(self, context: AgentContext, mission: MissionSpec) -> AgentCallResult[BrainstormResult]:
        return AgentCallResult(
            BrainstormResult(
                selected_strategy="dummy_strategy: execute simple plan and rely on reviewer feedback",
                rationale="Deterministic local fallback strategy.",
            )
        )

    def plan(
        self,
        context: AgentContext,
        mission: MissionSpec,
        strategy: BrainstormResult,
    ) -> AgentCallResult[TaskPlan]:
        intent = mission.intent.lower()
        if any(token in intent for token in ("split", "proposal", "next task", "拆分", "后续任务")):
            steps = [
                PlanStep(
                    title="Assess task boundary",
                    description="Determine whether this run should yield a follow-up task proposal.",
                    expected_artifacts=["boundary assessment"],
                    allowed_tools=["artifact.echo"],
                )
            ]
        elif mission.deliverables:
            steps = [
                PlanStep(
                    title="Produce requested deliverables",
                    description=(
                        "Complete the mission deliverables in one focused step and return artifacts that describe "
                        "the result."
                    ),
                    expected_artifacts=mission.deliverables,
                    allowed_tools=["artifact.echo"],
                )
            ]
        else:
            steps = [
                PlanStep(
                    title="Produce draft artifact",
                    description="Create the first deterministic dummy artifact for the mission.",
                    expected_artifacts=["draft artifact"],
                    allowed_tools=["artifact.echo"],
                ),
                PlanStep(
                    title="Validate final artifact",
                    description="Create the final deterministic dummy artifact for acceptance.",
                    expected_artifacts=["final artifact"],
                    allowed_tools=["artifact.echo"],
                ),
            ]
        return AgentCallResult(TaskPlan(selected_strategy=strategy.selected_strategy, steps=steps))

    def review(
        self,
        context: AgentContext,
        mission: MissionSpec,
        plan: TaskPlan,
        result: StepResult,
        *,
        retry_count: int,
        is_last_step: bool,
        validation_results: list[ValidationResult],
    ) -> AgentCallResult[ReviewResult]:
        intent = mission.intent.lower()
        if result.status in {StepStatus.BLOCKED_BY_AUTH, StepStatus.BLOCKED_BY_POLICY}:
            route = Route.AWAIT_AUTH if result.status == StepStatus.BLOCKED_BY_AUTH else Route.FAIL
            failure_type = FailureType.WORKER_ERROR if result.status == StepStatus.BLOCKED_BY_AUTH else FailureType.POLICY_BLOCK
            review = ReviewResult(
                step_id=result.step_id,
                passed=False,
                failure_type=failure_type,
                route=route,
                notes=result.error_log or result.status.value,
            )
        elif result.status == StepStatus.FAILED:
            if result.error_log and result.error_log.startswith("worker_error:"):
                review = ReviewResult(
                    step_id=result.step_id,
                    passed=False,
                    failure_type=FailureType.WORKER_ERROR,
                    route=Route.FAIL,
                    notes=result.error_log,
                )
            elif retry_count < mission.budget.max_step_retries and "fail" not in intent:
                review = ReviewResult(
                    step_id=result.step_id,
                    passed=False,
                    failure_type=FailureType.ARTIFACT_ERROR,
                    route=Route.RETRY_WORKER,
                    notes="Dummy reviewer allows one local worker retry.",
                )
            else:
                review = ReviewResult(
                    step_id=result.step_id,
                    passed=False,
                    failure_type=FailureType.ARTIFACT_ERROR,
                    route=Route.FAIL,
                    notes="Dummy reviewer exhausted retry budget or received hard fail intent.",
                )
        elif result.artifacts and result.artifacts[0].metadata.get("proposal"):
            review = ReviewResult(
                step_id=result.step_id,
                passed=True,
                failure_type=FailureType.NONE,
                route=Route.PROPOSE_NEXT_TASK,
                notes="Current mission should yield a NextTaskProposal.",
            )
        else:
            failed_required = []
            if is_last_step:
                failed_required = [
                    validation
                    for validation, criteria in zip(validation_results, mission.acceptance_criteria, strict=True)
                    if criteria.required and not validation.passed
                ]
            if failed_required:
                route = Route.RETRY_WORKER if retry_count < mission.budget.max_step_retries else Route.FAIL
                notes = "Artifact validation failed: " + "; ".join(item.message for item in failed_required)
                if route == Route.FAIL:
                    notes += " Retry budget exhausted."
                review = ReviewResult(
                    step_id=result.step_id,
                    passed=False,
                    failure_type=FailureType.ARTIFACT_ERROR,
                    route=route,
                    notes=notes,
                )
            else:
                route = Route.COMPLETE if is_last_step else Route.NEXT_STEP
                review = ReviewResult(step_id=result.step_id, passed=True, route=route)
        return AgentCallResult(review)


BRAINSTORM_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_strategy": {"type": "string"},
        "rationale": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
    "required": ["selected_strategy", "rationale", "risks", "notes"],
    "additionalProperties": False,
}


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_strategy": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                    "expected_artifacts": {"type": "array", "items": {"type": "string"}},
                    "allowed_tools": {"type": "array", "items": {"type": "string"}},
                    "max_retries": {"type": "integer"},
                },
                "required": ["title", "description", "depends_on", "expected_artifacts", "allowed_tools", "max_retries"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["selected_strategy", "steps"],
    "additionalProperties": False,
}


REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "failure_type": {
            "type": "string",
            "enum": ["none", "artifact_error", "strategy_error", "policy_block", "budget_exceeded", "worker_error"],
        },
        "route": {
            "type": "string",
            "enum": ["next_step", "retry_worker", "replan", "rebrainstorm", "propose_next_task", "await_auth", "fail", "complete"],
        },
        "notes": {"type": "string"},
    },
    "required": ["passed", "failure_type", "route", "notes"],
    "additionalProperties": False,
}


class CodexRoleAgentBackend:
    def __init__(self, options: CodexExecOptions | None = None, *, fallback_without_output_schema: bool = True) -> None:
        self.options = options or CodexExecOptions()
        self.fallback_without_output_schema = fallback_without_output_schema

    def brainstorm(self, context: AgentContext, mission: MissionSpec) -> AgentCallResult[BrainstormResult]:
        payload, usage = self._run_json(
            context,
            "brainstormer",
            None,
            BRAINSTORM_SCHEMA,
            _brainstorm_prompt(mission),
        )
        try:
            value = BrainstormResult.model_validate(_normalize_brainstorm_payload(payload))
        except ValidationError as exc:
            raise RoleAgentError("brainstormer", f"invalid brainstormer output: {exc}") from exc
        return AgentCallResult(value, **usage)

    def plan(
        self,
        context: AgentContext,
        mission: MissionSpec,
        strategy: BrainstormResult,
    ) -> AgentCallResult[TaskPlan]:
        payload, usage = self._run_json(
            context,
            "planner",
            None,
            PLAN_SCHEMA,
            _planner_prompt(mission, strategy),
        )
        try:
            payload = _normalize_plan_payload(payload)
            steps = [PlanStep.model_validate(_normalize_plan_step(item)) for item in payload.get("steps", [])]
            plan = TaskPlan(selected_strategy=str(payload.get("selected_strategy") or strategy.selected_strategy), steps=steps)
        except (ValidationError, ValueError) as exc:
            raise RoleAgentError("planner", f"invalid planner output: {exc}") from exc
        return AgentCallResult(plan, **usage)

    def review(
        self,
        context: AgentContext,
        mission: MissionSpec,
        plan: TaskPlan,
        result: StepResult,
        *,
        retry_count: int,
        is_last_step: bool,
        validation_results: list[ValidationResult],
    ) -> AgentCallResult[ReviewResult]:
        payload, usage = self._run_json(
            context,
            "strategy_reviewer",
            result.step_id,
            REVIEW_SCHEMA,
            _reviewer_prompt(
                mission,
                plan,
                result,
                retry_count=retry_count,
                is_last_step=is_last_step,
                validation_results=validation_results,
            ),
        )
        try:
            review = ReviewResult(step_id=result.step_id, **_normalize_review_payload(payload))
        except ValidationError as exc:
            raise RoleAgentError("strategy_reviewer", f"invalid reviewer output: {exc}") from exc
        return AgentCallResult(review, **usage)

    def _run_json(
        self,
        context: AgentContext,
        node: str,
        step_id: str | None,
        output_schema: dict,
        prompt: str,
    ) -> tuple[dict, dict[str, int]]:
        options = self.options.model_copy(update={"output_schema": output_schema})
        result, emitted_live = self._run_codex(prompt, context, node, step_id, options)
        if self._should_fallback(result, options):
            context.emit_event("codex_output_schema_fallback", node, step_id, {"reason": _fallback_reason(result)})
            fallback_options = options.model_copy(update={"use_output_schema": False})
            result, emitted_live = self._run_codex(
                prompt + "\n\nOutput only the JSON object. Do not use Markdown.",
                context,
                node,
                step_id,
                fallback_options,
            )

        if not emitted_live:
            for event in result.events:
                context.emit_event(map_codex_event_type(event), node, step_id, {"raw": event})

        if result.timed_out:
            raise RoleAgentError(node, "codex exec timed out")
        if result.returncode == 127:
            raise RoleAgentError(node, result.stderr or "codex binary not found")
        if result.returncode != 0:
            raise RoleAgentError(node, result.stderr or f"codex exec exited with code {result.returncode}")
        if not result.final_message:
            raise RoleAgentError(node, "codex exec produced no final agent message")
        try:
            payload = json.loads(result.final_message)
        except json.JSONDecodeError as exc:
            raise RoleAgentError(node, f"codex final message was not JSON: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise RoleAgentError(node, "codex final message JSON must be an object")
        usage = result.usage or {}
        return payload, {
            "tokens_used": int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0)),
            "tool_calls_used": sum(1 for event in result.events if str(map_codex_event_type(event)).endswith("_completed")),
        }

    def _run_codex(
        self,
        prompt: str,
        context: AgentContext,
        node: str,
        step_id: str | None,
        options: CodexExecOptions,
    ) -> tuple[CodexExecResult, bool]:
        emitted_live = False

        def emit_live(event):
            nonlocal emitted_live
            emitted_live = True
            context.emit_event(map_codex_event_type(event), node, step_id, {"raw": event})

        adapter = CodexExecAdapter(options)
        try:
            result = adapter.run(prompt, on_event=emit_live)
        except TypeError:
            result = adapter.run(prompt)
        return result, emitted_live

    def _should_fallback(self, result: CodexExecResult, options: CodexExecOptions) -> bool:
        if not self.fallback_without_output_schema or not options.use_output_schema:
            return False
        if result.ok and result.final_message:
            return False
        if result.returncode == 127 or result.timed_out:
            return False
        error_text = (result.stderr or "") + "\n" + _agent_error_summary(result)
        return result.returncode != 0 or "用户额度不足" in error_text or "responses" in error_text or "turn.failed" in error_text


def enforce_review_guards(
    review: ReviewResult,
    mission: MissionSpec,
    result: StepResult,
    *,
    retry_count: int,
    is_last_step: bool,
    validation_results: list[ValidationResult],
) -> ReviewResult:
    if result.status == StepStatus.BLOCKED_BY_AUTH and review.route != Route.AWAIT_AUTH:
        return ReviewResult(
            step_id=result.step_id,
            passed=False,
            failure_type=FailureType.WORKER_ERROR,
            route=Route.AWAIT_AUTH,
            notes=f"Hard guard: worker requested auth. Reviewer said {review.route.value}. {review.notes}",
        )
    if result.status == StepStatus.BLOCKED_BY_POLICY and review.route != Route.FAIL:
        return ReviewResult(
            step_id=result.step_id,
            passed=False,
            failure_type=FailureType.POLICY_BLOCK,
            route=Route.FAIL,
            notes=f"Hard guard: worker was blocked by policy. Reviewer said {review.route.value}. {review.notes}",
        )
    if result.status == StepStatus.FAILED and review.passed:
        route = Route.RETRY_WORKER if retry_count < mission.budget.max_step_retries else Route.FAIL
        return ReviewResult(
            step_id=result.step_id,
            passed=False,
            failure_type=FailureType.WORKER_ERROR if (result.error_log or "").startswith("worker_error:") else FailureType.ARTIFACT_ERROR,
            route=route,
            notes=f"Hard guard: failed worker result cannot pass review. {result.error_log or review.notes}",
        )

    failed_required = []
    if is_last_step:
        failed_required = [
            validation
            for validation, criteria in zip(validation_results, mission.acceptance_criteria, strict=True)
            if criteria.required and not validation.passed
        ]
    if failed_required and review.route == Route.COMPLETE:
        route = Route.RETRY_WORKER if retry_count < mission.budget.max_step_retries else Route.FAIL
        notes = "Hard guard: required artifact validation failed: " + "; ".join(item.message for item in failed_required)
        if route == Route.FAIL:
            notes += " Retry budget exhausted."
        return ReviewResult(
            step_id=result.step_id,
            passed=False,
            failure_type=FailureType.ARTIFACT_ERROR,
            route=route,
            notes=notes,
        )
    return review


def _brainstorm_prompt(mission: MissionSpec) -> str:
    return "\n\n".join(
        [
            "You are the MetaLoop Brainstormer agent.",
            "Your job is to propose the best execution strategy for this MissionSpec before planning begins.",
            "You must not edit files or execute the mission. Think about risks, task shape, and validation strategy.",
            "Return only JSON matching the required schema.",
            "MissionSpec:",
            mission.model_dump_json(indent=2),
        ]
    )


def _planner_prompt(mission: MissionSpec, strategy: BrainstormResult) -> str:
    return "\n\n".join(
        [
            "You are the MetaLoop Planner agent.",
            "Convert the MissionSpec and Brainstormer strategy into a concrete TaskPlan.",
            "Split complex work into meaningful steps instead of hiding everything in one generic step.",
            "Each step should be independently reviewable and should name expected artifacts.",
            "Do not edit files or execute the mission.",
            "Return only JSON matching the required schema.",
            "MissionSpec:",
            mission.model_dump_json(indent=2),
            "Brainstormer strategy:",
            strategy.model_dump_json(indent=2),
        ]
    )


def _reviewer_prompt(
    mission: MissionSpec,
    plan: TaskPlan,
    result: StepResult,
    *,
    retry_count: int,
    is_last_step: bool,
    validation_results: list[ValidationResult],
) -> str:
    return "\n\n".join(
        [
            "You are the MetaLoop Strategy Reviewer agent.",
            "Review the worker result against the current step, TaskPlan, MissionSpec, and validation results.",
            "Choose exactly one route: next_step, retry_worker, replan, rebrainstorm, propose_next_task, await_auth, fail, complete.",
            "Use complete only when this is the last step and the mission is genuinely satisfied.",
            "Use retry_worker when the current step is fixable by another worker attempt.",
            "Use replan or rebrainstorm when the plan or strategy is wrong rather than the worker's implementation.",
            "Use await_auth for sandbox/approval blocks. Use fail for unrecoverable errors.",
            "Do not edit files.",
            "Return only JSON matching the required schema.",
            f"Retry count for this step: {retry_count}",
            f"Is last step: {is_last_step}",
            "MissionSpec:",
            mission.model_dump_json(indent=2),
            "TaskPlan:",
            plan.model_dump_json(indent=2),
            "Worker StepResult:",
            result.model_dump_json(indent=2),
            "Local validation results:",
            json.dumps([item.model_dump() for item in validation_results], indent=2, ensure_ascii=False),
        ]
    )


def _normalize_plan_step(item):
    if not isinstance(item, dict):
        raise ValueError("Plan step must be an object")
    normalized = dict(item)
    normalized.setdefault("depends_on", [])
    normalized.setdefault("allowed_tools", [])
    normalized.setdefault("max_retries", 3)
    normalized["title"] = _normalize_optional_string(normalized.get("title")) or "Untitled step"
    normalized["description"] = _normalize_optional_string(normalized.get("description")) or normalized["title"]
    normalized["expected_artifacts"] = [
        str(artifact) for artifact in normalized.get("expected_artifacts", []) if str(artifact).strip()
    ]
    return normalized


def _normalize_brainstorm_payload(payload: dict) -> dict:
    normalized = dict(payload)
    normalized["selected_strategy"] = _normalize_optional_string(
        normalized.get("selected_strategy")
        or normalized.get("strategy")
        or normalized.get("recommended_strategy")
        or normalized.get("approach")
        or normalized.get("summary")
    ) or "Execute the mission with a conservative implementation and explicit validation."
    normalized["rationale"] = _normalize_optional_string(normalized.get("rationale") or normalized.get("reasoning")) or ""
    risks = normalized.get("risks")
    if risks is None:
        risks = normalized.get("key_risks") or normalized.get("risk_items") or []
    normalized["risks"] = _string_list(risks)
    normalized["notes"] = _normalize_optional_string(normalized.get("notes") or normalized.get("confidence")) or ""
    return {
        "selected_strategy": normalized["selected_strategy"],
        "rationale": normalized["rationale"],
        "risks": normalized["risks"],
        "notes": normalized["notes"],
    }


def _normalize_plan_payload(payload: dict) -> dict:
    normalized = dict(payload)
    if "steps" not in normalized:
        for key in ("execution_order", "plan", "tasks"):
            if isinstance(normalized.get(key), list):
                normalized["steps"] = normalized[key]
                break
    normalized.setdefault("steps", [])
    normalized["selected_strategy"] = _normalize_optional_string(
        normalized.get("selected_strategy") or normalized.get("strategy")
    ) or "Execute the mission plan."
    return normalized


def _normalize_review_payload(payload: dict) -> dict:
    normalized = dict(payload)
    route = normalized.get("route") or normalized.get("decision") or normalized.get("next_route")
    if isinstance(route, str):
        route = route.lower().strip()
        route_aliases = {
            "pass": "next_step",
            "passed": "next_step",
            "continue": "next_step",
            "next": "next_step",
            "retry": "retry_worker",
            "retry_step": "retry_worker",
            "auth": "await_auth",
            "blocked": "await_auth",
            "done": "complete",
            "completed": "complete",
            "success": "complete",
        }
        route = route_aliases.get(route, route)
    normalized["route"] = route or "fail"
    normalized["passed"] = bool(normalized.get("passed", normalized["route"] in {"next_step", "complete", "propose_next_task"}))
    normalized["failure_type"] = normalized.get("failure_type") or ("none" if normalized["passed"] else "artifact_error")
    normalized["notes"] = _normalize_optional_string(normalized.get("notes") or normalized.get("reason") or normalized.get("summary")) or ""
    return {
        "passed": normalized["passed"],
        "failure_type": normalized["failure_type"],
        "route": normalized["route"],
        "notes": normalized["notes"],
    }


def _string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = [value]
    result = []
    for item in items:
        if isinstance(item, dict):
            text = item.get("risk") or item.get("description") or item.get("message") or json.dumps(item, ensure_ascii=False)
        else:
            text = item
        text = str(text).strip()
        if text:
            result.append(text)
    return result


def _agent_error_summary(result: CodexExecResult) -> str:
    messages = []
    for event in result.events:
        if isinstance(event, dict):
            if isinstance(event.get("message"), str):
                messages.append(event["message"])
            error = event.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                messages.append(error["message"])
    return "\n".join(messages[-5:])
