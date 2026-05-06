from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from metaloop.schemas import AcceptanceCriteria, MissionSpec, new_id, utc_now


class LifecycleState(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    AUTHORIZED = "authorized"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW_READY = "review_ready"
    REPAIRING = "repairing"
    REDESIGN_REQUIRED = "redesign_required"
    WAITING_ON_CHILDREN = "waiting_on_children"
    CLOSED = "closed"
    ARCHIVED = "archived"


class ClosureOutcome(str, Enum):
    ACCEPTED = "accepted"
    ACCEPTED_WITH_LIMITATIONS = "accepted_with_limitations"
    ACCEPTED_PENDING_HUMAN = "accepted_pending_human"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    DECOMPOSED = "decomposed"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class EvidenceStatus(str, Enum):
    CURRENT = "current"
    INVALIDATED = "invalidated"
    CONTRADICTED = "contradicted"
    SUPERSEDED = "superseded"
    STALE = "stale"


class AttemptOutcome(str, Enum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    REPAIRED = "repaired"
    REDESIGN_NEEDED = "redesign_needed"


class CapsuleIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    capsule_id: str = Field(default_factory=lambda: new_id("capsule"))
    capsule_version: str = "1.0"
    created_at: str = Field(default_factory=utc_now)
    created_by: str = "metaloop"
    owner: str = "user"
    parent_capsule_id: str | None = None
    child_capsule_ids: tuple[str, ...] = ()


class MissionCharter(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_intent: str
    desired_outcome: str = ""
    explicit_non_goals: tuple[str, ...] = ()
    scope_boundaries: tuple[str, ...] = ()
    known_constraints: tuple[str, ...] = ()
    urgency: str = ""
    domain_profile_id: str = "engineering_development"
    locked: bool = True

    @model_validator(mode="after")
    def intent_required(self) -> MissionCharter:
        if not self.user_intent.strip():
            raise ValueError("MissionCharter requires user_intent")
        return self


class AuthorityContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    authorized_by: str = "user"
    workspace_root: str = "."
    allowed_files: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    allowed_commands: tuple[str, ...] = ()
    allowed_networks: tuple[str, ...] = ()
    allowed_side_effects: tuple[str, ...] = ()
    requires_approval_for: tuple[str, ...] = ()
    forbidden_files: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    forbidden_commands: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    max_tokens: int | None = None
    max_usd: float | None = None
    max_tool_calls: int | None = None
    max_wall_time_seconds: int | None = None
    decomposition_allowed: bool = False
    delegated_authority: dict[str, Any] = Field(default_factory=dict)
    locked: bool = True


class EvidenceRequirement(BaseModel):
    requirement_id: str = Field(default_factory=lambda: new_id("evidence_req"))
    criterion_id: str | None = None
    evidence_class: Literal["artifact", "command_output", "schema", "llm_review", "human_acceptance", "execution_report"]
    description: str
    required: bool = True


class EvidencePlan(BaseModel):
    required_evidence: tuple[EvidenceRequirement, ...] = ()
    summary: str = ""
    required_count: int = 0

    @model_validator(mode="after")
    def fill_summary(self) -> EvidencePlan:
        required = tuple(item for item in self.required_evidence if item.required)
        self.summary = self.summary.strip() or summarize_evidence_requirements(required)
        self.required_count = len(required)
        return self


class VerificationPlan(BaseModel):
    acceptance_criteria: tuple[AcceptanceCriteria, ...]
    hard_validator_ids: tuple[str, ...] = ()
    soft_review_criteria_ids: tuple[str, ...] = ()
    final_human_acceptance_criteria_ids: tuple[str, ...] = ()
    required_artifacts: tuple[str, ...] = ()

    @classmethod
    def from_criteria(cls, criteria: list[AcceptanceCriteria], deliverables: list[str]) -> VerificationPlan:
        hard_ids = []
        llm_ids = []
        human_ids = []
        required_artifacts = list(deliverables)
        for criterion in criteria:
            if criterion.validation_type == "llm_review":
                llm_ids.append(criterion.id)
            elif criterion.validation_type == "manual":
                human_ids.append(criterion.id)
            else:
                hard_ids.append(criterion.id)
                if criterion.validation_type == "file_exists" and criterion.validation_target:
                    required_artifacts.append(criterion.validation_target)
        return cls(
            acceptance_criteria=tuple(criteria),
            hard_validator_ids=tuple(hard_ids),
            soft_review_criteria_ids=tuple(llm_ids),
            final_human_acceptance_criteria_ids=tuple(human_ids),
            required_artifacts=tuple(dict.fromkeys(item for item in required_artifacts if item)),
        )


class AcceptanceContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    criteria: tuple[AcceptanceCriteria, ...]
    verification_plan: VerificationPlan
    evidence_plan: EvidencePlan
    required_artifacts: tuple[str, ...] = ()
    accepted_limitations: tuple[str, ...] = ()
    partial_acceptance_allowed: bool = False
    locked: bool = True

    @model_validator(mode="after")
    def criteria_required(self) -> AcceptanceContract:
        if not self.criteria:
            raise ValueError("AcceptanceContract requires criteria")
        return self


class DomainProfile(BaseModel):
    profile_id: str
    name: str
    artifact_types: tuple[str, ...] = ()
    validators: tuple[str, ...] = ()
    evidence_classes: tuple[str, ...] = ()
    source_policy: tuple[str, ...] = ()
    risk_policy: tuple[str, ...] = ()
    repair_strategy: tuple[str, ...] = ()
    decomposition_strategy: tuple[str, ...] = ()
    audit_requirements: tuple[str, ...] = ()
    evidence_obligations: tuple[str, ...] = ()


class ReferenceRecord(BaseModel):
    reference_id: str = Field(default_factory=lambda: new_id("ref"))
    source_type: Literal["user_provided", "discovered", "authoritative", "assumption", "exclusion"] = "user_provided"
    title: str
    uri: str | None = None
    summary: str = ""
    freshness_required: bool = False
    provenance: dict[str, Any] = Field(default_factory=dict)
    status: EvidenceStatus = EvidenceStatus.CURRENT
    created_at: str = Field(default_factory=utc_now)


class EvidenceRecord(BaseModel):
    evidence_id: str = Field(default_factory=lambda: new_id("evidence"))
    capsule_id: str
    capsule_version: str
    evidence_class: Literal["artifact", "command_output", "schema", "llm_review", "human_acceptance", "execution_report", "review_decision"]
    producer: str
    summary: str
    uri: str | None = None
    content: str | None = None
    criterion_ids: tuple[str, ...] = ()
    status: EvidenceStatus = EvidenceStatus.CURRENT
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class AttemptRecord(BaseModel):
    attempt_id: str = Field(default_factory=lambda: new_id("attempt"))
    capsule_id: str
    capsule_version: str
    executor: str
    git_commit_ref: str = ""
    changed_files: tuple[str, ...] = ()
    validation_summary: str = ""
    result: str = ""
    lesson: str = ""
    context_snapshot_ref: str = ""
    active_permissions: dict[str, Any] = Field(default_factory=dict)
    references_used: tuple[str, ...] = ()
    actions_taken: tuple[str, ...] = ()
    artifacts_produced: tuple[str, ...] = ()
    evidence_record_ids: tuple[str, ...] = ()
    outcome: AttemptOutcome
    failure_mode: str = ""
    lessons: tuple[str, ...] = ()
    staleness_markers: tuple[str, ...] = ()
    created_at: str = Field(default_factory=utc_now)


class DecisionRecord(BaseModel):
    decision_id: str = Field(default_factory=lambda: new_id("decision"))
    capsule_id: str
    capsule_version: str
    decision_type: str
    summary: str
    made_by: str = "metaloop"
    evidence_record_ids: tuple[str, ...] = ()
    created_at: str = Field(default_factory=utc_now)


class MissionCapsule(BaseModel):
    schema_name: Literal["metaloop.mission_capsule"] = Field(default="metaloop.mission_capsule", alias="schema")
    version: str = "1.0"
    identity: CapsuleIdentity
    mission_charter: MissionCharter
    authority_contract: AuthorityContract
    acceptance_contract: AcceptanceContract
    domain_profile_id: str = "engineering_development"
    domain_profile: DomainProfile
    reference_set: tuple[ReferenceRecord, ...] = ()
    evidence_ledger: tuple[EvidenceRecord, ...] = ()
    attempt_history: tuple[AttemptRecord, ...] = ()
    decision_ledger: tuple[DecisionRecord, ...] = ()
    lifecycle_state: LifecycleState = LifecycleState.AUTHORIZED
    closure_outcome: ClosureOutcome | None = None

    @classmethod
    def from_mission(
        cls,
        mission: MissionSpec,
        *,
        created_by: str = "metaloop",
        owner: str = "user",
        domain_profile: DomainProfile | None = None,
    ) -> MissionCapsule:
        requested_profile_id = str(
            mission.context.get("domain_profile_id") or mission.context.get("domain_profile") or "engineering_development"
        )
        profile = domain_profile or default_domain_profile(requested_profile_id)
        constraints = _tuple_from_context(mission.context.get("constraints"))
        out_of_scope = _tuple_from_context(mission.context.get("out_of_scope"))
        verification_plan = VerificationPlan.from_criteria(mission.acceptance_criteria, mission.deliverables)
        evidence_plan = EvidencePlan(required_evidence=_evidence_requirements(mission.acceptance_criteria, profile))
        charter = MissionCharter(
            user_intent=mission.intent,
            desired_outcome=_desired_outcome(mission),
            explicit_non_goals=out_of_scope,
            scope_boundaries=out_of_scope,
            known_constraints=constraints,
            domain_profile_id=profile.profile_id,
        )
        authority = AuthorityContract(
            authorized_by=owner,
            workspace_root=mission.policy.workspace_root,
            allowed_tools=tuple(mission.policy.allowed_tools),
            forbidden_tools=tuple(mission.policy.denied_tools),
            requires_approval_for=tuple(mission.policy.requires_human_auth_for),
            forbidden_actions=_forbidden_actions(out_of_scope),
            max_tokens=mission.budget.max_tokens,
            max_usd=mission.budget.max_usd,
            max_tool_calls=mission.budget.max_tool_calls,
            max_wall_time_seconds=mission.budget.max_wall_time_seconds,
        )
        acceptance = AcceptanceContract(
            criteria=tuple(mission.acceptance_criteria),
            verification_plan=verification_plan,
            evidence_plan=evidence_plan,
            required_artifacts=verification_plan.required_artifacts,
        )
        return cls(
            identity=CapsuleIdentity(capsule_id=mission.run_id, created_by=created_by, owner=owner),
            mission_charter=charter,
            authority_contract=authority,
            acceptance_contract=acceptance,
            domain_profile_id=profile.profile_id,
            domain_profile=profile,
            lifecycle_state=LifecycleState.AUTHORIZED if mission.locked else LifecycleState.PROPOSED,
        ).authorize("Compiled from MissionSpec for goal runtime.") if not mission.locked else cls(
            identity=CapsuleIdentity(capsule_id=mission.run_id, created_by=created_by, owner=owner),
            mission_charter=charter,
            authority_contract=authority,
            acceptance_contract=acceptance,
            domain_profile_id=profile.profile_id,
            domain_profile=profile,
            lifecycle_state=LifecycleState.AUTHORIZED,
        )

    def authorize(self, summary: str = "Mission authorized.") -> MissionCapsule:
        if self.lifecycle_state == LifecycleState.AUTHORIZED:
            return self
        updated = self.transition(LifecycleState.AUTHORIZED, summary=summary)
        return updated

    def transition(
        self,
        state: LifecycleState,
        *,
        closure_outcome: ClosureOutcome | None = None,
        summary: str = "",
        evidence_record_ids: tuple[str, ...] = (),
    ) -> MissionCapsule:
        if not _transition_allowed(self.lifecycle_state, state, closure_outcome):
            outcome = f"({closure_outcome.value})" if closure_outcome is not None else ""
            raise ValueError(f"Illegal lifecycle transition: {self.lifecycle_state.value} -> {state.value}{outcome}")
        if state == LifecycleState.CLOSED and closure_outcome is None:
            raise ValueError("Closing a MissionCapsule requires closure_outcome")
        if state != LifecycleState.CLOSED and closure_outcome is not None:
            raise ValueError("closure_outcome can only be set when lifecycle_state is closed")
        decision = DecisionRecord(
            capsule_id=self.identity.capsule_id,
            capsule_version=self.identity.capsule_version,
            decision_type="lifecycle_transition",
            summary=summary or f"{self.lifecycle_state.value} -> {state.value}",
            evidence_record_ids=evidence_record_ids,
        )
        return self.model_copy(
            update={
                "lifecycle_state": state,
                "closure_outcome": closure_outcome,
                "decision_ledger": (*self.decision_ledger, decision),
            }
        )

    def with_evidence(self, evidence: EvidenceRecord) -> MissionCapsule:
        _assert_record_binding(self, evidence.capsule_id, evidence.capsule_version)
        return self.model_copy(update={"evidence_ledger": (*self.evidence_ledger, evidence)})

    def with_attempt(self, attempt: AttemptRecord) -> MissionCapsule:
        _assert_record_binding(self, attempt.capsule_id, attempt.capsule_version)
        return self.model_copy(update={"attempt_history": (*self.attempt_history, attempt)})

    def with_reference(self, reference: ReferenceRecord) -> MissionCapsule:
        return self.model_copy(update={"reference_set": (*self.reference_set, reference)})

    def expand_permissions(
        self,
        *,
        allowed_tools: tuple[str, ...] = (),
        allowed_commands: tuple[str, ...] = (),
        allowed_networks: tuple[str, ...] = (),
        allowed_side_effects: tuple[str, ...] = (),
        summary: str,
    ) -> MissionCapsule:
        if not summary.strip():
            raise ValueError("Permission expansion requires a decision summary")
        authority = self.authority_contract.model_copy(
            update={
                "allowed_tools": _union_tuple(self.authority_contract.allowed_tools, allowed_tools),
                "allowed_commands": _union_tuple(self.authority_contract.allowed_commands, allowed_commands),
                "allowed_networks": _union_tuple(self.authority_contract.allowed_networks, allowed_networks),
                "allowed_side_effects": _union_tuple(self.authority_contract.allowed_side_effects, allowed_side_effects),
            }
        )
        decision = DecisionRecord(
            capsule_id=self.identity.capsule_id,
            capsule_version=self.identity.capsule_version,
            decision_type="authority_update",
            summary=summary,
        )
        return self.model_copy(
            update={
                "authority_contract": authority,
                "decision_ledger": (*self.decision_ledger, decision),
            }
        )

    def revise(
        self,
        *,
        mission_charter: MissionCharter | None = None,
        authority_contract: AuthorityContract | None = None,
        acceptance_contract: AcceptanceContract | None = None,
        summary: str,
    ) -> MissionCapsule:
        if not summary.strip():
            raise ValueError("Capsule revision requires a decision summary")
        next_version = _next_minor_version(self.identity.capsule_version)
        identity = self.identity.model_copy(update={"capsule_version": next_version})
        decision = DecisionRecord(
            capsule_id=identity.capsule_id,
            capsule_version=next_version,
            decision_type="capsule_revision",
            summary=summary,
        )
        return self.model_copy(
            update={
                "identity": identity,
                "mission_charter": mission_charter or self.mission_charter,
                "authority_contract": authority_contract or self.authority_contract,
                "acceptance_contract": acceptance_contract or self.acceptance_contract,
                "decision_ledger": (*self.decision_ledger, decision),
                "lifecycle_state": LifecycleState.PROPOSED,
                "closure_outcome": None,
            }
        )


def default_domain_profile(profile_id: str) -> DomainProfile:
    if profile_id == "algorithm_research":
        return DomainProfile(
            profile_id=profile_id,
            name="Algorithm Research",
            artifact_types=("analysis", "prototype", "benchmark", "report"),
            validators=("command", "schema", "llm_review"),
            evidence_classes=("experiment_result", "benchmark_output", "source_reference", "review_decision"),
            source_policy=("record assumptions", "cite authoritative references when used"),
            risk_policy=("mark uncertainty explicitly",),
            repair_strategy=("rerun failed benchmarks", "revise assumptions through explicit redesign"),
            decomposition_strategy=("split by hypothesis or experiment only when authorized",),
            audit_requirements=("preserve experiment commands and outputs",),
            evidence_obligations=("assumptions", "method", "experiment or benchmark evidence", "limitations"),
        )
    if profile_id == "codex_skill_creation":
        return DomainProfile(
            profile_id=profile_id,
            name="Codex Skill Creation",
            artifact_types=("SKILL.md", "scripts", "references", "assets"),
            validators=("file_exists", "file_contains", "command"),
            evidence_classes=("artifact", "command_output", "review_decision"),
            source_policy=("prefer local skill instructions",),
            risk_policy=("avoid leaking secrets into skill content",),
            repair_strategy=("validate folder structure and referenced scripts",),
            decomposition_strategy=("split examples, scripts, and documentation when authorized",),
            audit_requirements=("record changed files and validation commands",),
            evidence_obligations=("SKILL.md", "usage example", "validation checklist"),
        )
    if profile_id == "deep_research":
        return DomainProfile(
            profile_id=profile_id,
            name="Deep Research",
            artifact_types=("brief", "source_table", "report"),
            validators=("schema", "llm_review", "manual"),
            evidence_classes=("source_reference", "quote", "synthesis", "review_decision"),
            source_policy=("freshness metadata required for time-sensitive claims", "prefer primary sources"),
            risk_policy=("separate evidence from inference",),
            repair_strategy=("refresh stale sources", "replace unsupported claims"),
            decomposition_strategy=("split by research question only when authorized",),
            audit_requirements=("record provenance and freshness for cited sources",),
            evidence_obligations=("source table", "citation/provenance", "freshness", "claim support"),
        )
    return DomainProfile(
        profile_id="engineering_development",
        name="Engineering Development",
        artifact_types=("code", "test", "documentation", "configuration"),
        validators=("file_exists", "file_contains", "command", "schema"),
        evidence_classes=("artifact", "command_output", "execution_report", "review_decision"),
        source_policy=("prefer repository-local source of truth", "use official documentation for time-sensitive APIs"),
        risk_policy=("do not exfiltrate secrets", "do not weaken acceptance criteria"),
        repair_strategy=("fix failed validators before soft review", "keep repair scoped to the authorized contract"),
        decomposition_strategy=("do not create child capsules unless explicitly authorized",),
        audit_requirements=("record changed files", "record commands run", "record verification result"),
        evidence_obligations=(
            "changed files",
            "build/test/lint evidence when applicable",
            "regression test evidence for bugfix or public behavior changes",
        ),
    )


_LEGAL_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.DRAFT: {LifecycleState.PROPOSED, LifecycleState.CLOSED},
    LifecycleState.PROPOSED: {LifecycleState.DRAFT, LifecycleState.AUTHORIZED, LifecycleState.CLOSED},
    LifecycleState.AUTHORIZED: {LifecycleState.IN_PROGRESS, LifecycleState.BLOCKED, LifecycleState.CLOSED},
    LifecycleState.IN_PROGRESS: {
        LifecycleState.REVIEW_READY,
        LifecycleState.BLOCKED,
        LifecycleState.REPAIRING,
        LifecycleState.REDESIGN_REQUIRED,
        LifecycleState.WAITING_ON_CHILDREN,
        LifecycleState.CLOSED,
    },
    LifecycleState.BLOCKED: {
        LifecycleState.AUTHORIZED,
        LifecycleState.IN_PROGRESS,
        LifecycleState.REDESIGN_REQUIRED,
        LifecycleState.CLOSED,
    },
    LifecycleState.REVIEW_READY: {
        LifecycleState.CLOSED,
        LifecycleState.REPAIRING,
        LifecycleState.REDESIGN_REQUIRED,
        LifecycleState.WAITING_ON_CHILDREN,
    },
    LifecycleState.REPAIRING: {
        LifecycleState.IN_PROGRESS,
        LifecycleState.REVIEW_READY,
        LifecycleState.BLOCKED,
        LifecycleState.REDESIGN_REQUIRED,
        LifecycleState.CLOSED,
    },
    LifecycleState.REDESIGN_REQUIRED: {
        LifecycleState.PROPOSED,
        LifecycleState.AUTHORIZED,
        LifecycleState.WAITING_ON_CHILDREN,
        LifecycleState.CLOSED,
    },
    LifecycleState.WAITING_ON_CHILDREN: {
        LifecycleState.REVIEW_READY,
        LifecycleState.BLOCKED,
        LifecycleState.REDESIGN_REQUIRED,
        LifecycleState.CLOSED,
    },
    LifecycleState.CLOSED: {LifecycleState.ARCHIVED},
    LifecycleState.ARCHIVED: set(),
}

_CLOSURE_OUTCOMES_BY_STATE: dict[LifecycleState, set[ClosureOutcome]] = {
    LifecycleState.DRAFT: {ClosureOutcome.CANCELLED},
    LifecycleState.PROPOSED: {ClosureOutcome.CANCELLED},
    LifecycleState.AUTHORIZED: {ClosureOutcome.CANCELLED},
    LifecycleState.IN_PROGRESS: {ClosureOutcome.CANCELLED, ClosureOutcome.FAILED, ClosureOutcome.SUPERSEDED},
    LifecycleState.BLOCKED: {ClosureOutcome.CANCELLED, ClosureOutcome.FAILED},
    LifecycleState.REVIEW_READY: {
        ClosureOutcome.ACCEPTED,
        ClosureOutcome.ACCEPTED_WITH_LIMITATIONS,
        ClosureOutcome.ACCEPTED_PENDING_HUMAN,
        ClosureOutcome.REJECTED,
        ClosureOutcome.FAILED,
    },
    LifecycleState.REPAIRING: {ClosureOutcome.FAILED, ClosureOutcome.CANCELLED},
    LifecycleState.REDESIGN_REQUIRED: {ClosureOutcome.CANCELLED, ClosureOutcome.SUPERSEDED},
    LifecycleState.WAITING_ON_CHILDREN: {ClosureOutcome.DECOMPOSED, ClosureOutcome.FAILED, ClosureOutcome.CANCELLED},
}


def _transition_allowed(
    current: LifecycleState,
    target: LifecycleState,
    outcome: ClosureOutcome | None,
) -> bool:
    if target not in _LEGAL_TRANSITIONS[current]:
        return False
    if target != LifecycleState.CLOSED:
        return outcome is None
    if outcome is None:
        return False
    return outcome in _CLOSURE_OUTCOMES_BY_STATE.get(current, set())


def _tuple_from_context(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return ()


def _desired_outcome(mission: MissionSpec) -> str:
    parts = []
    if mission.deliverables:
        parts.append("Deliverables: " + "; ".join(mission.deliverables))
    if mission.acceptance_criteria:
        parts.append("Acceptance: " + "; ".join(item.description for item in mission.acceptance_criteria))
    return "\n".join(parts)


def summarize_evidence_requirements(requirements: tuple[EvidenceRequirement, ...] | list[EvidenceRequirement]) -> str:
    required = [item for item in requirements if item.required]
    if not required:
        return "No required evidence."
    counts: dict[str, int] = {}
    for item in required:
        counts[item.evidence_class] = counts.get(item.evidence_class, 0) + 1
    parts = [f"{count} {evidence_class}" for evidence_class, count in sorted(counts.items())]
    return f"{len(required)} required evidence item(s): " + ", ".join(parts)


def _evidence_requirements(
    criteria: list[AcceptanceCriteria],
    profile: DomainProfile | None = None,
) -> tuple[EvidenceRequirement, ...]:
    requirements = [
        EvidenceRequirement(
            criterion_id=criterion.id,
            evidence_class=_evidence_class_for_criterion(criterion),
            description=_evidence_description_for_criterion(criterion, profile),
            required=criterion.required,
        )
        for criterion in criteria
    ]
    requirements.append(
        EvidenceRequirement(
            evidence_class="execution_report",
            description="Executor must write the MetaLoop ExecutionReport.",
            required=True,
        )
    )
    requirements.extend(_profile_evidence_obligations(profile))
    return tuple(requirements)


def _profile_evidence_obligations(profile: DomainProfile | None) -> list[EvidenceRequirement]:
    if profile is None:
        return []
    evidence_class = "execution_report"
    if profile.profile_id == "engineering_development":
        descriptions = (
            "Record changed files in the ExecutionReport.",
            "Record build/test/lint evidence when applicable.",
            "Record regression test evidence for bugfix or public behavior changes.",
        )
    elif profile.profile_id == "algorithm_research":
        descriptions = (
            "Record assumptions.",
            "Record method.",
            "Record experiment or benchmark evidence when applicable.",
            "Record limitations.",
        )
    elif profile.profile_id == "codex_skill_creation":
        descriptions = (
            "Record SKILL.md as the main skill artifact.",
            "Record a usage example.",
            "Record a validation checklist.",
        )
    elif profile.profile_id == "deep_research":
        descriptions = (
            "Record a source table.",
            "Record citation/provenance.",
            "Record freshness for time-sensitive claims.",
            "Record claim support.",
        )
    else:
        descriptions = tuple(profile.evidence_obligations)
    return [
        EvidenceRequirement(
            evidence_class=evidence_class,
            description=description,
            required=False,
        )
        for description in descriptions
    ]


def _evidence_class_for_criterion(criterion: AcceptanceCriteria) -> str:
    if criterion.validation_type == "command":
        return "command_output"
    if criterion.validation_type == "schema":
        return "schema"
    if criterion.validation_type == "llm_review":
        return "llm_review"
    if criterion.validation_type == "manual":
        return "human_acceptance"
    return "artifact"


def _evidence_description_for_criterion(
    criterion: AcceptanceCriteria,
    profile: DomainProfile | None,
) -> str:
    suffix = ""
    if criterion.validation_target:
        suffix = f" Target: {criterion.validation_target}."
    profile_hint = ""
    if profile is not None and profile.audit_requirements:
        profile_hint = " Audit hint: " + "; ".join(profile.audit_requirements[:2]) + "."
    return f"{criterion.description}.{suffix}{profile_hint}".strip()


def _forbidden_actions(out_of_scope: tuple[str, ...]) -> tuple[str, ...]:
    return (
        "do not weaken acceptance criteria",
        "do not treat executor completion as MetaLoop verified completion",
        *out_of_scope,
    )


def _assert_record_binding(capsule: MissionCapsule, capsule_id: str, capsule_version: str) -> None:
    if capsule_id != capsule.identity.capsule_id:
        raise ValueError(f"record capsule_id mismatch: expected {capsule.identity.capsule_id}, got {capsule_id}")
    if capsule_version != capsule.identity.capsule_version:
        raise ValueError(
            f"record capsule_version mismatch: expected {capsule.identity.capsule_version}, got {capsule_version}"
        )


def _union_tuple(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*left, *right)))


def _next_minor_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        return f"{parts[0]}.{int(parts[1]) + 1}"
    return f"{version}.1"
