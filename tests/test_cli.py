import json
from pathlib import Path

import pytest

from metaloop.agents import RuleBasedRoleAgentBackend
from metaloop.cli import main
from metaloop.codex_adapter import CodexExecOptions
from metaloop.capsule import ClosureOutcome, LifecycleState, MissionCapsule
from metaloop.co_design import CoDesignAnswer, CoDesignBrainstorm, CoDesignInterviewerResult, CoDesignQuestion
from metaloop.co_design import build_draft_from_options
from metaloop.design_store import CoDesignCheckpointStore
from metaloop.goal import RedesignProposal, ReviewRoute, VerificationResult, VerificationStatus
from metaloop.goal_runtime import GoalRuntimeResult
from metaloop.run_artifacts import StructuredRunManifest
from metaloop.schemas import StepResult, StepStatus
from metaloop.schemas import AcceptanceCriteria, KernelState, MissionSpec, PolicyScope, RunStatus
from metaloop.storage import SQLiteRunStore
from metaloop.workers import CodexExecWorkerBackend


@pytest.fixture(autouse=True)
def _use_rule_role_agents_for_cli_tests(monkeypatch):
    monkeypatch.setattr("metaloop.cli.CodexRoleAgentBackend", lambda _options: RuleBasedRoleAgentBackend())


def test_cli_run_persists_state(tmp_path, capsys) -> None:
    db_path = tmp_path / "runs.sqlite"

    exit_code = main(["run", "Create a dummy artifact", "--db", str(db_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "status: completed" in output
    assert SQLiteRunStore(db_path).list_runs()


def test_cli_empty_command_opens_shell(monkeypatch, tmp_path, capsys) -> None:
    calls = {}

    class CapturingShell:
        def __init__(self, **kwargs) -> None:
            calls.update(kwargs)

        def run(self) -> int:
            return 0

    monkeypatch.setattr("metaloop.cli.TuiShell", CapturingShell)

    exit_code = main([])

    assert exit_code == 0
    assert calls["workspace"] == Path(".").expanduser().resolve()
    assert calls["confirm_actions"] is True
    assert calls["user_agent"].__class__.__name__ == "CodexSdkUserAgent"


def test_cli_shell_no_confirm_passes_confirmation_mode(monkeypatch, tmp_path, capsys) -> None:
    calls = {}

    class CapturingShell:
        def __init__(self, **kwargs) -> None:
            calls.update(kwargs)

        def run(self) -> int:
            return 0

    monkeypatch.setattr("metaloop.cli.TuiShell", CapturingShell)

    exit_code = main(["shell", "--workspace", str(tmp_path), "--no-confirm"])

    assert exit_code == 0
    assert calls["workspace"] == tmp_path.resolve()
    assert calls["confirm_actions"] is False


def test_cli_shell_can_use_local_user_agent(monkeypatch, tmp_path, capsys) -> None:
    calls = {}

    class CapturingShell:
        def __init__(self, **kwargs) -> None:
            calls.update(kwargs)

        def run(self) -> int:
            return 0

    monkeypatch.setattr("metaloop.cli.TuiShell", CapturingShell)

    exit_code = main(["shell", "--workspace", str(tmp_path), "--user-agent", "local"])

    assert exit_code == 0
    assert calls["user_agent"].__class__.__name__ == "UserAgent"


def test_cli_shell_reset_user_agent_thread_deletes_only_thread_file(monkeypatch, tmp_path, capsys) -> None:
    calls = {}
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    thread_path = metaloop_dir / "user_agent_thread.json"
    mission_path = metaloop_dir / "mission.json"
    thread_path.write_text('{"thread_id":"thread_old"}', encoding="utf-8")
    mission_path.write_text('{"intent":"keep me"}', encoding="utf-8")

    class CapturingShell:
        def __init__(self, **kwargs) -> None:
            calls.update(kwargs)

        def run(self) -> int:
            return 0

    monkeypatch.setattr("metaloop.cli.TuiShell", CapturingShell)

    exit_code = main(["shell", "--workspace", str(tmp_path), "--reset-user-agent-thread"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "user_agent_thread: reset" in output
    assert not thread_path.exists()
    assert mission_path.exists()
    assert calls == {}


def test_cli_shell_reset_user_agent_thread_is_idempotent(tmp_path, capsys) -> None:
    exit_code = main(["shell", "--workspace", str(tmp_path), "--reset-user-agent-thread"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "user_agent_thread: already_reset" in output


def test_cli_design_writes_mission_file(tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"
    review_path = tmp_path / "review.json"

    exit_code = main([
        "design",
        "--intent",
        "Create hello.txt",
        "--deliverable",
        "hello.txt",
        "--file-exists",
        "hello.txt",
        "--workspace",
        str(tmp_path),
        "--output",
        str(mission_path),
        "--review-output",
        str(review_path),
        "--no-interactive",
    ])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "mission:" in output
    assert "review:" in output
    assert mission_path.exists()
    assert review_path.exists()


def test_cli_design_defaults_to_workspace_metaloop_mission(tmp_path, capsys) -> None:
    exit_code = main([
        "design",
        "--intent",
        "Create hello.txt",
        "--deliverable",
        "hello.txt",
        "--file-exists",
        "hello.txt",
        "--workspace",
        str(tmp_path),
        "--no-interactive",
    ])
    capsys.readouterr()

    assert exit_code == 0
    assert (tmp_path / "metaloop.mission.json").exists()


def test_cli_design_noninteractive_refuses_to_lock_unresolved_questions(monkeypatch, tmp_path, capsys) -> None:
    class UnresolvedBrainstormer:
        def expand(self, _mission, _draft, _review):
            return CoDesignBrainstorm(unresolved_questions=["Confirm target runtime."])

    monkeypatch.setattr("metaloop.cli.RuleCoDesignBrainstormer", UnresolvedBrainstormer)

    exit_code = main([
        "design",
        "--intent",
        "Create hello.txt",
        "--deliverable",
        "hello.txt",
        "--file-exists",
        "hello.txt",
        "--workspace",
        str(tmp_path),
        "--no-interactive",
    ])
    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert exit_code == 1
    assert "unresolved decisions" in output
    assert not (tmp_path / "metaloop.mission.json").exists()
    assert not (tmp_path / ".metaloop" / "design_lock.json").exists()


def test_cli_design_reports_capsule_contract_readiness_and_writes_design_artifacts(tmp_path, capsys) -> None:
    exit_code = main([
        "design",
        "--intent",
        "Create hello.txt",
        "--deliverable",
        "hello.txt",
        "--file-exists",
        "hello.txt",
        "--workspace",
        str(tmp_path),
        "--no-interactive",
    ])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "capsule_contract: ready" in output
    assert "design_capsule:" in output
    assert "design_goal_contract:" in output
    assert (tmp_path / ".metaloop" / "design_capsule.json").exists()
    assert (tmp_path / ".metaloop" / "design_goal_contract.json").exists()
    assert (tmp_path / ".metaloop" / "design_transcript.jsonl").exists()
    assert (tmp_path / ".metaloop" / "design_draft.md").exists()
    assert (tmp_path / ".metaloop" / "design_review.md").exists()
    assert (tmp_path / ".metaloop" / "design_decisions.json").exists()
    assert (tmp_path / ".metaloop" / "design_lock.json").exists()
    assert not (tmp_path / ".metaloop" / "mission_capsule.json").exists()


def test_cli_design_default_output_suggests_simple_run(tmp_path, capsys) -> None:
    exit_code = main([
        "design",
        "--intent",
        "Create hello.txt",
        "--deliverable",
        "hello.txt",
        "--file-exists",
        "hello.txt",
        "--workspace",
        str(tmp_path),
        "--no-interactive",
    ])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "next: metaloop run" in output
    assert "--mission" not in output.split("next:", 1)[1]


def test_cli_design_quotes_next_command_for_paths_with_spaces(tmp_path, capsys) -> None:
    workspace = tmp_path / "workspace with spaces"
    mission_path = tmp_path / "mission file.json"

    exit_code = main([
        "design",
        "--intent",
        "Create hello.txt",
        "--deliverable",
        "hello.txt",
        "--file-exists",
        "hello.txt",
        "--workspace",
        str(workspace),
        "--output",
        str(mission_path),
        "--no-interactive",
    ])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert f"metaloop run --mission '{mission_path}'" in output


def test_cli_design_json_is_stdout_clean_and_non_interactive(tmp_path, capsys) -> None:
    exit_code = main([
        "design",
        "--intent",
        "Create hello.txt",
        "--deliverable",
        "hello.txt",
        "--file-exists",
        "hello.txt",
        "--workspace",
        str(tmp_path),
        "--json",
    ])
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["intent"] == "Create hello.txt"
    assert "MetaLoop Co-Design" not in captured.out
    assert captured.err == ""


def test_cli_design_json_missing_fields_fails_without_prompt(tmp_path, capsys) -> None:
    exit_code = main(["design", "--output", str(tmp_path / "mission.json"), "--json"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "missing: intent, deliverables, criteria" in captured.err


def test_cli_design_accepts_file_contains_criterion(tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"

    exit_code = main([
        "design",
        "--intent",
        "Create hello.txt containing hello from co-design",
        "--deliverable",
        "hello.txt",
        "--file-contains",
        "hello.txt::hello from co-design",
        "--workspace",
        str(tmp_path),
        "--output",
        str(mission_path),
        "--no-interactive",
        "--strict-review",
    ])
    capsys.readouterr()

    mission_text = mission_path.read_text(encoding="utf-8")
    assert exit_code == 0
    assert '"validation_type":"file_contains"' in mission_text.replace(" ", "")
    assert "hello from co-design" in mission_text


def test_cli_design_fails_when_required_fields_missing(tmp_path, capsys) -> None:
    exit_code = main(["design", "--output", str(tmp_path / "mission.json"), "--no-interactive"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "missing: intent, deliverables, criteria" in captured.err


def test_cli_design_strict_review_blocks_bad_spec(tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"

    exit_code = main([
        "design",
        "--intent",
        "Do it",
        "--deliverable",
        "output",
        "--criterion",
        "done",
        "--output",
        str(mission_path),
        "--no-interactive",
        "--strict-review",
    ])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "MissionSpec review failed" in captured.err
    assert not mission_path.exists()


def test_cli_design_blocks_invalid_contract_lock_without_strict_review(tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"

    exit_code = main([
        "design",
        "--intent",
        "Create documentation for the local workspace",
        "--deliverable",
        "docs/guide.md",
        "--file-exists",
        "Create docs/guide.md with setup examples",
        "--output",
        str(mission_path),
        "--workspace",
        str(tmp_path),
        "--no-interactive",
    ])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "refusing to lock invalid Co-Design contract" in captured.err
    assert "invalid_path_validation_target" in captured.err
    assert not mission_path.exists()
    assert (tmp_path / ".metaloop" / "design_review.md").exists()
    assert not (tmp_path / ".metaloop" / "design_lock.json").exists()
    assert not (tmp_path / ".metaloop" / "design_capsule.json").exists()
    assert not (tmp_path / ".metaloop" / "design_goal_contract.json").exists()


def test_cli_design_blocks_behavior_phrase_slash_file_exists(tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"

    exit_code = main([
        "design",
        "--intent",
        "Upgrade count_words behavior",
        "--deliverable",
        "Update count_words behavior and tests",
        "--file-exists",
        "tabs/newlines",
        "--output",
        str(mission_path),
        "--workspace",
        str(tmp_path),
        "--no-interactive",
    ])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "invalid_path_validation_target" in captured.err
    assert not mission_path.exists()


def test_cli_design_interactive_deep_question_creates_file_exists(monkeypatch, tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"
    answers = iter(["technical users", "local-only", "hello.txt"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    exit_code = main([
        "design",
        "--interviewer",
        "rule",
        "--intent",
        "Create hello.txt for the local workspace",
        "--deliverable",
        "hello.txt",
        "--criterion",
        "hello exists",
        "--output",
        str(mission_path),
    ])
    capsys.readouterr()

    assert exit_code == 0
    assert '"validation_type":"file_exists"' in mission_path.read_text(encoding="utf-8").replace(" ", "")


def test_cli_design_refinement_shows_feedback_progress(monkeypatch, tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"
    answers = iter(["acceptance: final report includes baseline comparison", "approve"])

    monkeypatch.setattr("metaloop.ui.MetaLoopUI._ask_editor", lambda _self, _label: next(answers))
    monkeypatch.setattr("builtins.input", lambda _prompt="": "1")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    exit_code = main([
        "design",
        "--interviewer",
        "rule",
        "--brainstormer",
        "rule",
        "--intent",
        "Create report.md documenting the baseline comparison for the local research run",
        "--deliverable",
        "report.md",
        "--file-exists",
        "report.md",
        "--output",
        str(mission_path),
        "--workspace",
        str(tmp_path),
        "--no-deep",
    ])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "feedback: received" in output
    assert "feedback: applied" in output
    assert "final report includes baseline comparison" in mission_path.read_text(encoding="utf-8")


def test_cli_design_resume_uses_saved_draft(monkeypatch, tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"
    state_path = tmp_path / "design.session.json"
    CoDesignCheckpointStore(state_path).save(
        build_draft_from_options(
            intent="Create hello.txt for the local workspace",
            deliverables=["hello.txt"],
            criteria=["hello exists"],
        ),
        [],
    )
    assert state_path.exists()

    answers = iter(["hello.txt"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    exit_code = main([
        "design",
        "--interviewer",
        "rule",
        "--resume",
        "--output",
        str(mission_path),
        "--design-state",
        str(state_path),
    ])
    capsys.readouterr()

    assert exit_code == 0
    assert mission_path.exists()
    assert not state_path.exists()
    assert '"validation_type":"file_exists"' in mission_path.read_text(encoding="utf-8").replace(" ", "")


def test_cli_design_codex_interviewer_cannot_create_core_mission(monkeypatch, tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"

    class PatchInterviewer:
        def __init__(self, _options: CodexExecOptions, *, autonomous: bool = False) -> None:
            assert autonomous is False
            pass

        def interview(self, draft):
            if any(criterion.validation_type == "file_contains" for criterion in draft.criteria):
                return CoDesignInterviewerResult()
            return CoDesignInterviewerResult(
                draft_patch={
                    "intent": "Create hello.txt for the local workspace",
                    "deliverables": ["hello.txt"],
                    "criteria": [
                        {
                            "description": "hello.txt exists",
                            "validation_type": "file_exists",
                            "validation_target": "hello.txt",
                        }
                    ],
                }
            )

    monkeypatch.setattr("metaloop.cli.CodexCoDesignInterviewer", PatchInterviewer)

    exit_code = main([
        "design",
        "--interviewer",
        "codex",
        "--output",
        str(mission_path),
        "--no-interactive",
        "--strict-review",
    ])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "missing: intent, deliverables, criteria" in captured.err
    assert not mission_path.exists()


def test_cli_design_codex_interviewer_may_enrich_optional_context(monkeypatch, tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"

    class ContextPatchInterviewer:
        def __init__(self, _options: CodexExecOptions, *, autonomous: bool = False) -> None:
            assert autonomous is False
            pass

        def interview(self, draft):
            if any(criterion.validation_type == "file_contains" for criterion in draft.criteria):
                return CoDesignInterviewerResult()
            return CoDesignInterviewerResult(
                draft_patch={
                    "intent": "Do not override",
                    "constraints": ["local only"],
                    "out_of_scope": ["network calls"],
                }
            )

    monkeypatch.setattr("metaloop.cli.CodexCoDesignInterviewer", ContextPatchInterviewer)

    exit_code = main([
        "design",
        "--interviewer",
        "codex",
        "--intent",
        "Create hello.txt for the local workspace",
        "--deliverable",
        "hello.txt",
        "--file-exists",
        "hello.txt",
        "--output",
        str(mission_path),
        "--no-interactive",
        "--strict-review",
    ])
    capsys.readouterr()

    mission_text = mission_path.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "Create hello.txt for the local workspace" in mission_text
    assert "Do not override" not in mission_text
    assert "local only" in mission_text


def test_cli_design_defaults_to_codex_interviewer_after_initial_intent(monkeypatch, tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"
    answers = iter(["Create hello.txt containing hello from option flow", "1", "1"])
    captured = {"codex": False}

    class OptionInterviewer:
        def __init__(self, _options: CodexExecOptions, *, autonomous: bool = False) -> None:
            captured["codex"] = True
            assert autonomous is False

        def interview(self, draft):
            if not draft.deliverables:
                return CoDesignInterviewerResult(
                    questions=[
                        CoDesignQuestion(
                            question_id="deliverables",
                            prompt="选择交付物",
                            options=["hello.txt"],
                        )
                    ],
                    draft_patch={
                        "constraints": ["local only"],
                    },
                )
            if not draft.criteria:
                return CoDesignInterviewerResult(
                    questions=[
                        CoDesignQuestion(
                            question_id="file_contains",
                            prompt="选择验收方式",
                            options=["hello.txt::hello from option flow"],
                        )
                    ]
                )
            return CoDesignInterviewerResult()

    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr("metaloop.cli.CodexCoDesignInterviewer", OptionInterviewer)

    exit_code = main([
        "design",
        "--output",
        str(mission_path),
    ])
    capsys.readouterr()

    mission_text = mission_path.read_text(encoding="utf-8")
    assert exit_code == 0
    assert captured["codex"] is True
    assert "hello from option flow" in mission_text


def test_cli_design_autonomous_codex_can_complete_core_mission(monkeypatch, tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"

    class AutonomousInterviewer:
        def __init__(self, _options: CodexExecOptions, *, autonomous: bool = False) -> None:
            assert autonomous is True

        def interview(self, _draft):
            return CoDesignInterviewerResult(
                draft_patch={
                    "intent": "Create hello.txt for the local workspace",
                    "deliverables": ["hello.txt"],
                    "criteria": [
                        {
                            "description": "hello.txt contains expected greeting",
                            "validation_type": "file_contains",
                            "validation_target": '{"path":"hello.txt","contains":"hello from autonomous co-design"}',
                        }
                    ],
                    "constraints": ["local only"],
                }
            )

    monkeypatch.setattr("metaloop.cli.CodexCoDesignInterviewer", AutonomousInterviewer)

    exit_code = main([
        "design",
        "--interviewer",
        "codex",
        "--autonomous",
        "--intent",
        "Create a hello file",
        "--output",
        str(mission_path),
        "--no-interactive",
    ])
    capsys.readouterr()

    assert exit_code == 0
    mission_text = mission_path.read_text(encoding="utf-8")
    assert '"validation_type":"file_contains"' in mission_text.replace(" ", "")
    assert "hello from autonomous co-design" in mission_text


def test_cli_design_autonomous_runs_multiple_co_design_rounds(monkeypatch, tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"
    calls = {"answers": 0}

    class PartialInterviewer:
        def __init__(self, _options: CodexExecOptions, *, autonomous: bool = False) -> None:
            assert autonomous is True

        def interview(self, draft):
            if any(criterion.validation_type == "file_contains" for criterion in draft.criteria):
                return CoDesignInterviewerResult()
            return CoDesignInterviewerResult(
                draft_patch={
                    "intent": "Create hello.txt for the local workspace",
                    "deliverables": ["hello.txt"],
                    "criteria": [{"description": "hello.txt has expected content"}],
                }
            )

    class FillingAnswerProvider:
        def __init__(self, _options: CodexExecOptions) -> None:
            pass

        def answer(self, question, _draft, _review=None):
            calls["answers"] += 1
            if question.question_id == "file_contains":
                return CoDesignAnswer(answer="hello.txt::hello from multi-round co-design")
            return CoDesignAnswer()

    monkeypatch.setattr("metaloop.cli.CodexCoDesignInterviewer", PartialInterviewer)
    monkeypatch.setattr("metaloop.cli.CodexCoDesignAnswerProvider", FillingAnswerProvider)

    exit_code = main([
        "design",
        "--interviewer",
        "codex",
        "--autonomous",
        "--intent",
        "Create a hello file",
        "--output",
        str(mission_path),
        "--no-interactive",
    ])
    capsys.readouterr()

    mission_text = mission_path.read_text(encoding="utf-8")
    assert exit_code == 0
    assert calls["answers"] == 0
    assert '"validation_type":"file_exists"' in mission_text.replace(" ", "")


def test_cli_design_autonomous_requires_seed_intent(monkeypatch, tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"

    exit_code = main([
        "design",
        "--interviewer",
        "codex",
        "--autonomous",
        "--output",
        str(mission_path),
        "--no-interactive",
    ])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "requires an initial --intent seed" in captured.err
    assert not mission_path.exists()


def test_cli_design_no_interactive_keeps_existing_behavior_for_basic_file_tasks(tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"

    exit_code = main([
        "design",
        "--intent",
        "Create hello.txt",
        "--deliverable",
        "hello.txt",
        "--workspace",
        str(tmp_path),
        "--output",
        str(mission_path),
        "--no-interactive",
    ])
    capsys.readouterr()

    mission_text = mission_path.read_text(encoding="utf-8")
    assert exit_code == 0
    assert '"validation_type":"file_exists"' in mission_text.replace(" ", "")
    assert '"domain_profile_id":"engineering_development"' in mission_text.replace(" ", "")
    capsule_path = tmp_path / ".metaloop" / "design_capsule.json"
    assert capsule_path.exists()
    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    assert capsule["schema"] == "metaloop.mission_capsule"
    assert capsule["domain_profile_id"] == "engineering_development"
    assert (tmp_path / ".metaloop" / "design_goal_contract.json").exists()
    status_code = main(["status", "--workspace", str(tmp_path), "--json"])
    status = json.loads(capsys.readouterr().out)
    assert status_code == 0
    assert status["capsule"]["state"] == "ready"
    assert status["capsule"]["path"].endswith("design_capsule.json")


def test_cli_design_no_interactive_writes_co_design_v2_process_artifacts(tmp_path, capsys) -> None:
    mission_path = tmp_path / "mission.json"

    exit_code = main([
        "design",
        "--intent",
        "Create hello.txt for the local workspace",
        "--deliverable",
        "hello.txt",
        "--file-exists",
        "hello.txt",
        "--workspace",
        str(tmp_path),
        "--output",
        str(mission_path),
        "--no-interactive",
    ])
    capsys.readouterr()

    metaloop_dir = tmp_path / ".metaloop"
    lock = json.loads((metaloop_dir / "design_lock.json").read_text(encoding="utf-8"))
    transcript = (metaloop_dir / "design_transcript.jsonl").read_text(encoding="utf-8")
    review = (metaloop_dir / "design_review.md").read_text(encoding="utf-8")
    mission = json.loads(mission_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert lock["schema"] == "metaloop.co_design_lock"
    assert lock["approval_source"] == "auto_non_interactive"
    assert "brainstorm_expansion" in transcript
    assert "Human Design Review" not in review
    assert "Goal Summary" in review
    assert mission["locked"] is True


def test_cli_list_runs(tmp_path, capsys) -> None:
    db_path = tmp_path / "runs.sqlite"
    main(["run", "Create a dummy artifact", "--db", str(db_path)])
    capsys.readouterr()

    exit_code = main(["list", "--db", str(db_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "completed" in output


def test_cli_strict_exit_code_for_next_task_proposal(tmp_path, capsys) -> None:
    db_path = tmp_path / "runs.sqlite"

    exit_code = main([
        "run",
        "Please split this into a next task proposal",
        "--db",
        str(db_path),
        "--strict-exit-code",
    ])
    capsys.readouterr()

    assert exit_code == 2


def test_cli_codex_no_output_schema_flag(monkeypatch, tmp_path, capsys) -> None:
    captured = {}

    class CapturingCodexWorker:
        def __init__(self, options: CodexExecOptions) -> None:
            captured["use_output_schema"] = options.use_output_schema
            self.worker = CodexExecWorkerBackend(options)

        def run_step(self, *args, **kwargs):
            from metaloop.schemas import StepResult, StepStatus

            step = args[3]
            return StepResult(step_id=step.step_id, status=StepStatus.SUCCESS)

    monkeypatch.setattr("metaloop.cli.CodexExecWorkerBackend", CapturingCodexWorker)

    exit_code = main([
        "run",
        "Create a dummy artifact",
        "--worker",
        "codex",
        "--no-output-schema",
        "--db",
        str(tmp_path / "runs.sqlite"),
    ])
    capsys.readouterr()

    assert exit_code == 0
    assert captured["use_output_schema"] is False


def test_cli_codex_worker_uses_mission_workspace(monkeypatch, tmp_path, capsys) -> None:
    mission_workspace = tmp_path / "mission-workspace"
    mission_workspace.mkdir()
    mission_path = tmp_path / "mission.json"
    mission_path.write_text(
        (
            '{"intent":"Create a dummy artifact",'
            '"acceptance_criteria":[{"description":"done"}],'
            f'"policy":{{"workspace_root":"{mission_workspace}"}}'
            "}"
        ),
        encoding="utf-8",
    )
    captured = {}

    class CapturingCodexWorker:
        def __init__(self, options: CodexExecOptions) -> None:
            captured["working_directory"] = options.working_directory

        def run_step(self, *args, **kwargs):
            step = args[3]
            return StepResult(step_id=step.step_id, status=StepStatus.SUCCESS)

    monkeypatch.setattr("metaloop.cli.CodexExecWorkerBackend", CapturingCodexWorker)

    exit_code = main([
        "run",
        "--mission",
        str(mission_path),
        "--worker",
        "codex",
        "--db",
        str(tmp_path / "runs.sqlite"),
    ])
    capsys.readouterr()

    assert exit_code == 0
    assert captured["working_directory"] == str(mission_workspace)


def test_cli_compile_writes_goal_objective(tmp_path, capsys) -> None:
    mission_path = tmp_path / "metaloop.mission.json"
    goal_path = tmp_path / ".metaloop" / "goal.txt"
    mission_path.write_text(
        (
            '{"intent":"Create hello.txt",'
            '"deliverables":["hello.txt"],'
            '"acceptance_criteria":[{"description":"hello.txt exists","validation_type":"file_exists","validation_target":"hello.txt"}],'
            '"policy":{"workspace_root":"."}}'
        ),
        encoding="utf-8",
    )

    exit_code = main(["compile", "--workspace", str(tmp_path), "--output", str(goal_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert f"goal: {goal_path}" in output
    assert '"schema": "metaloop.goal_contract"' in goal_path.read_text(encoding="utf-8")


def test_cli_verify_reports_completed_pending_human_acceptance(tmp_path, capsys) -> None:
    mission_path = tmp_path / "metaloop.mission.json"
    report_path = tmp_path / ".metaloop" / "execution_report.json"
    report_path.parent.mkdir()
    mission_path.write_text(
        (
            '{"run_id":"run_test","intent":"Assess UX",'
            '"acceptance_criteria":[{"description":"UX is acceptable","validation_type":"manual"}],'
            '"policy":{"workspace_root":"."}}'
        ),
        encoding="utf-8",
    )
    report_path.write_text(
        '{"schema":"metaloop.execution_report","version":"1.0","mission_id":"run_test","status":"completed","summary":"done"}',
        encoding="utf-8",
    )

    exit_code = main(["verify", "--workspace", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "verification: completed_pending_human_acceptance" in output


def test_cli_verify_with_original_mission_uses_latest_goal_runtime_mission(tmp_path, capsys) -> None:
    mission_path = tmp_path / "metaloop.mission.json"
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    mission_path.write_text(
        (
            '{"run_id":"run_original","intent":"Create hello.txt",'
            '"acceptance_criteria":[{"description":"hello.txt exists","validation_type":"file_exists","validation_target":"hello.txt"}],'
            '"policy":{"workspace_root":"."}}'
        ),
        encoding="utf-8",
    )
    (tmp_path / "hello.txt").write_text("hello\n", encoding="utf-8")
    (metaloop_dir / "mission.json").write_text(
        (
            '{"run_id":"run_runtime","intent":"Create hello.txt",'
            '"acceptance_criteria":[{"description":"hello.txt exists","validation_type":"file_exists","validation_target":"hello.txt"}],'
            f'"policy":{{"workspace_root":"{tmp_path}"}}}}'
        ),
        encoding="utf-8",
    )
    (metaloop_dir / "execution_report.json").write_text(
        '{"schema":"metaloop.execution_report","version":"1.0","mission_id":"run_runtime","status":"completed","summary":"done","changed_files":["hello.txt"],"evidence":["hello.txt"]}',
        encoding="utf-8",
    )
    (metaloop_dir / "run.json").write_text(
        StructuredRunManifest(
            run_id="run_runtime",
            mission_id="run_runtime",
            mode="goal",
            status="completed_verified",
            mission_path=".metaloop/mission.json",
            goal_contract_path=".metaloop/goal_contract.json",
            goal_prompt_path=".metaloop/goal_prompt.md",
            execution_report_path=".metaloop/execution_report.json",
            verification_result_path=".metaloop/verification_result.json",
            codex_events_path=".metaloop/runs/run_runtime/codex_events.jsonl",
        ).model_dump_json(by_alias=True),
        encoding="utf-8",
    )

    exit_code = main(["verify", "--mission", str(mission_path), "--workspace", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "verification: completed_verified" in output


def test_cli_status_reports_structured_workspace_state(tmp_path, capsys) -> None:
    mission_path = tmp_path / "metaloop.mission.json"
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    mission_path.write_text(
        (
            '{"run_id":"run_test","intent":"Assess UX",'
            '"acceptance_criteria":[{"description":"UX is acceptable","validation_type":"manual"}],'
            '"policy":{"workspace_root":"."}}'
        ),
        encoding="utf-8",
    )
    (metaloop_dir / "run.json").write_text(
        StructuredRunManifest(
            run_id="run_test",
            mission_id="run_test",
            mode="goal",
            status="completed_pending_human_acceptance",
            mission_path=".metaloop/mission.json",
            goal_contract_path=".metaloop/goal_contract.json",
            goal_prompt_path=".metaloop/goal_prompt.md",
            execution_report_path=".metaloop/execution_report.json",
            verification_result_path=".metaloop/verification_result.json",
            codex_events_path=".metaloop/runs/run_test/codex_events.jsonl",
        ).model_dump_json(by_alias=True),
        encoding="utf-8",
    )
    (metaloop_dir / "verification_result.json").write_text(
        VerificationResult(
            mission_id="run_test",
            status=VerificationStatus.COMPLETED_PENDING_HUMAN_ACCEPTANCE,
            reason="final user acceptance remains",
        ).model_dump_json(by_alias=True),
        encoding="utf-8",
    )

    exit_code = main(["status", "--workspace", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "mission: ready" in output
    assert "run_id=run_test" in output
    assert "status=completed_pending_human_acceptance" in output
    assert "next_action:" in output


def test_cli_status_json_reports_missing_workspace_state(tmp_path, capsys) -> None:
    exit_code = main(["status", "--workspace", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mission"]["state"] == "missing"
    assert payload["run"]["state"] == "missing"
    assert payload["verification"]["state"] == "missing"
    assert payload["next_action"] == "Run `metaloop design`"


def test_cli_status_json_recommends_run_when_mission_exists(tmp_path, capsys) -> None:
    (tmp_path / "metaloop.mission.json").write_text(
        (
            '{"intent":"Create hello.txt",'
            '"context":{"domain_profile_id":"engineering_development"},'
            '"acceptance_criteria":[{"description":"hello exists","validation_type":"file_exists","validation_target":"hello.txt"}]}'
        ),
        encoding="utf-8",
    )

    exit_code = main(["status", "--workspace", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mission"]["state"] == "ready"
    assert payload["mission"]["intent_summary"] == "Create hello.txt"
    assert payload["mission"]["domain_profile_id"] == "engineering_development"
    assert payload["next_action"] == "Run `metaloop run`"


def test_cli_status_json_reports_capsule_counts_and_last_codex_event(tmp_path, capsys) -> None:
    metaloop_dir = tmp_path / ".metaloop"
    run_dir = metaloop_dir / "runs" / "run_status"
    run_dir.mkdir(parents=True)
    mission = MissionSpec(
        run_id="run_status",
        intent="Create hello.txt",
        context={"domain_profile_id": "engineering_development"},
        deliverables=["hello.txt"],
        acceptance_criteria=[AcceptanceCriteria(description="hello exists", validation_type="file_exists", validation_target="hello.txt")],
    )
    (metaloop_dir / "mission.json").write_text(mission.model_dump_json(), encoding="utf-8")
    capsule = MissionCapsule.from_mission(mission).transition(LifecycleState.IN_PROGRESS, summary="runtime started")
    capsule = capsule.transition(LifecycleState.REVIEW_READY, summary="ready")
    capsule = capsule.transition(LifecycleState.CLOSED, closure_outcome=ClosureOutcome.ACCEPTED, summary="accepted")
    (metaloop_dir / "mission_capsule.json").write_text(capsule.model_dump_json(by_alias=True), encoding="utf-8")
    manifest = StructuredRunManifest(
        run_id="run_status",
        mission_id="run_status",
        mode="goal",
        status="completed_verified",
        mission_path=".metaloop/mission.json",
        goal_contract_path=".metaloop/goal_contract.json",
        goal_prompt_path=".metaloop/goal_prompt.md",
        execution_report_path=".metaloop/execution_report.json",
        verification_result_path=".metaloop/verification_result.json",
        codex_events_path=".metaloop/runs/run_status/codex_events.jsonl",
    )
    (metaloop_dir / "run.json").write_text(manifest.model_dump_json(by_alias=True), encoding="utf-8")
    (run_dir / "codex_events.jsonl").write_text(
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 2, "output_tokens": 3}}) + "\n",
        encoding="utf-8",
    )
    verification = VerificationResult(
        mission_id="run_status",
        status=VerificationStatus.COMPLETED_VERIFIED,
        reason="done",
    )
    (metaloop_dir / "verification_result.json").write_text(verification.model_dump_json(by_alias=True), encoding="utf-8")

    exit_code = main(["status", "--workspace", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["capsule"]["lifecycle_state"] == "closed"
    assert payload["capsule"]["closure_outcome"] == "accepted"
    assert payload["capsule"]["evidence_count"] == 0
    assert payload["capsule"]["required_evidence_count"] == 2
    assert payload["capsule"]["hard_validator_count"] == 1
    assert payload["capsule"]["attempt_count"] == 0
    assert payload["capsule"]["latest_decision_summary"] == "accepted"
    assert payload["attempt_history"]["state"] == "missing"
    assert payload["run"]["last_event_summary"] == "Codex turn completed (5 tokens)."
    assert payload["next_action"] == "Already complete; run `metaloop verify` for details"


def test_cli_status_json_reports_redesign_proposal_next_action(tmp_path, capsys) -> None:
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    mission = MissionSpec(
        run_id="run_redesign_status",
        intent="Create hello.txt",
        acceptance_criteria=[AcceptanceCriteria(description="hello exists", validation_type="file_exists", validation_target="hello.txt")],
    )
    (metaloop_dir / "mission.json").write_text(mission.model_dump_json(), encoding="utf-8")
    capsule = MissionCapsule.from_mission(mission).transition(LifecycleState.IN_PROGRESS, summary="runtime started")
    capsule = capsule.transition(LifecycleState.REDESIGN_REQUIRED, summary="redesign_required: acceptance is underspecified")
    (metaloop_dir / "mission_capsule.json").write_text(capsule.model_dump_json(by_alias=True), encoding="utf-8")
    manifest = StructuredRunManifest(
        run_id="run_redesign_status",
        mission_id="run_redesign_status",
        mode="goal",
        status="failed",
        mission_path=".metaloop/mission.json",
        goal_contract_path=".metaloop/goal_contract.json",
        goal_prompt_path=".metaloop/goal_prompt.md",
        execution_report_path=".metaloop/execution_report.json",
        verification_result_path=".metaloop/verification_result.json",
        codex_events_path=".metaloop/runs/run_redesign_status/codex_events.jsonl",
    )
    (metaloop_dir / "run.json").write_text(manifest.model_dump_json(by_alias=True), encoding="utf-8")
    verification = VerificationResult(
        mission_id="run_redesign_status",
        status=VerificationStatus.FAILED,
        reason="redesign_required: acceptance is underspecified",
    )
    (metaloop_dir / "verification_result.json").write_text(verification.model_dump_json(by_alias=True), encoding="utf-8")
    proposal = RedesignProposal(
        mission_id="run_redesign_status",
        capsule_id="run_redesign_status",
        capsule_version="1.0",
        reviewer_route=ReviewRoute.ASK_ARCHITECT_TO_RETHINK,
        reason="acceptance is underspecified",
        why_worker_repair_is_insufficient="worker repair would need to change acceptance",
    )
    (metaloop_dir / "redesign_proposal.json").write_text(proposal.model_dump_json(by_alias=True), encoding="utf-8")

    exit_code = main(["status", "--workspace", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["capsule"]["lifecycle_state"] == "redesign_required"
    assert payload["redesign"]["state"] == "ready"
    assert payload["redesign"]["reviewer_route"] == "ask_architect_to_rethink"
    assert payload["redesign"]["contract_delta"]["evidence_delta"] == []
    assert "contract_delta_summary" in payload["redesign"]
    assert "Review redesign proposal" in payload["next_action"]


def test_cli_run_accepts_mission_file(tmp_path, capsys) -> None:
    db_path = tmp_path / "runs.sqlite"
    mission_path = tmp_path / "mission.json"
    mission_path.write_text(
        '{"intent":"Create a dummy artifact","acceptance_criteria":[{"description":"done"}]}',
        encoding="utf-8",
    )

    exit_code = main(["run", "--mission", str(mission_path), "--worker", "dummy", "--db", str(db_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "status: completed" in output


def test_cli_run_goal_path_still_works(monkeypatch, tmp_path, capsys) -> None:
    mission_path = tmp_path / "metaloop.mission.json"
    mission_path.write_text(
        (
            '{"run_id":"run_goal_cli","intent":"Create hello.txt",'
            '"context":{"domain_profile_id":"engineering_development"},'
            '"deliverables":["hello.txt"],'
            '"acceptance_criteria":[{"description":"hello.txt exists","validation_type":"file_exists","validation_target":"hello.txt"}],'
            f'"policy":{{"workspace_root":"{tmp_path}"}}}}'
        ),
        encoding="utf-8",
    )

    captured = {}

    class CapturingGoalRuntime:
        def __init__(self, options: CodexExecOptions, **_kwargs) -> None:
            captured["cwd"] = options.working_directory

        def run(self, mission, **_kwargs):
            captured["mission_id"] = mission.run_id
            manifest = StructuredRunManifest(
                run_id=mission.run_id,
                mission_id=mission.run_id,
                mode="goal",
                status="completed_verified",
                mission_path=".metaloop/mission.json",
                goal_contract_path=".metaloop/goal_contract.json",
                goal_prompt_path=".metaloop/goal_prompt.md",
                execution_report_path=".metaloop/execution_report.json",
                verification_result_path=".metaloop/verification_result.json",
                codex_events_path=f".metaloop/runs/{mission.run_id}/codex_events.jsonl",
            )
            verification = VerificationResult(
                mission_id=mission.run_id,
                status=VerificationStatus.COMPLETED_VERIFIED,
                reason="goal path ok",
            )
            return GoalRuntimeResult(mission=mission, verification=verification, manifest=manifest)

    monkeypatch.setattr("metaloop.cli.CodexExecGoalRuntimeAdapter", CapturingGoalRuntime)

    exit_code = main(["run", "--mission", str(mission_path), "--workspace", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["cwd"] == str(tmp_path)
    assert captured["mission_id"] == "run_goal_cli"
    assert "verification: completed_verified" in output


def test_cli_run_assigns_fresh_run_id_for_mission_file(tmp_path, capsys) -> None:
    db_path = tmp_path / "runs.sqlite"
    mission_path = tmp_path / "mission.json"
    mission_path.write_text(
        '{"run_id":"run_fixed","intent":"Create a dummy artifact","acceptance_criteria":[{"description":"done"}]}',
        encoding="utf-8",
    )

    exit_code = main(["run", "--mission", str(mission_path), "--worker", "dummy", "--db", str(db_path)])
    capsys.readouterr()

    runs = SQLiteRunStore(db_path).list_runs()
    assert exit_code == 0
    assert runs[0]["run_id"] != "run_fixed"


def test_cli_run_overrides_token_budget(monkeypatch, tmp_path, capsys) -> None:
    captured = {}

    class CapturingWorker:
        def __init__(self, _options: CodexExecOptions) -> None:
            pass

        def run_step(self, _context, mission, _plan, step, **_kwargs):
            captured["max_tokens"] = mission.budget.max_tokens
            return StepResult(step_id=step.step_id, status=StepStatus.SUCCESS)

    monkeypatch.setattr("metaloop.cli.CodexExecWorkerBackend", CapturingWorker)

    exit_code = main([
        "run",
        "Create a dummy artifact",
        "--worker",
        "codex",
        "--max-tokens",
        "120000",
        "--db",
        str(tmp_path / "runs.sqlite"),
    ])
    capsys.readouterr()

    assert exit_code == 0
    assert captured["max_tokens"] == 120000


def test_cli_run_defaults_to_unlimited_token_budget(monkeypatch, tmp_path, capsys) -> None:
    captured = {}

    class CapturingWorker:
        def __init__(self, _options: CodexExecOptions) -> None:
            pass

        def run_step(self, _context, mission, _plan, step, **_kwargs):
            captured["max_tokens"] = mission.budget.max_tokens
            return StepResult(step_id=step.step_id, status=StepStatus.SUCCESS)

    monkeypatch.setattr("metaloop.cli.CodexExecWorkerBackend", CapturingWorker)

    exit_code = main([
        "run",
        "Create a dummy artifact",
        "--worker",
        "codex",
        "--db",
        str(tmp_path / "runs.sqlite"),
    ])
    capsys.readouterr()

    assert exit_code == 0
    assert captured["max_tokens"] is None


def test_cli_run_auto_discovers_single_mission_file(tmp_path, capsys) -> None:
    db_path = tmp_path / "runs.sqlite"
    mission_path = tmp_path / "metaloop.mission.json"
    mission_path.write_text(
        '{"intent":"Create a dummy artifact","acceptance_criteria":[{"description":"done"}]}',
        encoding="utf-8",
    )

    exit_code = main(["run", "--workspace", str(tmp_path), "--worker", "dummy", "--db", str(db_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "status: completed" in output


def test_cli_run_asks_user_to_select_when_multiple_missions(monkeypatch, tmp_path, capsys) -> None:
    db_path = tmp_path / "runs.sqlite"
    (tmp_path / "a.mission.json").write_text(
        '{"intent":"Create selected artifact","acceptance_criteria":[{"description":"done"}]}',
        encoding="utf-8",
    )
    (tmp_path / "b.mission.json").write_text(
        '{"intent":"Create other artifact","acceptance_criteria":[{"description":"done"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")

    exit_code = main(["run", "--workspace", str(tmp_path), "--worker", "dummy", "--db", str(db_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Multiple mission files found" in output
    assert "status: completed" in output


def test_cli_run_json_requires_explicit_mission_when_multiple_found(tmp_path, capsys) -> None:
    db_path = tmp_path / "runs.sqlite"
    (tmp_path / "a.mission.json").write_text(
        '{"intent":"Create selected artifact","acceptance_criteria":[{"description":"done"}]}',
        encoding="utf-8",
    )
    (tmp_path / "b.mission.json").write_text(
        '{"intent":"Create other artifact","acceptance_criteria":[{"description":"done"}]}',
        encoding="utf-8",
    )

    exit_code = main(["run", "--workspace", str(tmp_path), "--json", "--db", str(db_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "Pass --mission when using --json" in captured.err


def test_cli_run_without_intent_or_mission_reports_missing_mission(tmp_path, capsys) -> None:
    exit_code = main(["run", "--workspace", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Run `metaloop design` first" in captured.err


def test_cli_run_auto_discovered_mission_defaults_to_goal_runtime(monkeypatch, tmp_path, capsys) -> None:
    db_path = tmp_path / "runs.sqlite"
    mission_path = tmp_path / "metaloop.mission.json"
    mission_path.write_text(
        '{"intent":"Create a dummy artifact","acceptance_criteria":[{"description":"done"}]}',
        encoding="utf-8",
    )
    captured = {}

    class CapturingGoalRuntime:
        def __init__(self, options: CodexExecOptions, **_kwargs) -> None:
            captured["runtime"] = "goal"
            captured["working_directory"] = options.working_directory

        def run(self, mission, **kwargs):
            if kwargs.get("on_status") is not None:
                kwargs["on_status"]("Codex running command: pytest -q")
                kwargs["on_status"]("Reviewer route: complete (passed=true, confidence=high, findings=0)")
            verification = VerificationResult(
                mission_id=mission.run_id,
                status=VerificationStatus.COMPLETED_PENDING_HUMAN_ACCEPTANCE,
                reason="internal work is complete; final human acceptance remains",
            )
            manifest = StructuredRunManifest(
                run_id=mission.run_id,
                mission_id=mission.run_id,
                mode="goal",
                status=verification.status.value,
                mission_path=".metaloop/mission.json",
                goal_contract_path=".metaloop/goal_contract.json",
                goal_prompt_path=".metaloop/goal_prompt.md",
                execution_report_path=".metaloop/execution_report.json",
                verification_result_path=".metaloop/verification_result.json",
                codex_events_path=f".metaloop/runs/{mission.run_id}/codex_events.jsonl",
            )
            return GoalRuntimeResult(mission=mission, verification=verification, manifest=manifest)

    monkeypatch.setattr("metaloop.cli.CodexExecGoalRuntimeAdapter", CapturingGoalRuntime)

    exit_code = main(["run", "--workspace", str(tmp_path), "--db", str(db_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["runtime"] == "goal"
    assert captured["working_directory"] == str(tmp_path)
    assert "MetaLoop Run Monitor" in output
    assert "Codex running command: pytest -q" in output
    assert "Reviewer route: complete" in output
    assert "verification: completed_pending_human_acceptance" in output


def test_cli_resume_uses_latest_checkpoint(monkeypatch, tmp_path, capsys) -> None:
    db_path = tmp_path / "runs.sqlite"
    store = SQLiteRunStore(db_path)
    mission = MissionSpec(
        intent="Create a dummy artifact",
        acceptance_criteria=[AcceptanceCriteria(description="done")],
    )
    checkpoint = KernelState(mission=mission, status=RunStatus.RUNNING)
    store.start_run(checkpoint)
    store.save_checkpoint(checkpoint)

    exit_code = main(["resume", "--db", str(db_path), "--worker", "dummy"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Resuming run:" in output
    assert "status: completed" in output


def test_cli_resume_overrides_token_budget(monkeypatch, tmp_path, capsys) -> None:
    db_path = tmp_path / "runs.sqlite"
    store = SQLiteRunStore(db_path)
    mission = MissionSpec(
        intent="Create a dummy artifact",
        acceptance_criteria=[AcceptanceCriteria(description="done")],
    )
    checkpoint = KernelState(mission=mission, status=RunStatus.RUNNING)
    store.start_run(checkpoint)
    store.save_checkpoint(checkpoint)
    captured = {}

    class CapturingWorker:
        def __init__(self, _options: CodexExecOptions) -> None:
            pass

        def run_step(self, _context, mission, _plan, step, **_kwargs):
            captured["max_tokens"] = mission.budget.max_tokens
            return StepResult(step_id=step.step_id, status=StepStatus.SUCCESS)

    monkeypatch.setattr("metaloop.cli.CodexExecWorkerBackend", CapturingWorker)

    exit_code = main([
        "resume",
        mission.run_id,
        "--db",
        str(db_path),
        "--worker",
        "codex",
        "--max-tokens",
        "150000",
    ])
    capsys.readouterr()

    assert exit_code == 0
    assert captured["max_tokens"] == 150000


def test_cli_resume_reports_missing_run(tmp_path, capsys) -> None:
    exit_code = main(["resume", "--db", str(tmp_path / "runs.sqlite")])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "No resumable run found" in captured.err


def test_cli_resume_goal_reports_terminal_structured_run(tmp_path, capsys) -> None:
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    (metaloop_dir / "mission.json").write_text(
        (
            '{"run_id":"run_goal_done","intent":"Assess UX",'
            '"acceptance_criteria":[{"description":"UX is acceptable","validation_type":"manual"}],'
            f'"policy":{{"workspace_root":"{tmp_path}"}}}}'
        ),
        encoding="utf-8",
    )
    manifest = StructuredRunManifest(
        run_id="run_goal_done",
        mission_id="run_goal_done",
        mode="goal",
        status="completed_pending_human_acceptance",
        mission_path=".metaloop/mission.json",
        goal_contract_path=".metaloop/goal_contract.json",
        goal_prompt_path=".metaloop/goal_prompt.md",
        execution_report_path=".metaloop/execution_report.json",
        verification_result_path=".metaloop/verification_result.json",
        codex_events_path=".metaloop/runs/run_goal_done/codex_events.jsonl",
    )
    (metaloop_dir / "run.json").write_text(manifest.model_dump_json(by_alias=True), encoding="utf-8")
    verification = VerificationResult(
        mission_id="run_goal_done",
        status=VerificationStatus.COMPLETED_PENDING_HUMAN_ACCEPTANCE,
        reason="final user acceptance remains",
    )
    (metaloop_dir / "verification_result.json").write_text(verification.model_dump_json(by_alias=True), encoding="utf-8")

    exit_code = main(["resume", "--mode", "goal", "--workspace", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "resume: not needed" in output
    assert "status: completed_pending_human_acceptance" in output


def test_cli_resume_goal_reruns_incomplete_structured_run(monkeypatch, tmp_path, capsys) -> None:
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    (metaloop_dir / "mission.json").write_text(
        (
            '{"run_id":"run_goal_incomplete","intent":"Create hello.txt",'
            '"acceptance_criteria":[{"description":"hello exists","validation_type":"file_exists","validation_target":"hello.txt"}],'
            f'"policy":{{"workspace_root":"{tmp_path}"}}}}'
        ),
        encoding="utf-8",
    )
    manifest = StructuredRunManifest(
        run_id="run_goal_incomplete",
        mission_id="run_goal_incomplete",
        mode="goal",
        status="running",
        mission_path=".metaloop/mission.json",
        goal_contract_path=".metaloop/goal_contract.json",
        goal_prompt_path=".metaloop/goal_prompt.md",
        execution_report_path=".metaloop/execution_report.json",
        verification_result_path=".metaloop/verification_result.json",
        codex_events_path=".metaloop/runs/run_goal_incomplete/codex_events.jsonl",
    )
    (metaloop_dir / "run.json").write_text(manifest.model_dump_json(by_alias=True), encoding="utf-8")
    captured = {}

    class CapturingGoalRuntime:
        def __init__(self, options: CodexExecOptions, **_kwargs) -> None:
            captured["cwd"] = options.working_directory

        def run(self, mission, **_kwargs):
            captured["run_id"] = mission.run_id
            verification = VerificationResult(
                mission_id=mission.run_id,
                status=VerificationStatus.COMPLETED_VERIFIED,
                reason="resumed",
            )
            return GoalRuntimeResult(mission=mission, verification=verification, manifest=manifest)

    monkeypatch.setattr("metaloop.cli.CodexExecGoalRuntimeAdapter", CapturingGoalRuntime)

    exit_code = main(["resume", "--mode", "goal", "--workspace", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["run_id"] == "run_goal_incomplete"
    assert captured["cwd"] == str(tmp_path)
    assert "verification: completed_verified" in output


def test_cli_resume_goal_missing_execution_report_reruns_with_reason(monkeypatch, tmp_path, capsys) -> None:
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    (metaloop_dir / "mission.json").write_text(
        (
            '{"run_id":"run_missing_report","intent":"Create hello.txt",'
            '"acceptance_criteria":[{"description":"hello exists","validation_type":"file_exists","validation_target":"hello.txt"}],'
            f'"policy":{{"workspace_root":"{tmp_path}"}}}}'
        ),
        encoding="utf-8",
    )
    manifest = StructuredRunManifest(
        run_id="run_missing_report",
        mission_id="run_missing_report",
        mode="goal",
        status="running",
        mission_path=".metaloop/mission.json",
        goal_contract_path=".metaloop/goal_contract.json",
        goal_prompt_path=".metaloop/goal_prompt.md",
        execution_report_path=".metaloop/execution_report.json",
        verification_result_path=".metaloop/verification_result.json",
        codex_events_path=".metaloop/runs/run_missing_report/codex_events.jsonl",
    )
    (metaloop_dir / "run.json").write_text(manifest.model_dump_json(by_alias=True), encoding="utf-8")
    captured = {"runs": 0}

    class CapturingGoalRuntime:
        def __init__(self, _options: CodexExecOptions, **_kwargs) -> None:
            pass

        def run(self, mission, **_kwargs):
            captured["runs"] += 1
            verification = VerificationResult(
                mission_id=mission.run_id,
                status=VerificationStatus.COMPLETED_VERIFIED,
                reason="rerun done",
            )
            return GoalRuntimeResult(mission=mission, verification=verification, manifest=manifest)

    monkeypatch.setattr("metaloop.cli.CodexExecGoalRuntimeAdapter", CapturingGoalRuntime)

    exit_code = main(["resume", "--mode", "goal", "--workspace", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["runs"] == 1
    assert "missing execution report; rerunning goal runtime" in output


def test_cli_resume_goal_failed_verification_with_report_reruns_with_reason(monkeypatch, tmp_path, capsys) -> None:
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    (metaloop_dir / "mission.json").write_text(
        (
            '{"run_id":"run_failed_verify","intent":"Create hello.txt",'
            '"acceptance_criteria":[{"description":"hello exists","validation_type":"file_exists","validation_target":"hello.txt"}],'
            f'"policy":{{"workspace_root":"{tmp_path}"}}}}'
        ),
        encoding="utf-8",
    )
    (metaloop_dir / "execution_report.json").write_text(
        '{"schema":"metaloop.execution_report","version":"1.0","mission_id":"run_failed_verify","status":"completed","summary":"done"}',
        encoding="utf-8",
    )
    manifest = StructuredRunManifest(
        run_id="run_failed_verify",
        mission_id="run_failed_verify",
        mode="goal",
        status="failed",
        mission_path=".metaloop/mission.json",
        goal_contract_path=".metaloop/goal_contract.json",
        goal_prompt_path=".metaloop/goal_prompt.md",
        execution_report_path=".metaloop/execution_report.json",
        verification_result_path=".metaloop/verification_result.json",
        codex_events_path=".metaloop/runs/run_failed_verify/codex_events.jsonl",
    )
    (metaloop_dir / "run.json").write_text(manifest.model_dump_json(by_alias=True), encoding="utf-8")
    verification = VerificationResult(mission_id="run_failed_verify", status=VerificationStatus.FAILED, reason="hard validators failed")
    (metaloop_dir / "verification_result.json").write_text(verification.model_dump_json(by_alias=True), encoding="utf-8")
    captured = {"runs": 0}

    class CapturingGoalRuntime:
        def __init__(self, _options: CodexExecOptions, **_kwargs) -> None:
            pass

        def run(self, mission, **_kwargs):
            captured["runs"] += 1
            return GoalRuntimeResult(
                mission=mission,
                verification=VerificationResult(mission_id=mission.run_id, status=VerificationStatus.COMPLETED_VERIFIED, reason="repaired"),
                manifest=manifest,
            )

    monkeypatch.setattr("metaloop.cli.CodexExecGoalRuntimeAdapter", CapturingGoalRuntime)

    exit_code = main(["resume", "--mode", "goal", "--workspace", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["runs"] == 1
    assert "failed verification with existing execution report" in output


def test_cli_resume_goal_closed_failed_capsule_reruns_with_reason(monkeypatch, tmp_path, capsys) -> None:
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    mission = MissionSpec(
        run_id="run_closed_failed",
        intent="Create hello.txt",
        acceptance_criteria=[AcceptanceCriteria(description="hello exists", validation_type="file_exists", validation_target="hello.txt")],
        policy={"workspace_root": str(tmp_path)},
    )
    (metaloop_dir / "mission.json").write_text(mission.model_dump_json(), encoding="utf-8")
    capsule = MissionCapsule.from_mission(mission).transition(LifecycleState.IN_PROGRESS, summary="runtime started")
    capsule = capsule.transition(LifecycleState.CLOSED, closure_outcome=ClosureOutcome.FAILED, summary="failed")
    (metaloop_dir / "mission_capsule.json").write_text(capsule.model_dump_json(by_alias=True), encoding="utf-8")
    manifest = StructuredRunManifest(
        run_id="run_closed_failed",
        mission_id="run_closed_failed",
        mode="goal",
        status="failed",
        mission_path=".metaloop/mission.json",
        goal_contract_path=".metaloop/goal_contract.json",
        goal_prompt_path=".metaloop/goal_prompt.md",
        execution_report_path=".metaloop/execution_report.json",
        verification_result_path=".metaloop/verification_result.json",
        codex_events_path=".metaloop/runs/run_closed_failed/codex_events.jsonl",
    )
    (metaloop_dir / "run.json").write_text(manifest.model_dump_json(by_alias=True), encoding="utf-8")
    captured = {"runs": 0}

    class CapturingGoalRuntime:
        def __init__(self, _options: CodexExecOptions, **_kwargs) -> None:
            pass

        def run(self, mission, **_kwargs):
            captured["runs"] += 1
            return GoalRuntimeResult(
                mission=mission,
                verification=VerificationResult(mission_id=mission.run_id, status=VerificationStatus.COMPLETED_VERIFIED, reason="rerun"),
                manifest=manifest,
            )

    monkeypatch.setattr("metaloop.cli.CodexExecGoalRuntimeAdapter", CapturingGoalRuntime)

    exit_code = main(["resume", "--mode", "goal", "--workspace", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["runs"] == 1
    assert "failed capsule closure" in output


def test_cli_resume_goal_redesign_required_does_not_start_runtime(monkeypatch, tmp_path, capsys) -> None:
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    mission = MissionSpec(
        run_id="run_resume_redesign",
        intent="Create hello.txt",
        acceptance_criteria=[AcceptanceCriteria(description="hello exists", validation_type="file_exists", validation_target="hello.txt")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )
    (metaloop_dir / "mission.json").write_text(mission.model_dump_json(), encoding="utf-8")
    capsule = MissionCapsule.from_mission(mission).transition(LifecycleState.IN_PROGRESS, summary="runtime started")
    capsule = capsule.transition(LifecycleState.REDESIGN_REQUIRED, summary="redesign_required: scope mismatch")
    (metaloop_dir / "mission_capsule.json").write_text(capsule.model_dump_json(by_alias=True), encoding="utf-8")
    manifest = StructuredRunManifest(
        run_id="run_resume_redesign",
        mission_id="run_resume_redesign",
        mode="goal",
        status="failed",
        mission_path=".metaloop/mission.json",
        goal_contract_path=".metaloop/goal_contract.json",
        goal_prompt_path=".metaloop/goal_prompt.md",
        execution_report_path=".metaloop/execution_report.json",
        verification_result_path=".metaloop/verification_result.json",
        codex_events_path=".metaloop/runs/run_resume_redesign/codex_events.jsonl",
    )
    (metaloop_dir / "run.json").write_text(manifest.model_dump_json(by_alias=True), encoding="utf-8")
    verification = VerificationResult(
        mission_id="run_resume_redesign",
        status=VerificationStatus.FAILED,
        reason="redesign_required: scope mismatch",
    )
    (metaloop_dir / "verification_result.json").write_text(verification.model_dump_json(by_alias=True), encoding="utf-8")
    proposal = RedesignProposal(
        mission_id="run_resume_redesign",
        capsule_id="run_resume_redesign",
        capsule_version="1.0",
        reviewer_route=ReviewRoute.ASK_PLANNER_TO_REPLAN,
        reason="scope mismatch",
        why_worker_repair_is_insufficient="scope must be revised before implementation",
    )
    (metaloop_dir / "redesign_proposal.json").write_text(proposal.model_dump_json(by_alias=True), encoding="utf-8")
    captured = {"runs": 0}

    class CapturingGoalRuntime:
        def __init__(self, _options: CodexExecOptions, **_kwargs) -> None:
            pass

        def run(self, mission, **_kwargs):
            captured["runs"] += 1
            return GoalRuntimeResult(
                mission=mission,
                verification=VerificationResult(mission_id=mission.run_id, status=VerificationStatus.COMPLETED_VERIFIED, reason="should not run"),
                manifest=manifest,
            )

    monkeypatch.setattr("metaloop.cli.CodexExecGoalRuntimeAdapter", CapturingGoalRuntime)

    exit_code = main(["resume", "--mode", "goal", "--workspace", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert captured["runs"] == 0
    assert "redesign_required" in output
    assert "metaloop design --resume" in output


def test_cli_run_reports_invalid_mission_file(tmp_path, capsys) -> None:
    exit_code = main(["run", "--mission", str(tmp_path / "missing.json")])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Mission file not found" in captured.err


def test_cli_strict_exit_code_for_blocked(monkeypatch, tmp_path, capsys) -> None:
    class BlockedCodexWorker:
        def __init__(self, _options: CodexExecOptions) -> None:
            pass

        def run_step(self, *args, **kwargs):
            step = args[3]
            return StepResult(step_id=step.step_id, status=StepStatus.BLOCKED_BY_AUTH, error_log="needs auth")

    monkeypatch.setattr("metaloop.cli.CodexExecWorkerBackend", BlockedCodexWorker)

    exit_code = main([
        "run",
        "Create a dummy artifact",
        "--worker",
        "codex",
        "--strict-exit-code",
        "--db",
        str(tmp_path / "runs.sqlite"),
    ])
    capsys.readouterr()

    assert exit_code == 3
