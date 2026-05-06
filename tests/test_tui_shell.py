from pathlib import Path

from metaloop.tui_shell import TuiShell
from metaloop.user_agent import ProposedAction, UserAction, UserAgent


def _missing_status(workspace: Path) -> dict:
    return {
        "workspace": str(workspace),
        "design": {"state": "missing", "locked": False, "contract_path": None},
        "mission": {"state": "missing", "path": None, "intent_summary": ""},
        "run": {"state": "missing", "run_id": None, "mode": None},
        "verification": {"state": "missing", "status": None, "hard_validator_passed": 0, "hard_validator_total": 0},
        "redesign": {"state": "missing", "reviewer_route": None},
        "attempt_history": {"state": "missing", "count": 0, "latest_path": None},
        "capsule": {"lifecycle_state": None},
        "next_action": "Run `metaloop design`",
    }

def test_tui_shell_runs_confirmed_action_with_workspace(monkeypatch, tmp_path, capsys) -> None:
    calls = []
    inputs = iter(["", "y", "quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    shell = TuiShell(
        workspace=tmp_path,
        status_reader=_missing_status,
        command_runner=lambda argv: calls.append(argv) or 0,
        user_agent=UserAgent(),
    )

    exit_code = shell.run()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == [["design", "--workspace", str(tmp_path)]]
    assert "MetaLoop Shell" in output
    assert "action: start_design" in output
    assert "status: shell_closed" in output


def test_tui_shell_feedback_is_non_executable(monkeypatch, tmp_path, capsys) -> None:
    calls = []
    inputs = iter(["结果不满意", "quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    shell = TuiShell(
        workspace=tmp_path,
        status_reader=_missing_status,
        command_runner=lambda argv: calls.append(argv) or 0,
        user_agent=UserAgent(),
    )

    exit_code = shell.run()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == []
    assert "action: collect_feedback" in output
    assert "locked MissionSpec, MissionCapsule, and GoalContract were not modified" in output


def test_tui_shell_runs_startup_codex_agent_without_static_intake(monkeypatch, tmp_path, capsys) -> None:
    class StartupAgent:
        def start(self, _status):
            return ProposedAction(
                action=UserAction.SHOW_STATUS,
                reason="Codex inspected the project.",
                requires_confirmation=False,
                assistant_message="我先看了 README 和 Git 历史。",
            )

        def propose(self, user_text, _status):
            assert user_text == "quit"
            return ProposedAction(action=UserAction.QUIT, reason="bye", requires_confirmation=False)

    monkeypatch.setattr("builtins.input", lambda _prompt="": "quit")

    shell = TuiShell(
        workspace=tmp_path,
        status_reader=_missing_status,
        command_runner=lambda _argv: 0,
        user_agent=StartupAgent(),
    )

    exit_code = shell.run()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "UserAgent Startup" in output
    assert "我先看了 README 和 Git 历史。" in output
    assert "Workspace Intake" not in output
