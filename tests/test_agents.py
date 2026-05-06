from metaloop.agents import AgentContext, CodexRoleAgentBackend
from metaloop.codex_adapter import CodexExecResult
from metaloop.schemas import AcceptanceCriteria, BudgetUsage, MissionSpec, StepResult, StepStatus, TaskPlan


class SequenceAdapter:
    calls = 0
    results = []

    def __init__(self, _options) -> None:
        pass

    def run(self, _prompt: str) -> CodexExecResult:
        result = self.results[self.__class__.calls]
        self.__class__.calls += 1
        return result


def mission() -> MissionSpec:
    return MissionSpec(intent="Create a useful artifact", acceptance_criteria=[AcceptanceCriteria(description="done")])


def context(events):
    def emit(event_type, node=None, step_id=None, payload=None):
        events.append((event_type, node, step_id, payload or {}))

    return AgentContext(run_id="run_test", budget_usage=BudgetUsage(), emit_event=emit)


def result(message: str, *, tokens: int = 3) -> CodexExecResult:
    return CodexExecResult(
        events=[
            {"type": "item.completed", "item": {"type": "agent_message", "text": message}},
            {"type": "turn.completed", "usage": {"input_tokens": tokens, "output_tokens": 2}},
        ],
        final_message=message,
        usage={"input_tokens": tokens, "output_tokens": 2},
    )


def test_codex_role_agents_map_structured_outputs(monkeypatch) -> None:
    SequenceAdapter.calls = 0
    SequenceAdapter.results = [
        result('{"selected_strategy":"build then verify","rationale":"small task","risks":["missing tests"],"notes":""}'),
        result('{"selected_strategy":"build then verify","steps":[{"title":"Build","description":"Implement files","expected_artifacts":["files"]},{"title":"Verify","description":"Run checks","expected_artifacts":["passing checks"]}]}'),
        result('{"passed":true,"failure_type":"none","route":"next_step","notes":"first step done"}'),
    ]
    monkeypatch.setattr("metaloop.agents.CodexExecAdapter", SequenceAdapter)
    events = []
    backend = CodexRoleAgentBackend()

    brainstorm = backend.brainstorm(context(events), mission())
    plan = backend.plan(context(events), mission(), brainstorm.value)
    review = backend.review(
        context(events),
        mission(),
        TaskPlan(selected_strategy=plan.value.selected_strategy, steps=plan.value.steps),
        StepResult(step_id=plan.value.steps[0].step_id, status=StepStatus.SUCCESS),
        retry_count=0,
        is_last_step=False,
        validation_results=[],
    )

    assert brainstorm.value.selected_strategy == "build then verify"
    assert len(plan.value.steps) == 2
    assert review.value.route == "next_step"
    assert brainstorm.tokens_used == 5
    assert any(event_type == "codex_agent_message_completed" and node == "brainstormer" for event_type, node, *_ in events)
    assert any(event_type == "codex_agent_message_completed" and node == "planner" for event_type, node, *_ in events)
    assert any(event_type == "codex_agent_message_completed" and node == "strategy_reviewer" for event_type, node, *_ in events)


def test_codex_brainstormer_accepts_strategy_alias(monkeypatch) -> None:
    SequenceAdapter.calls = 0
    SequenceAdapter.results = [
        result('{"strategy":"Build a conservative MVP","key_risks":[{"risk":"missing fixture"}],"confidence":"high"}'),
    ]
    monkeypatch.setattr("metaloop.agents.CodexExecAdapter", SequenceAdapter)

    brainstorm = CodexRoleAgentBackend().brainstorm(context([]), mission())

    assert brainstorm.value.selected_strategy == "Build a conservative MVP"
    assert brainstorm.value.risks == ["missing fixture"]
    assert brainstorm.value.notes == "high"


def test_codex_role_output_schemas_are_strict_required() -> None:
    from metaloop.agents import BRAINSTORM_SCHEMA, PLAN_SCHEMA, REVIEW_SCHEMA

    for schema in [BRAINSTORM_SCHEMA, PLAN_SCHEMA, REVIEW_SCHEMA]:
        assert set(schema["required"]) == set(schema["properties"])
    step_schema = PLAN_SCHEMA["properties"]["steps"]["items"]
    assert set(step_schema["required"]) == set(step_schema["properties"])
