from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from metaloop.agents import (
    AgentCallResult,
    AgentContext,
    BrainstormResult,
    RoleAgentBackend,
    RoleAgentError,
    RuleBasedRoleAgentBackend,
    enforce_review_guards,
)
from metaloop.policy import PolicyEngine
from metaloop.schemas import (
    AcceptanceCriteria,
    FailureReport,
    FailureType,
    KernelState,
    MissionSpec,
    NextTaskProposal,
    PlanStep,
    ReviewResult,
    Route,
    RunStatus,
    StepResult,
    StepStatus,
    SystemEvent,
)
from metaloop.storage import SQLiteRunStore
from metaloop.tools import ToolRegistry, make_default_registry
from metaloop.validators import ArtifactValidator
from metaloop.workers import DummyWorkerBackend, WorkerBackend, WorkerContext


@dataclass(frozen=True)
class KernelLimits:
    max_scheduler_ticks: int = 100


class MetaLoopKernel:
    """Flat closed-loop runner with pluggable role agents.

    Codex-backed runs use separate Brainstormer, Planner, Worker, and Reviewer
    calls. Scheduler, policy, checkpoints, and validation guards stay local.
    """

    CHECKPOINT_EVENTS = {
        "mission_locked",
        "node_completed",
        "budget_updated",
        "next_task_proposed",
        "run_completed",
        "run_failed",
        "run_ended",
    }

    def __init__(
        self,
        limits: KernelLimits | None = None,
        *,
        store: SQLiteRunStore | None = None,
        policy_engine: PolicyEngine | None = None,
        tool_registry: ToolRegistry | None = None,
        worker_backend: WorkerBackend | None = None,
        role_agent_backend: RoleAgentBackend | None = None,
        artifact_validator: ArtifactValidator | None = None,
    ) -> None:
        self.limits = limits or KernelLimits()
        self.store = store
        self.policy_engine = policy_engine or PolicyEngine()
        self.tool_registry = tool_registry or make_default_registry(self.policy_engine)
        self.worker_backend = worker_backend or DummyWorkerBackend(self.tool_registry)
        self.role_agent_backend = role_agent_backend or RuleBasedRoleAgentBackend()
        self.artifact_validator = artifact_validator or ArtifactValidator(self.policy_engine)

    def run(self, mission: MissionSpec) -> KernelState:
        state = KernelState(mission=mission)
        state.status = RunStatus.RUNNING
        if self.store is not None:
            self.store.start_run(state)
        self._event(state, "run_started", node="system")

        try:
            self._co_design_gateway(state)
            if state.status != RunStatus.RUNNING:
                pass
            else:
                self._brainstorm(state)
            if state.status != RunStatus.RUNNING:
                pass
            else:
                self._plan(state)
            if state.status != RunStatus.RUNNING:
                pass
            else:
                self._execute_inner_loop(state)
        except RoleAgentError as exc:
            state.status = RunStatus.FAILED
            state.failure_report = FailureReport(
                run_id=state.mission.run_id,
                failed_node=exc.node,
                error_type=FailureType.STRATEGY_ERROR.value,
                message=exc.message,
                recoverable=False,
            )
            self._event(
                state,
                "run_failed",
                node=exc.node,
                payload={"error_type": FailureType.STRATEGY_ERROR.value, "message": exc.message},
            )
        except Exception as exc:  # pragma: no cover - defensive final guard
            state.status = RunStatus.FAILED
            state.failure_report = FailureReport(
                run_id=state.mission.run_id,
                failed_node="kernel",
                error_type=exc.__class__.__name__,
                message=str(exc),
                recoverable=False,
            )
            self._event(
                state,
                "run_failed",
                node="system",
                payload={"error_type": exc.__class__.__name__, "message": str(exc)},
            )

        if state.status in {RunStatus.COMPLETED, RunStatus.PROPOSED_NEXT_TASK, RunStatus.FAILED, RunStatus.BLOCKED}:
            self._event(state, "run_ended", node="system", payload={"status": state.status.value})
        if self.store is not None:
            self.store.finish_run(state)
        return state

    def stream(self, mission: MissionSpec) -> Iterable[KernelState]:
        """Yield state snapshots after every event boundary.

        The first milestone keeps streaming simple: it runs the kernel and then
        yields cumulative event snapshots. The public shape is useful for a TUI
        even before a true async graph runner exists.
        """

        final_state = self.run(mission)
        for event_index in range(1, len(final_state.events) + 1):
            snapshot = final_state.model_copy(deep=True)
            snapshot.events = final_state.events[:event_index]
            yield snapshot

    def _co_design_gateway(self, state: KernelState) -> None:
        self._event(state, "co_design_started", node="gateway")
        workspace_decision = self.policy_engine.check_workspace_path(state.mission, ".")
        if not workspace_decision.allowed:
            self._fail(state, "gateway", None, "policy_block", workspace_decision.reason)
            return
        state.mission.locked = True
        self._event(
            state,
            "mission_locked",
            node="gateway",
            payload={"run_id": state.mission.run_id, "criteria": len(state.mission.acceptance_criteria)},
        )

    def _brainstorm(self, state: KernelState) -> None:
        self._event(state, "node_started", node="brainstormer")
        result = self.role_agent_backend.brainstorm(self._agent_context(state), state.mission)
        self._record_agent_usage(state, result)
        if not self._ensure_budget(state, "brainstormer", None):
            return
        state.strategy = result.value.selected_strategy
        self._event(
            state,
            "node_completed",
            node="brainstormer",
            payload={
                "strategy": state.strategy,
                "risks": result.value.risks,
                "rationale": result.value.rationale,
            },
        )

    def _plan(self, state: KernelState) -> None:
        self._event(state, "node_started", node="planner")
        strategy = BrainstormResult(selected_strategy=state.strategy or "default_strategy")
        result = self.role_agent_backend.plan(self._agent_context(state), state.mission, strategy)
        self._record_agent_usage(state, result)
        if not self._ensure_budget(state, "planner", None):
            return
        state.plan = result.value
        self._event(
            state,
            "node_completed",
            node="planner",
            payload={"plan_id": state.plan.plan_id, "steps": [step.title for step in state.plan.steps]},
        )

    def _execute_inner_loop(self, state: KernelState) -> None:
        ticks = 0
        while state.status == RunStatus.RUNNING:
            ticks += 1
            if ticks > self.limits.max_scheduler_ticks:
                self._fail(state, "scheduler", None, "scheduler_tick_limit", "Scheduler tick limit exceeded")
                return

            budget_decision = self.policy_engine.check_budget(state.mission, state.budget_usage)
            if not budget_decision.allowed:
                self._fail(state, "scheduler", None, "budget_exceeded", budget_decision.reason)
                return

            step = state.current_step
            if step is None:
                state.status = RunStatus.COMPLETED
                self._event(state, "run_completed", node="scheduler")
                return

            self._event(state, "scheduler_routed", node="scheduler", step_id=step.step_id, payload={"route": "worker"})
            result = self._worker(state, step)
            review = self._review(state, result)
            self._schedule_after_review(state, review)

    def _worker(self, state: KernelState, step: PlanStep) -> StepResult:
        self._event(state, "node_started", node="worker", step_id=step.step_id)
        if state.plan is None:
            raise RuntimeError("worker cannot run without a task plan")
        result = self.worker_backend.run_step(
            self._worker_context(state),
            state.mission,
            state.plan,
            step,
            retry_count=state.budget_usage.retry_count_for(step.step_id),
        )

        state.step_results.append(result)
        state.budget_usage.tokens += result.tokens_used
        state.budget_usage.tool_calls += result.tool_calls_used
        self._event(
            state,
            "node_completed",
            node="worker",
            step_id=step.step_id,
            payload={"status": result.status.value, "artifacts": len(result.artifacts)},
        )
        budget_decision = self.policy_engine.check_budget(state.mission, state.budget_usage)
        if not budget_decision.allowed:
            result.status = StepStatus.FAILED
            result.error_log = budget_decision.reason
            self._event(
                state,
                "budget_exceeded",
                node="worker",
                step_id=step.step_id,
                payload={"reason": budget_decision.reason},
            )
        return result

    def _review(self, state: KernelState, result: StepResult) -> ReviewResult:
        self._event(state, "node_started", node="strategy_reviewer", step_id=result.step_id)
        if state.plan is None:
            raise RuntimeError("reviewer cannot run without a task plan")
        is_last_step = self._is_last_step(state, result.step_id)
        validation_results = []
        if is_last_step:
            validation_results = self.artifact_validator.validate(state.mission)
            self._event(
                state,
                "artifact_validated",
                node="artifact_validator",
                step_id=result.step_id,
                payload={"results": [item.model_dump() for item in validation_results]},
            )
        retry_count = state.budget_usage.retry_count_for(result.step_id)
        agent_result = self.role_agent_backend.review(
            self._agent_context(state),
            state.mission,
            state.plan,
            result,
            retry_count=retry_count,
            is_last_step=is_last_step,
            validation_results=validation_results,
        )
        self._record_agent_usage(state, agent_result)
        if not self._ensure_budget(state, "strategy_reviewer", result.step_id):
            guarded_review = ReviewResult(
                step_id=result.step_id,
                passed=False,
                failure_type=FailureType.BUDGET_EXCEEDED,
                route=Route.FAIL,
                notes="budget exceeded",
            )
            state.review_results.append(guarded_review)
            return guarded_review
        review = enforce_review_guards(
            agent_result.value,
            state.mission,
            result,
            retry_count=retry_count,
            is_last_step=is_last_step,
            validation_results=validation_results,
        )
        if review != agent_result.value:
            self._event(
                state,
                "review_guard_applied",
                node="strategy_reviewer",
                step_id=result.step_id,
                payload={"original_route": agent_result.value.route.value, "guarded_route": review.route.value},
            )
        state.review_results.append(review)
        self._event(
            state,
            "node_completed",
            node="strategy_reviewer",
            step_id=result.step_id,
            payload={"route": review.route.value, "passed": review.passed},
        )
        return review

    def _record_agent_usage(self, state: KernelState, result: AgentCallResult) -> None:
        state.budget_usage.tokens += result.tokens_used
        state.budget_usage.tool_calls += result.tool_calls_used

    def _ensure_budget(self, state: KernelState, node: str, step_id: str | None) -> bool:
        budget_decision = self.policy_engine.check_budget(state.mission, state.budget_usage)
        if budget_decision.allowed:
            return True
        self._fail(state, node, step_id, "budget_exceeded", budget_decision.reason)
        return False

    def _agent_context(self, state: KernelState) -> AgentContext:
        return AgentContext(
            run_id=state.mission.run_id,
            budget_usage=state.budget_usage,
            emit_event=lambda event_type, node=None, step_id=None, payload=None: self._event(
                state,
                event_type,
                node=node,
                step_id=step_id,
                payload=payload,
            ),
        )

    def _schedule_after_review(self, state: KernelState, review: ReviewResult) -> None:
        self._event(
            state,
            "scheduler_routed",
            node="scheduler",
            step_id=review.step_id,
            payload={"route": review.route.value},
        )

        if review.route == Route.NEXT_STEP:
            state.current_step_index += 1
            return

        if review.route == Route.COMPLETE:
            state.status = RunStatus.COMPLETED
            self._event(state, "run_completed", node="scheduler")
            return

        if review.route == Route.RETRY_WORKER:
            state.budget_usage.step_retries[review.step_id] = state.budget_usage.retry_count_for(review.step_id) + 1
            self._event(
                state,
                "budget_updated",
                node="scheduler",
                step_id=review.step_id,
                payload={"step_retries": state.budget_usage.step_retries[review.step_id]},
            )
            return

        if review.route == Route.REPLAN:
            if not self._consume_replan_budget(state, review):
                return
            state.current_step_index = 0
            self._plan(state)
            return

        if review.route == Route.REBRAINSTORM:
            if not self._consume_replan_budget(state, review):
                return
            state.current_step_index = 0
            self._brainstorm(state)
            if state.status == RunStatus.RUNNING:
                self._plan(state)
            return

        if review.route == Route.PROPOSE_NEXT_TASK:
            state.next_task_proposal = self._build_next_task_proposal(state, review)
            state.status = RunStatus.PROPOSED_NEXT_TASK
            self._event(
                state,
                "next_task_proposed",
                node="scheduler",
                step_id=review.step_id,
                payload={"proposal_id": state.next_task_proposal.proposal_id},
            )
            return

        if review.route == Route.FAIL:
            self._fail(state, "scheduler", review.step_id, review.failure_type.value, review.notes)
            return

        if review.route == Route.AWAIT_AUTH:
            state.status = RunStatus.BLOCKED
            state.failure_report = FailureReport(
                run_id=state.mission.run_id,
                failed_node="scheduler",
                failed_step_id=review.step_id,
                error_type=review.failure_type.value,
                message=review.notes,
                recoverable=True,
                recommended_next_step="Authorize the required operation or rerun with adjusted sandbox/approval settings.",
            )
            self._event(
                state,
                "run_blocked",
                node="scheduler",
                step_id=review.step_id,
                payload={"reason": review.notes, "recoverable": True},
            )
            return

        self._fail(state, "scheduler", review.step_id, "unsupported_route", f"Unsupported route: {review.route}")

    def _consume_replan_budget(self, state: KernelState, review: ReviewResult) -> bool:
        if state.budget_usage.replan_count >= state.mission.budget.max_replan_count:
            self._fail(
                state,
                "scheduler",
                review.step_id,
                FailureType.STRATEGY_ERROR.value,
                f"Replan budget exhausted. Last reviewer note: {review.notes}",
            )
            return False
        state.budget_usage.replan_count += 1
        self._event(
            state,
            "budget_updated",
            node="scheduler",
            step_id=review.step_id,
            payload={"replan_count": state.budget_usage.replan_count, "route": review.route.value},
        )
        return True

    def _build_next_task_proposal(self, state: KernelState, review: ReviewResult) -> NextTaskProposal:
        return NextTaskProposal(
            source_run_id=state.mission.run_id,
            source_step_id=review.step_id,
            reason=review.notes or "Task should continue in a separate MetaLoop run.",
            suggested_intent=f"Continue from {state.mission.intent}",
            required_context={
                "source_run_id": state.mission.run_id,
                "source_deliverables": state.mission.deliverables,
            },
            expected_artifacts=["independent closed-loop result"],
            suggested_acceptance_criteria=[
                AcceptanceCriteria(description="New MetaLoop run produces a verified result.")
            ],
            blocking=True,
        )

    def _is_last_step(self, state: KernelState, step_id: str) -> bool:
        if state.plan is None:
            return True
        return state.plan.steps[-1].step_id == step_id

    def _fail(
        self,
        state: KernelState,
        node: str,
        step_id: str | None,
        error_type: str,
        message: str,
    ) -> None:
        recoverable = error_type == "budget_exceeded"
        state.status = RunStatus.FAILED
        state.failure_report = FailureReport(
            run_id=state.mission.run_id,
            failed_node=node,
            failed_step_id=step_id,
            error_type=error_type,
            message=message,
            recoverable=recoverable,
            recommended_next_step="Resume with a larger budget or simplify the mission." if recoverable else None,
        )
        self._event(
            state,
            "run_failed",
            node=node,
            step_id=step_id,
            payload={"error_type": error_type, "message": message},
        )

    def _event(
        self,
        state: KernelState,
        event_type: str,
        *,
        node: str | None = None,
        step_id: str | None = None,
        payload: dict | None = None,
    ) -> SystemEvent:
        event = state.add_event(event_type, node=node, step_id=step_id, payload=payload)
        if self.store is not None:
            self.store.append_event(event, len(state.events))
            if event_type in self.CHECKPOINT_EVENTS:
                self.store.save_checkpoint(state)
        return event

    def _worker_context(self, state: KernelState) -> WorkerContext:
        return WorkerContext(
            run_id=state.mission.run_id,
            budget_usage=state.budget_usage,
            policy_engine=self.policy_engine,
            tool_registry=self.tool_registry,
            emit_event=lambda event_type, node=None, step_id=None, payload=None: self._event(
                state,
                event_type,
                node=node,
                step_id=step_id,
                payload=payload,
            ),
            deadline_seconds=state.mission.budget.max_wall_time_seconds,
        )
