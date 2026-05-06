from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from metaloop.capsule import EvidenceRequirement, MissionCapsule
from metaloop.schemas import AcceptanceCriteria, MissionSpec, RiskLevel, new_id, utc_now
from metaloop.validators import ArtifactValidator, ValidationResult


DEFAULT_EXECUTION_REPORT_PATH = ".metaloop/execution_report.json"


class GoalContract(BaseModel):
    schema_name: Literal["metaloop.goal_contract"] = Field(default="metaloop.goal_contract", alias="schema")
    version: str = "1.0"
    mission_id: str
    capsule_id: str | None = None
    capsule_version: str | None = None
    domain_profile_id: str | None = None
    locked_intent: bool = True
    locked_acceptance: bool = True
    objective: str
    purpose: str = ""
    desired_end_state: str = ""
    key_tasks: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    workspace_root: str = "."
    forbidden_paths: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    acceptance: list[AcceptanceCriteria] = Field(default_factory=list)
    evidence_requirements: list[EvidenceRequirement] = Field(default_factory=list)
    required_evidence_summary: str = ""
    required_evidence_count: int = 0
    required_report_path: str = DEFAULT_EXECUTION_REPORT_PATH

    @model_validator(mode="after")
    def objective_required(self) -> GoalContract:
        if not self.objective.strip():
            raise ValueError("GoalContract requires objective")
        if not self.acceptance:
            raise ValueError("GoalContract requires acceptance criteria")
        return self


class ExecutionReportStatus(str, Enum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class ExecutionReport(BaseModel):
    schema_name: Literal["metaloop.execution_report"] = Field(default="metaloop.execution_report", alias="schema")
    version: str = "1.0"
    mission_id: str
    status: ExecutionReportStatus
    summary: str
    changed_files: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    validation_results: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class VerificationStatus(str, Enum):
    COMPLETED_VERIFIED = "completed_verified"
    COMPLETED_WITH_SOFT_ACCEPTANCE = "completed_with_soft_acceptance"
    COMPLETED_WITH_LIMITATIONS = "completed_with_limitations"
    COMPLETED_PENDING_HUMAN_ACCEPTANCE = "completed_pending_human_acceptance"
    # Backward-compatible legacy spelling. New runs should use
    # completed_pending_human_acceptance because human acceptance happens after
    # internal agent work is complete; it is not an agent routing state.
    PENDING_HUMAN_ACCEPTANCE = "pending_human_acceptance"
    FAILED = "failed"
    BLOCKED = "blocked"


class ReviewRoute(str, Enum):
    COMPLETE = "complete"
    ASK_WORKER_TO_FIX = "ask_worker_to_fix"
    ASK_ARCHITECT_TO_RETHINK = "ask_architect_to_rethink"
    ASK_PLANNER_TO_REPLAN = "ask_planner_to_replan"
    ASK_BRAINSTORMER_FOR_OPTIONS = "ask_brainstormer_for_options"
    FAIL = "fail"


class ReviewFinding(BaseModel):
    severity: Literal["info", "warning", "blocking"]
    area: str
    message: str
    evidence: list[str] = Field(default_factory=list)
    recommendation: str = ""


class SoftReviewDecision(BaseModel):
    schema_name: Literal["metaloop.soft_review_decision"] = Field(default="metaloop.soft_review_decision", alias="schema")
    version: str = "1.0"
    mission_id: str
    passed: bool
    route: ReviewRoute
    confidence: Literal["low", "medium", "high"] = "medium"
    findings: list[ReviewFinding] = Field(default_factory=list)
    repair_instructions: str = ""
    rationale: str = ""

    @model_validator(mode="after")
    def route_matches_passed(self) -> SoftReviewDecision:
        if self.passed and self.route != ReviewRoute.COMPLETE:
            raise ValueError("passed soft review must use route=complete")
        if not self.passed and self.route == ReviewRoute.COMPLETE:
            raise ValueError("failed soft review cannot use route=complete")
        if self.route == ReviewRoute.ASK_WORKER_TO_FIX and not self.repair_instructions.strip():
            raise ValueError("ask_worker_to_fix requires repair_instructions")
        return self


class RedesignContractDelta(BaseModel):
    added_scope: list[str] = Field(default_factory=list)
    removed_scope: list[str] = Field(default_factory=list)
    added_non_goals: list[str] = Field(default_factory=list)
    added_acceptance: list[str] = Field(default_factory=list)
    modified_acceptance: list[str] = Field(default_factory=list)
    removed_acceptance: list[str] = Field(default_factory=list)
    authority_delta: list[str] = Field(default_factory=list)
    evidence_delta: list[str] = Field(default_factory=list)


class RedesignProposal(BaseModel):
    schema_name: Literal["metaloop.redesign_proposal"] = Field(default="metaloop.redesign_proposal", alias="schema")
    version: str = "1.0"
    proposal_id: str = Field(default_factory=lambda: new_id("redesign"))
    mission_id: str
    capsule_id: str
    capsule_version: str
    reviewer_route: ReviewRoute
    reason: str
    why_worker_repair_is_insufficient: str
    proposed_intent_changes: list[str] = Field(default_factory=list)
    proposed_acceptance_changes: list[str] = Field(default_factory=list)
    proposed_scope_changes: list[str] = Field(default_factory=list)
    proposed_authority_changes: list[str] = Field(default_factory=list)
    contract_delta: RedesignContractDelta = Field(default_factory=RedesignContractDelta)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def required_text(self) -> RedesignProposal:
        if not self.reason.strip():
            raise ValueError("RedesignProposal requires reason")
        if not self.why_worker_repair_is_insufficient.strip():
            raise ValueError("RedesignProposal requires why_worker_repair_is_insufficient")
        return self


class EvidenceCheck(BaseModel):
    name: str
    passed: bool
    message: str = ""
    requirement_id: str | None = None
    evidence_class: str | None = None
    required: bool = True


class SoftReviewResult(BaseModel):
    criteria_id: str
    required: bool = True
    validation_type: Literal["manual", "llm_review"]
    description: str
    status: Literal["requires_final_human_acceptance", "pending_llm_review"]


class RepairAttemptEvidence(BaseModel):
    repair_attempt_index: int
    reviewer_route: ReviewRoute = ReviewRoute.ASK_WORKER_TO_FIX
    root_cause: str = ""
    hypothesis: str = ""
    failed_fix_summary: str = ""
    prompt_requirements: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class VerificationResult(BaseModel):
    schema_name: Literal["metaloop.verification_result"] = Field(default="metaloop.verification_result", alias="schema")
    version: str = "1.0"
    verification_id: str = Field(default_factory=lambda: new_id("verification"))
    mission_id: str
    status: VerificationStatus
    hard_validator_results: list[ValidationResult] = Field(default_factory=list)
    soft_review_results: list[SoftReviewResult] = Field(default_factory=list)
    soft_review_decision: SoftReviewDecision | None = None
    evidence_results: list[EvidenceCheck] = Field(default_factory=list)
    required_evidence_summary: str = ""
    required_evidence_total: int = 0
    required_evidence_satisfied: int = 0
    execution_report: ExecutionReport | None = None
    repair_attempts: list[RepairAttemptEvidence] = Field(default_factory=list)
    reason: str = ""
    created_at: str = Field(default_factory=utc_now)


def compile_goal_contract(mission: MissionSpec) -> GoalContract:
    return compile_goal_contract_from_capsule(compile_mission_capsule(mission))


def compile_mission_capsule(mission: MissionSpec) -> MissionCapsule:
    return MissionCapsule.from_mission(mission)


def compile_goal_contract_from_capsule(capsule: MissionCapsule) -> GoalContract:
    mission_charter = capsule.mission_charter
    acceptance_contract = capsule.acceptance_contract
    authority_contract = capsule.authority_contract
    constraints = list(mission_charter.known_constraints)
    out_of_scope = list(mission_charter.explicit_non_goals)
    return GoalContract(
        mission_id=capsule.identity.capsule_id,
        capsule_id=capsule.identity.capsule_id,
        capsule_version=capsule.identity.capsule_version,
        domain_profile_id=capsule.domain_profile_id,
        locked_intent=mission_charter.locked,
        locked_acceptance=acceptance_contract.locked,
        objective=mission_charter.user_intent,
        purpose=mission_charter.desired_outcome or mission_charter.user_intent,
        desired_end_state=mission_charter.desired_outcome,
        key_tasks=list(acceptance_contract.required_artifacts),
        constraints=constraints,
        out_of_scope=out_of_scope,
        workspace_root=authority_contract.workspace_root,
        forbidden_paths=list(authority_contract.forbidden_files),
        forbidden_actions=list(authority_contract.forbidden_actions),
        acceptance=list(acceptance_contract.criteria),
        evidence_requirements=list(acceptance_contract.evidence_plan.required_evidence),
        required_evidence_summary=acceptance_contract.evidence_plan.summary,
        required_evidence_count=acceptance_contract.evidence_plan.required_count,
    )


def render_goal_objective(mission: MissionSpec) -> str:
    capsule = compile_mission_capsule(mission)
    return render_goal_objective_from_capsule(capsule)


def render_goal_objective_from_capsule(capsule: MissionCapsule) -> str:
    contract = compile_goal_contract_from_capsule(capsule)
    contract_json = contract.model_dump_json(by_alias=True, indent=2)
    capsule_summary_json = json.dumps(_goal_capsule_summary(capsule), indent=2, ensure_ascii=False)
    report_contract_json = json.dumps(_execution_report_prompt_contract(), indent=2, ensure_ascii=False)
    return "\n\n".join(
        [
            "You are Codex executing a MetaLoop mission goal.",
            "Work autonomously inside the workspace. Use your normal repository exploration, editing, and validation judgement.",
            "MissionCapsule is the canonical governance object. Do not change its locked intent, scope, permissions, or acceptance criteria.",
            "If something cannot be verified, record the limitation explicitly.",
            "Before finishing, write the required ExecutionReport JSON file at the path specified by required_report_path.",
            "Set ExecutionReport.mission_id exactly to GoalContract.mission_id for this run.",
            "MetaLoop will independently verify the result after you finish; your ExecutionReport is candidate evidence, not final acceptance.",
            "MissionCapsule summary:",
            capsule_summary_json,
            "GoalContract:",
            contract_json,
            "ExecutionReport schema:",
            report_contract_json,
        ]
    )


def _goal_capsule_summary(capsule: MissionCapsule) -> dict:
    charter = capsule.mission_charter
    acceptance = capsule.acceptance_contract
    authority = capsule.authority_contract
    return {
        "schema": capsule.schema_name,
        "capsule_id": capsule.identity.capsule_id,
        "capsule_version": capsule.identity.capsule_version,
        "domain_profile_id": capsule.domain_profile_id,
        "lifecycle_state": capsule.lifecycle_state.value,
        "mission_charter": {
            "user_intent": charter.user_intent,
            "desired_outcome": charter.desired_outcome,
            "known_constraints": list(charter.known_constraints),
            "explicit_non_goals": list(charter.explicit_non_goals),
            "locked": charter.locked,
        },
        "acceptance_contract": {
            "required_artifacts": list(acceptance.required_artifacts),
            "criteria": [criterion.model_dump() for criterion in acceptance.criteria],
            "evidence_plan": {
                "summary": acceptance.evidence_plan.summary,
                "required_count": acceptance.evidence_plan.required_count,
            },
            "locked": acceptance.locked,
        },
        "authority_contract": {
            "workspace_root": authority.workspace_root,
            "allowed_files": list(authority.allowed_files),
            "allowed_tools": list(authority.allowed_tools),
            "allowed_networks": list(authority.allowed_networks),
            "forbidden_files": list(authority.forbidden_files),
            "forbidden_tools": list(authority.forbidden_tools),
            "forbidden_commands": list(authority.forbidden_commands),
            "forbidden_actions": list(authority.forbidden_actions),
        },
    }


def _execution_report_prompt_contract() -> dict:
    return {
        "schema": "metaloop.execution_report",
        "required_fields": {
            "schema": "literal metaloop.execution_report",
            "version": "1.0",
            "mission_id": "must exactly equal GoalContract.mission_id",
            "status": ["completed", "blocked", "failed"],
            "summary": "concise factual summary of work completed or why it stopped",
        },
        "optional_evidence_fields": {
            "changed_files": "workspace-relative files intentionally changed; exclude .metaloop and generated caches",
            "commands_run": "commands actually executed for validation or inspection",
            "validation_results": "short outcomes of tests, builds, checks, or manual tool inspections",
            "evidence": "paths, outputs, or observations proving acceptance criteria",
            "known_limitations": "remaining limitations without hiding acceptance failures",
        },
    }


def execution_report_json_schema() -> dict:
    return ExecutionReport.model_json_schema(by_alias=True)


def load_execution_report(workspace_root: str | Path, report_path: str = DEFAULT_EXECUTION_REPORT_PATH) -> ExecutionReport:
    path = Path(report_path)
    if not path.is_absolute():
        path = Path(workspace_root).expanduser().resolve() / path
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ExecutionReport.model_validate(payload)


def verify_mission(
    mission: MissionSpec,
    *,
    report_path: str = DEFAULT_EXECUTION_REPORT_PATH,
    artifact_validator: ArtifactValidator | None = None,
) -> VerificationResult:
    validator = artifact_validator or ArtifactValidator()
    capsule = compile_mission_capsule(mission)
    evidence_requirements = list(capsule.acceptance_contract.evidence_plan.required_evidence)
    required_evidence_summary = capsule.acceptance_contract.evidence_plan.summary
    hard_criteria = [
        criterion
        for criterion in mission.acceptance_criteria
        if criterion.validation_type not in {"manual", "llm_review"}
    ]
    soft_results = [
        SoftReviewResult(
            criteria_id=criterion.id,
            required=criterion.required,
            validation_type=criterion.validation_type,  # type: ignore[arg-type]
            description=criterion.description,
            status="requires_final_human_acceptance" if criterion.validation_type == "manual" else "pending_llm_review",
        )
        for criterion in mission.acceptance_criteria
        if criterion.validation_type in {"manual", "llm_review"}
    ]

    hard_mission = mission.model_copy(update={"acceptance_criteria": hard_criteria})
    hard_results = validator.validate(hard_mission) if hard_criteria else []
    evidence_results: list[EvidenceCheck] = []
    report = None

    try:
        report = load_execution_report(mission.policy.workspace_root, report_path)
    except FileNotFoundError:
        evidence_results.append(
            EvidenceCheck(
                name="execution_report",
                passed=False,
                message=f"missing: {report_path}",
                evidence_class="execution_report",
            )
        )
    except (json.JSONDecodeError, ValidationError, OSError) as exc:
        evidence_results.append(
            EvidenceCheck(
                name="execution_report",
                passed=False,
                message=f"invalid: {exc}",
                evidence_class="execution_report",
            )
        )
    else:
        evidence_results.append(
            EvidenceCheck(
                name="execution_report",
                passed=True,
                message="valid execution report",
                evidence_class="execution_report",
            )
        )
        if report.mission_id != mission.run_id:
            evidence_results.append(
                EvidenceCheck(
                    name="execution_report.mission_id",
                    passed=False,
                    message=f"expected current run_id {mission.run_id}, got execution_report.mission_id {report.mission_id}",
                    evidence_class="execution_report",
                )
            )
    evidence_results.extend(_check_required_evidence(mission, evidence_requirements, hard_results, report))
    evidence_results.extend(_check_domain_profile_evidence_obligations(mission, report))

    status, reason = _classify_verification(report, hard_results, soft_results, evidence_results)
    required_checks = [item for item in evidence_results if item.required]
    return VerificationResult(
        mission_id=mission.run_id,
        status=status,
        hard_validator_results=hard_results,
        soft_review_results=soft_results,
        evidence_results=evidence_results,
        required_evidence_summary=required_evidence_summary,
        required_evidence_total=len(required_checks),
        required_evidence_satisfied=sum(1 for item in required_checks if item.passed),
        execution_report=report,
        reason=reason,
    )


def _check_required_evidence(
    mission: MissionSpec,
    requirements: list[EvidenceRequirement],
    hard_results: list[ValidationResult],
    report: ExecutionReport | None,
) -> list[EvidenceCheck]:
    checks: list[EvidenceCheck] = []
    hard_by_criterion = {result.criteria_id: result for result in hard_results}
    criteria_by_id = {criterion.id: criterion for criterion in mission.acceptance_criteria}
    report_items = _execution_report_evidence_items(report)
    for requirement in requirements:
        if requirement.evidence_class == "execution_report":
            continue
        if requirement.evidence_class in {"llm_review", "human_acceptance"}:
            checks.append(
                EvidenceCheck(
                    name=f"required_evidence.{requirement.evidence_class}",
                    passed=True,
                    message="deferred to soft review or final human acceptance",
                    requirement_id=requirement.requirement_id,
                    evidence_class=requirement.evidence_class,
                    required=False,
                )
            )
            continue
        criterion = criteria_by_id.get(requirement.criterion_id or "")
        hard_result = hard_by_criterion.get(requirement.criterion_id or "")
        if hard_result is not None:
            checks.append(
                EvidenceCheck(
                    name=f"required_evidence.{requirement.evidence_class}",
                    passed=hard_result.passed,
                    message=hard_result.message,
                    requirement_id=requirement.requirement_id,
                    evidence_class=requirement.evidence_class,
                    required=requirement.required,
                )
            )
            continue
        target = criterion.validation_target if criterion is not None else ""
        has_report_evidence = _report_mentions_required_evidence(report_items, target, requirement.description)
        checks.append(
            EvidenceCheck(
                name=f"required_evidence.{requirement.evidence_class}",
                passed=has_report_evidence,
                message="present in execution report" if has_report_evidence else "missing required evidence in execution report",
                requirement_id=requirement.requirement_id,
                evidence_class=requirement.evidence_class,
                required=requirement.required,
            )
        )
    return checks


def _execution_report_evidence_items(report: ExecutionReport | None) -> list[str]:
    if report is None:
        return []
    return [
        item
        for item in [
            *report.changed_files,
            *report.commands_run,
            *report.validation_results,
            *report.evidence,
        ]
        if item
    ]


def _check_domain_profile_evidence_obligations(
    mission: MissionSpec,
    report: ExecutionReport | None,
) -> list[EvidenceCheck]:
    profile_id = str(mission.context.get("domain_profile_id") or mission.context.get("domain_profile") or "engineering_development")
    text = " ".join(
        [
            mission.intent,
            *mission.deliverables,
            *[criterion.description for criterion in mission.acceptance_criteria],
        ]
    ).lower()
    report_text = " ".join(_execution_report_evidence_items(report) + ([report.summary] if report is not None else [])).lower()
    checks: list[EvidenceCheck] = []
    if profile_id == "engineering_development":
        file_or_code_task = bool(mission.deliverables) or any(
            criterion.validation_type in {"file_exists", "file_contains", "schema", "command"}
            for criterion in mission.acceptance_criteria
        )
        if file_or_code_task:
            checks.append(
                EvidenceCheck(
                    name="domain.engineering.changed_files",
                    passed=report is not None and bool(report.changed_files),
                    message="changed files recorded" if report is not None and report.changed_files else "changed files not recorded in ExecutionReport",
                    evidence_class="execution_report",
                    required=False,
                )
            )
        needs_regression = any(token in text for token in ["bug", "fix", "regression", "public behavior", "api behavior"])
        if needs_regression:
            has_regression = report is not None and any(
                token in report_text for token in ["test", "pytest", "lint", "regression", "build"]
            )
            checks.append(
                EvidenceCheck(
                    name="domain.engineering.regression_evidence",
                    passed=has_regression,
                    message="regression/build/test evidence recorded" if has_regression else "bugfix or public-behavior task lacks regression/build/test evidence",
                    evidence_class="command_output",
                    required=True,
                )
            )
    elif profile_id == "algorithm_research":
        for name, tokens in {
            "assumptions": ["assumption", "assumptions"],
            "method": ["method", "approach"],
            "experiment_or_benchmark": ["experiment", "benchmark", "measurement"],
            "limitations": ["limitation", "limitations", "uncertainty"],
        }.items():
            checks.append(
                EvidenceCheck(
                    name=f"domain.algorithm_research.{name}",
                    passed=any(token in report_text for token in tokens),
                    message=f"{name.replace('_', ' ')} evidence recorded" if any(token in report_text for token in tokens) else f"{name.replace('_', ' ')} evidence not recorded",
                    evidence_class="execution_report",
                    required=False,
                )
            )
    elif profile_id == "codex_skill_creation":
        for name, tokens in {
            "skill_md": ["skill.md"],
            "usage_example": ["usage example", "example"],
            "validation_checklist": ["validation checklist", "checklist", "validation"],
        }.items():
            checks.append(
                EvidenceCheck(
                    name=f"domain.codex_skill_creation.{name}",
                    passed=any(token in report_text for token in tokens),
                    message=f"{name.replace('_', ' ')} evidence recorded" if any(token in report_text for token in tokens) else f"{name.replace('_', ' ')} evidence not recorded",
                    evidence_class="execution_report",
                    required=False,
                )
            )
    elif profile_id == "deep_research":
        source_required = any(token in text for token in ["source", "citation", "provenance", "freshness", "claim", "research"])
        for name, tokens in {
            "source_table": ["source table", "sources"],
            "citation_provenance": ["citation", "provenance", "cited"],
            "freshness": ["freshness", "date", "current"],
            "claim_support": ["claim support", "supported claim", "evidence"],
        }.items():
            passed = any(token in report_text for token in tokens)
            checks.append(
                EvidenceCheck(
                    name=f"domain.deep_research.{name}",
                    passed=passed,
                    message=f"{name.replace('_', ' ')} evidence recorded" if passed else f"{name.replace('_', ' ')} evidence not recorded",
                    evidence_class="execution_report",
                    required=source_required and name in {"source_table", "citation_provenance", "claim_support"},
                )
            )
    return checks


def _report_mentions_required_evidence(items: list[str], target: str | None, description: str) -> bool:
    if not items:
        return False
    needles = [item for item in (target, description) if item]
    if not needles:
        return bool(items)
    lowered_items = [item.lower() for item in items]
    for needle in needles:
        lowered = needle.lower()
        if any(lowered in item or item in lowered for item in lowered_items):
            return True
    return False


def _classify_verification(
    report: ExecutionReport | None,
    hard_results: list[ValidationResult],
    soft_results: list[SoftReviewResult],
    evidence_results: list[EvidenceCheck],
) -> tuple[VerificationStatus, str]:
    if report is not None and report.status == ExecutionReportStatus.BLOCKED:
        return VerificationStatus.BLOCKED, "ExecutionReport status is blocked."
    if report is not None and report.status == ExecutionReportStatus.FAILED:
        return VerificationStatus.FAILED, "ExecutionReport status is failed."
    failed_required_hard = [result for result in hard_results if not result.passed]
    if failed_required_hard:
        return VerificationStatus.FAILED, "Required hard validators failed."
    failed_evidence = [result for result in evidence_results if result.required and not result.passed]
    if failed_evidence:
        return VerificationStatus.FAILED, "Required evidence is missing or invalid."
    if any(result.required and result.validation_type == "manual" for result in soft_results):
        return (
            VerificationStatus.COMPLETED_PENDING_HUMAN_ACCEPTANCE,
            "Internal work is complete; manual acceptance remains a final user decision.",
        )
    if any(result.required and result.validation_type == "llm_review" for result in soft_results):
        return VerificationStatus.COMPLETED_WITH_SOFT_ACCEPTANCE, "LLM-review criteria remain soft acceptance."
    if report is not None and report.known_limitations:
        return VerificationStatus.COMPLETED_WITH_LIMITATIONS, "ExecutionReport declares known limitations."
    return VerificationStatus.COMPLETED_VERIFIED, "All hard validators and evidence checks passed."


def _desired_end_state(mission: MissionSpec) -> str:
    parts = []
    if mission.deliverables:
        parts.append("Deliverables: " + "; ".join(mission.deliverables))
    if mission.acceptance_criteria:
        parts.append("Acceptance: " + "; ".join(item.description for item in mission.acceptance_criteria))
    return "\n".join(parts)


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _forbidden_actions(risk_level: RiskLevel, out_of_scope: list[str]) -> list[str]:
    actions = ["do not weaken acceptance criteria", "do not mark unverifiable work as verified"]
    if risk_level in {RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL}:
        actions.extend(["do not exfiltrate secrets", "do not upload private workspace files"])
    actions.extend(out_of_scope)
    return actions
