from __future__ import annotations

import json

from metaloop_core import WorkspaceState
from metaloop_core.adaptive_loop import new_adaptive_loop, record_iteration, write_adaptive_loop
from metaloop_core.execution import build_execution_report, write_execution_report
from metaloop_core.feedback import diagnose_next, observe_workspace, write_diagnosis_report, write_observation_report
from metaloop_core.verification import write_verification_result


def test_observe_workspace_reports_missing_feedback(tmp_path) -> None:
    observation = observe_workspace(tmp_path)
    diagnosis = diagnose_next(observation)

    assert observation["schema"] == "metaloop.observation_report"
    assert observation["status"] == "missing_feedback"
    assert diagnosis["schema"] == "metaloop.diagnosis_report"
    assert diagnosis["evaluation_status"] == "unknown"
    assert diagnosis["decision"] == "continue"


def test_observe_workspace_summarizes_completed_verified_feedback(tmp_path) -> None:
    capsule = {"capsule_id": "capsule_test", "revision": 1}
    report = build_execution_report(workspace=tmp_path, capsule=capsule, status="completed", commands=[{"command": "true"}], evidence=["ok"])
    write_execution_report(tmp_path, report)
    write_verification_result(
        tmp_path,
        {
            "status": "completed_verified",
            "reason": "All gates passed.",
            "hard_validator_results": [{"severity": "blocking", "passed": True}],
            "forbidden_path_results": [],
            "manual_validator_results": [],
            "unsupported_validator_results": [],
        },
    )

    observation = observe_workspace(tmp_path, write=True)
    diagnosis = diagnose_next(observation)
    write_diagnosis_report(tmp_path, diagnosis)

    assert observation["status"] == "satisfied"
    assert observation["signals"]["command_count"] == 1
    assert diagnosis["decision"] == "complete"
    status = WorkspaceState(tmp_path).status()
    assert status["observation"]["status"] == "satisfied"
    assert status["diagnosis"]["status"] == "satisfied"


def test_diagnose_next_routes_hard_failure_to_repair_or_continue(tmp_path) -> None:
    write_verification_result(
        tmp_path,
        {
            "status": "failed",
            "reason": "One validator failed.",
            "hard_validator_results": [{"severity": "blocking", "passed": False}],
            "forbidden_path_results": [],
            "manual_validator_results": [],
            "unsupported_validator_results": [],
        },
    )

    observation = observe_workspace(tmp_path)
    diagnosis = diagnose_next(observation)
    repair = diagnose_next(observation, next_plan="Repair the implementation bug and rerun locked gates.")

    assert observation["status"] == "not_satisfied"
    assert observation["signals"]["hard_failures"] == 1
    assert diagnosis["evaluation_status"] == "not_satisfied"
    assert diagnosis["decision"] == "continue"
    assert repair["decision"] == "repair"


def test_diagnose_next_routes_manual_and_unsupported_blockers(tmp_path) -> None:
    write_verification_result(
        tmp_path,
        {
            "status": "review_required",
            "reason": "Review blocker.",
            "hard_validator_results": [],
            "forbidden_path_results": [],
            "manual_validator_results": [{"severity": "blocking", "passed": False, "delegable": True, "reviewer": "codex_reviewer"}],
            "unsupported_validator_results": [],
        },
    )
    manual = diagnose_next(observe_workspace(tmp_path))
    assert manual["evaluation_status"] == "blocked"
    assert manual["decision"] == "escalate"

    write_verification_result(
        tmp_path,
        {
            "status": "unsupported_verification_spec",
            "reason": "Unsupported blocker.",
            "hard_validator_results": [],
            "forbidden_path_results": [],
            "manual_validator_results": [],
            "unsupported_validator_results": [{"severity": "blocking", "passed": False}],
        },
    )
    unsupported = diagnose_next(observe_workspace(tmp_path))
    assert unsupported["evaluation_status"] == "blocked"
    assert unsupported["decision"] == "escalate"


def test_feedback_can_feed_adaptive_loop_iteration(tmp_path) -> None:
    write_adaptive_loop(
        tmp_path,
        new_adaptive_loop(goal="Reach a locked target.", current_plan="Run a first attempt and verify it."),
    )
    write_verification_result(
        tmp_path,
        {
            "status": "failed",
            "reason": "Metric gate failed.",
            "hard_validator_results": [{"severity": "blocking", "passed": False}],
            "forbidden_path_results": [],
            "manual_validator_results": [],
            "unsupported_validator_results": [],
        },
    )
    observation = observe_workspace(tmp_path, write=True)
    diagnosis = diagnose_next(observation, next_plan="Repair the implementation bug and rerun the same metric gate.")
    write_diagnosis_report(tmp_path, diagnosis)

    updated = record_iteration(
        tmp_path,
        plan="Run a first attempt and verify it.",
        observation=observation["summary"],
        evaluation_status=diagnosis["evaluation_status"],
        diagnosis=diagnosis["diagnosis"],
        decision=diagnosis["decision"],
        next_plan=diagnosis["next_plan"],
        evidence=diagnosis["evidence"],
    )

    assert updated["iterations"][0]["decision"] == "repair"
    assert json.loads((tmp_path / ".metaloop" / "adaptive_loop.json").read_text(encoding="utf-8"))["iterations"]
