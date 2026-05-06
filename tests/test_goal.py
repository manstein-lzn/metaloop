import json

from metaloop.goal import ExecutionReport, VerificationStatus, compile_goal_contract, render_goal_objective, verify_mission
from metaloop.schemas import AcceptanceCriteria, MissionSpec, PolicyScope


def test_compile_goal_contract_preserves_mission_boundaries(tmp_path) -> None:
    mission = MissionSpec(
        intent="Build a local tool",
        context={"constraints": ["local only"], "out_of_scope": ["cloud sync"]},
        deliverables=["tool.py"],
        acceptance_criteria=[AcceptanceCriteria(description="tool.py exists", validation_type="file_exists", validation_target="tool.py")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    contract = compile_goal_contract(mission)

    assert contract.mission_id == mission.run_id
    assert contract.objective == "Build a local tool"
    assert contract.key_tasks == ["tool.py"]
    assert contract.required_evidence_count == 2
    assert "artifact" in contract.required_evidence_summary
    assert "local only" in contract.constraints
    assert "cloud sync" in contract.out_of_scope
    assert contract.required_report_path == ".metaloop/execution_report.json"


def test_render_goal_objective_embeds_contract_and_report_schema(tmp_path) -> None:
    mission = MissionSpec(
        intent="Create hello.txt",
        deliverables=["hello.txt"],
        acceptance_criteria=[AcceptanceCriteria(description="hello.txt exists", validation_type="file_exists", validation_target="hello.txt")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    objective = render_goal_objective(mission)

    assert "GoalContract" in objective
    assert '"schema": "metaloop.goal_contract"' in objective
    assert "ExecutionReport schema" in objective
    assert '"required_fields"' in objective
    assert '"mission_id": "must exactly equal GoalContract.mission_id"' in objective
    assert "MissionCapsule summary" in objective


def test_verify_mission_completed_verified_when_hard_checks_and_report_pass(tmp_path) -> None:
    (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")
    report_dir = tmp_path / ".metaloop"
    report_dir.mkdir()
    mission = MissionSpec(
        intent="Create hello.txt",
        acceptance_criteria=[AcceptanceCriteria(description="hello.txt exists", validation_type="file_exists", validation_target="hello.txt")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )
    report = ExecutionReport(mission_id=mission.run_id, status="completed", summary="done")
    (report_dir / "execution_report.json").write_text(report.model_dump_json(by_alias=True), encoding="utf-8")

    result = verify_mission(mission)

    assert result.status == VerificationStatus.COMPLETED_VERIFIED
    assert result.hard_validator_results[0].passed is True
    assert result.required_evidence_total == 2
    assert result.required_evidence_satisfied == 2
    assert "execution_report" in result.required_evidence_summary


def test_verify_mission_manual_criteria_complete_pending_final_human_acceptance(tmp_path) -> None:
    report_dir = tmp_path / ".metaloop"
    report_dir.mkdir()
    mission = MissionSpec(
        intent="Assess UX",
        acceptance_criteria=[AcceptanceCriteria(description="UX feels good", validation_type="manual")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )
    payload = {"schema": "metaloop.execution_report", "version": "1.0", "mission_id": mission.run_id, "status": "completed", "summary": "done"}
    (report_dir / "execution_report.json").write_text(json.dumps(payload), encoding="utf-8")

    result = verify_mission(mission)

    assert result.status == VerificationStatus.COMPLETED_PENDING_HUMAN_ACCEPTANCE
    assert result.soft_review_results[0].status == "requires_final_human_acceptance"


def test_verify_mission_missing_report_fails_even_when_artifacts_exist(tmp_path) -> None:
    (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")
    mission = MissionSpec(
        intent="Create hello.txt",
        acceptance_criteria=[AcceptanceCriteria(description="hello.txt exists", validation_type="file_exists", validation_target="hello.txt")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = verify_mission(mission)

    assert result.status == VerificationStatus.FAILED
    assert result.evidence_results[0].passed is False


def test_verify_mission_failed_hard_validator_fails(tmp_path) -> None:
    mission = MissionSpec(
        intent="Create hello.txt",
        acceptance_criteria=[AcceptanceCriteria(description="hello.txt exists", validation_type="file_exists", validation_target="hello.txt")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = verify_mission(mission)

    assert result.status == VerificationStatus.FAILED


def test_verify_mission_report_id_mismatch_names_current_run_id(tmp_path) -> None:
    (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")
    report_dir = tmp_path / ".metaloop"
    report_dir.mkdir()
    mission = MissionSpec(
        intent="Create hello.txt",
        acceptance_criteria=[AcceptanceCriteria(description="hello.txt exists", validation_type="file_exists", validation_target="hello.txt")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )
    report = ExecutionReport(mission_id="run_other", status="completed", summary="done")
    (report_dir / "execution_report.json").write_text(report.model_dump_json(by_alias=True), encoding="utf-8")

    result = verify_mission(mission)

    assert result.status == VerificationStatus.FAILED
    assert any(
        item.name == "execution_report.mission_id" and "expected current run_id" in item.message
        for item in result.evidence_results
    )


def test_verify_mission_rejects_invalid_path_target_even_when_artifact_exists(tmp_path) -> None:
    (tmp_path / "tabs").mkdir()
    (tmp_path / "tabs" / "newlines").write_text("noise", encoding="utf-8")
    report_dir = tmp_path / ".metaloop"
    report_dir.mkdir()
    mission = MissionSpec(
        intent="Upgrade count_words behavior",
        acceptance_criteria=[
            AcceptanceCriteria(
                description="tabs/newlines exists",
                validation_type="file_exists",
                validation_target="tabs/newlines",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )
    report = ExecutionReport(mission_id=mission.run_id, status="completed", summary="done")
    (report_dir / "execution_report.json").write_text(report.model_dump_json(by_alias=True), encoding="utf-8")

    result = verify_mission(mission)

    assert result.status == VerificationStatus.FAILED
    assert any(not item.passed and "invalid path validation target" in item.message for item in result.hard_validator_results)


def test_engineering_bugfix_requires_regression_evidence(tmp_path) -> None:
    (tmp_path / "bug.py").write_text("fixed", encoding="utf-8")
    report_dir = tmp_path / ".metaloop"
    report_dir.mkdir()
    mission = MissionSpec(
        intent="Fix a public behavior regression in bug.py",
        context={"domain_profile_id": "engineering_development"},
        deliverables=["bug.py"],
        acceptance_criteria=[AcceptanceCriteria(description="bug.py exists", validation_type="file_exists", validation_target="bug.py")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )
    report = ExecutionReport(
        mission_id=mission.run_id,
        status="completed",
        summary="fixed behavior",
        changed_files=["bug.py"],
    )
    (report_dir / "execution_report.json").write_text(report.model_dump_json(by_alias=True), encoding="utf-8")

    result = verify_mission(mission)

    assert result.status == VerificationStatus.FAILED
    assert any(check.name == "domain.engineering.regression_evidence" and check.required for check in result.evidence_results)
