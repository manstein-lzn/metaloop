from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from metaloop.codex_adapter import CodexExecAdapter, CodexExecOptions
from metaloop.goal import compile_goal_contract, compile_mission_capsule
from metaloop.path_targets import is_valid_path_validation_target, normalize_path_validation_target
from metaloop.prompt_pack import PromptPackError, render_prompt
from metaloop.schemas import AcceptanceCriteria, Budget, MissionSpec, PolicyScope, RiskLevel, utc_now


ValidationType = Literal["manual", "file_exists", "file_contains", "command", "schema", "llm_review"]


class CoDesignQuestion(BaseModel):
    question_id: str
    prompt: str
    required: bool = True
    help_text: str = ""
    reason: str = ""
    options: list[str] = Field(default_factory=list)


class CoDesignCriterionDraft(BaseModel):
    description: str
    validation_type: ValidationType = "manual"
    validation_target: str | None = None
    required: bool = True


class CoDesignDraft(BaseModel):
    intent: str = ""
    audience: str = ""
    background: str = ""
    deliverables: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    criteria: list[CoDesignCriterionDraft] = Field(default_factory=list)
    workspace_root: str = "."
    risk_level: RiskLevel = RiskLevel.MEDIUM
    max_tokens: int | None = None
    max_usd: float = 2.0
    domain_profile_id: str | None = None


class MissionSpecReviewFinding(BaseModel):
    severity: Literal["blocking", "warning", "info"]
    code: str
    message: str
    recommendation: str = ""


class MissionSpecReview(BaseModel):
    passed: bool
    findings: list[MissionSpecReviewFinding] = Field(default_factory=list)

    @property
    def blocking_findings(self) -> list[MissionSpecReviewFinding]:
        return [finding for finding in self.findings if finding.severity == "blocking"]


class CoDesignInterviewerResult(BaseModel):
    questions: list[CoDesignQuestion] = Field(default_factory=list)
    draft_patch: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class CoDesignAnswer(BaseModel):
    answer: str = ""
    draft_patch: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class CoDesignAgentError(ValueError):
    """Raised when a selected LLM co-design agent cannot produce usable output."""


class CoDesignLockError(ValueError):
    """Raised when a MissionSpec is not safe to lock."""


class CoDesignRound(BaseModel):
    round_index: int
    questions: list[CoDesignQuestion] = Field(default_factory=list)
    answers: dict[str, str] = Field(default_factory=dict)
    draft_patch: dict[str, Any] = Field(default_factory=dict)
    review: MissionSpecReview | None = None
    notes: list[str] = Field(default_factory=list)


class CoDesignRunResult(BaseModel):
    mission: MissionSpec
    review: MissionSpecReview
    rounds: list[CoDesignRound] = Field(default_factory=list)
    converged: bool = False


class CoDesignOption(BaseModel):
    title: str
    summary: str
    tradeoffs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class CoDesignBrainstorm(BaseModel):
    options: list[CoDesignOption] = Field(default_factory=list)
    recommended_option: str = ""
    mvp: list[str] = Field(default_factory=list)
    v1: list[str] = Field(default_factory=list)
    later: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    overlooked_points: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    notes: str = ""


class CoDesignDecision(BaseModel):
    decision_id: str
    status: Literal["accepted", "rejected", "open"] = "open"
    summary: str
    rationale: str = ""
    source: str = "human_review"
    created_at: str = Field(default_factory=utc_now)


class CoDesignLock(BaseModel):
    schema_name: Literal["metaloop.co_design_lock"] = Field(default="metaloop.co_design_lock", alias="schema")
    version: str = "2.0"
    locked_at: str = Field(default_factory=utc_now)
    approved: bool = True
    approval_source: str = "human"
    mission_id: str
    design_version: str = "co-design-v2"
    decision_count: int = 0
    unresolved_questions: list[str] = Field(default_factory=list)
    mission_path: str | None = None
    capsule_path: str | None = None
    goal_contract_path: str | None = None


class CoDesignPatchMode(str):
    SAFE = "safe"
    AUTONOMOUS = "autonomous"


class CoDesignInterviewer(Protocol):
    def interview(self, draft: CoDesignDraft) -> CoDesignInterviewerResult:
        ...


class CoDesignAnswerProvider(Protocol):
    def answer(
        self,
        question: CoDesignQuestion,
        draft: CoDesignDraft,
        review: MissionSpecReview | None = None,
    ) -> CoDesignAnswer:
        ...


class CoDesignBrainstormer(Protocol):
    def expand(
        self,
        mission: MissionSpec,
        draft: CoDesignDraft,
        review: MissionSpecReview,
    ) -> CoDesignBrainstorm:
        ...


DEFAULT_QUESTIONS = [
    CoDesignQuestion(
        question_id="intent",
        prompt="What should this MetaLoop run accomplish?",
        help_text="Describe the task in one concrete sentence.",
    ),
    CoDesignQuestion(
        question_id="deliverables",
        prompt="What concrete deliverables should exist when the run is done?",
        help_text="Separate multiple deliverables with semicolons.",
    ),
    CoDesignQuestion(
        question_id="criteria",
        prompt="How should MetaLoop know the work is accepted?",
        help_text="Separate multiple criteria with semicolons.",
    ),
    CoDesignQuestion(
        question_id="audience",
        prompt="Who is the result for?",
        required=False,
    ),
    CoDesignQuestion(
        question_id="constraints",
        prompt="What constraints, preferences, or boundaries must the worker respect?",
        required=False,
        help_text="Separate multiple constraints with semicolons.",
    ),
]


class CoDesignSession:
    def __init__(self, draft: CoDesignDraft | None = None) -> None:
        self.draft = draft or CoDesignDraft()

    def missing_questions(self) -> list[CoDesignQuestion]:
        missing = []
        if not self.draft.intent.strip():
            missing.append(_question("intent"))
        if not self.draft.deliverables and not _can_infer_deliverables_from_intent(self.draft.intent):
            missing.append(_question("deliverables"))
        if not self.draft.criteria and not _can_infer_criteria_from_intent(self.draft.intent, self.draft.deliverables):
            missing.append(_question("criteria"))
        if not self.draft.audience.strip():
            missing.append(_question("audience"))
        if not self.draft.constraints:
            missing.append(_question("constraints"))
        return missing

    def required_missing_questions(self) -> list[CoDesignQuestion]:
        return [question for question in self.missing_questions() if question.required]

    def deep_questions(self) -> list[CoDesignQuestion]:
        return RuleCoDesignInterviewer().interview(self.draft).questions

    def apply_patch(self, patch: dict[str, Any], *, allow_core_edits: bool = True) -> None:
        if not patch:
            return
        if allow_core_edits and isinstance(patch.get("intent"), str) and patch["intent"].strip():
            self.draft.intent = patch["intent"].strip()
        if isinstance(patch.get("audience"), str) and patch["audience"].strip():
            self.draft.audience = patch["audience"].strip()
        if isinstance(patch.get("background"), str) and patch["background"].strip():
            self.draft.background = patch["background"].strip()
        if isinstance(patch.get("domain_profile_id"), str) and patch["domain_profile_id"].strip():
            self.draft.domain_profile_id = patch["domain_profile_id"].strip()
        if allow_core_edits and "deliverables" in patch:
            self.draft.deliverables = _coerce_string_list(patch["deliverables"])
        if "constraints" in patch:
            self.draft.constraints = _coerce_string_list(patch["constraints"])
        if "out_of_scope" in patch:
            self.draft.out_of_scope = _coerce_string_list(patch["out_of_scope"])
        if allow_core_edits and "criteria" in patch:
            criteria = _coerce_criteria_list(patch["criteria"])
            if criteria:
                self.draft.criteria = criteria

    def answer(self, question_id: str, value: str) -> None:
        value = value.strip()
        if not value:
            return
        if question_id == "intent":
            self.draft.intent = value
        elif question_id == "deliverables":
            self.draft.deliverables = _split_list(value)
        elif question_id == "criteria":
            self.draft.criteria = [CoDesignCriterionDraft(description=item) for item in _split_list(value)]
        elif question_id == "file_exists":
            self.draft.criteria.extend(
                CoDesignCriterionDraft(
                    description=f"{item} exists",
                    validation_type="file_exists",
                    validation_target=item,
                )
                for item in _split_list(value)
            )
        elif question_id == "file_contains":
            self.draft.criteria.extend(_file_contains_criteria_from_answer(value))
        elif question_id == "audience":
            self.draft.audience = value
        elif question_id == "constraints":
            self.draft.constraints = _split_list(value)
        elif question_id == "out_of_scope":
            self.draft.out_of_scope = _split_list(value)
        elif question_id == "domain_profile_id":
            self.draft.domain_profile_id = value
        else:
            raise ValueError(f"Unknown Co-Design question: {question_id}")

    def build_mission(self) -> MissionSpec:
        missing = self.required_missing_questions()
        if missing:
            question_ids = ", ".join(question.question_id for question in missing)
            raise ValueError(f"Co-Design draft is incomplete; missing: {question_ids}")

        domain_profile_id = self.draft.domain_profile_id or _infer_domain_profile_id(
            self.draft.intent,
            self.draft.deliverables,
            self.draft.criteria,
            self.draft.background,
        )
        deliverables = _apply_domain_profile_deliverables(
            domain_profile_id,
            self.draft.intent,
            _normalize_deliverables(self.draft.intent, self.draft.deliverables),
        )
        criteria = _apply_domain_profile_criteria(
            domain_profile_id,
            self.draft.intent,
            deliverables,
            _normalize_and_infer_criteria(self.draft.intent, deliverables, self.draft.criteria),
        )
        context: dict[str, Any] = {}
        if self.draft.audience:
            context["audience"] = self.draft.audience
        if self.draft.background:
            context["background"] = self.draft.background
        if self.draft.constraints:
            context["constraints"] = self.draft.constraints
        if self.draft.out_of_scope:
            context["out_of_scope"] = self.draft.out_of_scope
        if domain_profile_id:
            context["domain_profile_id"] = domain_profile_id
            context["evidence_hints"] = _domain_profile_evidence_hints(domain_profile_id)
        context["co_design"] = {
            "version": "2.0",
            "source": "metaloop design",
            "stages": [
                "requirement_discovery",
                "brainstorm_expansion",
                "human_design_review",
                "interactive_refinement",
                "contract_lock",
            ],
        }

        return MissionSpec(
            intent=self.draft.intent,
            context=context,
            deliverables=deliverables,
            acceptance_criteria=[
                AcceptanceCriteria(
                    description=criterion.description,
                    validation_type=criterion.validation_type,
                    validation_target=criterion.validation_target,
                    required=criterion.required,
                )
                for criterion in criteria
            ],
            budget=Budget(max_tokens=self.draft.max_tokens, max_usd=self.draft.max_usd),
            policy=PolicyScope(workspace_root=self.draft.workspace_root, risk_level=self.draft.risk_level),
        )


class CoDesignRunner:
    def __init__(
        self,
        interviewer: CoDesignInterviewer,
        answer_provider: CoDesignAnswerProvider | None = None,
        *,
        reviewer: MissionSpecReviewer | None = None,
        max_rounds: int = 8,
        max_questions_per_round: int = 3,
        allow_core_edits: bool = False,
        require_clean_review: bool = True,
        on_status: Callable[[str], None] | None = None,
        on_checkpoint: Callable[[CoDesignDraft, list[CoDesignRound]], None] | None = None,
        initial_rounds: list[CoDesignRound] | None = None,
    ) -> None:
        self.interviewer = interviewer
        self.answer_provider = answer_provider
        self.reviewer = reviewer or MissionSpecReviewer()
        self.max_rounds = max_rounds
        self.max_questions_per_round = max_questions_per_round
        self.allow_core_edits = allow_core_edits
        self.require_clean_review = require_clean_review
        self.on_status = on_status
        self.on_checkpoint = on_checkpoint
        self.initial_rounds = initial_rounds or []

    def run(self, draft: CoDesignDraft) -> CoDesignRunResult:
        session = CoDesignSession(draft)
        rounds: list[CoDesignRound] = list(self.initial_rounds)
        last_review: MissionSpecReview | None = None
        last_mission: MissionSpec | None = None

        for round_index in range(len(rounds) + 1, self.max_rounds + 1):
            self._status(f"Co-Design round {round_index}: interviewer is analyzing the current draft...")
            round_record = CoDesignRound(round_index=round_index)
            missing_questions = session.required_missing_questions()
            interviewer_result = self.interviewer.interview(session.draft)
            self._status(f"Co-Design round {round_index}: applying interviewer suggestions...")
            round_record.notes.extend(_notes_from_interviewer(interviewer_result))
            session.apply_patch(interviewer_result.draft_patch, allow_core_edits=self.allow_core_edits)
            round_record.draft_patch = interviewer_result.draft_patch

            self._status(f"Co-Design round {round_index}: reviewer is checking MissionSpec quality...")
            mission, review = _try_review_session(session, self.reviewer)
            if review is not None:
                last_mission = mission
                last_review = review
                round_record.review = review
                if _review_converged(review, require_clean=self.require_clean_review):
                    rounds.append(round_record)
                    self._checkpoint(session.draft, rounds)
                    return CoDesignRunResult(mission=mission, review=review, rounds=rounds, converged=True)

            questions = _select_next_questions(
                session,
                last_review,
                [*interviewer_result.questions, *missing_questions],
                limit=self.max_questions_per_round,
            )
            round_record.questions = questions
            if not questions:
                rounds.append(round_record)
                self._checkpoint(session.draft, rounds)
                break
            if self.answer_provider is None:
                rounds.append(round_record)
                self._checkpoint(session.draft, rounds)
                break

            for question in questions:
                self._status(f"Co-Design round {round_index}: waiting for answer to {_question_title_for_status(question.question_id)}...")
                answer = self.answer_provider.answer(question, session.draft, last_review)
                self._status(f"Co-Design round {round_index}: applying answer and updating draft...")
                if answer.notes:
                    round_record.notes.append(answer.notes)
                if answer.draft_patch:
                    session.apply_patch(answer.draft_patch, allow_core_edits=self.allow_core_edits)
                    round_record.draft_patch = _merge_patch(round_record.draft_patch, answer.draft_patch)
                elif answer.answer:
                    session.answer(question.question_id, answer.answer)
                    round_record.answers[question.question_id] = answer.answer
                self._checkpoint(session.draft, [*rounds, round_record])
            rounds.append(round_record)
            self._checkpoint(session.draft, rounds)

        if last_mission is None:
            last_mission = session.build_mission()
            last_review = self.reviewer.review(last_mission)
        final_review = last_review or self.reviewer.review(last_mission)
        return CoDesignRunResult(
            mission=last_mission,
            review=final_review,
            rounds=rounds,
            converged=_review_converged(final_review, require_clean=self.require_clean_review),
        )

    def _status(self, message: str) -> None:
        if self.on_status is not None:
            self.on_status(message)

    def _checkpoint(self, draft: CoDesignDraft, rounds: list[CoDesignRound]) -> None:
        if self.on_checkpoint is not None:
            self.on_checkpoint(draft, rounds)


class InteractiveAnswerProvider:
    def __init__(self, ui: Any | None = None) -> None:
        self.ui = ui

    def answer(
        self,
        question: CoDesignQuestion,
        _draft: CoDesignDraft,
        _review: MissionSpecReview | None = None,
    ) -> CoDesignAnswer:
        if self.ui is not None:
            return CoDesignAnswer(answer=self.ui.ask_question(question))
        suffix_parts = []
        if question.reason:
            suffix_parts.append(question.reason)
        if question.help_text:
            suffix_parts.append(question.help_text)
        suffix = f" ({' '.join(suffix_parts)})" if suffix_parts else ""
        if question.options:
            print(f"{question.prompt}{suffix}")
            for index, option in enumerate(question.options, start=1):
                print(f"{index}. {option}")
            other_index = len(question.options) + 1
            print(f"{other_index}. Other / 手动输入")
            value = input("> ").strip()
            if value.isdigit():
                selected = int(value)
                if 1 <= selected <= len(question.options):
                    return CoDesignAnswer(answer=question.options[selected - 1])
                if selected == other_index:
                    return CoDesignAnswer(answer=input("请输入你的想法：\n> "))
            if value:
                return CoDesignAnswer(answer=value)
            return CoDesignAnswer(answer=question.options[0])
        return CoDesignAnswer(answer=input(f"{question.prompt}{suffix}\n> "))


class CodexCoDesignAnswerProvider:
    def __init__(self, options: CodexExecOptions | None = None) -> None:
        self.options = options or CodexExecOptions(
            sandbox="read-only",
            approval_policy="never",
            timeout_seconds=180,
            use_output_schema=False,
        )

    def answer(
        self,
        question: CoDesignQuestion,
        draft: CoDesignDraft,
        review: MissionSpecReview | None = None,
    ) -> CoDesignAnswer:
        result = CodexExecAdapter(self.options).run(_build_codex_answer_prompt(question, draft, review))
        if result.returncode != 0 or not result.final_message:
            raise CoDesignAgentError(f"codex answer unavailable: {result.stderr or 'no final message'}")
        try:
            payload = json.loads(result.final_message)
        except json.JSONDecodeError as exc:
            raise CoDesignAgentError(f"codex answer returned invalid JSON: {exc}") from exc
        return _normalize_answer_result(payload, draft=draft)


class RuleCoDesignInterviewer:
    def interview(self, draft: CoDesignDraft) -> CoDesignInterviewerResult:
        questions = []
        intent = draft.intent.strip().lower()
        inferred_domain_profile_id = _infer_domain_profile_id(
            draft.intent,
            draft.deliverables,
            draft.criteria,
            draft.background,
        )
        if intent and (_is_vague_text(intent) or len(intent.split()) < 4):
            questions.append(
                CoDesignQuestion(
                    question_id="intent",
                    prompt="Please restate the task as a concrete outcome with the object, action, and finish line.",
                    reason="Intent is too vague for reliable planning.",
                )
            )
        if any(_is_vague_text(deliverable) for deliverable in draft.deliverables):
            questions.append(
                CoDesignQuestion(
                    question_id="deliverables",
                    prompt="Please name the concrete files, reports, commands, or artifacts that should be produced.",
                    reason="At least one deliverable is generic.",
                )
            )
        if draft.deliverables and not draft.criteria:
            questions.append(
                CoDesignQuestion(
                    question_id="criteria",
                    prompt="Please define acceptance criteria that prove each deliverable is complete.",
                    reason="Deliverables exist but no acceptance criteria were provided.",
                )
            )
        if _looks_file_based(draft.deliverables) and not _has_executable_criterion(draft.criteria):
            questions.append(
                CoDesignQuestion(
                    question_id="file_exists",
                    prompt="This looks file-based. Which files should MetaLoop require to exist?",
                    reason="File-like deliverables are easier to verify with executable criteria.",
                    required=False,
                )
            )
        if inferred_domain_profile_id and not draft.domain_profile_id:
            questions.append(
                CoDesignQuestion(
                    question_id="domain_profile_id",
                    prompt="Which domain profile best fits this mission?",
                    reason=f"The task looks like {inferred_domain_profile_id}.",
                    required=False,
                    options=[
                        inferred_domain_profile_id,
                        "engineering_development",
                        "deep_research",
                    ],
                )
            )
        if draft.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL} and not draft.constraints:
            questions.append(
                CoDesignQuestion(
                    question_id="constraints",
                    prompt="This is high risk. What explicit constraints or safety boundaries should the worker follow?",
                    reason="High-risk missions need explicit operational boundaries.",
                )
            )
        if draft.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL} and not draft.out_of_scope:
            questions.append(
                CoDesignQuestion(
                    question_id="out_of_scope",
                    prompt="What is explicitly out of scope for this run?",
                    reason="High-risk missions need explicit non-goals.",
                    required=False,
                )
            )
        return CoDesignInterviewerResult(questions=_dedupe_questions(questions))


class CodexCoDesignInterviewer:
    def __init__(self, options: CodexExecOptions | None = None, *, autonomous: bool = False) -> None:
        self.options = options or CodexExecOptions(
            sandbox="read-only",
            approval_policy="never",
            timeout_seconds=180,
            use_output_schema=False,
        )
        self.autonomous = autonomous

    def interview(self, draft: CoDesignDraft) -> CoDesignInterviewerResult:
        result = CodexExecAdapter(self.options).run(_build_codex_interviewer_prompt(draft, autonomous=self.autonomous))
        if result.returncode != 0 or not result.final_message:
            raise CoDesignAgentError(f"codex interviewer unavailable: {result.stderr or 'no final message'}")
        try:
            payload = json.loads(result.final_message)
            return _normalize_interviewer_result(payload, autonomous=self.autonomous, draft=draft)
        except Exception as exc:
            raise CoDesignAgentError(f"codex interviewer returned invalid output: {exc}") from exc


class RuleCoDesignBrainstormer:
    def expand(
        self,
        mission: MissionSpec,
        _draft: CoDesignDraft,
        review: MissionSpecReview,
    ) -> CoDesignBrainstorm:
        domain_profile_id = str(mission.context.get("domain_profile_id") or "")
        file_deliverables = [item for item in mission.deliverables if _looks_like_file_path(item)]
        hard_criteria = [
            criterion
            for criterion in mission.acceptance_criteria
            if criterion.validation_type in {"file_exists", "file_contains", "schema", "command"}
        ]
        soft_criteria = [
            criterion
            for criterion in mission.acceptance_criteria
            if criterion.validation_type in {"manual", "llm_review"}
        ]
        options = [
            CoDesignOption(
                title="MVP: execute the locked deliverables directly",
                summary="Keep the first run focused on the current deliverables and acceptance checks.",
                tradeoffs=[
                    "Fastest path to a runnable MissionSpec.",
                    "Leaves broader product polish and follow-up discovery for later runs.",
                ],
                risks=[
                    "If the current acceptance is too narrow, Codex may satisfy checks without solving the broader need.",
                ],
            ),
            CoDesignOption(
                title="V1: add explicit quality and review evidence",
                summary="Preserve hard checks while asking the worker to report reasoning, limitations, and validation evidence.",
                tradeoffs=[
                    "Better audit trail and safer completion classification.",
                    "Slightly more reporting overhead for the worker.",
                ],
                risks=[
                    "Soft quality expectations still need human or LLM review.",
                ],
            ),
        ]
        if domain_profile_id in {"algorithm_research", "deep_research"} or soft_criteria:
            options.append(
                CoDesignOption(
                    title="Research-grade route: separate claims, evidence, and uncertainty",
                    summary="Treat the output as a synthesis task with explicit source/evidence notes and limitations.",
                    tradeoffs=[
                        "Improves trust for analysis-heavy work.",
                        "May require a follow-up run if fresh external research is needed.",
                    ],
                    risks=[
                        "Without source provenance, final review may remain soft or blocked.",
                    ],
                )
            )
        if domain_profile_id == "engineering_development" or file_deliverables:
            options.append(
                CoDesignOption(
                    title="Engineering route: tighten file and command evidence",
                    summary="Use file/schema checks now, then add command validators only when the policy explicitly allows them.",
                    tradeoffs=[
                        "Keeps execution verifiable without broadening authority.",
                        "Command-level validation may need a later policy decision.",
                    ],
                    risks=[
                        "File existence alone may not prove behavior.",
                    ],
                )
            )
        unresolved = []
        if not hard_criteria:
            unresolved.append("Confirm whether at least one machine-checkable acceptance criterion can be added.")
        if any(finding.severity == "warning" for finding in review.findings):
            unresolved.append("Resolve reviewer warnings or consciously accept them before lock.")
        return CoDesignBrainstorm(
            options=options,
            recommended_option=options[0].title if options else "",
            mvp=list(mission.deliverables),
            v1=[
                "Keep the MissionSpec locked before run.",
                "Require ExecutionReport evidence for changed files, validation, and limitations.",
                "Use MetaLoop verification before treating Codex completion as done.",
            ],
            later=[
                "Split follow-up enhancements into a revised MissionSpec or Capsule revision.",
                "Add command validators only after confirming the authority boundary.",
            ],
            risks=[
                "Acceptance criteria may pass while subjective quality still needs final human review.",
                "Unstated non-goals can let implementation drift into adjacent work.",
            ],
            overlooked_points=[
                "Ask what should explicitly not change.",
                "Decide whether final human acceptance is required after internal verification.",
                "Keep execution authority narrower than the design conversation.",
            ],
            unresolved_questions=unresolved,
        )


class CodexCoDesignBrainstormer:
    def __init__(self, options: CodexExecOptions | None = None) -> None:
        self.options = options or CodexExecOptions(
            sandbox="read-only",
            approval_policy="never",
            timeout_seconds=180,
            use_output_schema=False,
        )

    def expand(
        self,
        mission: MissionSpec,
        draft: CoDesignDraft,
        review: MissionSpecReview,
    ) -> CoDesignBrainstorm:
        result = CodexExecAdapter(self.options).run(_build_codex_brainstorm_prompt(mission, draft, review))
        if result.returncode != 0 or not result.final_message:
            raise CoDesignAgentError(f"codex brainstorm unavailable: {result.stderr or 'no final message'}")
        try:
            payload = json.loads(result.final_message)
        except json.JSONDecodeError as exc:
            raise CoDesignAgentError(f"codex brainstorm returned invalid JSON: {exc}") from exc
        return _normalize_brainstorm_result(payload)


class MissionSpecReviewer:
    """Independent deterministic reviewer for generated MissionSpec quality."""

    def review(self, mission: MissionSpec) -> MissionSpecReview:
        findings: list[MissionSpecReviewFinding] = []
        domain_profile_id = str(mission.context.get("domain_profile_id") or mission.context.get("domain_profile") or "").strip()
        inferred_domain_profile_id = _infer_domain_profile_id(
            mission.intent,
            mission.deliverables,
            list(mission.acceptance_criteria),
            str(mission.context.get("background") or ""),
        )
        if not domain_profile_id:
            findings.append(
                MissionSpecReviewFinding(
                    severity="warning",
                    code="missing_domain_profile_id",
                    message="Mission context has no domain_profile_id.",
                    recommendation="Set context.domain_profile_id when this is engineering_development, algorithm_research, codex_skill_creation, or deep_research.",
                )
            )
        elif inferred_domain_profile_id and domain_profile_id != inferred_domain_profile_id:
            findings.append(
                MissionSpecReviewFinding(
                    severity="warning",
                    code="domain_profile_mismatch",
                    message=f"Mission context domain_profile_id={domain_profile_id} does not match inferred profile {inferred_domain_profile_id}.",
                    recommendation="Align the domain profile with the task type or remove the conflicting hint.",
                )
            )
        findings.extend(_domain_profile_review_findings(mission, domain_profile_id))
        findings.extend(_spec_discipline_findings(mission))
        if (_is_vague_text(mission.intent) or len(mission.intent.split()) < 4) and not _short_intent_has_concrete_target(mission.intent):
            findings.append(
                MissionSpecReviewFinding(
                    severity="blocking",
                    code="vague_intent",
                    message="Mission intent is too vague for dependable execution.",
                    recommendation="Describe the exact object, action, and desired finish line.",
                )
            )
        if not mission.deliverables:
            findings.append(
                MissionSpecReviewFinding(
                    severity="blocking",
                    code="missing_deliverables",
                    message="Mission has no deliverables.",
                    recommendation="Add at least one concrete deliverable.",
                )
            )
        if any(_is_vague_text(deliverable) for deliverable in mission.deliverables):
            findings.append(
                MissionSpecReviewFinding(
                    severity="warning",
                    code="generic_deliverable",
                    message="At least one deliverable is generic.",
                    recommendation="Name concrete files, reports, commands, or artifacts.",
                )
            )
        if not mission.acceptance_criteria:
            findings.append(
                MissionSpecReviewFinding(
                    severity="blocking",
                    code="missing_acceptance_criteria",
                    message="Mission has no acceptance criteria.",
                    recommendation="Add criteria that prove completion.",
                )
            )
        soft_required = [
            criterion
            for criterion in mission.acceptance_criteria
            if criterion.required and criterion.validation_type in {"manual", "llm_review"}
        ]
        manual_required = [
            criterion
            for criterion in mission.acceptance_criteria
            if criterion.required and criterion.validation_type == "manual"
        ]
        executable_required = [
            criterion
            for criterion in mission.acceptance_criteria
            if criterion.required and criterion.validation_type in {"file_exists", "file_contains", "command", "schema"}
        ]
        if soft_required and not executable_required and _looks_file_based(mission.deliverables):
            findings.append(
                MissionSpecReviewFinding(
                    severity="blocking",
                    code="manual_validation_for_file_task",
                    message="File-like deliverables only have manual/LLM validation.",
                    recommendation="Prefer file_exists, file_contains, schema, or command criteria for local tool tasks.",
                )
            )
        if not executable_required and not _mission_soft_review_only(mission):
            findings.append(
                MissionSpecReviewFinding(
                    severity="blocking",
                    code="missing_executable_acceptance",
                    message="Mission has no executable or checkable acceptance criteria.",
                    recommendation="Add at least one file_exists, file_contains, command, or schema criterion unless the task is naturally soft-review-only.",
                )
            )
        if manual_required:
            findings.append(
                MissionSpecReviewFinding(
                    severity="warning",
                    code="manual_acceptance_present",
                    message="Manual acceptance is present in the mission.",
                    recommendation="Reserve manual criteria for final human acceptance only, and prefer llm_review when internal review is needed.",
                )
            )
        if any(criterion.validation_type == "manual" for criterion in mission.acceptance_criteria) and _looks_file_based(mission.deliverables):
            findings.append(
                MissionSpecReviewFinding(
                    severity="warning",
                    code="manual_used_for_file_deliverable",
                    message="A file-oriented mission still contains manual criteria.",
                    recommendation="Use hard validators for deliverables and keep manual criteria only as final human acceptance if needed.",
                )
            )
        missing_targets = [
            criterion.validation_type
            for criterion in mission.acceptance_criteria
            if criterion.validation_type in {"file_exists", "file_contains", "command", "schema"} and not criterion.validation_target
        ]
        if missing_targets:
            findings.append(
                MissionSpecReviewFinding(
                    severity="blocking",
                    code="missing_validation_target",
                    message="Executable validation criteria are missing validation_target.",
                    recommendation="Provide a file path, file_contains JSON/path::text target, command, or JSON path target.",
                )
            )
        invalid_path_targets = [
            criterion.id
            for criterion in mission.acceptance_criteria
            if criterion.validation_type in {"file_exists", "schema"}
            and criterion.validation_target
            and not _is_valid_path_validation_target(criterion.validation_target)
        ]
        if invalid_path_targets:
            findings.append(
                MissionSpecReviewFinding(
                    severity="blocking",
                    code="invalid_path_validation_target",
                    message="Path-based validation criteria must target concrete repository paths, not prose.",
                    recommendation="Use a relative path such as src/app.py, tests/test_app.py, README.md, docs/guide.md, or .metaloop/result.json.",
                )
            )
        if any(criterion.validation_type == "command" for criterion in mission.acceptance_criteria):
            if "validator.command" not in mission.policy.allowed_tools:
                findings.append(
                    MissionSpecReviewFinding(
                        severity="blocking",
                        code="command_validator_without_policy_allow",
                        message="Command validation is not enabled by policy.",
                        recommendation="Add validator.command to policy.allowed_tools only when arbitrary local command validation is acceptable.",
                    )
                )
        if any(criterion.validation_type == "schema" for criterion in mission.acceptance_criteria):
            if "validator.schema" not in mission.policy.allowed_tools and not any(
                criterion.validation_type == "schema" and criterion.validation_target and criterion.validation_target.endswith((".json", ".yaml", ".yml"))
                for criterion in mission.acceptance_criteria
            ):
                findings.append(
                    MissionSpecReviewFinding(
                        severity="warning",
                        code="schema_validator_without_policy_hint",
                        message="Schema validation should point to a concrete JSON/YAML artifact or be paired with policy guidance.",
                        recommendation="Use schema validation for concrete files and keep the target explicit.",
                    )
                )
        invalid_file_contains_targets = [
            criterion.id
            for criterion in mission.acceptance_criteria
            if criterion.validation_type == "file_contains" and not _is_valid_file_contains_target(criterion.validation_target)
        ]
        if invalid_file_contains_targets:
            findings.append(
                MissionSpecReviewFinding(
                    severity="blocking",
                    code="invalid_file_contains_target",
                    message="file_contains criteria must use a machine-parseable target.",
                    recommendation='Use JSON {"path":"relative/file.txt","contains":"expected text"} or path::expected text.',
                )
            )
        if mission.policy.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            constraints = mission.context.get("constraints", [])
            out_of_scope = mission.context.get("out_of_scope", [])
            if not constraints:
                findings.append(
                    MissionSpecReviewFinding(
                        severity="blocking",
                        code="high_risk_without_constraints",
                        message="High-risk mission has no explicit constraints.",
                        recommendation="Add concrete constraints before execution.",
                    )
                )
            if not out_of_scope:
                findings.append(
                    MissionSpecReviewFinding(
                        severity="warning",
                        code="high_risk_without_non_goals",
                        message="High-risk mission has no out-of-scope boundaries.",
                        recommendation="Add explicit non-goals or forbidden operations.",
                    )
                )
        if any(criterion.validation_type == "llm_review" for criterion in mission.acceptance_criteria):
            if not any(criterion.validation_type in {"file_exists", "file_contains", "command", "schema"} for criterion in mission.acceptance_criteria):
                findings.append(
                    MissionSpecReviewFinding(
                        severity="warning",
                        code="llm_review_without_hard_validator",
                        message="LLM review is present without a hard validator anchor.",
                        recommendation="Add a machine-checkable criterion when the task produces concrete artifacts.",
                    )
                )
        if (
            (mission.budget.max_tokens is not None and mission.budget.max_tokens <= 0)
            or (mission.budget.max_tool_calls is not None and mission.budget.max_tool_calls <= 0)
            or mission.budget.max_usd < 0
            or mission.budget.max_wall_time_seconds <= 0
            or mission.budget.max_step_retries < 0
            or mission.budget.max_replan_count < 0
        ):
            findings.append(
                MissionSpecReviewFinding(
                    severity="blocking",
                    code="invalid_budget",
                    message="Mission budget cannot support execution.",
                    recommendation="Use a positive token budget when capped, and positive tool-call budgets.",
                )
            )
        return MissionSpecReview(passed=not any(finding.severity == "blocking" for finding in findings), findings=findings)


def _domain_profile_review_findings(
    mission: MissionSpec,
    domain_profile_id: str,
) -> list[MissionSpecReviewFinding]:
    findings: list[MissionSpecReviewFinding] = []
    descriptions = " ".join(criterion.description for criterion in mission.acceptance_criteria).lower()
    deliverables = " ".join(mission.deliverables).lower()
    if domain_profile_id == "codex_skill_creation":
        if "skill.md" not in deliverables and "skill.md" not in descriptions:
            findings.append(
                MissionSpecReviewFinding(
                    severity="warning",
                    code="skill_profile_without_skill_artifact",
                    message="Codex skill profile should name SKILL.md or an equivalent skill artifact.",
                    recommendation="Add SKILL.md as a deliverable or explain the alternate skill artifact.",
                )
            )
    elif domain_profile_id == "algorithm_research":
        if not _contains_any_word(" ".join([mission.intent, deliverables, descriptions]), {"experiment", "benchmark", "assumption", "limitations", "method"}):
            findings.append(
                MissionSpecReviewFinding(
                    severity="warning",
                    code="algorithm_profile_without_research_evidence",
                    message="Algorithm research profile lacks explicit experiment, benchmark, assumption, method, or limitation evidence.",
                    recommendation="Add acceptance criteria that require method, evidence, and limitations.",
                )
            )
    elif domain_profile_id == "deep_research":
        if not _contains_any_word(" ".join([mission.intent, deliverables, descriptions]), {"source", "citation", "provenance", "freshness", "claims"}):
            findings.append(
                MissionSpecReviewFinding(
                    severity="warning",
                    code="deep_research_without_source_evidence",
                    message="Deep research profile lacks explicit source, citation, provenance, freshness, or claim-support evidence.",
                    recommendation="Add source table or citation/freshness acceptance criteria.",
                )
            )
    return findings


def build_draft_from_options(
    *,
    intent: str = "",
    deliverables: list[str] | None = None,
    criteria: list[str] | None = None,
    file_exists: list[str] | None = None,
    file_contains: list[str] | None = None,
    commands: list[str] | None = None,
    schemas: list[str] | None = None,
    audience: str = "",
    background: str = "",
    constraints: list[str] | None = None,
    out_of_scope: list[str] | None = None,
    workspace_root: str = ".",
    risk_level: str = "medium",
    max_tokens: int | None = None,
    max_usd: float = 2.0,
    domain_profile_id: str | None = None,
) -> CoDesignDraft:
    criterion_drafts = [CoDesignCriterionDraft(description=item) for item in (criteria or [])]
    criterion_drafts.extend(
        CoDesignCriterionDraft(
            description=f"{target} exists",
            validation_type="file_exists",
            validation_target=target,
        )
        for target in (file_exists or [])
    )
    criterion_drafts.extend(_file_contains_criteria_from_answer("\n".join(file_contains or [])))
    criterion_drafts.extend(
        CoDesignCriterionDraft(
            description=f"Command succeeds: {target}",
            validation_type="command",
            validation_target=target,
        )
        for target in (commands or [])
    )
    criterion_drafts.extend(
        CoDesignCriterionDraft(
            description=f"JSON parses: {target}",
            validation_type="schema",
            validation_target=target,
        )
        for target in (schemas or [])
    )
    return CoDesignDraft(
        intent=intent,
        audience=audience,
        background=background,
        deliverables=deliverables or [],
        constraints=constraints or [],
        out_of_scope=out_of_scope or [],
        criteria=criterion_drafts,
        workspace_root=workspace_root,
        risk_level=RiskLevel(risk_level),
        max_tokens=max_tokens,
        max_usd=max_usd,
        domain_profile_id=domain_profile_id,
    )


def write_mission(mission: MissionSpec, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mission.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_design_artifacts(mission: MissionSpec, workspace_root: str | Path | None = None) -> dict[str, Path]:
    workspace = Path(workspace_root or mission.policy.workspace_root).expanduser().resolve()
    root = workspace / ".metaloop"
    root.mkdir(parents=True, exist_ok=True)
    capsule = compile_mission_capsule(mission)
    contract = compile_goal_contract(mission)
    capsule_path = root / "design_capsule.json"
    contract_path = root / "design_goal_contract.json"
    capsule_path.write_text(capsule.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
    contract_path.write_text(contract.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
    return {
        "design_capsule": capsule_path,
        "design_goal_contract": contract_path,
    }


def write_design_process_artifacts(
    mission: MissionSpec,
    review: MissionSpecReview,
    brainstorm: CoDesignBrainstorm,
    workspace_root: str | Path | None = None,
    *,
    rounds: list[CoDesignRound] | None = None,
    decisions: list[CoDesignDecision] | None = None,
    lock: CoDesignLock | None = None,
) -> dict[str, Path]:
    workspace = Path(workspace_root or mission.policy.workspace_root).expanduser().resolve()
    root = workspace / ".metaloop"
    root.mkdir(parents=True, exist_ok=True)
    rounds = rounds or []
    decisions = decisions or []

    transcript_path = root / "design_transcript.jsonl"
    draft_path = root / "design_draft.md"
    review_path = root / "design_review.md"
    decisions_path = root / "design_decisions.json"
    draft_path.write_text(render_design_draft_markdown(mission, brainstorm), encoding="utf-8")
    review_path.write_text(render_design_review_markdown(mission, review, brainstorm, decisions), encoding="utf-8")
    decisions_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.co_design_decisions",
                "version": "2.0",
                "mission_id": mission.run_id,
                "decisions": [decision.model_dump() for decision in decisions],
                "unresolved_questions": brainstorm.unresolved_questions,
                "updated_at": utc_now(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _write_design_transcript(
        transcript_path,
        mission=mission,
        review=review,
        brainstorm=brainstorm,
        rounds=rounds,
        decisions=decisions,
        lock=lock,
    )
    artifacts = {
        "design_transcript": transcript_path,
        "design_draft": draft_path,
        "design_review": review_path,
        "design_decisions": decisions_path,
    }
    if lock is not None:
        lock_path = root / "design_lock.json"
        lock_path.write_text(lock.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        artifacts["design_lock"] = lock_path
    return artifacts


def lock_design(
    mission: MissionSpec,
    *,
    workspace_root: str | Path | None = None,
    mission_path: str | Path | None = None,
    brainstorm: CoDesignBrainstorm | None = None,
    decisions: list[CoDesignDecision] | None = None,
    approval_source: str = "human",
) -> CoDesignLock:
    review = MissionSpecReviewer().review(mission)
    if not review.passed:
        codes = ", ".join(finding.code for finding in review.blocking_findings)
        raise CoDesignLockError(f"MissionSpec cannot be locked while reviewer has blocking findings: {codes}")
    workspace = Path(workspace_root or mission.policy.workspace_root).expanduser().resolve()
    unresolved = list(brainstorm.unresolved_questions if brainstorm is not None else [])
    if unresolved and not _has_accepted_design_decision(decisions or []):
        raise CoDesignLockError(
            "Co-Design cannot be locked with unresolved decisions: "
            + "; ".join(question.strip() for question in unresolved if question.strip())
        )
    return CoDesignLock(
        mission_id=mission.run_id,
        approval_source=approval_source,
        decision_count=len(decisions or []),
        unresolved_questions=unresolved,
        mission_path=str(mission_path) if mission_path is not None else None,
        capsule_path=str(workspace / ".metaloop" / "design_capsule.json"),
        goal_contract_path=str(workspace / ".metaloop" / "design_goal_contract.json"),
    )


def _has_accepted_design_decision(decisions: list[CoDesignDecision]) -> bool:
    return any(decision.status == "accepted" for decision in decisions)


def mission_preview(mission: MissionSpec) -> str:
    return json.dumps(
        {
            "intent": mission.intent,
            "deliverables": mission.deliverables,
            "acceptance_criteria": [
                {
                    "description": criterion.description,
                    "validation_type": criterion.validation_type,
                    "validation_target": criterion.validation_target,
                }
                for criterion in mission.acceptance_criteria
            ],
            "workspace_root": mission.policy.workspace_root,
            "risk_level": mission.policy.risk_level.value,
            "domain_profile_id": mission.context.get("domain_profile_id"),
        },
        indent=2,
        ensure_ascii=False,
    )


def review_preview(review: MissionSpecReview) -> str:
    return json.dumps(review.model_dump(), indent=2, ensure_ascii=False)


APPROVAL_WORDS = {"approve", "approved", "lock", "locked", "done", "finish", "confirm", "confirmed", "完成", "确认", "锁定", "同意"}


def is_design_approval(value: str) -> bool:
    return value.strip().lower() in APPROVAL_WORDS


def apply_human_design_feedback(draft: CoDesignDraft, feedback: str) -> tuple[CoDesignDraft, CoDesignDecision]:
    updated = draft.model_copy(deep=True)
    text = feedback.strip()
    lower = text.lower()
    status: Literal["accepted", "rejected", "open"] = "open"
    summary = text
    rationale = "Recorded as design review feedback."
    if lower.startswith(("constraint:", "constraints:", "约束:", "限制:")):
        value = _after_colon(text)
        updated.constraints = _dedupe_strings([*updated.constraints, *_split_list(value)])
        status = "accepted"
        summary = f"Add constraints: {value}"
    elif lower.startswith(("out_of_scope:", "out of scope:", "exclude:", "non-goal:", "非目标:", "不做:")):
        value = _after_colon(text)
        updated.out_of_scope = _dedupe_strings([*updated.out_of_scope, *_split_list(value)])
        status = "accepted"
        summary = f"Add out-of-scope boundaries: {value}"
    elif lower.startswith(("deliverable:", "deliverables:", "include:", "交付物:", "包含:")):
        value = _after_colon(text)
        updated.deliverables = _dedupe_strings([*updated.deliverables, *_split_list(value)])
        status = "accepted"
        summary = f"Add deliverables: {value}"
    elif lower.startswith(("criteria:", "criterion:", "acceptance:", "验收:", "验收标准:")):
        value = _after_colon(text)
        updated.criteria.extend(CoDesignCriterionDraft(description=item) for item in _split_list(value))
        status = "accepted"
        summary = f"Add acceptance criteria: {value}"
    elif lower.startswith(("audience:", "用户:", "受众:")):
        value = _after_colon(text)
        updated.audience = value
        status = "accepted"
        summary = f"Set audience: {value}"
    elif lower.startswith(("background:", "context:", "背景:")):
        value = _after_colon(text)
        updated.background = value
        status = "accepted"
        summary = f"Set background: {value}"
    else:
        updated.constraints = _dedupe_strings([*updated.constraints, f"Human design note: {text}"])
        rationale = "Free-form feedback was preserved as a design constraint for the locked contract."
    return updated, CoDesignDecision(
        decision_id=f"decision_{abs(hash((text, utc_now()))) % 10_000_000:07d}",
        status=status,
        summary=summary,
        rationale=rationale,
    )


def _write_design_transcript(
    path: Path,
    *,
    mission: MissionSpec,
    review: MissionSpecReview,
    brainstorm: CoDesignBrainstorm,
    rounds: list[CoDesignRound],
    decisions: list[CoDesignDecision],
    lock: CoDesignLock | None,
) -> None:
    events = [
        {
            "event_type": "requirement_discovery",
            "created_at": utc_now(),
            "round_count": len(rounds),
            "rounds": [round_record.model_dump() for round_record in rounds],
        },
        {
            "event_type": "brainstorm_expansion",
            "created_at": utc_now(),
            "brainstorm": brainstorm.model_dump(),
        },
        {
            "event_type": "human_design_review",
            "created_at": utc_now(),
            "review_passed": review.passed,
            "review": review.model_dump(),
            "compact_state": compact_design_state(mission, review, brainstorm, decisions),
        },
    ]
    if decisions:
        events.append(
            {
                "event_type": "interactive_refinement",
                "created_at": utc_now(),
                "decisions": [decision.model_dump() for decision in decisions],
            }
        )
    if lock is not None:
        events.append(
            {
                "event_type": "contract_lock",
                "created_at": utc_now(),
                "lock": lock.model_dump(by_alias=True),
            }
        )
    path.write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n", encoding="utf-8")


def _markdown_list(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items if str(item).strip()] or ["- Not specified."]


def _string_list_from_context(mission: MissionSpec, key: str) -> list[str]:
    value = mission.context.get(key)
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _product_shape_summary(mission: MissionSpec) -> str:
    domain_profile_id = str(mission.context.get("domain_profile_id") or "general")
    if domain_profile_id == "engineering_development":
        return "Engineering task: Codex should modify or create workspace artifacts and report validation evidence."
    if domain_profile_id == "codex_skill_creation":
        return "Codex skill package: the output should be usable as local Codex skill instructions and supporting assets."
    if domain_profile_id == "deep_research":
        return "Research deliverable: the output should separate claims, evidence, uncertainty, and freshness notes."
    if domain_profile_id == "algorithm_research":
        return "Algorithm research deliverable: the output should preserve assumptions, method, experiments or benchmark evidence, and limitations."
    if mission.deliverables:
        return "Artifact-oriented mission with explicit deliverables and MetaLoop acceptance checks."
    return "General mission with structured acceptance."


def _execution_route_summary(mission: MissionSpec, brainstorm: CoDesignBrainstorm) -> str:
    recommended = brainstorm.recommended_option or "Use the locked MissionSpec as the Codex goal contract."
    validators = sorted({criterion.validation_type for criterion in mission.acceptance_criteria})
    return (
        f"{recommended} MetaLoop will compile the locked MissionSpec into a MissionCapsule and GoalContract; "
        f"Codex executes, then MetaLoop verifies via {', '.join(validators)} criteria."
    )


def compact_design_state(
    mission: MissionSpec,
    review: MissionSpecReview,
    brainstorm: CoDesignBrainstorm,
    decisions: list[CoDesignDecision] | None = None,
) -> dict[str, Any]:
    return {
        "intent": mission.intent,
        "deliverables": mission.deliverables,
        "included": mission.deliverables,
        "not_included": mission.context.get("out_of_scope", []),
        "constraints": mission.context.get("constraints", []),
        "acceptance": [
            {
                "description": criterion.description,
                "validation_type": criterion.validation_type,
                "validation_target": criterion.validation_target,
                "required": criterion.required,
            }
            for criterion in mission.acceptance_criteria
        ],
        "risk_level": mission.policy.risk_level.value,
        "domain_profile_id": mission.context.get("domain_profile_id"),
        "review_passed": review.passed,
        "review_findings": [finding.model_dump() for finding in review.findings],
        "recommended_option": brainstorm.recommended_option,
        "unresolved_questions": brainstorm.unresolved_questions,
        "decisions": [decision.model_dump() for decision in decisions or []],
    }


def render_design_draft_markdown(mission: MissionSpec, brainstorm: CoDesignBrainstorm) -> str:
    lines = [
        "# Co-Design Draft",
        "",
        "## Goal Summary",
        mission.intent,
        "",
        "## Product Shape",
        _product_shape_summary(mission),
        "",
        "## Deliverables",
        *_markdown_list(mission.deliverables),
        "",
        "## Included",
        *_markdown_list(mission.deliverables),
        "",
        "## Not Included",
        *_markdown_list(_string_list_from_context(mission, "out_of_scope") or ["Not specified yet."]),
        "",
        "## Execution Route",
        _execution_route_summary(mission, brainstorm),
        "",
        "## Acceptance Criteria",
        *_markdown_list(
            [
                f"{criterion.description} [{criterion.validation_type}]"
                + (f" target={criterion.validation_target}" if criterion.validation_target else "")
                for criterion in mission.acceptance_criteria
            ]
        ),
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_design_review_markdown(
    mission: MissionSpec,
    review: MissionSpecReview,
    brainstorm: CoDesignBrainstorm,
    decisions: list[CoDesignDecision] | None = None,
) -> str:
    decisions = decisions or []
    lines = [
        "# Co-Design Review",
        "",
        "## Goal Summary",
        mission.intent,
        "",
        "## Product Shape",
        _product_shape_summary(mission),
        "",
        "## Deliverables",
        *_markdown_list(mission.deliverables),
        "",
        "## Included / Not Included",
        "Included:",
        *_markdown_list(mission.deliverables),
        "",
        "Not included:",
        *_markdown_list(_string_list_from_context(mission, "out_of_scope") or ["Not specified yet."]),
        "",
        "## Technical Or Execution Route",
        _execution_route_summary(mission, brainstorm),
        "",
        "## Brainstorm Options",
    ]
    if brainstorm.options:
        for option in brainstorm.options:
            lines.extend(
                [
                    f"### {option.title}",
                    option.summary,
                    "",
                    "Tradeoffs:",
                    *_markdown_list(option.tradeoffs or ["None recorded."]),
                    "",
                    "Risks:",
                    *_markdown_list(option.risks or ["None recorded."]),
                    "",
                ]
            )
    else:
        lines.extend(["No brainstorm options recorded.", ""])
    lines.extend(
        [
            "## MVP / V1 / Later",
            "MVP:",
            *_markdown_list(brainstorm.mvp or mission.deliverables or ["Current MissionSpec deliverables."]),
            "",
            "V1:",
            *_markdown_list(brainstorm.v1 or ["No V1 expansion recorded."]),
            "",
            "Later:",
            *_markdown_list(brainstorm.later or ["No later roadmap recorded."]),
            "",
            "## Acceptance Criteria",
            *_markdown_list(
                [
                    f"{criterion.description} [{criterion.validation_type}]"
                    + (f" target={criterion.validation_target}" if criterion.validation_target else "")
                    for criterion in mission.acceptance_criteria
                ]
            ),
            "",
            "## Risks",
            *_markdown_list(brainstorm.risks or ["No explicit risks recorded."]),
            "",
            "## Reviewer Findings",
            *_markdown_list(
                [
                    f"{finding.severity}: {finding.code} - {finding.message}"
                    for finding in review.findings
                ]
                or ["No reviewer findings."]
            ),
            "",
            "## Decisions",
            *_markdown_list([f"{decision.status}: {decision.summary}" for decision in decisions] or ["No human decisions recorded yet."]),
            "",
            "## Decisions To Confirm",
            *_markdown_list(brainstorm.unresolved_questions or ["No unresolved decisions recorded."]),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _build_codex_interviewer_prompt(
    draft: CoDesignDraft,
    *,
    autonomous: bool = False,
    prompt_root: str | Path | None = None,
) -> str:
    patch_mode = "autonomous" if autonomous else "safe"
    variables = {
        "patch_mode": patch_mode,
        "patch_mode_instruction": _codex_interviewer_patch_mode_instruction(autonomous=autonomous),
        "co_design_draft": _fenced_json(draft),
    }
    try:
        rendered = render_prompt(
            "co_design/discovery",
            variables,
            prompt_root=prompt_root,
            required_variables=("patch_mode", "patch_mode_instruction", "co_design_draft"),
        )
    except PromptPackError as exc:
        raise CoDesignAgentError(f"codex interviewer prompt pack render failed: {exc}") from exc
    return rendered.rendered_text


def _codex_interviewer_patch_mode_instruction(*, autonomous: bool = False) -> str:
    if autonomous:
        return (
            "AUTONOMOUS MODE: You may patch intent, audience, background, deliverables, constraints, "
            "out_of_scope, and criteria. Do not invent facts that conflict with the user's draft. "
            "Complete a self-contained MissionSpec that can be executed without asking the user again. "
            "Prefer machine-checkable criteria: file_exists, file_contains, or schema. For file_contains, "
            "set validation_target to JSON like {\"path\":\"hello.txt\",\"contains\":\"expected text\"}. "
            "Do not use command validation."
        )
    return (
        "SAFE MODE: draft_patch may include only audience, background, constraints, out_of_scope. "
        "Do not patch intent, deliverables, or criteria. If those need changes, ask a question. "
        "Do not suggest command validation. Use file_exists, file_contains, or schema questions for machine-checkable artifacts."
    )


def _build_codex_answer_prompt(
    question: CoDesignQuestion,
    draft: CoDesignDraft,
    review: MissionSpecReview | None,
) -> str:
    review_json = review.model_dump_json(indent=2) if review is not None else "null"
    return "\n\n".join(
        [
            "You are the autonomous MetaLoop Co-Design answerer.",
            "Answer exactly one Co-Design question by updating the MissionSpec draft.",
            "Use only information already present in the user's seed, current draft, and reviewer findings.",
            "Do not invent external facts. Make conservative assumptions explicit in constraints or background.",
            "Prefer machine-checkable criteria: file_exists, file_contains, or schema. Do not use command validation.",
            "For file_contains, set validation_target to JSON like {\"path\":\"hello.txt\",\"contains\":\"expected text\"}.",
            "Return raw JSON only with keys: answer, draft_patch, notes.",
            "Question:",
            question.model_dump_json(indent=2),
            "Current draft:",
            draft.model_dump_json(indent=2),
            "Latest review:",
            review_json,
        ]
    )


def _build_codex_brainstorm_prompt(
    mission: MissionSpec,
    draft: CoDesignDraft,
    review: MissionSpecReview,
    *,
    prompt_root: str | Path | None = None,
) -> str:
    variables = {
        "mission_spec": _fenced_json(mission),
        "co_design_draft": _fenced_json(draft),
        "mission_spec_review": _fenced_json(review),
    }
    try:
        rendered = render_prompt(
            "co_design/brainstorm",
            variables,
            prompt_root=prompt_root,
            required_variables=("mission_spec", "co_design_draft", "mission_spec_review"),
        )
    except PromptPackError as exc:
        raise CoDesignAgentError(f"codex brainstorm prompt pack render failed: {exc}") from exc
    return rendered.rendered_text


def _fenced_json(value: BaseModel | dict[str, Any]) -> str:
    if isinstance(value, BaseModel):
        payload = json.loads(value.model_dump_json())
    else:
        payload = value
    return "```json\n" + json.dumps(payload, indent=2, ensure_ascii=False) + "\n```"


def _normalize_brainstorm_result(payload: dict[str, Any]) -> CoDesignBrainstorm:
    if not isinstance(payload, dict):
        raise CoDesignAgentError("codex brainstorm output must be a JSON object")
    options = []
    for item in payload.get("options", []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not title or not summary:
            continue
        options.append(
            CoDesignOption(
                title=title,
                summary=summary,
                tradeoffs=_coerce_string_list(item.get("tradeoffs") or []),
                risks=_coerce_string_list(item.get("risks") or []),
            )
        )
    if not options:
        raise CoDesignAgentError("codex brainstorm output contains no usable options")
    return CoDesignBrainstorm(
        options=options,
        recommended_option=str(payload.get("recommended_option") or options[0].title),
        mvp=_coerce_string_list(payload.get("mvp") or []),
        v1=_coerce_string_list(payload.get("v1") or []),
        later=_coerce_string_list(payload.get("later") or []),
        risks=_coerce_string_list(payload.get("risks") or []),
        overlooked_points=_coerce_string_list(payload.get("overlooked_points") or []),
        unresolved_questions=_coerce_string_list(payload.get("unresolved_questions") or []),
        notes=str(payload.get("notes") or ""),
    )


def _normalize_interviewer_result(
    payload: dict[str, Any],
    *,
    autonomous: bool = False,
    draft: CoDesignDraft | None = None,
) -> CoDesignInterviewerResult:
    questions = []
    for item in payload.get("questions", []):
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("question_id") or "").strip()
        prompt = str(item.get("prompt") or "").strip()
        if question_id not in _allowed_question_ids() or not prompt:
            continue
        questions.append(
            CoDesignQuestion(
                question_id=question_id,
                prompt=prompt,
                required=bool(item.get("required", True)),
                help_text=str(item.get("help_text") or ""),
                reason=str(item.get("reason") or ""),
                options=_coerce_string_list(item.get("options") or []),
            )
        )
    draft_patch = (
        _sanitize_autonomous_patch(payload.get("draft_patch"), seed_intent=draft.intent if draft is not None else "")
        if autonomous
        else _sanitize_interviewer_patch(payload.get("draft_patch"))
    )
    notes = str(payload.get("notes") or "")
    return CoDesignInterviewerResult(questions=_dedupe_questions(questions), draft_patch=draft_patch, notes=notes)


def _normalize_answer_result(payload: dict[str, Any], *, draft: CoDesignDraft) -> CoDesignAnswer:
    if not isinstance(payload, dict):
        return CoDesignAnswer()
    patch = _sanitize_autonomous_patch(payload.get("draft_patch"), seed_intent=draft.intent)
    answer = str(payload.get("answer") or "")
    notes = str(payload.get("notes") or "")
    return CoDesignAnswer(answer=answer, draft_patch=patch, notes=notes)


def _try_review_session(
    session: CoDesignSession,
    reviewer: MissionSpecReviewer,
) -> tuple[MissionSpec, MissionSpecReview] | tuple[None, None]:
    try:
        mission = session.build_mission()
    except ValueError:
        return None, None
    return mission, reviewer.review(mission)


def _review_converged(review: MissionSpecReview, *, require_clean: bool) -> bool:
    if not review.passed:
        return False
    if require_clean and any(finding.severity in {"blocking", "warning"} for finding in review.findings):
        return False
    return True


def _select_next_questions(
    session: CoDesignSession,
    review: MissionSpecReview | None,
    candidates: list[CoDesignQuestion],
    *,
    limit: int,
) -> list[CoDesignQuestion]:
    questions = [*candidates]
    if review is not None:
        questions.extend(_questions_from_review(review, session.draft))
    if not questions:
        questions.extend(session.missing_questions())
    return _dedupe_questions(questions)[:limit]


def _questions_from_review(review: MissionSpecReview, draft: CoDesignDraft) -> list[CoDesignQuestion]:
    questions = []
    for finding in review.findings:
        if finding.severity not in {"blocking", "warning"}:
            continue
        if finding.code == "missing_domain_profile_id":
            questions.append(
                CoDesignQuestion(
                    question_id="domain_profile_id",
                    prompt="Which domain profile should MetaLoop record for this mission?",
                    reason=finding.message,
                    required=False,
                    options=[
                        "engineering_development",
                        "algorithm_research",
                        "codex_skill_creation",
                        "deep_research",
                    ],
                )
            )
        elif finding.code == "domain_profile_mismatch":
            questions.append(
                CoDesignQuestion(
                    question_id="domain_profile_id",
                    prompt="Please align the domain profile with the mission type.",
                    reason=finding.message,
                    required=False,
                    options=[
                        "engineering_development",
                        "algorithm_research",
                        "codex_skill_creation",
                        "deep_research",
                    ],
                )
            )
        if finding.code == "vague_intent":
            questions.append(
                CoDesignQuestion(
                    question_id="intent",
                    prompt="Restate the mission intent as a concrete, executable outcome with object, action, and finish line.",
                    reason=finding.message,
                )
            )
        elif finding.code in {"missing_deliverables", "generic_deliverable"}:
            questions.append(
                CoDesignQuestion(
                    question_id="deliverables",
                    prompt="Name the exact files, reports, or artifacts this run must produce.",
                    reason=finding.message,
                )
            )
        elif finding.code in {"missing_acceptance_criteria", "manual_validation_for_file_task"}:
            if _looks_file_based(draft.deliverables):
                questions.append(
                    CoDesignQuestion(
                        question_id="file_contains",
                        prompt='Provide machine-checkable file content criteria as "path::expected text", one per line.',
                        required=False,
                        reason=finding.message,
                    )
                )
                questions.append(
                    CoDesignQuestion(
                        question_id="file_exists",
                        prompt="Which concrete files must exist when the mission is complete?",
                        required=False,
                        reason=finding.message,
                    )
                )
            else:
                questions.append(
                    CoDesignQuestion(
                        question_id="criteria",
                        prompt="Define concrete acceptance criteria that prove the deliverables are complete.",
                        reason=finding.message,
                    )
                )
        elif finding.code == "missing_executable_acceptance":
            questions.append(
                CoDesignQuestion(
                    question_id="file_exists",
                    prompt="Name a concrete file, directory, or artifact that can be checked automatically.",
                    required=False,
                    reason=finding.message,
                )
            )
            questions.append(
                CoDesignQuestion(
                    question_id="file_contains",
                    prompt='If a file should contain specific text, provide "path::expected text".',
                    required=False,
                    reason=finding.message,
                )
            )
        elif finding.code in {"missing_validation_target", "invalid_file_contains_target"}:
            questions.append(
                CoDesignQuestion(
                    question_id="file_contains",
                    prompt='Repair file content validation targets as "path::expected text".',
                    required=False,
                    reason=finding.message,
                )
            )
        elif finding.code == "command_validator_without_policy_allow":
            questions.append(
                CoDesignQuestion(
                    question_id="criteria",
                    prompt="Replace command validation with file_exists, file_contains, schema, or manual criteria.",
                    reason=finding.message,
                )
            )
        elif finding.code == "high_risk_without_constraints":
            questions.append(
                CoDesignQuestion(
                    question_id="constraints",
                    prompt="List explicit safety, permission, and operational constraints for this high-risk mission.",
                    reason=finding.message,
                )
            )
        elif finding.code == "high_risk_without_non_goals":
            questions.append(
                CoDesignQuestion(
                    question_id="out_of_scope",
                    prompt="List operations or outcomes that are explicitly out of scope.",
                    required=False,
                    reason=finding.message,
                )
            )
        elif finding.code in {"scope_too_broad", "needs_decomposition"}:
            questions.append(
                CoDesignQuestion(
                    question_id="deliverables",
                    prompt="Narrow this mission to one independently verifiable MVP slice. Which exact deliverables stay in scope?",
                    reason=finding.message,
                )
            )
        elif finding.code == "missing_non_goals":
            questions.append(
                CoDesignQuestion(
                    question_id="out_of_scope",
                    prompt="What is explicitly out of scope or forbidden for this run?",
                    required=False,
                    reason=finding.message,
                )
            )
        elif finding.code in {"missing_evidence_path", "weak_acceptance"}:
            questions.append(
                CoDesignQuestion(
                    question_id="criteria",
                    prompt="What concrete evidence should prove this mission is complete?",
                    reason=finding.message,
                )
            )
        elif finding.code == "unclear_authority":
            questions.append(
                CoDesignQuestion(
                    question_id="constraints",
                    prompt="What tools, paths, permissions, or safety constraints bound the worker's authority?",
                    reason=finding.message,
                )
            )
        elif finding.code == "missing_tradeoff_review":
            questions.append(
                CoDesignQuestion(
                    question_id="constraints",
                    prompt="What MVP route and tradeoffs should be recorded before build?",
                    required=False,
                    reason=finding.message,
                )
            )
        elif finding.code in {"manual_acceptance_present", "manual_used_for_file_deliverable", "llm_review_without_hard_validator"}:
            questions.append(
                CoDesignQuestion(
                    question_id="criteria",
                    prompt="Separate machine-checkable acceptance from final human acceptance. What should be checked automatically?",
                    required=False,
                    reason=finding.message,
                )
            )
    return questions


def _notes_from_interviewer(result: CoDesignInterviewerResult) -> list[str]:
    return [result.notes] if result.notes else []


def _question_title_for_status(question_id: str) -> str:
    return question_id.replace("_", " ")


def _merge_patch(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        merged[key] = value
    return merged


def _allowed_question_ids() -> set[str]:
    return {
        "intent",
        "deliverables",
        "criteria",
        "file_exists",
        "file_contains",
        "audience",
        "constraints",
        "out_of_scope",
        "domain_profile_id",
    }


def _sanitize_interviewer_patch(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    safe_patch = {}
    for key in ("audience", "background", "domain_profile_id"):
        if isinstance(value.get(key), str) and value[key].strip():
            safe_patch[key] = value[key].strip()
    for key in ("constraints", "out_of_scope"):
        if key in value:
            safe_patch[key] = _coerce_string_list(value[key])
    return safe_patch


def _sanitize_autonomous_patch(value: Any, *, seed_intent: str = "") -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    safe_patch = _sanitize_interviewer_patch(value)
    if isinstance(value.get("intent"), str) and value["intent"].strip():
        safe_patch["intent"] = value["intent"].strip()
    if "deliverables" in value:
        safe_patch["deliverables"] = _coerce_string_list(value["deliverables"])
    if "criteria" in value:
        criteria = [
            criterion
            for criterion in _coerce_criteria_list(value["criteria"])
            if criterion.validation_type != "command"
        ]
        inferred_criteria = _infer_machine_criteria(
            "\n".join(
                item
                for item in (
                    seed_intent,
                    str(safe_patch.get("intent") or value.get("intent") or ""),
                )
                if item
            ),
            _coerce_string_list(safe_patch.get("deliverables") or value.get("deliverables") or []),
        )
        criteria = _merge_inferred_criteria(criteria, inferred_criteria)
        if criteria:
            safe_patch["criteria"] = [criterion.model_dump() for criterion in criteria]
    if "criteria" not in safe_patch:
        inferred_criteria = _infer_machine_criteria(
            "\n".join(
                item
                for item in (
                    seed_intent,
                    str(safe_patch.get("intent") or value.get("intent") or ""),
                )
                if item
            ),
            _coerce_string_list(safe_patch.get("deliverables") or value.get("deliverables") or []),
        )
        if inferred_criteria:
            safe_patch["criteria"] = [criterion.model_dump() for criterion in inferred_criteria]
    return safe_patch


def _normalize_deliverables(intent: str, deliverables: list[str]) -> list[str]:
    normalized = [item.strip() for item in deliverables if item and item.strip()]
    if normalized:
        return list(dict.fromkeys(normalized))
    inferred = _infer_deliverables_from_intent(intent)
    return list(dict.fromkeys([item for item in inferred if item]))


def _infer_deliverables_from_intent(intent: str) -> list[str]:
    text = intent.strip()
    if not text:
        return []
    lower = text.lower()
    inferred: list[str] = []
    file_path = _extract_first_file_path(text)
    if file_path:
        inferred.append(file_path)
    if any(token in lower for token in {"code", "bug", "fix", "implement", "refactor", "test", "cli", "script", "tool"}):
        inferred.extend(["src/", "tests/"])
    if any(token in lower for token in {"doc", "readme", "guide", "document", "writeup", "spec"}):
        inferred.extend(["README.md", "docs/"])
    if any(token in lower for token in {"skill", "skill.md", "codex skill"}):
        inferred.append("SKILL.md")
    if any(token in lower for token in {"deep research", "citations", "source table", "literature"}):
        inferred.extend(["research_report.md", "source_table.md"])
    if any(token in lower for token in {"research", "analysis", "benchmark", "study", "investigate"}):
        inferred.extend(["report.md", "notes.md"])
    return inferred


def _domain_profile_review_findings(
    mission: MissionSpec,
    domain_profile_id: str,
) -> list[MissionSpecReviewFinding]:
    criteria = mission.acceptance_criteria
    deliverables = mission.deliverables
    descriptions = " ".join(criterion.description for criterion in criteria).lower()
    mission_text = " ".join([mission.intent, *deliverables, descriptions, str(mission.context.get("background") or "")]).lower()
    findings: list[MissionSpecReviewFinding] = []
    if domain_profile_id == "codex_skill_creation":
        if not any(item.strip().lower() == "skill.md" for item in deliverables):
            findings.append(
                MissionSpecReviewFinding(
                    severity="warning",
                    code="codex_skill_profile_without_skill_md",
                    message="Codex skill missions usually produce SKILL.md.",
                    recommendation="Include SKILL.md unless this mission is intentionally preparing only supporting material.",
                )
            )
        if not _contains_all_concepts(mission_text, (("usage", "example"), ("validation", "checklist", "validate"))):
            findings.append(
                MissionSpecReviewFinding(
                    severity="warning",
                    code="codex_skill_missing_evidence_obligations",
                    message="Codex skill profile should define evidence for usage examples and validation checklist.",
                    recommendation="Add acceptance or evidence notes for SKILL.md, a usage example, and validation checklist.",
                )
            )
    elif domain_profile_id == "deep_research":
        if not any(criterion.validation_type == "llm_review" for criterion in criteria):
            findings.append(
                MissionSpecReviewFinding(
                    severity="info",
                    code="deep_research_without_llm_review",
                    message="Deep research missions usually need LLM synthesis review.",
                    recommendation="Add an llm_review criterion for source support, uncertainty, and synthesis quality.",
                )
            )
        if not _contains_all_concepts(mission_text, (("source", "sources", "source table"), ("citation", "provenance", "cite"), ("claim", "support", "evidence"))):
            findings.append(
                MissionSpecReviewFinding(
                    severity="warning",
                    code="deep_research_missing_evidence_obligations",
                    message="Deep research profile should require source table, citation/provenance, and claim support evidence.",
                    recommendation="Add acceptance criteria or deliverables for sources, provenance/freshness, and supported claims.",
                )
            )
    elif domain_profile_id == "algorithm_research":
        if not any("benchmark" in (criterion.description or "").lower() or "experiment" in (criterion.description or "").lower() for criterion in criteria):
            findings.append(
                MissionSpecReviewFinding(
                    severity="info",
                    code="algorithm_research_without_experiment_evidence",
                    message="Algorithm research missions should preserve experiment or benchmark evidence when applicable.",
                    recommendation="Record benchmark commands, assumptions, and results in the final evidence.",
                )
            )
        if not _contains_all_concepts(mission_text, (("assumption", "assumptions"), ("method", "approach"), ("experiment", "benchmark"), ("limitation", "limitations"))):
            findings.append(
                MissionSpecReviewFinding(
                    severity="warning",
                    code="algorithm_research_missing_evidence_obligations",
                    message="Algorithm research profile should state assumptions, method, experiment/benchmark evidence, and limitations.",
                    recommendation="Add acceptance or evidence requirements for assumptions, method, experiment/benchmark, and limitations.",
                )
            )
    elif domain_profile_id == "engineering_development":
        if _looks_file_based(deliverables) and not any(
            criterion.validation_type in {"file_exists", "file_contains", "schema", "command"}
            for criterion in criteria
        ):
            findings.append(
                MissionSpecReviewFinding(
                    severity="info",
                    code="engineering_profile_prefers_hard_validator",
                    message="Engineering missions are strongest with at least one hard validator.",
                    recommendation="Prefer file_exists, file_contains, schema, or command validation.",
                )
            )
        if _contains_any_word(mission_text, {"bug", "fix", "regression"}) and not _contains_any_word(mission_text, {"test", "lint", "build", "regression"}):
            findings.append(
                MissionSpecReviewFinding(
                    severity="warning",
                    code="engineering_missing_regression_evidence",
                    message="Engineering bugfix/public behavior missions should require regression, build, lint, or test evidence.",
                    recommendation="Add a command criterion or evidence requirement for relevant regression/build/test validation.",
                )
            )
    return findings


def _spec_discipline_findings(mission: MissionSpec) -> list[MissionSpecReviewFinding]:
    findings: list[MissionSpecReviewFinding] = []
    constraints = _context_list(mission.context.get("constraints"))
    non_goals = _context_list(mission.context.get("out_of_scope"))
    text = " ".join(
        [
            mission.intent,
            *mission.deliverables,
            *[criterion.description for criterion in mission.acceptance_criteria],
            str(mission.context.get("background") or ""),
        ]
    ).lower()
    high_risk = mission.policy.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
    broad = _mission_scope_too_broad(mission)
    complex_shape = len(mission.deliverables) >= 4 or len(mission.acceptance_criteria) >= 5
    evidence_anchored = any(
        criterion.validation_type in {"file_exists", "file_contains", "command", "schema"}
        and bool(criterion.validation_target)
        for criterion in mission.acceptance_criteria
    ) or _contains_any_word(text, {"evidence", "source", "benchmark", "test", "validation", "checklist"})

    if broad:
        findings.append(
            MissionSpecReviewFinding(
                severity="blocking" if high_risk else "warning",
                code="scope_too_broad",
                message="Mission scope is broad enough that agree-before-build boundaries may be unclear.",
                recommendation="Narrow the MVP, name the concrete deliverables, or split broad follow-up work out of this run.",
            )
        )
    if not non_goals and (high_risk or broad or complex_shape):
        severity = "blocking" if high_risk and broad else "warning"
        findings.append(
            MissionSpecReviewFinding(
                severity=severity,
                code="missing_non_goals",
                message="Mission has no explicit non-goals or out-of-scope boundaries.",
                recommendation="State what this run must not change or solve before authorizing implementation.",
            )
        )
    if not evidence_anchored:
        findings.append(
            MissionSpecReviewFinding(
                severity="blocking" if high_risk or broad else "warning",
                code="missing_evidence_path",
                message="Mission does not make the evidence path explicit enough for independent verification.",
                recommendation="Name the file, command, source table, report section, or checklist that proves completion.",
            )
        )
    if _weak_acceptance(mission):
        findings.append(
            MissionSpecReviewFinding(
                severity="blocking" if high_risk or broad else "warning",
                code="weak_acceptance",
                message="Acceptance criteria are too weak to protect the agreed MissionSpec.",
                recommendation="Replace vague completion language with observable checks, targets, or review evidence.",
            )
        )
    if not constraints and (high_risk or broad):
        findings.append(
            MissionSpecReviewFinding(
                severity="blocking" if high_risk else "warning",
                code="unclear_authority",
                message="Mission authority is unclear for the requested scope.",
                recommendation="Add constraints, allowed tools, approval boundaries, or forbidden operations before execution.",
            )
        )
    if (high_risk or broad or complex_shape) and not _has_tradeoff_review(mission):
        findings.append(
            MissionSpecReviewFinding(
                severity="warning",
                code="missing_tradeoff_review",
                message="Mission lacks an explicit tradeoff/options review before build.",
                recommendation="Record the chosen MVP route, alternatives considered, and accepted tradeoffs.",
            )
        )
    if broad and complex_shape:
        findings.append(
            MissionSpecReviewFinding(
                severity="blocking" if high_risk else "warning",
                code="needs_decomposition",
                message="Mission appears large enough to need decomposition before worker execution.",
                recommendation="Split it into smaller authorized capsules or narrow this MissionSpec to one independently verifiable slice.",
            )
        )
    return findings


def _mission_scope_too_broad(mission: MissionSpec) -> bool:
    text = " ".join([mission.intent, *mission.deliverables]).lower()
    broad_words = {"entire", "everything", "all", "platform", "rewrite", "redesign"}
    broad_phrases = {"complete system", "full app", "full product", "end-to-end", "production-ready"}
    has_broad_term = _contains_any_word(text, broad_words) or any(phrase in text for phrase in broad_phrases)
    many_outputs = len(mission.deliverables) >= 5
    return has_broad_term or many_outputs


def _weak_acceptance(mission: MissionSpec) -> bool:
    if not mission.acceptance_criteria:
        return True
    vague = {"done", "works", "looks good", "complete", "ready", "acceptable", "quality is good"}
    weak_count = 0
    for criterion in mission.acceptance_criteria:
        description = criterion.description.strip().lower()
        if description in vague or _is_vague_text(description):
            weak_count += 1
        elif criterion.validation_type in {"file_exists", "file_contains", "command", "schema"} and not criterion.validation_target:
            weak_count += 1
    return weak_count == len(mission.acceptance_criteria)


def _has_tradeoff_review(mission: MissionSpec) -> bool:
    keys = {"tradeoffs", "alternatives", "options_reviewed", "mvp", "design_decisions"}
    if any(key in mission.context and mission.context.get(key) for key in keys):
        return True
    text = " ".join(str(mission.context.get(key) or "") for key in mission.context).lower()
    return any(token in text for token in ["tradeoff", "alternative", "mvp", "option"])


def _context_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _contains_all_concepts(text: str, concepts: tuple[tuple[str, ...], ...]) -> bool:
    lower = text.lower()
    return all(any(token in lower for token in concept) for concept in concepts)


def _apply_domain_profile_deliverables(
    domain_profile_id: str | None,
    intent: str,
    deliverables: list[str],
) -> list[str]:
    if deliverables:
        return deliverables
    if domain_profile_id == "codex_skill_creation":
        return ["SKILL.md"]
    if domain_profile_id == "deep_research":
        return ["research_report.md", "source_table.md"]
    if domain_profile_id == "algorithm_research":
        return ["experiment_report.md", "benchmark_notes.md"]
    if domain_profile_id == "engineering_development":
        inferred = _infer_deliverables_from_intent(intent)
        if inferred:
            return inferred
    return deliverables


def _apply_domain_profile_criteria(
    domain_profile_id: str | None,
    intent: str,
    deliverables: list[str],
    criteria: list[CoDesignCriterionDraft],
) -> list[CoDesignCriterionDraft]:
    result = list(criteria)
    if domain_profile_id == "codex_skill_creation":
        skill_path = _first_matching_deliverable(deliverables, {"SKILL.md"}) or "SKILL.md"
        if not _has_criterion(result, "file_exists", skill_path):
            result.append(
                CoDesignCriterionDraft(
                    description=f"{skill_path} exists",
                    validation_type="file_exists",
                    validation_target=skill_path,
                )
            )
        if not any(criterion.validation_type == "llm_review" for criterion in result):
            result.append(
                CoDesignCriterionDraft(
                    description="LLM review confirms the skill instructions are clear, scoped, and include actionable usage guidance.",
                    validation_type="llm_review",
                )
            )
    elif domain_profile_id == "algorithm_research":
        if not any(criterion.validation_type == "llm_review" for criterion in result):
            result.append(
                CoDesignCriterionDraft(
                    description="LLM review confirms the report states assumptions, method, experiment or benchmark evidence, and limitations.",
                    validation_type="llm_review",
                )
            )
    elif domain_profile_id == "deep_research":
        if not any(criterion.validation_type == "llm_review" for criterion in result):
            result.append(
                CoDesignCriterionDraft(
                    description="LLM review confirms claims are separated from inference and supported by cited sources with freshness notes where needed.",
                    validation_type="llm_review",
                )
            )
    elif domain_profile_id == "engineering_development":
        result = _ensure_hard_validators_for_files(result, deliverables)
    return result


def _domain_profile_evidence_hints(domain_profile_id: str) -> list[str]:
    if domain_profile_id == "codex_skill_creation":
        return ["changed skill files", "referenced scripts/assets", "validation commands or structural checks"]
    if domain_profile_id == "algorithm_research":
        return ["experiment commands", "benchmark outputs", "assumptions and limitations"]
    if domain_profile_id == "deep_research":
        return ["source table", "citation/provenance notes", "freshness metadata for time-sensitive claims"]
    return ["changed files", "commands run", "test or validator output"]


def _first_matching_deliverable(deliverables: list[str], names: set[str]) -> str | None:
    lowered = {name.lower() for name in names}
    for deliverable in deliverables:
        if deliverable.strip().lower() in lowered:
            return deliverable.strip()
    return None


def _has_criterion(criteria: list[CoDesignCriterionDraft], validation_type: str, target: str) -> bool:
    return any(
        criterion.validation_type == validation_type and criterion.validation_target == target
        for criterion in criteria
    )


def _normalize_and_infer_criteria(
    intent: str,
    deliverables: list[str],
    criteria: list[CoDesignCriterionDraft],
) -> list[CoDesignCriterionDraft]:
    normalized = [
        _promote_manual_criterion(criterion, intent=intent, deliverables=deliverables)
        for criterion in criteria
    ]
    normalized = [_normalize_criterion(criterion) for criterion in normalized]
    normalized = _ensure_hard_validators_for_files(normalized, deliverables)
    inferred = _infer_machine_criteria(
        "\n".join([intent, *[criterion.description for criterion in criteria]]),
        deliverables,
    )
    normalized = _merge_inferred_criteria(normalized, inferred)
    normalized = _infer_soft_review_criteria(intent, deliverables, normalized)
    return normalized


def _promote_manual_criterion(
    criterion: CoDesignCriterionDraft,
    *,
    intent: str,
    deliverables: list[str],
) -> CoDesignCriterionDraft:
    if criterion.validation_type != "manual":
        return criterion
    if _looks_final_human_acceptance(criterion.description):
        return criterion
    text = "\n".join([intent, criterion.description, *deliverables])
    file_path = _extract_path_like_validation_target(text) or _first_file_deliverable(deliverables)
    if file_path:
        expected_text = _extract_expected_file_text(text)
        if expected_text is not None:
            return CoDesignCriterionDraft(
                description=f"{file_path} contains expected text",
                validation_type="file_contains",
                validation_target=json.dumps({"path": file_path, "contains": expected_text}, ensure_ascii=False),
                required=criterion.required,
            )
        if re.search(r"\b(exists?|created|present|written|generated)\b", criterion.description, re.IGNORECASE):
            return CoDesignCriterionDraft(
                description=f"{file_path} exists",
                validation_type="file_exists",
                validation_target=file_path,
                required=criterion.required,
            )
    if _looks_file_based(deliverables) or _infer_domain_profile_id(intent, deliverables, [criterion], "") == "engineering_development":
        return CoDesignCriterionDraft(
            description=criterion.description,
            validation_type="llm_review",
            required=criterion.required,
        )
    return criterion


def _ensure_hard_validators_for_files(
    criteria: list[CoDesignCriterionDraft],
    deliverables: list[str],
) -> list[CoDesignCriterionDraft]:
    if not deliverables:
        return criteria
    hard_paths = {
        criterion.validation_target
        for criterion in criteria
        if criterion.validation_type in {"file_exists", "schema", "command"} and criterion.validation_target
    }
    hard_paths.update(
        path
        for path in _file_paths_from_targets(
            {criterion.validation_target for criterion in criteria if criterion.validation_type == "file_contains"}
        )
        if path
    )
    result = list(criteria)
    for deliverable in deliverables:
        path_target = _extract_path_like_validation_target(deliverable)
        if path_target is None:
            continue
        if path_target in hard_paths:
            continue
        result.append(
            CoDesignCriterionDraft(
                description=f"{path_target} exists",
                validation_type="file_exists",
                validation_target=path_target,
            )
        )
        hard_paths.add(path_target)
    return result


def _first_file_deliverable(deliverables: list[str]) -> str | None:
    for deliverable in deliverables:
        path = _extract_path_like_validation_target(deliverable)
        if path:
            return path
    return None


def _infer_soft_review_criteria(
    intent: str,
    deliverables: list[str],
    criteria: list[CoDesignCriterionDraft],
) -> list[CoDesignCriterionDraft]:
    text = " ".join([intent, *deliverables]).lower()
    if _contains_any_word(text, {"research", "analysis", "recommendation", "evaluation", "compare"}):
        normalized = []
        for criterion in criteria:
            if criterion.validation_type == "manual" and not _looks_final_human_acceptance(criterion.description):
                normalized.append(
                    criterion.model_copy(
                        update={
                            "validation_type": "llm_review",
                            "description": criterion.description
                            or "LLM review confirms the analysis is coherent, well supported, and clearly explains limitations.",
                        }
                    )
                )
            else:
                normalized.append(criterion)
        if not any(criterion.validation_type == "llm_review" for criterion in normalized):
            normalized.append(
                CoDesignCriterionDraft(
                    description="LLM review confirms the analysis is coherent, well supported, and clearly explains limitations.",
                    validation_type="llm_review",
                    required=True,
                )
            )
        return normalized
    if any(criterion.validation_type in {"manual", "llm_review"} for criterion in criteria):
        return [
            criterion
            for criterion in criteria
        ]
    if _contains_any_word(text, {"ux", "experience", "feel", "polish", "readability"}):
        return [
            *criteria,
            CoDesignCriterionDraft(
                description="Final human acceptance confirms the experience is acceptable.",
                validation_type="manual",
                required=True,
            ),
        ]
    return criteria


def _looks_like_file_path(value: str) -> bool:
    return _extract_path_like_validation_target(value) is not None


def _extract_path_like_validation_target(value: str) -> str | None:
    text = value.strip().strip("`\"'")
    if _is_valid_path_validation_target(text):
        return normalize_path_validation_target(text)
    file_path = _extract_first_file_path(text)
    if file_path and _is_valid_path_validation_target(file_path):
        return file_path
    directory_match = re.search(r"(?P<path>(?:[\w.-]+/)+)(?=$|[\s`\"'.,;:)])", text)
    if directory_match is not None:
        path = normalize_path_validation_target(directory_match.group("path"))
        if _is_valid_path_validation_target(path):
            return path
    return None


def _is_valid_path_validation_target(value: str | None) -> bool:
    return is_valid_path_validation_target(value)


def _mission_soft_review_only(mission: MissionSpec) -> bool:
    text = " ".join([mission.intent, *mission.deliverables, *[criterion.description for criterion in mission.acceptance_criteria]]).lower()
    return _contains_any_word(text, {"research", "analysis", "evaluation", "ux", "experience", "review", "recommendation"})


def _short_intent_has_concrete_target(intent: str) -> bool:
    return _extract_path_like_validation_target(intent) is not None and _contains_any_word(
        intent,
        {"create", "write", "add", "update", "fix", "build", "implement"},
    )


def _infer_domain_profile_id(
    intent: str,
    deliverables: list[str],
    criteria: list[CoDesignCriterionDraft | AcceptanceCriteria],
    background: str,
) -> str | None:
    text = " ".join(
        [
            intent,
            background,
            *deliverables,
            *[criterion.description for criterion in criteria],
        ]
    ).lower()
    if any(token in text for token in {"skill", "plugin", "skill.md", "skill creation"}):
        return "codex_skill_creation"
    if any(token in text for token in {"deep research", "literature", "sources", "citations", "evidence table"}):
        return "deep_research"
    if any(token in text for token in {"research", "benchmark", "analysis", "experiment", "algorithm"}):
        return "algorithm_research"
    if (
        any(token in text for token in {"code", "bug", "fix", "implement", "refactor", "test", "cli", "tool"})
        or _looks_file_based(deliverables)
        or _extract_first_file_path(intent) is not None
    ):
        return "engineering_development"
    return None


def _looks_final_human_acceptance(description: str) -> bool:
    text = description.lower()
    return any(token in text for token in {"human acceptance", "user acceptance", "final acceptance", "looks good", "approve", "accepted"})


def _contains_any_word(text: str, words: set[str]) -> bool:
    normalized = re.sub(r"[^a-z0-9_]+", " ", text.lower())
    return bool(set(normalized.split()) & words)


def _merge_inferred_criteria(
    criteria: list[CoDesignCriterionDraft],
    inferred_criteria: list[CoDesignCriterionDraft],
) -> list[CoDesignCriterionDraft]:
    if not inferred_criteria:
        return criteria
    if any(criterion.validation_type == "file_contains" for criterion in criteria):
        inferred_criteria = [criterion for criterion in inferred_criteria if criterion.validation_type != "file_exists"]
    if any(criterion.validation_type == "file_contains" for criterion in inferred_criteria):
        inferred_targets = {criterion.validation_target for criterion in inferred_criteria}
        criteria = [
            criterion
            for criterion in criteria
            if not (criterion.validation_type == "file_exists" and criterion.validation_target in _file_paths_from_targets(inferred_targets))
        ]
    existing = {(criterion.validation_type, criterion.validation_target) for criterion in criteria}
    for criterion in inferred_criteria:
        key = (criterion.validation_type, criterion.validation_target)
        if key not in existing:
            criteria.append(criterion)
            existing.add(key)
    return criteria


def _file_paths_from_targets(targets: set[str | None]) -> set[str]:
    paths = set()
    for target in targets:
        if not target:
            continue
        parsed = _parse_file_contains_target(target)
        if parsed is not None:
            paths.add(parsed[0])
    return paths


def _question(question_id: str) -> CoDesignQuestion:
    for question in DEFAULT_QUESTIONS:
        if question.question_id == question_id:
            return question
    raise ValueError(f"Unknown question: {question_id}")


def _split_list(value: str) -> list[str]:
    separators = [";", "\n"]
    items = [value]
    for separator in separators:
        split_items = []
        for item in items:
            split_items.extend(item.split(separator))
        items = split_items
    return [item.strip() for item in items if item.strip()]


def _after_colon(value: str) -> str:
    if ":" in value:
        return value.split(":", 1)[1].strip()
    if "：" in value:
        return value.split("：", 1)[1].strip()
    return value.strip()


def _dedupe_strings(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result


def _file_contains_criteria_from_answer(value: str) -> list[CoDesignCriterionDraft]:
    criteria = []
    for item in _split_list(value):
        if "::" not in item:
            continue
        path, expected_text = item.split("::", 1)
        path = path.strip()
        if not path:
            continue
        target = json.dumps({"path": path, "contains": expected_text}, ensure_ascii=False)
        criteria.append(
            CoDesignCriterionDraft(
                description=f"{path} contains expected text",
                validation_type="file_contains",
                validation_target=target,
            )
        )
    return criteria


def _is_valid_file_contains_target(target: str | None) -> bool:
    if not target or not target.strip():
        return False
    text = target.strip()
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return False
        return (
            isinstance(payload, dict)
            and isinstance(payload.get("path"), str)
            and _is_valid_path_validation_target(payload["path"])
            and isinstance(payload.get("contains"), str)
        )
    if "::" not in text:
        return False
    path, _contains = text.split("::", 1)
    return _is_valid_path_validation_target(path)


def _infer_machine_criteria(intent: str, deliverables: list[str]) -> list[CoDesignCriterionDraft]:
    text = "\n".join([intent, *deliverables])
    file_path = _extract_path_like_validation_target(text)
    if not file_path:
        return []
    expected_text = _extract_expected_file_text(text)
    if expected_text is not None:
        return [
            CoDesignCriterionDraft(
                description=f"{file_path} contains expected text",
                validation_type="file_contains",
                validation_target=json.dumps({"path": file_path, "contains": expected_text}, ensure_ascii=False),
            )
        ]
    return [
        CoDesignCriterionDraft(
            description=f"{file_path} exists",
            validation_type="file_exists",
            validation_target=file_path,
        )
    ]


def _can_infer_deliverables_from_intent(intent: str) -> bool:
    return bool(_infer_deliverables_from_intent(intent))


def _can_infer_criteria_from_intent(intent: str, deliverables: list[str]) -> bool:
    inferred_deliverables = deliverables or _infer_deliverables_from_intent(intent)
    return bool(
        _infer_machine_criteria(intent, inferred_deliverables)
        or _infer_soft_review_criteria(intent, inferred_deliverables, [])
    )


def _extract_first_file_path(text: str) -> str | None:
    match = re.search(r"(?P<path>[\w./-]+\.(?:py|md|txt|json|yaml|yml|toml|html|css|js|ts))", text, re.IGNORECASE)
    if match is None:
        return None
    return normalize_path_validation_target(match.group("path"))


def _extract_expected_file_text(text: str) -> str | None:
    patterns = [
        r"containing\s+(?P<content>.+?)(?:[.;\n]|$)",
        r"contains?\s+the\s+exact\s+text\s*:?\s*(?P<content>.+?)(?:[.;\n]|$)",
        r"must\s+contain\s+(?P<content>.+?)(?:[.;\n]|$)",
        r"contains?\s+(?P<content>.+?)(?:[.;\n]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is None:
            continue
        content = match.group("content").strip().strip('"').strip("'").strip()
        if content:
            return _normalize_expected_text(content)
    return None


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return _split_list(value)
    if isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, dict):
                text = _string_from_mapping(item)
            else:
                text = str(item).strip()
            if text:
                items.append(text)
        return items
    return []


def _string_from_mapping(value: dict[str, Any]) -> str:
    for key in ("path", "file", "name", "title", "description"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
    return json.dumps(value, ensure_ascii=False)


def _coerce_criteria_list(value: Any) -> list[CoDesignCriterionDraft]:
    criteria = []
    for item in value if isinstance(value, list) else []:
        try:
            if isinstance(item, str):
                criteria.append(CoDesignCriterionDraft(description=item))
            elif isinstance(item, dict) and item.get("description"):
                criteria.append(_normalize_criterion(CoDesignCriterionDraft.model_validate(item)))
        except ValidationError:
            continue
    return criteria


def _normalize_criterion(criterion: CoDesignCriterionDraft) -> CoDesignCriterionDraft:
    if criterion.validation_type != "file_contains" or not criterion.validation_target:
        return criterion
    parsed = _parse_file_contains_target(criterion.validation_target)
    if parsed is None:
        return criterion
    path, expected_text = parsed
    criterion.validation_target = json.dumps(
        {"path": path, "contains": _normalize_expected_text(expected_text)},
        ensure_ascii=False,
    )
    return criterion


def _parse_file_contains_target(target: str) -> tuple[str, str] | None:
    text = target.strip()
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("path"), str)
            and payload["path"].strip()
            and isinstance(payload.get("contains"), str)
        ):
            return payload["path"].strip(), payload["contains"]
        return None
    if "::" not in text:
        return None
    path, expected_text = text.split("::", 1)
    if not path.strip():
        return None
    return path.strip(), expected_text


def _normalize_expected_text(value: str) -> str:
    text = value.strip()
    wrappers = [
        r"^the\s+exact\s+phrase\s+`(?P<content>.+)`$",
        r"^the\s+exact\s+text\s+`(?P<content>.+)`$",
        r"^exact\s+phrase\s+`(?P<content>.+)`$",
        r"^exact\s+text\s+`(?P<content>.+)`$",
        r"^the\s+exact\s+phrase\s+\"(?P<content>.+)\"$",
        r"^the\s+exact\s+text\s+\"(?P<content>.+)\"$",
        r"^exact\s+phrase\s+\"(?P<content>.+)\"$",
        r"^exact\s+text\s+\"(?P<content>.+)\"$",
        r"^the\s+text\s*:\s*(?P<content>.+)$",
        r"^text\s*:\s*(?P<content>.+)$",
        r"^the\s+phrase\s*:\s*(?P<content>.+)$",
        r"^phrase\s*:\s*(?P<content>.+)$",
    ]
    for wrapper in wrappers:
        match = re.match(wrapper, text, re.IGNORECASE)
        if match is not None:
            return match.group("content").strip()
    if ":" in text:
        label, content = text.split(":", 1)
        normalized_label = re.sub(r"\s+", " ", label.strip().lower())
        content = content.strip()
        if content and normalized_label in {
            "exactly",
            "contains",
            "content",
            "text",
            "the text",
            "phrase",
            "the phrase",
            "exact text",
            "the exact text",
            "exactly the text",
            "exact phrase",
            "the exact phrase",
            "exactly the phrase",
        }:
            return content.strip("`").strip('"').strip("'")
    return text.strip("`").strip('"').strip("'")


def _dedupe_questions(questions: list[CoDesignQuestion]) -> list[CoDesignQuestion]:
    seen = set()
    deduped = []
    for question in questions:
        key = question.question_id
        if key in seen:
            continue
        seen.add(key)
        deduped.append(question)
    return deduped


def _is_vague_text(value: str) -> bool:
    text = value.strip().lower()
    vague_terms = {
        "thing",
        "things",
        "stuff",
        "something",
        "artifact",
        "artifacts",
        "output",
        "result",
        "results",
        "improve",
        "optimize",
        "handle",
        "fix it",
        "make it better",
        "do it",
    }
    if text in vague_terms:
        return True
    return any(f" {term} " in f" {text} " for term in vague_terms if " " in term)


def _looks_file_based(deliverables: list[str]) -> bool:
    file_suffixes = (".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".html", ".css", ".js", ".ts")
    return any("/" in item or item.endswith(file_suffixes) or _extract_first_file_path(item) for item in deliverables)


def _has_executable_criterion(criteria: list[CoDesignCriterionDraft]) -> bool:
    return any(criterion.validation_type in {"file_exists", "file_contains", "command", "schema"} for criterion in criteria)
