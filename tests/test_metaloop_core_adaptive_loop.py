from __future__ import annotations

import json

from metaloop_core import WorkspaceState
from metaloop_core.adaptive_loop import (
    append_iteration,
    decide_next,
    load_adaptive_loop,
    new_adaptive_loop,
    record_iteration,
    validate_adaptive_loop,
    write_adaptive_loop,
)


def test_new_adaptive_loop_is_generic_and_valid() -> None:
    state = new_adaptive_loop(
        goal="Reduce production error rate below the agreed threshold.",
        current_plan="Inspect recent failures and choose the highest-signal fix.",
        constraints=["Do not weaken user-facing validation."],
        success_criteria=["Error rate is below threshold on held-out traffic."],
        known_facts=["Current best result is still above threshold."],
        open_questions=["Is the main bottleneck data quality or implementation behavior?"],
    )

    assert state["schema"] == "metaloop.adaptive_goal_loop"
    assert state["status"] == "active"
    assert state["iterations"] == []
    assert validate_adaptive_loop(state) == []


def test_append_iteration_records_observe_evaluate_diagnose_decide_next_plan() -> None:
    state = new_adaptive_loop(goal="Improve a measurable target.", current_plan="Run the first diagnostic attempt.")

    updated = append_iteration(
        state,
        plan="Run the first diagnostic attempt.",
        rationale="This distinguishes implementation bugs from goal-definition issues.",
        observation="The run produced artifacts, but the target metric did not improve.",
        evaluation_status="not_satisfied",
        diagnosis="The likely issue is an implementation bug in the candidate change.",
        next_plan="Repair the implementation bug, rerun the same metric gate, and compare against baseline.",
        decision="repair",
        evidence=[".metaloop/verification_result.json"],
    )

    iteration = updated["iterations"][0]
    assert updated["status"] == "active"
    assert updated["current_plan"].startswith("Repair the implementation bug")
    assert iteration["decision"] == "repair"
    assert iteration["observation"].startswith("The run produced artifacts")
    assert iteration["diagnosis"].startswith("The likely issue")
    assert iteration["evidence"] == [".metaloop/verification_result.json"]


def test_record_iteration_persists_loop_and_workspace_state(tmp_path) -> None:
    state = new_adaptive_loop(goal="Ship a reliable feature.", current_plan="Implement and test the smallest useful slice.")
    write_adaptive_loop(tmp_path, state)

    updated = record_iteration(
        tmp_path,
        plan="Implement and test the smallest useful slice.",
        observation="Tests pass, but reviewer found the acceptance criteria missed an edge case.",
        evaluation_status="partial",
        diagnosis="The contract is too narrow for the actual user workflow.",
        next_plan="Redesign acceptance criteria to include the edge case before more implementation.",
        decision="redesign",
    )

    loaded = load_adaptive_loop(tmp_path)
    workspace_status = WorkspaceState(tmp_path).status()

    assert loaded == updated
    assert workspace_status["adaptive_loop"]["state"] == "ready"
    assert workspace_status["adaptive_loop"]["status"] == "active"
    assert loaded["iterations"][0]["decision"] == "redesign"


def test_decide_next_uses_general_problem_solving_vocabulary() -> None:
    assert decide_next(evaluation_status="satisfied") == "complete"
    assert decide_next(evaluation_status="invalid_goal", diagnosis="Acceptance is wrong") == "redesign"
    assert decide_next(evaluation_status="blocked", diagnosis="GPU resource requires approval") == "escalate"
    assert decide_next(evaluation_status="not_satisfied", diagnosis="wrong direction, pivot away") == "continue"
    assert decide_next(evaluation_status="partial", diagnosis="Need another high-signal attempt") == "continue"


def test_decide_next_does_not_infer_semantic_route_from_keywords() -> None:
    assert decide_next(evaluation_status="partial", diagnosis="implementation bug requires repair") == "continue"
    assert decide_next(evaluation_status="partial", diagnosis="scope is wrong and needs redesign") == "continue"
    assert decide_next(evaluation_status="partial", next_plan="pivot to another architecture") == "continue"


def test_adaptive_loop_validation_rejects_missing_diagnosis() -> None:
    state = new_adaptive_loop(goal="Improve a target.", current_plan="Try a plan.")
    state["iterations"] = [
        {
            "schema": "metaloop.adaptive_goal_iteration",
            "version": "1.0",
            "iteration_id": "iteration_bad",
            "created_at": "2026-05-09T00:00:00Z",
            "goal": "Improve a target.",
            "plan": "Try a plan.",
            "observation": "It failed.",
            "evaluation_status": "not_satisfied",
            "diagnosis": "",
            "decision": "continue",
            "next_plan": "Try again with a reason.",
            "evidence": [],
        }
    ]

    errors = validate_adaptive_loop(json.loads(json.dumps(state)))

    assert any("diagnosis" in error for error in errors)
