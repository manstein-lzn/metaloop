from metaloop.kernel import MetaLoopKernel
from metaloop.schemas import AcceptanceCriteria, MissionSpec, Route, RunStatus, StepResult, StepStatus


def mission(intent: str) -> MissionSpec:
    return MissionSpec(
        intent=intent,
        acceptance_criteria=[AcceptanceCriteria(description="Dummy acceptance")],
    )


def test_kernel_completes_happy_path() -> None:
    state = MetaLoopKernel().run(mission("Create a dummy artifact"))

    assert state.status == RunStatus.COMPLETED
    assert state.mission.locked is True
    assert state.plan is not None
    assert len(state.step_results) == 2
    assert state.review_results[-1].route == Route.COMPLETE
    assert state.failure_report is None


def test_kernel_retries_then_completes() -> None:
    state = MetaLoopKernel().run(mission("Create a dummy artifact with retry"))

    assert state.status == RunStatus.COMPLETED
    assert state.budget_usage.step_retries
    assert len(state.step_results) == 3
    assert any(event.event_type == "budget_updated" for event in state.events)


def test_kernel_can_fail() -> None:
    state = MetaLoopKernel().run(mission("Create a dummy artifact but fail"))

    assert state.status == RunStatus.FAILED
    assert state.failure_report is not None
    assert state.failure_report.error_type == "artifact_error"


def test_kernel_yields_next_task_proposal() -> None:
    state = MetaLoopKernel().run(mission("Please split this into a next task proposal"))

    assert state.status == RunStatus.PROPOSED_NEXT_TASK
    assert state.next_task_proposal is not None
    assert state.next_task_proposal.source_run_id == state.mission.run_id
    assert any(event.event_type == "next_task_proposed" for event in state.events)


def test_kernel_uses_single_step_for_declared_deliverables() -> None:
    mission_spec = mission("Summarize repository")
    mission_spec.deliverables = ["one sentence summary"]

    state = MetaLoopKernel().run(mission_spec)

    assert state.status == RunStatus.COMPLETED
    assert state.plan is not None
    assert len(state.plan.steps) == 1
    assert state.plan.steps[0].expected_artifacts == ["one sentence summary"]


class AuthBlockedWorker:
    def run_step(self, _context, _mission, _task_plan, step, *, retry_count=0):
        return StepResult(step_id=step.step_id, status=StepStatus.BLOCKED_BY_AUTH, error_log="needs approval")


def test_kernel_blocks_on_worker_auth_request() -> None:
    state = MetaLoopKernel(worker_backend=AuthBlockedWorker()).run(mission("Need protected operation"))

    assert state.status == RunStatus.BLOCKED
    assert state.failure_report is not None
    assert state.failure_report.recoverable is True
    assert state.review_results[-1].route == Route.AWAIT_AUTH
    assert any(event.event_type == "run_blocked" for event in state.events)
    assert state.events[-1].event_type == "run_ended"
