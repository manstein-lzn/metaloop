from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from metaloop.codex_adapter import CodexExecAdapter, CodexExecOptions
from metaloop.goal import (
    GoalContract,
    ReviewFinding,
    ReviewRoute,
    SoftReviewDecision,
    VerificationResult,
    compile_goal_contract,
)
from metaloop.prompt_pack import PromptPackError, render_prompt
from metaloop.schemas import MissionSpec


class SoftReviewer(Protocol):
    def review(self, mission: MissionSpec, verification: VerificationResult) -> SoftReviewDecision:
        ...


class RuleSoftReviewer:
    """Deterministic fallback used when no LLM reviewer is configured."""

    def review(self, mission: MissionSpec, verification: VerificationResult) -> SoftReviewDecision:
        failed_hard = [item for item in verification.hard_validator_results if not item.passed]
        if failed_hard:
            return SoftReviewDecision(
                mission_id=mission.run_id,
                passed=False,
                route=ReviewRoute.ASK_WORKER_TO_FIX,
                confidence="high",
                findings=[
                    ReviewFinding(
                        severity="blocking",
                        area="hard_validation",
                        message="Required hard validators failed.",
                        evidence=[item.message for item in failed_hard],
                        recommendation="Fix the failing validator evidence and rerun validation.",
                    )
                ],
                repair_instructions="Fix the failing hard validators and update the execution report with new evidence.",
                rationale="Hard validators are authoritative.",
            )
        return SoftReviewDecision(
            mission_id=mission.run_id,
            passed=True,
            route=ReviewRoute.COMPLETE,
            confidence="medium",
            rationale="No hard validator failure was present.",
        )


class CodexSoftReviewer:
    def __init__(self, options: CodexExecOptions | None = None) -> None:
        self.options = options or CodexExecOptions(use_output_schema=False)

    def review(self, mission: MissionSpec, verification: VerificationResult) -> SoftReviewDecision:
        contract = compile_goal_contract(mission)
        try:
            prompt = build_soft_review_prompt(mission, contract, verification)
        except SoftReviewPromptError as exc:
            return _fallback_failed_review(mission, f"soft reviewer prompt pack render failed: {exc}")
        result = CodexExecAdapter(self.options.model_copy(update={"use_output_schema": False, "output_schema": None})).run(prompt)
        if not result.ok or not result.final_message:
            return _fallback_failed_review(mission, f"soft reviewer failed: {result.stderr or result.returncode}")
        try:
            payload = json.loads(_extract_json_object(result.final_message))
            decision = SoftReviewDecision.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            return _fallback_failed_review(mission, f"invalid soft reviewer output: {exc}")
        if decision.mission_id != mission.run_id:
            return _fallback_failed_review(
                mission,
                f"soft reviewer mission_id mismatch: expected {mission.run_id}, got {decision.mission_id}",
            )
        return decision


class SoftReviewPromptError(ValueError):
    """Raised when the soft reviewer prompt cannot be compiled safely."""


def build_soft_review_prompt(
    mission: MissionSpec,
    contract: GoalContract,
    verification: VerificationResult,
    *,
    prompt_root: str | Path | None = None,
) -> str:
    variables = {
        "mission_spec": _fenced_json(mission),
        "goal_contract": _fenced_json(contract),
        "verification_result": _fenced_json(verification),
        "soft_review_schema": _fenced_json(SoftReviewDecision.model_json_schema(by_alias=True)),
    }
    try:
        rendered = render_prompt(
            "run/soft_reviewer",
            variables,
            prompt_root=prompt_root,
            required_variables=(
                "mission_spec",
                "goal_contract",
                "verification_result",
                "soft_review_schema",
            ),
        )
    except PromptPackError as exc:
        raise SoftReviewPromptError(str(exc)) from exc
    return rendered.rendered_text


def _fenced_json(value: Any) -> str:
    if hasattr(value, "model_dump_json"):
        payload = json.loads(value.model_dump_json(by_alias=True))
    else:
        payload = value
    return "```json\n" + json.dumps(payload, indent=2, ensure_ascii=False) + "\n```"


def _fallback_failed_review(mission: MissionSpec, message: str) -> SoftReviewDecision:
    return SoftReviewDecision(
        mission_id=mission.run_id,
        passed=False,
        route=ReviewRoute.FAIL,
        confidence="low",
        findings=[
            ReviewFinding(
                severity="blocking",
                area="soft_review",
                message=message,
                recommendation="Rerun soft review or inspect the execution evidence manually.",
            )
        ],
        rationale="Soft reviewer did not produce a trusted decision.",
    )


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if match is None:
        raise ValueError("no JSON object found")
    return match.group(0)
