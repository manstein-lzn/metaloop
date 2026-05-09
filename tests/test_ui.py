from metaloop.co_design import CoDesignQuestion
from metaloop.schemas import AcceptanceCriteria, FailureReport, KernelState, MissionSpec, RunStatus
from metaloop.ui import MetaLoopUI, _recovery_hint, _submit_enter_key_bindings


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


def test_ask_uses_native_input_prompt(monkeypatch) -> None:
    ui = MetaLoopUI()
    prompts = []

    def fake_input(prompt=""):
        prompts.append(prompt)
        return "ship it"

    monkeypatch.setattr("builtins.input", fake_input)

    answer = ui._ask("Design review")

    assert answer == "ship it"
    assert prompts == ["Design review: "]


def test_ask_uses_native_input_prompt_with_default(monkeypatch) -> None:
    ui = MetaLoopUI()
    prompts = []

    def fake_input(prompt=""):
        prompts.append(prompt)
        return ""

    monkeypatch.setattr("builtins.input", fake_input)

    answer = ui._ask("Choose", default="1")

    assert answer == "1"
    assert prompts == ["Choose [1]: "]


def test_design_review_uses_editor_prompt(monkeypatch, capsys) -> None:
    ui = MetaLoopUI()
    prompts = []

    def fake_editor(label):
        prompts.append(label)
        return "需要深入复盘历史实验并扩大时间预算。"

    monkeypatch.setattr(ui, "_ask_editor", fake_editor)

    answer = ui.ask_design_review_action(1)
    output = capsys.readouterr().out

    assert answer == "需要深入复盘历史实验并扩大时间预算。"
    assert prompts == ["Design review"]
    assert "Alt+Enter inserts a newline" in output
    assert "Paste works as normal" in output


def test_design_review_reprompts_on_empty_editor_input(monkeypatch, capsys) -> None:
    ui = MetaLoopUI()
    answers = iter(["", "approve"])

    monkeypatch.setattr(ui, "_ask_editor", lambda _label: next(answers))

    answer = ui.ask_design_review_action(1)
    output = capsys.readouterr().out

    assert answer == "approve"
    assert "No input submitted" in output


def test_editor_prompt_enter_submits_and_alt_enter_inserts_newline() -> None:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    with create_pipe_input() as pipe:
        session = PromptSession(input=pipe, output=DummyOutput())
        pipe.send_text("hello\r")
        result = session.prompt(multiline=True, key_bindings=_submit_enter_key_bindings())
    assert result == "hello"

    with create_pipe_input() as pipe:
        session = PromptSession(input=pipe, output=DummyOutput())
        pipe.send_text("hello\x1b\rworld\r")
        result = session.prompt(multiline=True, key_bindings=_submit_enter_key_bindings())
    assert result == "hello\nworld"


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
