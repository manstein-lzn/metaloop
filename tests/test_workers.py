from metaloop.codex_adapter import CodexExecResult
from metaloop.kernel import MetaLoopKernel
from metaloop.schemas import AcceptanceCriteria, MissionSpec, PlanStep, RunStatus, StepResult, StepStatus, TaskPlan
from metaloop.workers import CodexExecWorkerBackend, WorkerContext, _fallback_reason


def mission(intent: str = "Create artifact") -> MissionSpec:
    return MissionSpec(intent=intent, acceptance_criteria=[AcceptanceCriteria(description="done")])


def plan() -> TaskPlan:
    return TaskPlan(
        selected_strategy="test",
        steps=[PlanStep(title="Step", description="Do work", allowed_tools=[])],
    )


class StaticAdapter:
    def __init__(self, result: CodexExecResult) -> None:
        self.result = result

    def run(self, _prompt: str) -> CodexExecResult:
        return self.result


class SequenceAdapter:
    calls = 0
    results = []

    def __init__(self, _options) -> None:
        pass

    def run(self, _prompt: str) -> CodexExecResult:
        result = self.results[self.__class__.calls]
        self.__class__.calls += 1
        return result


def context() -> WorkerContext:
    events = []
    kernel = MetaLoopKernel()
    state = kernel.run(mission())

    def emit(event_type, node=None, step_id=None, payload=None):
        event = state.add_event(event_type, node=node, step_id=step_id, payload=payload)
        events.append(event)
        return event

    return WorkerContext(
        run_id=state.mission.run_id,
        budget_usage=state.budget_usage,
        policy_engine=kernel.policy_engine,
        tool_registry=kernel.tool_registry,
        emit_event=emit,
    )


def test_codex_worker_maps_success(monkeypatch) -> None:
    result = CodexExecResult(
        events=[
            {"type": "item.completed", "item": {"type": "agent_message", "text": '{"status":"success","summary":"ok","artifacts":[{"kind":"text","content":"done"}]}'}},
            {"type": "turn.completed", "usage": {"input_tokens": 7, "output_tokens": 11}},
        ],
        final_message='{"status":"success","summary":"ok","artifacts":[{"kind":"text","content":"done"}]}',
        usage={"input_tokens": 7, "output_tokens": 11},
    )
    monkeypatch.setattr("metaloop.workers.CodexExecAdapter", lambda _options: StaticAdapter(result))

    step_result = CodexExecWorkerBackend().run_step(context(), mission(), plan(), plan().steps[0])

    assert step_result.status == StepStatus.SUCCESS
    assert step_result.tokens_used == 18
    assert step_result.artifacts[0].content == "done"


def test_codex_worker_output_schema_is_strict_required() -> None:
    from metaloop.workers import CODEX_WORKER_OUTPUT_SCHEMA

    assert set(CODEX_WORKER_OUTPUT_SCHEMA["required"]) == set(CODEX_WORKER_OUTPUT_SCHEMA["properties"])
    artifact_schema = CODEX_WORKER_OUTPUT_SCHEMA["properties"]["artifacts"]["items"]
    assert set(artifact_schema["required"]) == set(artifact_schema["properties"])


def test_codex_worker_missing_binary_fails(monkeypatch) -> None:
    result = CodexExecResult(returncode=127, stderr="codex binary not found")
    monkeypatch.setattr("metaloop.workers.CodexExecAdapter", lambda _options: StaticAdapter(result))

    step_result = CodexExecWorkerBackend().run_step(context(), mission(), plan(), plan().steps[0])

    assert step_result.status == StepStatus.FAILED
    assert "codex binary" in (step_result.error_log or "")
    assert (step_result.error_log or "").startswith("worker_error:")


def test_codex_worker_falls_back_without_output_schema(monkeypatch) -> None:
    SequenceAdapter.calls = 0
    SequenceAdapter.results = [
        CodexExecResult(
            returncode=1,
            events=[
                {
                    "type": "turn.failed",
                    "error": {"message": "unexpected status 403 Forbidden: 用户额度不足, url: /responses"},
                }
            ],
        ),
        CodexExecResult(
            events=[
                {"type": "item.completed", "item": {"type": "agent_message", "text": '{"status":"success","summary":"ok","artifacts":[]}'}},
                {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 2}},
            ],
            final_message='{"status":"success","summary":"ok","artifacts":[]}',
            usage={"input_tokens": 1, "output_tokens": 2},
        ),
    ]
    monkeypatch.setattr("metaloop.workers.CodexExecAdapter", SequenceAdapter)
    worker_context = context()

    step_result = CodexExecWorkerBackend().run_step(worker_context, mission(), plan(), plan().steps[0])

    assert SequenceAdapter.calls == 2
    assert step_result.status == StepStatus.SUCCESS


def test_codex_worker_does_not_fallback_when_disabled(monkeypatch) -> None:
    SequenceAdapter.calls = 0
    SequenceAdapter.results = [
        CodexExecResult(
            returncode=1,
            events=[
                {
                    "type": "turn.failed",
                    "error": {"message": "unexpected status 403 Forbidden: 用户额度不足, url: /responses"},
                }
            ],
        ),
        CodexExecResult(final_message='{"status":"success","summary":"ok","artifacts":[]}'),
    ]
    monkeypatch.setattr("metaloop.workers.CodexExecAdapter", SequenceAdapter)

    step_result = CodexExecWorkerBackend(fallback_without_output_schema=False).run_step(context(), mission(), plan(), plan().steps[0])

    assert SequenceAdapter.calls == 1
    assert step_result.status == StepStatus.FAILED


def test_codex_fallback_reason_truncates_html_noise() -> None:
    result = CodexExecResult(
        returncode=1,
        stderr="WARN plugin sync failed\n<html>\n" + ("x" * 2000) + "\n</html>\nERROR final line",
        events=[{"type": "turn.failed", "error": {"message": "provider failed on /responses"}}],
    )

    reason = _fallback_reason(result, max_length=180)

    assert "provider failed on /responses" in reason
    assert "<html>...[redacted]" in reason
    assert "x" * 20 not in reason
    assert len(reason) <= 180


def test_codex_worker_normalizes_loose_artifacts(monkeypatch) -> None:
    result = CodexExecResult(
        events=[
            {"type": "item.completed", "item": {"type": "agent_message", "text": '{"status":"completed","summary":"ok","artifacts":[{"name":"draft","description":"loose"}],"error_log":["note"]}'}},
        ],
        final_message='{"status":"completed","summary":"ok","artifacts":[{"name":"draft","description":"loose"}],"error_log":["note"]}',
    )
    monkeypatch.setattr("metaloop.workers.CodexExecAdapter", lambda _options: StaticAdapter(result))

    step_result = CodexExecWorkerBackend().run_step(context(), mission(), plan(), plan().steps[0])

    assert step_result.status == StepStatus.SUCCESS
    assert step_result.artifacts[0].kind == "text"
    assert "draft" in (step_result.artifacts[0].content or "")
    assert step_result.error_log == "note"


class BudgetBurnWorker:
    def run_step(self, context, mission, task_plan, step, *, retry_count=0):
        return StepResult(step_id=step.step_id, status=StepStatus.SUCCESS, tokens_used=999999)


def test_kernel_checks_budget_after_worker() -> None:
    low_budget_mission = mission()
    low_budget_mission.budget.max_tokens = 1

    state = MetaLoopKernel(worker_backend=BudgetBurnWorker()).run(low_budget_mission)

    assert state.status == RunStatus.FAILED
    assert state.failure_report is not None
    assert state.failure_report.error_type == "budget_exceeded"
    assert any(event.event_type == "budget_exceeded" for event in state.events)
