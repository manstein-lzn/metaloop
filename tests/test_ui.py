from metaloop.co_design import CoDesignQuestion
from metaloop.schemas import AcceptanceCriteria, FailureReport, KernelState, MissionSpec, RunStatus
from metaloop.ui import MetaLoopUI, _recovery_hint


def test_option_question_falls_back_to_numbered_input(monkeypatch, capsys) -> None:
    ui = MetaLoopUI()
    monkeypatch.setattr("builtins.input", lambda _prompt="": "2")

    answer = ui.ask_question(
        CoDesignQuestion(
            question_id="deliverables",
            prompt="Choose deliverable",
            options=["a.txt", "b.txt"],
        )
    )
    capsys.readouterr()

    assert answer == "b.txt"


def test_option_question_falls_back_to_custom_input(monkeypatch, capsys) -> None:
    ui = MetaLoopUI()
    answers = iter(["3", "custom.txt"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    answer = ui.ask_question(
        CoDesignQuestion(
            question_id="deliverables",
            prompt="Choose deliverable",
            options=["a.txt", "b.txt"],
        )
    )
    capsys.readouterr()

    assert answer == "custom.txt"


def test_option_selector_lines_wrap_long_answers() -> None:
    ui = MetaLoopUI()
    ui.console.width = 50

    lines = ui._option_selector_lines(
        [
            "交付一个可运行的 VS Code 扩展 MVP：支持选择/打开 PyTorch traced .pt 文件，解析 TorchScript graph。",
            "Other / 手动输入",
        ],
        0,
    )

    assert len(lines) > 3
    assert all(len(text) <= 55 for text, _style in lines)


def test_recovery_hint_suggests_sandbox_resume_for_bwrap_failure() -> None:
    mission = MissionSpec(
        intent="Build tool",
        acceptance_criteria=[AcceptanceCriteria(description="done")],
        policy={"workspace_root": "/tmp/project"},
    )
    state = KernelState(
        mission=mission,
        status=RunStatus.BLOCKED,
        failure_report=FailureReport(
            run_id=mission.run_id,
            failed_node="scheduler",
            error_type="worker_error",
            message="bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted",
            recoverable=True,
        ),
    )

    hint = _recovery_hint(state)

    assert "metaloop resume" in hint
    assert "--sandbox danger-full-access" in hint
    assert "cd /tmp/project" in hint


def test_recovery_hint_suggests_budget_override() -> None:
    mission = MissionSpec(
        intent="Build tool",
        acceptance_criteria=[AcceptanceCriteria(description="done")],
    )
    state = KernelState(
        mission=mission,
        status=RunStatus.FAILED,
        failure_report=FailureReport(
            run_id=mission.run_id,
            failed_node="scheduler",
            error_type="budget_exceeded",
            message="token budget exceeded",
            recoverable=False,
        ),
    )
    state.budget_usage.tokens = 55_000

    hint = _recovery_hint(state)

    assert "metaloop resume" in hint
    assert "--max-tokens" in hint
