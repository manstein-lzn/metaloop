from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from metaloop.attempt_history import filter_attempt_changed_files, inspect_git_snapshot, write_attempt_history_record
from metaloop.codex_adapter import CodexExecAdapter, CodexExecOptions, CodexExecResult, map_codex_event_type
from metaloop.capsule import AttemptOutcome, AttemptRecord, ClosureOutcome, EvidenceRecord, LifecycleState, MissionCapsule
from metaloop.goal import (
    DEFAULT_EXECUTION_REPORT_PATH,
    EvidenceCheck,
    RedesignProposal,
    RedesignContractDelta,
    ReviewRoute,
    RepairAttemptEvidence,
    VerificationResult,
    VerificationStatus,
    compile_goal_contract_from_capsule,
    compile_mission_capsule,
    render_goal_objective_from_capsule,
    verify_mission,
)
from metaloop.prompt_pack import PromptPackError, render_prompt
from metaloop.run_artifacts import StructuredRunArtifacts, StructuredRunManifest
from metaloop.schemas import MissionSpec
from metaloop.soft_review import RuleSoftReviewer, SoftReviewer


GoalStatusCallback = Callable[[str], None]
GoalEventCallback = Callable[[dict[str, Any]], None]
_REDESIGN_ROUTES = {
    ReviewRoute.ASK_ARCHITECT_TO_RETHINK,
    ReviewRoute.ASK_PLANNER_TO_REPLAN,
    ReviewRoute.ASK_BRAINSTORMER_FOR_OPTIONS,
}


@dataclass
class GoalRuntimeResult:
    mission: MissionSpec
    verification: VerificationResult
    manifest: StructuredRunManifest
    codex_result: CodexExecResult | None = None
    goal_prompt: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verification.status not in {VerificationStatus.FAILED, VerificationStatus.BLOCKED}


class GoalRuntimePromptError(ValueError):
    """Raised when a goal runtime prompt cannot be compiled safely."""


class GoalRuntimeAdapter(Protocol):
    def run(
        self,
        mission: MissionSpec,
        *,
        on_status: GoalStatusCallback | None = None,
        on_event: GoalEventCallback | None = None,
    ) -> GoalRuntimeResult:
        ...


class CodexExecGoalRuntimeAdapter:
    """Use one ordinary Codex exec agent call as the current goal runtime."""

    def __init__(
        self,
        options: CodexExecOptions | None = None,
        *,
        soft_reviewer: SoftReviewer | None = None,
        max_worker_repairs: int = 1,
    ) -> None:
        self.options = options or CodexExecOptions(use_output_schema=False)
        self.soft_reviewer = soft_reviewer or RuleSoftReviewer()
        self.max_worker_repairs = max_worker_repairs

    def run(
        self,
        mission: MissionSpec,
        *,
        on_status: GoalStatusCallback | None = None,
        on_event: GoalEventCallback | None = None,
    ) -> GoalRuntimeResult:
        workspace = Path(mission.policy.workspace_root).expanduser().resolve()
        artifacts = StructuredRunArtifacts(workspace, mission.run_id)
        _status(on_status, "Compiling MissionSpec into MissionCapsule and GoalContract...")
        capsule = compile_mission_capsule(mission)
        contract = compile_goal_contract_from_capsule(capsule)
        prompt = render_goal_objective_from_capsule(capsule)
        manifest = artifacts.write_inputs(mission, contract, prompt, mode="goal", capsule=capsule)
        capsule = capsule.transition(LifecycleState.IN_PROGRESS, summary="Codex goal runtime started.")
        artifacts.write_capsule(capsule)
        _status(
            on_status,
            "Structured artifacts prepared: "
            f"{manifest.mission_capsule_path}, {manifest.goal_contract_path}, "
            f"{manifest.goal_prompt_path}, {manifest.codex_events_path}",
        )

        _status(on_status, "Starting Codex goal runtime...")
        events: list[dict[str, Any]] = []

        def handle_event(event: dict[str, Any]) -> None:
            events.append(event)
            artifacts.append_codex_event(event)
            if on_event is not None:
                on_event(event)
            detail = _event_status(event)
            if detail:
                _status(on_status, detail)

        options = self.options.model_copy(
            update={
                "working_directory": str(workspace),
                "use_output_schema": False,
                "output_schema": None,
            }
        )
        result = CodexExecAdapter(options).run(prompt, on_event=handle_event)

        if not result.ok:
            _status(
                on_status,
                f"Codex runtime failed: exit={result.returncode}, timed_out={str(result.timed_out).lower()}. "
                "Verifying available evidence...",
            )
        else:
            _status(on_status, "Codex finished; verifying MissionSpec acceptance...")

        verification = verify_mission(mission, report_path=DEFAULT_EXECUTION_REPORT_PATH)
        _status(on_status, _verification_summary("Initial verification", verification))
        if not result.ok:
            verification.evidence_results.append(
                EvidenceCheck(
                    name="codex_runtime",
                    passed=False,
                    message=f"codex exec exited with {result.returncode}",
                )
            )
            verification.status = VerificationStatus.FAILED
            verification.reason = f"Codex runtime failed before verified completion. {verification.reason}".strip()
        if result.ok:
            verification = self._review_and_repair(
                mission,
                verification,
                capsule,
                options,
                artifacts,
                handle_event,
                on_status,
            )
        artifacts.write_verification(verification)
        capsule, attempt_path = _record_final_capsule_state(capsule, verification, result, events, workspace_root=workspace)
        artifacts.write_capsule(capsule)
        manifest.status = verification.status.value
        manifest.attempt_record_path = _relative_to_workspace(workspace, attempt_path)
        manifest.metadata.update(
            {
                "codex_returncode": result.returncode,
                "codex_thread_id": result.thread_id,
                "codex_timed_out": result.timed_out,
                "attempt_record_path": manifest.attempt_record_path,
            }
        )
        artifacts.write_manifest(manifest)
        _status(on_status, _verification_summary("Final verification", verification))

        return GoalRuntimeResult(
            mission=mission,
            verification=verification,
            manifest=manifest,
            codex_result=result,
            goal_prompt=prompt,
            events=events,
        )

    def _review_and_repair(
        self,
        mission: MissionSpec,
        verification: VerificationResult,
        capsule: MissionCapsule,
        options: CodexExecOptions,
        artifacts: StructuredRunArtifacts,
        on_event: GoalEventCallback,
        on_status: GoalStatusCallback | None,
    ) -> VerificationResult:
        repairs = 0
        while True:
            _status(on_status, "Running internal soft reviewer...")
            decision = self.soft_reviewer.review(mission, verification)
            verification.soft_review_decision = decision
            artifacts.write_verification(verification)
            _status(
                on_status,
                "Reviewer route: "
                f"{decision.route.value} "
                f"(passed={str(decision.passed).lower()}, confidence={decision.confidence}, findings={len(decision.findings)})",
            )
            if decision.route == ReviewRoute.COMPLETE:
                _status(on_status, "Reviewer accepted the current result.")
                return verification
            if decision.route == ReviewRoute.FAIL:
                verification.status = VerificationStatus.FAILED
                verification.reason = "Soft reviewer routed to fail."
                _status(on_status, "Reviewer routed to fail; stopping run.")
                return verification
            if decision.route in _REDESIGN_ROUTES:
                _status(on_status, f"Soft reviewer routed to {decision.route.value}; generating redesign proposal.")
                proposal = self._generate_redesign_proposal(
                    mission,
                    verification,
                    capsule,
                    options,
                    artifacts,
                    on_event,
                    on_status,
                )
                verification.status = VerificationStatus.FAILED
                verification.reason = (
                    f"redesign_required: reviewer route {decision.route.value}; "
                    f"proposal written to {artifacts.redesign_proposal_path.name}. {proposal.reason}"
                )
                artifacts.write_verification(verification)
                return verification
            if repairs >= 2:
                _status(on_status, "Repeated repair requests reached the redesign gate; generating redesign proposal.")
                proposal = self._generate_redesign_proposal(
                    mission,
                    verification,
                    capsule,
                    options,
                    artifacts,
                    on_event,
                    on_status,
                )
                verification.status = VerificationStatus.FAILED
                verification.reason = (
                    "redesign_required: repeated implementation repairs did not converge; "
                    f"proposal written to {artifacts.redesign_proposal_path.name}. {proposal.reason}"
                )
                artifacts.write_verification(verification)
                return verification
            if repairs >= self.max_worker_repairs:
                verification.status = VerificationStatus.FAILED
                verification.reason = f"Soft reviewer routed to {decision.route.value}, but repair retry budget is exhausted."
                _status(on_status, "Repair retry budget exhausted; stopping run.")
                return verification
            repairs += 1
            previous_failed_fix_summary = _repair_failed_fix_summary(verification)
            repair_attempt = RepairAttemptEvidence(
                repair_attempt_index=repairs,
                reviewer_route=decision.route,
                root_cause="" if repairs == 1 else "required in repair response before editing",
                hypothesis="" if repairs == 1 else "required in repair response before editing",
                failed_fix_summary=previous_failed_fix_summary,
                prompt_requirements=_repair_prompt_requirements(repairs),
            )
            verification.repair_attempts.append(repair_attempt)
            artifacts.write_verification(verification)
            _status(
                on_status,
                f"Repair attempt {repairs}/{self.max_worker_repairs}: route={decision.route.value} "
                "(implementation-level; locked contract unchanged).",
            )
            _status(on_status, "Capsule lifecycle: repairing implementation without changing locked contract.")
            _status(on_status, "Sending implementation repair prompt to Codex worker...")
            repair_prompt = build_repair_prompt(
                mission,
                verification,
                repair_attempt_index=repairs,
                failed_fix_summary=previous_failed_fix_summary,
            )
            result = CodexExecAdapter(options).run(repair_prompt, on_event=on_event)
            if not result.ok:
                verification.status = VerificationStatus.FAILED
                verification.reason = f"Worker repair failed: codex exec exited with {result.returncode}."
                verification.repair_attempts[-1].failed_fix_summary = verification.reason
                verification.evidence_results.append(
                    EvidenceCheck(
                        name="codex_repair_runtime",
                        passed=False,
                        message=result.stderr or f"codex exec exited with {result.returncode}",
                    )
                )
                return verification
            _status(on_status, "Repair completed; rerunning MetaLoop verification...")
            prior_attempts = list(verification.repair_attempts)
            verification = verify_mission(mission, report_path=DEFAULT_EXECUTION_REPORT_PATH)
            verification.repair_attempts = prior_attempts
            _status(on_status, _verification_summary("Post-repair verification", verification))

    def _generate_redesign_proposal(
        self,
        mission: MissionSpec,
        verification: VerificationResult,
        capsule: MissionCapsule,
        options: CodexExecOptions,
        artifacts: StructuredRunArtifacts,
        on_event: GoalEventCallback,
        on_status: GoalStatusCallback | None,
    ) -> RedesignProposal:
        decision = verification.soft_review_decision
        route = decision.route if decision is not None else ReviewRoute.FAIL
        route_result = CodexExecAdapter(options).run(
            build_focused_route_prompt(mission, verification, capsule=capsule),
            on_event=on_event,
        )
        guidance = route_result.final_message if route_result.ok and route_result.final_message else ""
        if not guidance:
            guidance = decision.rationale if decision is not None and decision.rationale else "Focused redesign guidance was unavailable."
            verification.evidence_results.append(
                EvidenceCheck(
                    name=f"{route.value}_runtime",
                    passed=False,
                    message=route_result.stderr or f"codex exec exited with {route_result.returncode}",
                )
            )
        proposal = build_redesign_proposal(
            mission,
            capsule,
            verification,
            reviewer_route=route,
            guidance=guidance,
        )
        artifacts.write_redesign_proposal(proposal)
        _status(on_status, f"Redesign proposal written: {artifacts.redesign_proposal_path}")
        return proposal


def _status(callback: GoalStatusCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _event_status(event: dict[str, Any]) -> str:
    mapped = map_codex_event_type(event)
    if mapped == "codex_turn_started":
        return "Codex turn started."
    if mapped == "codex_turn_completed":
        usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
        tokens = int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0)
        return f"Codex turn completed ({tokens} tokens)."
    if mapped == "codex_command_started":
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        return f"Codex running command: {_shorten(item.get('command') or 'command')}"
    if mapped == "codex_command_completed":
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        code = item.get("exit_code")
        suffix = f" exit={code}" if code is not None else ""
        return f"Codex command completed{suffix}: {_shorten(item.get('command') or 'command')}"
    if mapped == "codex_file_change_completed":
        return "Codex edited files."
    if mapped == "codex_agent_message_completed":
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        return f"Codex reported: {_shorten(item.get('text') or '')}"
    return ""


def _verification_summary(label: str, verification: VerificationResult) -> str:
    hard_total = len(verification.hard_validator_results)
    hard_passed = sum(1 for item in verification.hard_validator_results if item.passed)
    evidence_total = len(verification.evidence_results)
    evidence_passed = sum(1 for item in verification.evidence_results if item.passed)
    soft_total = len(verification.soft_review_results)
    return (
        f"{label}: status={verification.status.value}, "
        f"hard={hard_passed}/{hard_total}, evidence={evidence_passed}/{evidence_total}, soft={soft_total}. "
        f"{_shorten(verification.reason, 120)}"
    )


def _record_final_capsule_state(
    capsule: MissionCapsule,
    verification: VerificationResult,
    codex_result: CodexExecResult,
    events: list[dict[str, Any]],
    *,
    workspace_root: Path,
) -> tuple[MissionCapsule, Path]:
    evidence_ids: list[str] = []
    if verification.execution_report is not None:
        evidence = EvidenceRecord(
            capsule_id=capsule.identity.capsule_id,
            capsule_version=capsule.identity.capsule_version,
            evidence_class="execution_report",
            producer="codex",
            summary=verification.execution_report.summary,
            uri=DEFAULT_EXECUTION_REPORT_PATH,
            content=verification.execution_report.model_dump_json(by_alias=True),
        )
        capsule = capsule.with_evidence(evidence)
        evidence_ids.append(evidence.evidence_id)

    verification_evidence = EvidenceRecord(
        capsule_id=capsule.identity.capsule_id,
        capsule_version=capsule.identity.capsule_version,
        evidence_class="schema",
        producer="metaloop",
        summary=f"VerificationResult: {verification.status.value}. {verification.reason}",
        uri=".metaloop/verification_result.json",
        content=verification.model_dump_json(by_alias=True),
    )
    capsule = capsule.with_evidence(verification_evidence)
    evidence_ids.append(verification_evidence.evidence_id)

    if verification.soft_review_decision is not None:
        review_evidence = EvidenceRecord(
            capsule_id=capsule.identity.capsule_id,
            capsule_version=capsule.identity.capsule_version,
            evidence_class="review_decision",
            producer="metaloop.soft_reviewer",
            summary=(
                f"SoftReviewDecision route={verification.soft_review_decision.route.value}, "
                f"passed={str(verification.soft_review_decision.passed).lower()}."
            ),
            content=verification.soft_review_decision.model_dump_json(by_alias=True),
        )
        capsule = capsule.with_evidence(review_evidence)
        evidence_ids.append(review_evidence.evidence_id)

    git = inspect_git_snapshot(workspace_root)
    changed_files = filter_attempt_changed_files(_merge_unique([*git.changed_files, *_artifacts_from_verification(verification)]))
    lesson = _attempt_lesson(verification)
    attempt = AttemptRecord(
        capsule_id=capsule.identity.capsule_id,
        capsule_version=capsule.identity.capsule_version,
        executor="codex_exec_goal_runtime",
        git_commit_ref=git.commit or "",
        changed_files=tuple(changed_files),
        validation_summary=_verification_summary("Final verification", verification),
        result=verification.status.value,
        lesson=lesson,
        context_snapshot_ref=git.commit or "",
        active_permissions={
            "sandbox": getattr(codex_result, "sandbox", None),
            "returncode": codex_result.returncode,
            "timed_out": codex_result.timed_out,
        },
        actions_taken=_summarize_codex_events(events),
        artifacts_produced=tuple(changed_files),
        evidence_record_ids=tuple(evidence_ids),
        outcome=_attempt_outcome_for_verification(verification),
        failure_mode="" if verification.status not in {VerificationStatus.FAILED, VerificationStatus.BLOCKED} else verification.reason,
        lessons=tuple(item.message for item in verification.evidence_results if not item.passed),
    )
    capsule = capsule.with_attempt(attempt)
    attempt_path = write_attempt_history_record(workspace_root=workspace_root, attempt=attempt, verification=verification)
    return _close_or_route_capsule(capsule, verification, tuple(evidence_ids)), attempt_path


def _attempt_outcome_for_verification(verification: VerificationResult) -> AttemptOutcome:
    if _verification_is_redesign_required(verification):
        return AttemptOutcome.REDESIGN_NEEDED
    if verification.status == VerificationStatus.BLOCKED:
        return AttemptOutcome.BLOCKED
    if verification.status == VerificationStatus.FAILED:
        return AttemptOutcome.FAILED
    if verification.soft_review_decision is not None and verification.soft_review_decision.route != ReviewRoute.COMPLETE:
        return AttemptOutcome.REPAIRED
    return AttemptOutcome.COMPLETED


def _close_or_route_capsule(
    capsule: MissionCapsule,
    verification: VerificationResult,
    evidence_record_ids: tuple[str, ...],
) -> MissionCapsule:
    if capsule.lifecycle_state == LifecycleState.AUTHORIZED:
        capsule = capsule.transition(LifecycleState.IN_PROGRESS, summary="Final result recorded after implicit runtime start.")
    if _verification_is_redesign_required(verification):
        return capsule.transition(
            LifecycleState.REDESIGN_REQUIRED,
            summary=verification.reason or "redesign_required",
            evidence_record_ids=evidence_record_ids,
        )
    if verification.status == VerificationStatus.BLOCKED:
        return capsule.transition(
            LifecycleState.BLOCKED,
            summary=verification.reason or "Run blocked.",
            evidence_record_ids=evidence_record_ids,
        )
    if verification.status == VerificationStatus.FAILED:
        return capsule.transition(
            LifecycleState.CLOSED,
            closure_outcome=ClosureOutcome.FAILED,
            summary=verification.reason or "Run failed.",
            evidence_record_ids=evidence_record_ids,
        )

    if capsule.lifecycle_state == LifecycleState.IN_PROGRESS:
        capsule = capsule.transition(
            LifecycleState.REVIEW_READY,
            summary="Runtime result is ready for closure decision.",
            evidence_record_ids=evidence_record_ids,
        )
    return capsule.transition(
        LifecycleState.CLOSED,
        closure_outcome=_closure_outcome_for_verification(verification),
        summary=verification.reason or verification.status.value,
        evidence_record_ids=evidence_record_ids,
    )


def _verification_is_redesign_required(verification: VerificationResult) -> bool:
    if "redesign_required" in verification.reason:
        return True
    decision = verification.soft_review_decision
    return decision is not None and decision.route in _REDESIGN_ROUTES


def _closure_outcome_for_verification(verification: VerificationResult) -> ClosureOutcome:
    if verification.status == VerificationStatus.COMPLETED_PENDING_HUMAN_ACCEPTANCE:
        return ClosureOutcome.ACCEPTED_PENDING_HUMAN
    if verification.status == VerificationStatus.COMPLETED_WITH_LIMITATIONS:
        return ClosureOutcome.ACCEPTED_WITH_LIMITATIONS
    return ClosureOutcome.ACCEPTED


def _artifacts_from_verification(verification: VerificationResult) -> tuple[str, ...]:
    artifacts: list[str] = []
    if verification.execution_report is not None:
        artifacts.extend(verification.execution_report.changed_files)
    return tuple(dict.fromkeys(item for item in artifacts if item))


def _attempt_lesson(verification: VerificationResult) -> str:
    failed = [item.message for item in verification.evidence_results if not item.passed and item.message]
    if failed:
        return "; ".join(failed[:5])
    if verification.reason:
        return verification.reason
    return verification.status.value


def _merge_unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _relative_to_workspace(workspace: Path, path: Path) -> str:
    try:
        return str(path.relative_to(workspace))
    except ValueError:
        return str(path)


def _summarize_codex_events(events: list[dict[str, Any]]) -> tuple[str, ...]:
    summaries: list[str] = []
    for event in events:
        detail = _event_status(event)
        if detail:
            summaries.append(detail)
        if len(summaries) >= 20:
            break
    return tuple(summaries)


def build_focused_route_prompt(
    mission: MissionSpec,
    verification: VerificationResult,
    *,
    capsule: MissionCapsule | None = None,
    prompt_root: str | Path | None = None,
) -> str:
    decision = verification.soft_review_decision
    route = decision.route.value if decision is not None else "unknown"
    role = {
        ReviewRoute.ASK_ARCHITECT_TO_RETHINK: "architect",
        ReviewRoute.ASK_PLANNER_TO_REPLAN: "planner",
        ReviewRoute.ASK_BRAINSTORMER_FOR_OPTIONS: "brainstormer",
    }.get(decision.route if decision is not None else None, "specialist")
    variables = {
        "route_role": role,
        "reviewer_route": route,
        "mission_spec": _fenced_json(mission),
        "mission_capsule": _fenced_json(capsule if capsule is not None else {}),
        "verification_result": _fenced_json(verification),
        "soft_review_decision": _fenced_json(decision),
    }
    try:
        rendered = render_prompt(
            "run/redesign",
            variables,
            prompt_root=prompt_root,
            required_variables=(
                "route_role",
                "reviewer_route",
                "mission_spec",
                "mission_capsule",
                "verification_result",
                "soft_review_decision",
            ),
        )
    except PromptPackError as exc:
        raise GoalRuntimePromptError(f"focused route prompt pack render failed: {exc}") from exc
    return rendered.rendered_text


def _fenced_json(value: Any) -> str:
    if hasattr(value, "model_dump_json"):
        payload = json.loads(value.model_dump_json(by_alias=True))
    else:
        payload = value
    return "```json\n" + json.dumps(payload, indent=2, ensure_ascii=False) + "\n```"


def build_repair_prompt(
    mission: MissionSpec,
    verification: VerificationResult,
    *,
    route_guidance: str = "",
    repair_attempt_index: int = 1,
    failed_fix_summary: str = "",
) -> str:
    decision = verification.soft_review_decision
    instructions = decision.repair_instructions if decision is not None else "Fix the acceptance issues."
    parts = [
        "You are Codex repairing a MetaLoop mission at implementation level after internal review.",
        "This prompt is only for implementation defects. If the MissionSpec, acceptance, scope, or authority is wrong, stop and report that redesign is required.",
        "Do not change the mission goal or weaken acceptance criteria.",
        "Do not edit .metaloop/mission.json, .metaloop/mission_capsule.json, .metaloop/goal_contract.json, or change the locked Mission Capsule contract; redesign requires an explicit RedesignProposal and Capsule revision.",
        "Make focused changes that address the review findings. Then update .metaloop/execution_report.json.",
        f"Repair attempt index: {repair_attempt_index}.",
        "Before editing, identify the likely root_cause and hypothesis for the fix in your reasoning or final repair summary.",
        "Repair instructions:",
        instructions,
    ]
    if repair_attempt_index >= 2:
        parts.extend(
            [
                "This is a repeated repair. You must state a root_cause, a testable hypothesis, and why the previous fix failed before making changes.",
                "If the root cause is a wrong MissionSpec, acceptance criterion, scope boundary, or authority boundary, stop and report redesign_required instead of editing.",
            ]
        )
    if failed_fix_summary.strip():
        parts.extend(["Previous failed fix summary:", failed_fix_summary.strip()])
    if route_guidance.strip():
        parts.extend(["Focused route-agent guidance:", route_guidance.strip()])
    parts.extend(
        [
            "MissionSpec:",
            mission.model_dump_json(indent=2),
            "VerificationResult:",
            verification.model_dump_json(by_alias=True, indent=2),
        ]
    )
    return "\n\n".join(parts)


def build_redesign_proposal(
    mission: MissionSpec,
    capsule: MissionCapsule,
    verification: VerificationResult,
    *,
    reviewer_route: ReviewRoute,
    guidance: str,
) -> RedesignProposal:
    decision = verification.soft_review_decision
    reason = _first_non_empty(
        guidance,
        decision.rationale if decision is not None else "",
        verification.reason,
        f"Reviewer routed to {reviewer_route.value}.",
    )
    why_worker_repair_is_insufficient = _why_worker_repair_is_insufficient(verification, guidance)
    contract_delta = _build_contract_delta(mission, verification, guidance)
    return RedesignProposal(
        mission_id=mission.run_id,
        capsule_id=capsule.identity.capsule_id,
        capsule_version=capsule.identity.capsule_version,
        reviewer_route=reviewer_route,
        reason=reason,
        why_worker_repair_is_insufficient=why_worker_repair_is_insufficient,
        proposed_intent_changes=_proposal_items(guidance, ["intent", "objective", "goal"]),
        proposed_acceptance_changes=_proposal_items(guidance, ["acceptance", "validator", "verification", "criterion"]),
        proposed_scope_changes=_proposal_items(guidance, ["scope", "constraint", "out of scope", "boundary"]),
        proposed_authority_changes=_proposal_items(guidance, ["authority", "permission", "tool", "network", "approval"]),
        contract_delta=contract_delta,
        evidence_refs=_redesign_evidence_refs(verification),
    )


def _build_contract_delta(
    mission: MissionSpec,
    verification: VerificationResult,
    guidance: str,
) -> RedesignContractDelta:
    decision = verification.soft_review_decision
    reason_text = " ".join(
        [
            guidance,
            verification.reason,
            decision.rationale if decision is not None else "",
            " ".join(finding.message for finding in decision.findings) if decision is not None else "",
        ]
    )
    added_acceptance = _proposal_items(reason_text, ["acceptance", "validator", "verification", "criterion", "test"])
    modified_acceptance: list[str] = []
    if not added_acceptance and any(result.required and not result.passed for result in verification.hard_validator_results):
        modified_acceptance.append("Clarify failing hard validators without weakening required acceptance.")
    added_scope = _proposal_items(reason_text, ["scope", "deliverable", "mvp", "slice"])
    added_non_goals = _proposal_items(reason_text, ["non-goal", "out of scope", "exclude", "boundary"])
    if "scope" in reason_text.lower() and not added_non_goals and not mission.context.get("out_of_scope"):
        added_non_goals.append("Add explicit out-of-scope boundaries for the revised MissionSpec.")
    authority_delta = _proposal_items(reason_text, ["authority", "permission", "tool", "approval", "network", "workspace"])
    evidence_delta = _proposal_items(reason_text, ["evidence", "source", "benchmark", "test", "lint", "build", "verification"])
    if not evidence_delta:
        evidence_delta.append("Add explicit evidence required to prove the revised contract.")
    return RedesignContractDelta(
        added_scope=added_scope,
        removed_scope=[],
        added_non_goals=added_non_goals,
        added_acceptance=added_acceptance,
        modified_acceptance=modified_acceptance,
        removed_acceptance=[],
        authority_delta=authority_delta,
        evidence_delta=evidence_delta,
    )


def _first_non_empty(*values: str) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return "redesign_required"


def _why_worker_repair_is_insufficient(verification: VerificationResult, guidance: str) -> str:
    decision = verification.soft_review_decision
    if decision is not None and decision.rationale.strip():
        return decision.rationale.strip()
    if "worker repair" in guidance.lower():
        return _shorten(guidance, 240)
    return "The reviewer selected a contract-level route; implementation repair must not change locked intent, acceptance, scope, or authority."


def _proposal_items(guidance: str, keywords: list[str]) -> list[str]:
    items: list[str] = []
    lowered_keywords = [keyword.lower() for keyword in keywords]
    for line in guidance.splitlines():
        text = line.strip(" -*\t")
        if not text:
            continue
        lowered = text.lower()
        if any(keyword in lowered for keyword in lowered_keywords):
            items.append(text)
    return items[:8]


def _redesign_evidence_refs(verification: VerificationResult) -> list[str]:
    refs: list[str] = [".metaloop/verification_result.json"]
    if verification.execution_report is not None:
        refs.append(DEFAULT_EXECUTION_REPORT_PATH)
    refs.extend(item.name for item in verification.evidence_results if not item.passed)
    return list(dict.fromkeys(refs))


def _repair_prompt_requirements(repair_attempt_index: int) -> list[str]:
    requirements = [
        "keep repair implementation-level",
        "do not modify locked MissionSpec, MissionCapsule, or GoalContract",
        "update ExecutionReport after repair",
    ]
    if repair_attempt_index >= 2:
        requirements.extend(
            [
                "state root_cause before editing",
                "state hypothesis before editing",
                "summarize why the previous fix failed",
            ]
        )
    return requirements


def _repair_failed_fix_summary(verification: VerificationResult) -> str:
    failed = [item.message for item in verification.evidence_results if not item.passed and item.message]
    failed.extend(result.message for result in verification.hard_validator_results if not result.passed and result.message)
    if verification.reason:
        failed.append(verification.reason)
    return "; ".join(dict.fromkeys(failed))[:480]


def _shorten(value: object, limit: int = 96) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
