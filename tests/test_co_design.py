import pytest

from metaloop.co_design import (
    CoDesignBrainstorm,
    CoDesignAgentError,
    CoDesignLockError,
    CoDesignDecision,
    CoDesignOption,
    CodexCoDesignInterviewer,
    CodexCoDesignBrainstormer,
    CoDesignAnswer,
    CoDesignRunner,
    CoDesignSession,
    CoDesignCriterionDraft,
    CoDesignInterviewerResult,
    MissionSpecReviewer,
    RuleCoDesignInterviewer,
    RuleCoDesignBrainstormer,
    apply_human_design_feedback,
    build_draft_from_options,
    is_design_approval,
    lock_design,
    mission_preview,
    render_design_review_markdown,
    review_preview,
    write_design_process_artifacts,
    write_design_artifacts,
    write_mission,
)
from metaloop.codex_adapter import CodexExecResult
from metaloop.mission_loader import load_mission_file


def test_co_design_builds_mission_from_complete_draft(tmp_path) -> None:
    draft = build_draft_from_options(
        intent="Create a CLI guide",
        deliverables=["README section"],
        criteria=["Guide explains installation"],
        file_exists=["README.md"],
        audience="technical users",
        constraints=["local first"],
        workspace_root=str(tmp_path),
        risk_level="low",
    )

    mission = CoDesignSession(draft).build_mission()

    assert mission.intent == "Create a CLI guide"
    assert mission.deliverables == ["README section"]
    assert len(mission.acceptance_criteria) == 2
    assert mission.acceptance_criteria[1].validation_type == "file_exists"
    assert mission.context["audience"] == "technical users"
    assert mission.policy.risk_level.value == "low"


def test_co_design_reports_required_missing_fields() -> None:
    session = CoDesignSession()

    missing = session.required_missing_questions()

    assert [question.question_id for question in missing] == ["intent", "deliverables", "criteria"]


def test_session_apply_patch_updates_draft() -> None:
    session = CoDesignSession()

    session.apply_patch(
        {
            "intent": "Create hello.txt for the local workspace",
            "deliverables": ["hello.txt"],
            "criteria": [
                {
                    "description": "hello.txt exists",
                    "validation_type": "file_exists",
                    "validation_target": "hello.txt",
                }
            ],
            "constraints": ["local only"],
        }
    )
    mission = session.build_mission()

    assert mission.intent == "Create hello.txt for the local workspace"
    assert mission.acceptance_criteria[0].validation_type == "file_exists"
    assert mission.context["constraints"] == ["local only"]


def test_session_apply_patch_can_reject_core_edits() -> None:
    session = CoDesignSession(
        build_draft_from_options(
            intent="Create original file for the workspace",
            deliverables=["original.txt"],
            criteria=["done"],
        )
    )

    session.apply_patch(
        {
            "intent": "Replace user intent",
            "deliverables": ["replacement.txt"],
            "criteria": [{"description": "replacement exists", "validation_type": "file_exists", "validation_target": "replacement.txt"}],
            "constraints": ["local only"],
        },
        allow_core_edits=False,
    )
    mission = session.build_mission()

    assert mission.intent == "Create original file for the workspace"
    assert mission.deliverables == ["original.txt"]
    assert mission.acceptance_criteria[0].description == "done"
    assert mission.acceptance_criteria[0].validation_type == "llm_review"
    assert mission.context["constraints"] == ["local only"]


def test_co_design_answers_questions_and_writes_mission(tmp_path) -> None:
    session = CoDesignSession()
    session.answer("intent", "Create hello.txt")
    session.answer("deliverables", "hello.txt")
    session.answer("criteria", "hello.txt exists")
    mission = session.build_mission()

    output = write_mission(mission, tmp_path / "mission.json")
    loaded = load_mission_file(output)

    assert loaded.intent == "Create hello.txt"
    assert loaded.deliverables == ["hello.txt"]


def test_co_design_writes_design_capsule_and_contract_artifacts(tmp_path) -> None:
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        file_exists=["hello.txt"],
        workspace_root=str(tmp_path),
    )
    mission = CoDesignSession(draft).build_mission()

    artifacts = write_design_artifacts(mission, tmp_path)

    assert artifacts["design_capsule"] == tmp_path / ".metaloop" / "design_capsule.json"
    assert artifacts["design_goal_contract"] == tmp_path / ".metaloop" / "design_goal_contract.json"
    assert artifacts["design_capsule"].exists()
    assert '"schema": "metaloop.mission_capsule"' in artifacts["design_capsule"].read_text(encoding="utf-8")
    assert '"required_evidence_summary"' in artifacts["design_goal_contract"].read_text(encoding="utf-8")


def test_co_design_v2_brainstorm_review_and_lock_artifacts(tmp_path) -> None:
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        file_exists=["hello.txt"],
        workspace_root=str(tmp_path),
    )
    mission = CoDesignSession(draft).build_mission()
    review = MissionSpecReviewer().review(mission)
    brainstorm = RuleCoDesignBrainstormer().expand(mission, draft, review)
    lock = CoDesignDecision(
        decision_id="decision_test",
        status="accepted",
        summary="Human approved the MVP route.",
    )

    artifacts = write_design_process_artifacts(
        mission,
        review,
        brainstorm,
        tmp_path,
        decisions=[lock],
    )

    assert artifacts["design_transcript"] == tmp_path / ".metaloop" / "design_transcript.jsonl"
    assert artifacts["design_draft"].exists()
    assert artifacts["design_review"].exists()
    assert artifacts["design_decisions"].exists()
    review_markdown = artifacts["design_review"].read_text(encoding="utf-8")
    assert "Goal Summary" in review_markdown
    assert "Technical Or Execution Route" in review_markdown
    assert "Decisions To Confirm" in review_markdown
    assert "brainstorm_expansion" in artifacts["design_transcript"].read_text(encoding="utf-8")


def test_design_review_markdown_contains_required_sections(tmp_path) -> None:
    draft = build_draft_from_options(
        intent="Prepare a repo summary",
        deliverables=["report.md"],
        criteria=["Report is clear"],
        workspace_root=str(tmp_path),
    )
    mission = CoDesignSession(draft).build_mission()
    review = MissionSpecReviewer().review(mission)
    brainstorm = CoDesignBrainstorm(
        options=[CoDesignOption(title="MVP", summary="Write the summary.")],
        recommended_option="MVP",
        risks=["Scope can drift."],
        unresolved_questions=["Confirm audience."],
    )

    markdown = render_design_review_markdown(mission, review, brainstorm)

    for section in [
        "Goal Summary",
        "Product Shape",
        "Deliverables",
        "Included / Not Included",
        "Technical Or Execution Route",
        "Acceptance Criteria",
        "Risks",
        "Decisions To Confirm",
    ]:
        assert section in markdown


def test_interactive_refinement_feedback_updates_compact_draft() -> None:
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        file_exists=["hello.txt"],
    )

    updated, decision = apply_human_design_feedback(draft, "out_of_scope: network calls; changing README.md")

    assert decision.status == "accepted"
    assert updated.out_of_scope == ["network calls", "changing README.md"]
    assert is_design_approval("确认") is True


def test_design_lock_artifact_records_locked_contract_paths(tmp_path) -> None:
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        file_exists=["hello.txt"],
        workspace_root=str(tmp_path),
    )
    mission = CoDesignSession(draft).build_mission()
    review = MissionSpecReviewer().review(mission)
    brainstorm = RuleCoDesignBrainstormer().expand(mission, draft, review)
    lock = lock_design(mission, workspace_root=tmp_path, mission_path=tmp_path / "mission.json", brainstorm=brainstorm)

    artifacts = write_design_process_artifacts(mission, review, brainstorm, tmp_path, lock=lock)

    payload = artifacts["design_lock"].read_text(encoding="utf-8")
    assert '"schema": "metaloop.co_design_lock"' in payload
    assert "design_capsule.json" in payload
    assert "design_goal_contract.json" in payload


def test_lock_design_rejects_unresolved_questions_without_accepted_decision(tmp_path) -> None:
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        file_exists=["hello.txt"],
        workspace_root=str(tmp_path),
    )
    mission = CoDesignSession(draft).build_mission()
    brainstorm = CoDesignBrainstorm(unresolved_questions=["Confirm target audience."])

    with pytest.raises(CoDesignLockError, match="unresolved decisions"):
        lock_design(mission, workspace_root=tmp_path, mission_path=tmp_path / "mission.json", brainstorm=brainstorm)


def test_lock_design_allows_unresolved_questions_after_explicit_acceptance(tmp_path) -> None:
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        file_exists=["hello.txt"],
        workspace_root=str(tmp_path),
    )
    mission = CoDesignSession(draft).build_mission()
    brainstorm = CoDesignBrainstorm(unresolved_questions=["Confirm target audience."])

    lock = lock_design(
        mission,
        workspace_root=tmp_path,
        mission_path=tmp_path / "mission.json",
        brainstorm=brainstorm,
        decisions=[CoDesignDecision(decision_id="decision_accept", status="accepted", summary="Approved as-is.")],
    )

    assert lock.unresolved_questions == ["Confirm target audience."]


def test_domain_profiles_add_useful_defaults_and_evidence_hints(tmp_path) -> None:
    skill_mission = CoDesignSession(
        build_draft_from_options(
            intent="Create a Codex skill for daily notes",
            workspace_root=str(tmp_path),
            domain_profile_id="codex_skill_creation",
        )
    ).build_mission()
    research_mission = CoDesignSession(
        build_draft_from_options(
            intent="Prepare deep research about API migration sources",
            workspace_root=str(tmp_path),
            domain_profile_id="deep_research",
        )
    ).build_mission()

    assert "SKILL.md" in skill_mission.deliverables
    assert any(criterion.validation_target == "SKILL.md" for criterion in skill_mission.acceptance_criteria)
    assert "validation commands or structural checks" in skill_mission.context["evidence_hints"][-1]
    assert "source_table.md" in research_mission.deliverables
    assert any(criterion.validation_type == "llm_review" for criterion in research_mission.acceptance_criteria)
    assert "freshness metadata for time-sensitive claims" in research_mission.context["evidence_hints"]


def test_co_design_runner_loops_until_reviewer_warnings_are_resolved() -> None:
    class StaticInterviewer:
        def interview(self, _draft):
            return CoDesignInterviewerResult()

    class AnswerProvider:
        def __init__(self) -> None:
            self.questions = []

        def answer(self, question, _draft, _review=None):
            self.questions.append(question.question_id)
            if question.question_id == "file_contains":
                return CoDesignAnswer(answer="hello.txt::hello from runner")
            return CoDesignAnswer()

    provider = AnswerProvider()
    result = CoDesignRunner(
        StaticInterviewer(),
        provider,
        max_rounds=4,
        max_questions_per_round=2,
        allow_core_edits=False,
        require_clean_review=True,
    ).run(
        build_draft_from_options(
            intent="Create hello.txt for the local workspace",
            deliverables=["hello.txt"],
            criteria=["hello.txt contains hello from runner"],
        )
    )

    assert result.converged is True
    assert len(result.rounds) >= 1
    assert result.mission.acceptance_criteria[-1].validation_type == "file_contains"


def test_mission_preview_contains_core_fields() -> None:
    draft = build_draft_from_options(
        intent="Summarize repo",
        deliverables=["summary"],
        criteria=["summary is concise"],
    )
    mission = CoDesignSession(draft).build_mission()

    preview = mission_preview(mission)

    assert "Summarize repo" in preview
    assert "summary is concise" in preview


def test_deep_questions_detect_vague_intent_and_file_validation_gap() -> None:
    draft = build_draft_from_options(
        intent="Improve stuff",
        deliverables=["hello.txt"],
        criteria=["it works"],
    )
    session = CoDesignSession(draft)

    questions = session.deep_questions()

    assert any(question.question_id == "intent" for question in questions)
    assert any(question.question_id == "file_exists" for question in questions)


def test_rule_interviewer_returns_same_deep_questions() -> None:
    draft = build_draft_from_options(intent="Do it", deliverables=["hello.txt"], criteria=["done"])

    result = RuleCoDesignInterviewer().interview(draft)

    assert any(question.question_id == "intent" for question in result.questions)


def test_deep_file_question_answer_creates_file_exists_criterion() -> None:
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        criteria=["hello.txt exists"],
    )
    session = CoDesignSession(draft)

    session.answer("file_exists", "hello.txt")
    mission = session.build_mission()

    assert any(
        criterion.validation_type == "file_exists" and criterion.validation_target == "hello.txt"
        for criterion in mission.acceptance_criteria
    )


def test_file_contains_question_answer_creates_machine_checkable_criterion() -> None:
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        criteria=["hello.txt has expected greeting"],
    )
    session = CoDesignSession(draft)

    session.answer("file_contains", "hello.txt::hello from co-design")
    mission = session.build_mission()

    assert any(
        criterion.validation_type == "file_contains" and "hello from co-design" in (criterion.validation_target or "")
        for criterion in mission.acceptance_criteria
    )


def test_mission_reviewer_blocks_vague_intent() -> None:
    draft = build_draft_from_options(
        intent="Do it",
        deliverables=["output"],
        criteria=["done"],
    )
    mission = CoDesignSession(draft).build_mission()

    review = MissionSpecReviewer().review(mission)

    assert review.passed is False
    assert any(finding.code == "vague_intent" for finding in review.blocking_findings)


def test_mission_reviewer_adds_spec_discipline_findings_conservatively(tmp_path) -> None:
    draft = build_draft_from_options(
        intent="Implement the full production-ready platform rewrite",
        deliverables=["src/a.py", "src/b.py", "src/c.py", "src/d.py", "src/e.py"],
        file_exists=["src/a.py"],
        workspace_root=str(tmp_path),
        risk_level="high",
    )
    mission = CoDesignSession(draft).build_mission()

    review = MissionSpecReviewer().review(mission)

    codes = {finding.code for finding in review.findings}
    assert review.passed is False
    assert {"scope_too_broad", "missing_non_goals", "unclear_authority", "missing_tradeoff_review", "needs_decomposition"} <= codes
    assert any(finding.code == "scope_too_broad" for finding in review.blocking_findings)


def test_mission_reviewer_warns_missing_non_goals_without_blocking_broad_task(tmp_path) -> None:
    draft = build_draft_from_options(
        intent="Implement the full app MVP",
        deliverables=["src/app.py", "src/api.py", "src/ui.py", "README.md"],
        file_exists=["src/app.py"],
        workspace_root=str(tmp_path),
        risk_level="medium",
    )
    mission = CoDesignSession(draft).build_mission()

    review = MissionSpecReviewer().review(mission)

    assert review.passed is True
    assert any(finding.code == "missing_non_goals" and finding.severity == "warning" for finding in review.findings)


def test_mission_reviewer_warns_on_manual_validation_for_file_task() -> None:
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        criteria=["hello.txt exists"],
    )
    mission = CoDesignSession(draft).build_mission()

    review = MissionSpecReviewer().review(mission)

    assert review.passed is True
    assert not any(finding.code == "manual_validation_for_file_task" for finding in review.findings)


def test_mission_reviewer_does_not_warn_when_file_task_has_executable_validation() -> None:
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        criteria=["manual smoke check"],
        file_exists=["hello.txt"],
    )
    mission = CoDesignSession(draft).build_mission()

    review = MissionSpecReviewer().review(mission)

    assert review.passed is True
    assert not any(finding.code == "manual_validation_for_file_task" for finding in review.findings)


def test_co_design_generates_hard_validators_for_engineering_tasks() -> None:
    draft = build_draft_from_options(
        intent="Implement a small CLI parser for the local workspace",
        deliverables=["src/parser.py"],
        criteria=["Parser is ready"],
    )
    mission = CoDesignSession(draft).build_mission()

    assert any(
        criterion.validation_type in {"file_exists", "file_contains", "command", "schema"}
        for criterion in mission.acceptance_criteria
    )
    assert mission.context["domain_profile_id"] == "engineering_development"
    assert all(criterion.validation_type != "manual" for criterion in mission.acceptance_criteria)


def test_file_deliverables_do_not_rely_only_on_manual_acceptance() -> None:
    draft = build_draft_from_options(
        intent="Create a local README for the tool",
        deliverables=["README.md"],
        criteria=["Looks good"],
    )
    mission = CoDesignSession(draft).build_mission()

    review = MissionSpecReviewer().review(mission)

    assert any(
        criterion.validation_type in {"file_exists", "file_contains", "command", "schema"}
        for criterion in mission.acceptance_criteria
    )
    assert not all(criterion.validation_type == "manual" for criterion in mission.acceptance_criteria)
    assert not any(finding.code == "manual_validation_for_file_task" and finding.severity == "warning" for finding in review.findings)


def test_deep_research_tasks_keep_llm_review_with_explicit_evidence() -> None:
    draft = build_draft_from_options(
        intent="Do deep research on current local inference strategies",
        deliverables=["report.md"],
        criteria=["The analysis is coherent and well supported"],
    )
    draft.domain_profile_id = "deep_research"
    mission = CoDesignSession(draft).build_mission()

    review = MissionSpecReviewer().review(mission)

    assert mission.context["domain_profile_id"] == "deep_research"
    assert any(criterion.validation_type == "llm_review" for criterion in mission.acceptance_criteria)
    assert any(criterion.validation_type in {"file_exists", "file_contains", "command", "schema"} for criterion in mission.acceptance_criteria)
    assert all(finding.code != "missing_executable_acceptance" for finding in review.findings)


def test_domain_profile_id_can_be_explicitly_preserved() -> None:
    draft = build_draft_from_options(
        intent="Create a Codex skill package",
        deliverables=["SKILL.md"],
        criteria=["Skill structure is complete"],
        domain_profile_id="codex_skill_creation",
    )
    mission = CoDesignSession(draft).build_mission()

    assert mission.context["domain_profile_id"] == "codex_skill_creation"


def test_mission_reviewer_blocks_missing_validation_target() -> None:
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
    )
    draft.criteria = [
        CoDesignCriterionDraft(
            description="file exists",
            validation_type="file_exists",
            validation_target=None,
        )
    ]
    mission = CoDesignSession(draft).build_mission()

    review = MissionSpecReviewer().review(mission)

    assert review.passed is False
    assert any(finding.code == "missing_validation_target" for finding in review.blocking_findings)


def test_mission_reviewer_blocks_command_validator_without_policy_allow() -> None:
    draft = build_draft_from_options(
        intent="Validate the repository with a local command",
        deliverables=["command output"],
        commands=["pwd"],
    )
    mission = CoDesignSession(draft).build_mission()

    review = MissionSpecReviewer().review(mission)

    assert review.passed is False
    assert any(finding.code == "command_validator_without_policy_allow" for finding in review.blocking_findings)


def test_mission_reviewer_blocks_invalid_file_contains_target() -> None:
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
    )
    draft.criteria = [
        CoDesignCriterionDraft(
            description="file contains greeting",
            validation_type="file_contains",
            validation_target="hello.txt",
        )
    ]
    mission = CoDesignSession(draft).build_mission()

    review = MissionSpecReviewer().review(mission)

    assert review.passed is False
    assert any(finding.code == "invalid_file_contains_target" for finding in review.blocking_findings)


def test_hard_validator_inference_extracts_paths_from_deliverable_sentences() -> None:
    draft = build_draft_from_options(
        intent="Create documentation for the local workspace",
        deliverables=["Create docs/guide.md with setup examples"],
        criteria=["Documentation is clear"],
    )
    mission = CoDesignSession(draft).build_mission()

    assert any(
        criterion.validation_type == "file_exists" and criterion.validation_target == "docs/guide.md"
        for criterion in mission.acceptance_criteria
    )
    assert not any(
        criterion.validation_type == "file_exists" and criterion.validation_target == "Create docs/guide.md with setup examples"
        for criterion in mission.acceptance_criteria
    )


def test_mission_reviewer_blocks_prose_file_exists_target() -> None:
    draft = build_draft_from_options(
        intent="Create documentation for the local workspace",
        deliverables=["docs/guide.md"],
        file_exists=["Create docs/guide.md with setup examples"],
    )
    mission = CoDesignSession(draft).build_mission()

    review = MissionSpecReviewer().review(mission)

    assert review.passed is False
    assert any(finding.code == "invalid_path_validation_target" for finding in review.blocking_findings)


def test_mission_reviewer_blocks_behavior_phrase_slash_target() -> None:
    draft = build_draft_from_options(
        intent="Upgrade count_words to handle punctuation and whitespace",
        deliverables=["Update count_words behavior and tests"],
        file_exists=["tabs/newlines"],
    )
    mission = CoDesignSession(draft).build_mission()

    review = MissionSpecReviewer().review(mission)

    assert review.passed is False
    assert any(finding.code == "invalid_path_validation_target" for finding in review.blocking_findings)


def test_behavior_phrase_with_slash_is_not_inferred_as_file_target() -> None:
    draft = build_draft_from_options(
        intent="Upgrade count_words to handle punctuation and whitespace",
        deliverables=["Update count_words behavior and tests"],
        criteria=["tabs/newlines behavior is covered"],
    )
    mission = CoDesignSession(draft).build_mission()

    assert not any(
        criterion.validation_type == "file_exists" and criterion.validation_target in {"tabs/newlines", "tabs/"}
        for criterion in mission.acceptance_criteria
    )


def test_directory_path_target_must_be_explicit_directory() -> None:
    valid = build_draft_from_options(
        intent="Create source directory for the local workspace",
        deliverables=["src/"],
        file_exists=["src/"],
    )
    invalid = build_draft_from_options(
        intent="Create source directory for the local workspace",
        deliverables=["src/"],
        file_exists=["src/app"],
    )

    assert MissionSpecReviewer().review(CoDesignSession(valid).build_mission()).passed is True
    review = MissionSpecReviewer().review(CoDesignSession(invalid).build_mission())
    assert review.passed is False
    assert any(finding.code == "invalid_path_validation_target" for finding in review.blocking_findings)


def test_lock_design_refuses_blocking_review(tmp_path) -> None:
    draft = build_draft_from_options(
        intent="Create documentation for the local workspace",
        deliverables=["docs/guide.md"],
        file_exists=["Create docs/guide.md with setup examples"],
        workspace_root=str(tmp_path),
    )
    mission = CoDesignSession(draft).build_mission()

    with pytest.raises(CoDesignLockError):
        lock_design(mission, workspace_root=tmp_path)


def test_mission_reviewer_blocks_invalid_budget() -> None:
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        file_exists=["hello.txt"],
        max_usd=-1,
    )
    mission = CoDesignSession(draft).build_mission()

    review = MissionSpecReviewer().review(mission)

    assert review.passed is False
    assert any(finding.code == "invalid_budget" for finding in review.blocking_findings)


def test_review_preview_contains_findings() -> None:
    draft = build_draft_from_options(intent="Do it", deliverables=["output"], criteria=["done"])
    mission = CoDesignSession(draft).build_mission()
    review = MissionSpecReviewer().review(mission)

    preview = review_preview(review)

    assert "vague_intent" in preview


class StaticCodexAdapter:
    def __init__(self, result: CodexExecResult) -> None:
        self.result = result

    def run(self, _prompt: str) -> CodexExecResult:
        return self.result


def test_codex_interviewer_parses_questions_and_patch(monkeypatch) -> None:
    result = CodexExecResult(
        final_message=(
            '{"questions":[{"question_id":"constraints","prompt":"Any boundaries?","required":false}],'
            '"draft_patch":{"audience":"technical users","deliverables":["hello.txt"],"criteria":[{"description":"bad","validation_type":"command","validation_target":"rm -rf /"}]},'
            '"notes":"ok"}'
        )
    )
    monkeypatch.setattr("metaloop.co_design.CodexExecAdapter", lambda _options: StaticCodexAdapter(result))

    interview = CodexCoDesignInterviewer().interview(build_draft_from_options(intent="Create hello file"))

    assert interview.questions[0].question_id == "constraints"
    assert interview.draft_patch["audience"] == "technical users"
    assert "deliverables" not in interview.draft_patch
    assert "criteria" not in interview.draft_patch
    assert interview.notes == "ok"


def test_codex_interviewer_autonomous_allows_core_patch_but_filters_command(monkeypatch) -> None:
    result = CodexExecResult(
        final_message=(
            '{"questions":[],'
            '"draft_patch":{"intent":"Create hello.txt for the local workspace",'
            '"deliverables":["hello.txt"],'
            '"criteria":['
            '{"description":"hello.txt contains greeting","validation_type":"file_contains","validation_target":"{\\"path\\":\\"hello.txt\\",\\"contains\\":\\"hello\\"}"},'
            '{"description":"danger","validation_type":"command","validation_target":"rm -rf /"}'
            ']}}'
        )
    )
    monkeypatch.setattr("metaloop.co_design.CodexExecAdapter", lambda _options: StaticCodexAdapter(result))

    interview = CodexCoDesignInterviewer(autonomous=True).interview(build_draft_from_options(intent="Create a file"))

    assert interview.draft_patch["intent"] == "Create hello.txt for the local workspace"
    assert interview.draft_patch["deliverables"] == ["hello.txt"]
    assert len(interview.draft_patch["criteria"]) == 1
    assert interview.draft_patch["criteria"][0]["validation_type"] == "file_contains"


def test_codex_interviewer_autonomous_infers_file_contains_criterion(monkeypatch) -> None:
    result = CodexExecResult(
        final_message=(
            '{"questions":[],'
            '"draft_patch":{"intent":"Create hello.txt containing hello from autonomous co-design",'
            '"deliverables":["Create hello.txt at the workspace root. The file must contain the exact text: hello from autonomous co-design"]}}'
        )
    )
    monkeypatch.setattr("metaloop.co_design.CodexExecAdapter", lambda _options: StaticCodexAdapter(result))

    interview = CodexCoDesignInterviewer(autonomous=True).interview(
        build_draft_from_options(intent="Create hello.txt containing hello from autonomous co-design")
    )

    assert interview.draft_patch["criteria"][0]["validation_type"] == "file_contains"
    assert "hello from autonomous co-design" in interview.draft_patch["criteria"][0]["validation_target"]


def test_codex_interviewer_autonomous_normalizes_structured_deliverables_and_wrapped_content(monkeypatch) -> None:
    result = CodexExecResult(
        final_message=(
            '{"questions":[],'
            '"draft_patch":{"intent":"Create hello.txt containing hello from autonomous co-design",'
            '"deliverables":[{"path":"hello.txt","description":"A text file"}],'
            '"criteria":[{"description":"hello.txt contains greeting",'
            '"validation_type":"file_contains",'
            '"validation_target":"{\\"path\\":\\"hello.txt\\",\\"contains\\":\\"the exact phrase `hello from autonomous co-design`\\"}"}]}}'
        )
    )
    monkeypatch.setattr("metaloop.co_design.CodexExecAdapter", lambda _options: StaticCodexAdapter(result))

    interview = CodexCoDesignInterviewer(autonomous=True).interview(
        build_draft_from_options(intent="Create hello.txt containing hello from autonomous co-design")
    )

    assert interview.draft_patch["deliverables"] == ["hello.txt"]
    assert '"contains": "hello from autonomous co-design"' in interview.draft_patch["criteria"][0]["validation_target"]


def test_codex_interviewer_autonomous_normalizes_the_text_prefix(monkeypatch) -> None:
    result = CodexExecResult(
        final_message=(
            '{"questions":[],'
            '"draft_patch":{"intent":"Create hello.txt containing hello from autonomous co-design",'
            '"deliverables":["Create hello.txt. The file must contain the text: hello from autonomous co-design"]}}'
        )
    )
    monkeypatch.setattr("metaloop.co_design.CodexExecAdapter", lambda _options: StaticCodexAdapter(result))

    interview = CodexCoDesignInterviewer(autonomous=True).interview(
        build_draft_from_options(intent="Create hello.txt containing hello from autonomous co-design")
    )

    assert '"contains": "hello from autonomous co-design"' in interview.draft_patch["criteria"][0]["validation_target"]


def test_codex_interviewer_autonomous_normalizes_exactly_prefix(monkeypatch) -> None:
    result = CodexExecResult(
        final_message=(
            '{"questions":[],'
            '"draft_patch":{"intent":"Create hello.txt containing hello from autonomous co-design",'
            '"deliverables":["hello.txt"],'
            '"criteria":[{"description":"hello.txt contains greeting",'
            '"validation_type":"file_contains",'
            '"validation_target":"{\\"path\\":\\"hello.txt\\",\\"contains\\":\\"exactly: hello from autonomous co-design\\"}"}]}}'
        )
    )
    monkeypatch.setattr("metaloop.co_design.CodexExecAdapter", lambda _options: StaticCodexAdapter(result))

    interview = CodexCoDesignInterviewer(autonomous=True).interview(
        build_draft_from_options(intent="Create hello.txt containing hello from autonomous co-design")
    )

    assert '"contains": "hello from autonomous co-design"' in interview.draft_patch["criteria"][0]["validation_target"]


def test_codex_interviewer_autonomous_normalizes_exactly_the_text_prefix(monkeypatch) -> None:
    result = CodexExecResult(
        final_message=(
            '{"questions":[],'
            '"draft_patch":{"intent":"Create hello.txt containing hello from autonomous co-design",'
            '"deliverables":["Create hello.txt. The file must contain exactly the text: hello from autonomous co-design"]}}'
        )
    )
    monkeypatch.setattr("metaloop.co_design.CodexExecAdapter", lambda _options: StaticCodexAdapter(result))

    interview = CodexCoDesignInterviewer(autonomous=True).interview(
        build_draft_from_options(intent="Create hello.txt containing hello from autonomous co-design")
    )

    assert '"contains": "hello from autonomous co-design"' in interview.draft_patch["criteria"][0]["validation_target"]


def test_codex_interviewer_autonomous_upgrades_file_exists_when_content_is_known(monkeypatch) -> None:
    result = CodexExecResult(
        final_message=(
            '{"questions":[],'
            '"draft_patch":{"intent":"Create hello.txt containing hello from autonomous co-design",'
            '"deliverables":["hello.txt"],'
            '"criteria":[{"description":"hello.txt exists",'
            '"validation_type":"file_exists",'
            '"validation_target":"hello.txt"}]}}'
        )
    )
    monkeypatch.setattr("metaloop.co_design.CodexExecAdapter", lambda _options: StaticCodexAdapter(result))

    interview = CodexCoDesignInterviewer(autonomous=True).interview(
        build_draft_from_options(intent="Create hello.txt containing hello from autonomous co-design")
    )

    assert interview.draft_patch["criteria"][0]["validation_type"] == "file_contains"
    assert "hello from autonomous co-design" in interview.draft_patch["criteria"][0]["validation_target"]


def test_codex_interviewer_autonomous_uses_seed_intent_to_upgrade_file_exists(monkeypatch) -> None:
    result = CodexExecResult(
        final_message=(
            '{"questions":[],'
            '"draft_patch":{"deliverables":["hello.txt"],'
            '"criteria":[{"description":"hello.txt exists",'
            '"validation_type":"file_exists",'
            '"validation_target":"hello.txt"}]}}'
        )
    )
    monkeypatch.setattr("metaloop.co_design.CodexExecAdapter", lambda _options: StaticCodexAdapter(result))

    interview = CodexCoDesignInterviewer(autonomous=True).interview(
        build_draft_from_options(intent="Create hello.txt containing hello from autonomous co-design")
    )

    assert interview.draft_patch["criteria"][0]["validation_type"] == "file_contains"
    assert "hello from autonomous co-design" in interview.draft_patch["criteria"][0]["validation_target"]


def test_codex_interviewer_ignores_malformed_patch(monkeypatch) -> None:
    result = CodexExecResult(
        final_message='{"questions":[],"draft_patch":{"constraints":["ok"],"criteria":[{"description":"bad","validation_type":"danger"}]}}'
    )
    monkeypatch.setattr("metaloop.co_design.CodexExecAdapter", lambda _options: StaticCodexAdapter(result))

    interview = CodexCoDesignInterviewer().interview(build_draft_from_options(intent="Create hello file"))

    assert interview.draft_patch == {"constraints": ["ok"]}


def test_codex_interviewer_errors_when_agent_unavailable(monkeypatch) -> None:
    result = CodexExecResult(returncode=1, stderr="provider unavailable")
    monkeypatch.setattr("metaloop.co_design.CodexExecAdapter", lambda _options: StaticCodexAdapter(result))

    with pytest.raises(CoDesignAgentError, match="provider unavailable"):
        CodexCoDesignInterviewer().interview(
            build_draft_from_options(intent="Do it", deliverables=["hello.txt"], criteria=["done"])
        )


def test_codex_brainstormer_errors_when_agent_unavailable(monkeypatch, tmp_path) -> None:
    result = CodexExecResult(returncode=1, stderr="provider unavailable")
    monkeypatch.setattr("metaloop.co_design.CodexExecAdapter", lambda _options: StaticCodexAdapter(result))
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        file_exists=["hello.txt"],
        workspace_root=str(tmp_path),
    )
    mission = CoDesignSession(draft).build_mission()
    review = MissionSpecReviewer().review(mission)

    with pytest.raises(CoDesignAgentError, match="provider unavailable"):
        CodexCoDesignBrainstormer().expand(mission, draft, review)


def test_codex_brainstormer_parses_expansion_payload(monkeypatch, tmp_path) -> None:
    result = CodexExecResult(
        final_message=(
            '{"options":[{"title":"MVP","summary":"Ship the smallest useful artifact.",'
            '"tradeoffs":["fast"],"risks":["narrow"]}],'
            '"recommended_option":"MVP","mvp":["hello.txt"],"v1":["add validation"],'
            '"later":["split follow-up"],"risks":["scope drift"],'
            '"overlooked_points":["non-goals"],"unresolved_questions":["confirm scope"],"notes":"ok"}'
        )
    )
    monkeypatch.setattr("metaloop.co_design.CodexExecAdapter", lambda _options: StaticCodexAdapter(result))
    draft = build_draft_from_options(
        intent="Create hello.txt for the local workspace",
        deliverables=["hello.txt"],
        file_exists=["hello.txt"],
        workspace_root=str(tmp_path),
    )
    mission = CoDesignSession(draft).build_mission()
    review = MissionSpecReviewer().review(mission)

    brainstorm = CodexCoDesignBrainstormer().expand(mission, draft, review)

    assert brainstorm.recommended_option == "MVP"
    assert brainstorm.options[0].tradeoffs == ["fast"]
    assert brainstorm.unresolved_questions == ["confirm scope"]
