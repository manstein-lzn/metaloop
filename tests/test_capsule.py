import pytest

from metaloop.capsule import (
    AttemptOutcome,
    AttemptRecord,
    ClosureOutcome,
    EvidenceRecord,
    LifecycleState,
    MissionCapsule,
)
from metaloop.goal import compile_goal_contract, compile_mission_capsule
from metaloop.schemas import AcceptanceCriteria, MissionSpec, PolicyScope


def test_compile_mission_capsule_locks_normative_contract(tmp_path) -> None:
    mission = MissionSpec(
        intent="Create hello.txt",
        context={"constraints": ["local only"], "out_of_scope": ["cloud sync"]},
        deliverables=["hello.txt"],
        acceptance_criteria=[
            AcceptanceCriteria(
                description="hello.txt exists",
                validation_type="file_exists",
                validation_target="hello.txt",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path), allowed_tools=["shell"]),
    )

    capsule = compile_mission_capsule(mission)

    assert capsule.lifecycle_state == LifecycleState.AUTHORIZED
    assert capsule.identity.capsule_id == mission.run_id
    assert capsule.mission_charter.locked is True
    assert capsule.acceptance_contract.locked is True
    assert capsule.authority_contract.workspace_root == str(tmp_path)
    assert capsule.acceptance_contract.verification_plan.hard_validator_ids == (
        mission.acceptance_criteria[0].id,
    )
    assert capsule.acceptance_contract.evidence_plan.required_evidence[-1].evidence_class == "execution_report"


def test_goal_contract_is_compiled_through_capsule(tmp_path) -> None:
    mission = MissionSpec(
        intent="Build a local tool",
        context={
            "constraints": ["local only"],
            "out_of_scope": ["cloud sync"],
            "domain_profile_id": "codex_skill_creation",
        },
        deliverables=["tool.py"],
        acceptance_criteria=[
            AcceptanceCriteria(
                description="tool.py exists",
                validation_type="file_exists",
                validation_target="tool.py",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    contract = compile_goal_contract(mission)

    assert contract.mission_id == mission.run_id
    assert contract.capsule_id == mission.run_id
    assert contract.capsule_version == "1.0"
    assert contract.domain_profile_id == "codex_skill_creation"
    assert contract.locked_intent is True
    assert contract.locked_acceptance is True
    assert contract.objective == "Build a local tool"
    assert contract.key_tasks == ["tool.py"]
    assert "local only" in contract.constraints
    assert "cloud sync" in contract.out_of_scope
    assert "do not weaken acceptance criteria" in contract.forbidden_actions
    assert [item.evidence_class for item in contract.evidence_requirements[:2]] == [
        "artifact",
        "execution_report",
    ]
    assert contract.evidence_requirements[0].criterion_id == mission.acceptance_criteria[0].id
    assert any("usage example" in item.description for item in contract.evidence_requirements)
    assert "usage example" in contract.required_evidence_summary or contract.required_evidence_count == 2


def test_evidence_and_attempts_are_append_only_values(tmp_path) -> None:
    mission = MissionSpec(
        intent="Create hello.txt",
        acceptance_criteria=[AcceptanceCriteria(description="manual check")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )
    capsule = MissionCapsule.from_mission(mission)
    evidence = EvidenceRecord(
        capsule_id=capsule.identity.capsule_id,
        capsule_version=capsule.identity.capsule_version,
        evidence_class="artifact",
        producer="test",
        summary="hello.txt exists",
        uri="hello.txt",
    )
    attempt = AttemptRecord(
        capsule_id=capsule.identity.capsule_id,
        capsule_version=capsule.identity.capsule_version,
        executor="codex",
        outcome=AttemptOutcome.COMPLETED,
        evidence_record_ids=(evidence.evidence_id,),
    )

    with_evidence = capsule.with_evidence(evidence)
    with_attempt = with_evidence.with_attempt(attempt)

    assert capsule.evidence_ledger == ()
    assert with_evidence.evidence_ledger == (evidence,)
    assert with_attempt.attempt_history == (attempt,)
    with pytest.raises(AttributeError):
        with_attempt.evidence_ledger.append(evidence)  # type: ignore[attr-defined]


def test_lifecycle_transitions_and_closure_outcomes_are_validated(tmp_path) -> None:
    mission = MissionSpec(
        intent="Create hello.txt",
        acceptance_criteria=[AcceptanceCriteria(description="manual check")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )
    capsule = MissionCapsule.from_mission(mission)

    with pytest.raises(ValueError):
        capsule.transition(LifecycleState.ARCHIVED)

    closed = (
        capsule.transition(LifecycleState.IN_PROGRESS)
        .transition(LifecycleState.REVIEW_READY)
        .transition(LifecycleState.CLOSED, closure_outcome=ClosureOutcome.ACCEPTED)
    )

    assert closed.lifecycle_state == LifecycleState.CLOSED
    assert closed.closure_outcome == ClosureOutcome.ACCEPTED
    assert closed.transition(LifecycleState.ARCHIVED).lifecycle_state == LifecycleState.ARCHIVED


def test_permission_expansion_requires_recorded_decision(tmp_path) -> None:
    mission = MissionSpec(
        intent="Create hello.txt",
        acceptance_criteria=[AcceptanceCriteria(description="manual check")],
        policy=PolicyScope(workspace_root=str(tmp_path), allowed_tools=["shell"]),
    )
    capsule = MissionCapsule.from_mission(mission)

    with pytest.raises(ValueError):
        capsule.expand_permissions(allowed_tools=("network",), summary="")

    expanded = capsule.expand_permissions(allowed_tools=("network",), summary="User allowed network for docs lookup.")

    assert expanded.authority_contract.allowed_tools == ("shell", "network")
    assert expanded.decision_ledger[-1].decision_type == "authority_update"
