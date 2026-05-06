import json
from types import SimpleNamespace

import pytest

from metaloop.co_design import (
    CoDesignSession,
    CoDesignAgentError,
    CoDesignQuestion,
    MissionSpecReviewer,
    _build_codex_answer_prompt,
    _build_codex_brainstorm_prompt,
    _build_codex_interviewer_prompt,
    build_draft_from_options,
)
from metaloop.goal import ReviewRoute, SoftReviewDecision, VerificationResult, VerificationStatus, compile_goal_contract
from metaloop.goal_runtime import GoalRuntimePromptError, build_focused_route_prompt, build_repair_prompt
from metaloop.prompt_pack import PromptPackError
from metaloop.schemas import AcceptanceCriteria, MissionSpec, PolicyScope
from metaloop.soft_review import CodexSoftReviewer, SoftReviewPromptError, build_soft_review_prompt


def _mission(tmp_path) -> MissionSpec:
    return MissionSpec(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        acceptance_criteria=[
            AcceptanceCriteria(
                description="hello.txt exists",
                validation_type="file_exists",
                validation_target="hello.txt",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )


def _brainstorm_inputs(tmp_path):
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        file_exists=["hello.txt"],
        workspace_root=str(tmp_path),
    )
    mission = CoDesignSession(draft).build_mission()
    review = MissionSpecReviewer().review(mission)
    return mission, draft, review


def test_prompt_pack_brainstorm_prompt_keeps_design_semantics(tmp_path) -> None:
    mission, draft, review = _brainstorm_inputs(tmp_path)
    prompt = _build_codex_brainstorm_prompt(mission, draft, review)

    assert "You are the MetaLoop Co-Design brainstormer." in prompt
    assert "Expand the preliminary MissionSpec with options, tradeoffs, risks" in prompt
    assert "Do not execute the mission" in prompt
    assert "Return raw JSON only with keys: options, recommended_option, mvp, v1, later, risks, overlooked_points, unresolved_questions, notes" in prompt
    assert 'Option shape: {"title":"...", "summary":"...", "tradeoffs":["..."], "risks":["..."]}.' in prompt
    assert "MissionSpec:" in prompt
    assert "CoDesignDraft:" in prompt
    assert "MissionSpecReview:" in prompt
    assert "```json" in prompt
    assert mission.run_id in prompt
    assert draft.intent in prompt


def test_prompt_pack_brainstorm_missing_prompt_fails_fast(tmp_path) -> None:
    mission, draft, review = _brainstorm_inputs(tmp_path)

    with pytest.raises(CoDesignAgentError, match="prompt pack render failed"):
        _build_codex_brainstorm_prompt(mission, draft, review, prompt_root=tmp_path)


def test_prompt_pack_brainstorm_missing_variable_fails_fast(monkeypatch, tmp_path) -> None:
    mission, draft, review = _brainstorm_inputs(tmp_path)

    def fail_render(*_args, **_kwargs):
        raise PromptPackError("missing required variable: mission_spec")

    monkeypatch.setattr("metaloop.co_design.render_prompt", fail_render)

    with pytest.raises(CoDesignAgentError, match="missing required variable: mission_spec"):
        _build_codex_brainstorm_prompt(mission, draft, review)


def test_prompt_pack_discovery_prompt_uses_loader(monkeypatch) -> None:
    draft = build_draft_from_options(intent="Create hello file")
    captured = {}

    def fake_render(prompt_id, variables, **kwargs):
        captured["prompt_id"] = prompt_id
        captured["variables"] = variables
        captured["kwargs"] = kwargs
        return SimpleNamespace(rendered_text="rendered from discovery prompt pack")

    monkeypatch.setattr("metaloop.co_design.render_prompt", fake_render)

    prompt = _build_codex_interviewer_prompt(draft, autonomous=False)

    assert prompt == "rendered from discovery prompt pack"
    assert captured["prompt_id"] == "co_design/discovery"
    assert captured["variables"]["patch_mode"] == "safe"
    assert "SAFE MODE" in captured["variables"]["patch_mode_instruction"]
    assert "```json" in captured["variables"]["co_design_draft"]
    assert captured["kwargs"]["required_variables"] == ("patch_mode", "patch_mode_instruction", "co_design_draft")


def test_prompt_pack_discovery_prompt_safe_and_autonomous_modes_differ() -> None:
    draft = build_draft_from_options(intent="Create hello file")

    safe_prompt = _build_codex_interviewer_prompt(draft, autonomous=False)
    autonomous_prompt = _build_codex_interviewer_prompt(draft, autonomous=True)

    assert "SAFE MODE" in safe_prompt
    assert "draft_patch may include only audience, background, constraints, out_of_scope" in safe_prompt
    assert "Do not patch intent, deliverables, or criteria" in safe_prompt
    assert "Do not execute the mission" in safe_prompt
    assert "Return raw JSON only with keys: questions, draft_patch, notes" in safe_prompt
    assert "Current draft:" in safe_prompt
    assert "AUTONOMOUS MODE" in autonomous_prompt
    assert "You may patch intent, audience, background, deliverables, constraints, out_of_scope, and criteria" in autonomous_prompt
    assert "Do not invent facts that conflict with the user's draft" in autonomous_prompt
    assert "set validation_target to JSON" in autonomous_prompt
    assert "Do not use command validation" in autonomous_prompt
    assert "Do not execute the mission" in autonomous_prompt


def test_prompt_pack_discovery_missing_prompt_fails_fast(tmp_path) -> None:
    draft = build_draft_from_options(intent="Create hello file")

    with pytest.raises(CoDesignAgentError, match="prompt pack render failed"):
        _build_codex_interviewer_prompt(draft, prompt_root=tmp_path)


def test_prompt_pack_discovery_render_failure_fails_fast(monkeypatch) -> None:
    draft = build_draft_from_options(intent="Create hello file")

    def fail_render(*_args, **_kwargs):
        raise PromptPackError("missing required variable: patch_mode_instruction")

    monkeypatch.setattr("metaloop.co_design.render_prompt", fail_render)

    with pytest.raises(CoDesignAgentError, match="missing required variable: patch_mode_instruction"):
        _build_codex_interviewer_prompt(draft)


def test_hardcoded_answer_prompt_is_not_migrated_to_prompt_pack(monkeypatch) -> None:
    draft = build_draft_from_options(intent="Create hello file")
    question = CoDesignQuestion(question_id="constraints", prompt="Any boundaries?")

    def fail_render(*_args, **_kwargs):
        raise AssertionError("answer prompt should not use prompt pack yet")

    monkeypatch.setattr("metaloop.co_design.render_prompt", fail_render)

    prompt = _build_codex_answer_prompt(question, draft, review=None)

    assert "You are the autonomous MetaLoop Co-Design answerer." in prompt
    assert "Question:" in prompt


def test_prompt_pack_soft_reviewer_prompt_uses_loader(monkeypatch, tmp_path) -> None:
    mission = _mission(tmp_path)
    contract = compile_goal_contract(mission)
    verification = VerificationResult(
        mission_id=mission.run_id,
        status=VerificationStatus.FAILED,
        reason="Required hard validators failed.",
    )
    captured = {}

    def fake_render(prompt_id, variables, **kwargs):
        captured["prompt_id"] = prompt_id
        captured["variables"] = variables
        captured["kwargs"] = kwargs
        return SimpleNamespace(rendered_text="rendered from soft reviewer prompt pack")

    monkeypatch.setattr("metaloop.soft_review.render_prompt", fake_render)

    prompt = build_soft_review_prompt(mission, contract, verification)

    assert prompt == "rendered from soft reviewer prompt pack"
    assert captured["prompt_id"] == "run/soft_reviewer"
    assert "```json" in captured["variables"]["mission_spec"]
    assert "```json" in captured["variables"]["goal_contract"]
    assert "```json" in captured["variables"]["verification_result"]
    assert "```json" in captured["variables"]["soft_review_schema"]
    assert captured["kwargs"]["required_variables"] == (
        "mission_spec",
        "goal_contract",
        "verification_result",
        "soft_review_schema",
    )


def test_prompt_pack_soft_reviewer_prompt_keeps_route_and_schema_semantics(tmp_path) -> None:
    mission = _mission(tmp_path)
    contract = compile_goal_contract(mission)
    verification = VerificationResult(
        mission_id=mission.run_id,
        status=VerificationStatus.FAILED,
        reason="Required hard validators failed.",
    )

    prompt = build_soft_review_prompt(mission, contract, verification)

    assert "Hard validator results are authoritative" in prompt
    assert "do not override failed hard validators" in prompt
    assert "must not mark the mission complete" in prompt
    assert "Human acceptance is not an internal route" in prompt
    assert "Do not ask the user for acceptance" in prompt
    assert "complete, ask_worker_to_fix, ask_architect_to_rethink, ask_planner_to_replan, ask_brainstormer_for_options, fail" in prompt
    assert "Use ask_worker_to_fix for concrete implementation defects" in prompt
    assert "contract, design, decomposition, or solution-path uncertainty" in prompt
    assert "Return raw JSON only matching the actual SoftReviewDecision JSON schema below" in prompt
    assert '"properties"' in prompt
    assert '"route"' in prompt
    for route in ReviewRoute:
        assert route.value in prompt
    assert "MissionSpec:" in prompt
    assert "GoalContract:" in prompt
    assert "VerificationResult so far:" in prompt
    assert "```json" in prompt
    assert mission.run_id in prompt
    assert contract.objective in prompt


def test_prompt_pack_soft_reviewer_prompt_render_failure_fails_fast(tmp_path) -> None:
    mission = _mission(tmp_path)
    contract = compile_goal_contract(mission)
    verification = VerificationResult(
        mission_id=mission.run_id,
        status=VerificationStatus.FAILED,
        reason="Required hard validators failed.",
    )

    with pytest.raises(SoftReviewPromptError, match="prompt file not found"):
        build_soft_review_prompt(mission, contract, verification, prompt_root=tmp_path)


def test_codex_soft_reviewer_prompt_render_error_returns_failed_low_confidence(monkeypatch, tmp_path) -> None:
    mission = _mission(tmp_path)
    verification = VerificationResult(
        mission_id=mission.run_id,
        status=VerificationStatus.FAILED,
        reason="Required hard validators failed.",
    )

    def fail_render(*_args, **_kwargs):
        raise PromptPackError("missing required variable: verification_result")

    class ExplodingAdapter:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("Codex adapter should not run after prompt render failure")

    monkeypatch.setattr("metaloop.soft_review.render_prompt", fail_render)
    monkeypatch.setattr("metaloop.soft_review.CodexExecAdapter", ExplodingAdapter)

    decision = CodexSoftReviewer().review(mission, verification)

    assert decision.passed is False
    assert decision.route is ReviewRoute.FAIL
    assert decision.confidence == "low"
    assert "soft reviewer prompt pack render failed" in decision.findings[0].message
    assert "missing required variable: verification_result" in decision.findings[0].message


def test_hardcoded_repair_prompt_keeps_locked_contract_and_attempt_semantics(tmp_path) -> None:
    mission = _mission(tmp_path)
    verification = VerificationResult(
        mission_id=mission.run_id,
        status=VerificationStatus.FAILED,
        reason="Required hard validators failed.",
        soft_review_decision=SoftReviewDecision(
            mission_id=mission.run_id,
            passed=False,
            route=ReviewRoute.ASK_WORKER_TO_FIX,
            repair_instructions="Create the missing file.",
        ),
    )

    first_prompt = build_repair_prompt(mission, verification, repair_attempt_index=1)
    second_prompt = build_repair_prompt(
        mission,
        verification,
        repair_attempt_index=2,
        failed_fix_summary="first repair did not create hello.txt",
    )

    assert "Do not edit .metaloop/mission.json, .metaloop/mission_capsule.json, .metaloop/goal_contract.json" in first_prompt
    assert "Repair attempt index: 1" in first_prompt
    assert "update .metaloop/execution_report.json" in first_prompt
    assert "MissionSpec:" in first_prompt
    assert "VerificationResult:" in first_prompt
    assert "Repair attempt index: 2" in second_prompt
    assert "root_cause" in second_prompt
    assert "hypothesis" in second_prompt
    assert "previous fix failed" in second_prompt
    assert "first repair did not create hello.txt" in second_prompt


def test_prompt_pack_focused_route_prompt_uses_loader(monkeypatch, tmp_path) -> None:
    mission = _mission(tmp_path)
    verification = VerificationResult(
        mission_id=mission.run_id,
        status=VerificationStatus.FAILED,
        reason="Design mismatch.",
        soft_review_decision=SoftReviewDecision(
            mission_id=mission.run_id,
            passed=False,
            route=ReviewRoute.ASK_PLANNER_TO_REPLAN,
            rationale="Scope needs redesign.",
        ),
    )
    captured = {}

    def fake_render(prompt_id, variables, **kwargs):
        captured["prompt_id"] = prompt_id
        captured["variables"] = variables
        captured["kwargs"] = kwargs
        return SimpleNamespace(rendered_text="rendered from focused route prompt pack")

    monkeypatch.setattr("metaloop.goal_runtime.render_prompt", fake_render)

    prompt = build_focused_route_prompt(mission, verification)

    assert prompt == "rendered from focused route prompt pack"
    assert captured["prompt_id"] == "run/redesign"
    assert captured["variables"]["route_role"] == "planner"
    assert captured["variables"]["reviewer_route"] == "ask_planner_to_replan"
    assert "```json" in captured["variables"]["mission_spec"]
    assert "```json" in captured["variables"]["mission_capsule"]
    assert "```json" in captured["variables"]["verification_result"]
    assert "```json" in captured["variables"]["soft_review_decision"]
    assert captured["kwargs"]["required_variables"] == (
        "route_role",
        "reviewer_route",
        "mission_spec",
        "mission_capsule",
        "verification_result",
        "soft_review_decision",
    )


def test_prompt_pack_focused_route_prompt_render_failure_fails_fast(monkeypatch, tmp_path) -> None:
    mission = _mission(tmp_path)
    verification = VerificationResult(
        mission_id=mission.run_id,
        status=VerificationStatus.FAILED,
        reason="Design mismatch.",
    )

    def fail_render(*_args, **_kwargs):
        raise PromptPackError("missing required variable: verification_result")

    monkeypatch.setattr("metaloop.goal_runtime.render_prompt", fail_render)

    with pytest.raises(GoalRuntimePromptError, match="missing required variable: verification_result"):
        build_focused_route_prompt(mission, verification)


def test_prompt_pack_focused_route_prompt_keeps_redesign_semantics(tmp_path) -> None:
    mission = _mission(tmp_path)
    verification = VerificationResult(
        mission_id=mission.run_id,
        status=VerificationStatus.FAILED,
        reason="Design mismatch.",
        soft_review_decision=SoftReviewDecision(
            mission_id=mission.run_id,
            passed=False,
            route=ReviewRoute.ASK_ARCHITECT_TO_RETHINK,
            rationale="Acceptance needs redesign.",
        ),
    )

    prompt = build_focused_route_prompt(mission, verification)
    verification_payload = json.loads(verification.model_dump_json(by_alias=True))

    assert "focused architect agent" in prompt
    assert "routed this mission to ask_architect_to_rethink" in prompt
    assert "contract-level redesign route" in prompt
    assert "not an implementation repair route" in prompt
    assert "Do not edit files in this step" in prompt
    assert "Do not weaken locked Mission Capsule intent, scope, permissions, or acceptance criteria" in prompt
    assert "Do not modify .metaloop/mission.json, .metaloop/mission_capsule.json, .metaloop/goal_contract.json" in prompt
    assert "Human acceptance is not an internal route" in prompt
    assert "diagnosis" in prompt
    assert "why worker repair is insufficient" in prompt
    assert "proposed intent changes" in prompt
    assert "proposed scope changes" in prompt
    assert "proposed acceptance changes" in prompt
    assert "proposed authority changes" in prompt
    assert "proposed evidence changes" in prompt
    assert "evidence references" in prompt
    assert "MissionSpec:" in prompt
    assert "MissionCapsule:" in prompt
    assert "VerificationResult:" in prompt
    assert "SoftReviewDecision:" in prompt
    assert "```json" in prompt
    assert verification_payload["soft_review_decision"]["route"] in prompt


def test_repair_prompt_is_not_migrated_to_prompt_pack(monkeypatch, tmp_path) -> None:
    mission = _mission(tmp_path)
    verification = VerificationResult(
        mission_id=mission.run_id,
        status=VerificationStatus.FAILED,
        reason="Required hard validators failed.",
        soft_review_decision=SoftReviewDecision(
            mission_id=mission.run_id,
            passed=False,
            route=ReviewRoute.ASK_WORKER_TO_FIX,
            repair_instructions="Create the missing file.",
        ),
    )

    def fail_render(*_args, **_kwargs):
        raise AssertionError("repair prompt should not use prompt pack yet")

    monkeypatch.setattr("metaloop.goal_runtime.render_prompt", fail_render)

    repair_prompt = build_repair_prompt(mission, verification, repair_attempt_index=1)

    assert "You are Codex repairing a MetaLoop mission at implementation level" in repair_prompt
