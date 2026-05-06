from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich import box
from rich.panel import Panel
from rich.table import Table

from metaloop.ui import MetaLoopUI
from metaloop.user_agent import ProposedAction, UserAction, UserAgent


StatusReader = Callable[[Path], dict[str, Any]]
CommandRunner = Callable[[list[str]], int]


class TuiShell:
    def __init__(
        self,
        *,
        workspace: str | Path,
        status_reader: StatusReader,
        command_runner: CommandRunner,
        user_agent: UserAgent | None = None,
        ui: MetaLoopUI | None = None,
        confirm_actions: bool = True,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.status_reader = status_reader
        self.command_runner = command_runner
        self.user_agent = user_agent or UserAgent()
        self.ui = ui or MetaLoopUI()
        self.confirm_actions = confirm_actions

    def run(self) -> int:
        try:
            self._print_header()
            status = self._read_status()
            self._print_overview(status)
            exit_code = self._run_startup_agent(status)
            if exit_code != 0:
                return exit_code
            exit_code = 0
            while True:
                try:
                    user_text = input("metaloop> ").strip()
                except EOFError:
                    self.ui.console.print()
                    return exit_code
                except KeyboardInterrupt:
                    self.ui.console.print()
                    self.ui.print_error("Shell interrupted.")
                    return 130

                try:
                    action = self.user_agent.propose(user_text, self._read_status())
                except RuntimeError as exc:
                    self.ui.print_error(str(exc))
                    return 1
                if action.action == UserAction.QUIT:
                    self.ui.console.out("status: shell_closed")
                    return exit_code
                exit_code = self._handle_action(action)
                status = self._read_status()
                if action.action != UserAction.SHOW_STATUS:
                    self._print_overview(status)
        finally:
            close = getattr(self.user_agent, "close", None)
            if close is not None:
                close()

    def _handle_action(self, action: ProposedAction) -> int:
        self._print_action(action)
        if action.action in {UserAction.UNKNOWN, UserAction.COLLECT_FEEDBACK, UserAction.PROPOSE_REVISION, UserAction.APPLY_REDESIGN}:
            self._print_non_executable_action(action)
            return 0
        if not action.command:
            return 0
        if self.confirm_actions and action.requires_confirmation and not self._confirm(action):
            self.ui.console.out("action: cancelled")
            return 0
        argv = [*action.command, "--workspace", str(self.workspace)]
        return self.command_runner(argv)

    def _read_status(self) -> dict[str, Any]:
        return self.status_reader(self.workspace)

    def _run_startup_agent(self, status: dict[str, Any]) -> int:
        starter = getattr(self.user_agent, "start", None)
        if starter is None:
            return 0
        try:
            action = starter(status)
        except RuntimeError as exc:
            self.ui.print_error(str(exc))
            return 1
        self._print_action(action, title="UserAgent Startup")
        if action.action == UserAction.QUIT:
            return 0
        if action.command and (not action.requires_confirmation or not self.confirm_actions):
            argv = [*action.command, "--workspace", str(self.workspace)]
            return self.command_runner(argv)
        return 0

    def _print_header(self) -> None:
        body = Table.grid(padding=(0, 2))
        body.add_column(style="dim", no_wrap=True)
        body.add_column()
        body.add_row("workspace", str(self.workspace))
        body.add_row("input", "natural language or design/run/verify/status/resume/revise/quit")
        body.add_row("state", ".metaloop structured artifacts")
        self.ui.console.print(Panel(body, title="MetaLoop Shell", border_style="blue", box=box.ROUNDED))

    def _print_overview(self, status: dict[str, Any]) -> None:
        table = Table.grid(padding=(0, 2))
        table.add_column(style="dim", no_wrap=True)
        table.add_column()
        table.add_row("design", self._design_summary(status))
        table.add_row("mission", self._mission_summary(status))
        table.add_row("run", self._run_summary(status))
        table.add_row("verification", self._verification_summary(status))
        table.add_row("redesign", self._redesign_summary(status))
        table.add_row("attempts", self._attempt_summary(status))
        table.add_row("next", str(status.get("next_action") or "-"))
        self.ui.console.print(Panel(table, title="Workspace Overview", border_style="cyan", box=box.ROUNDED))

    def _print_action(self, action: ProposedAction, *, title: str = "Proposed Action") -> None:
        lines = [f"action: {action.action.value}", f"reason: {action.reason}"]
        if action.assistant_message:
            lines.insert(0, action.assistant_message)
        if action.command:
            lines.append(f"command: metaloop {' '.join(action.command)} --workspace {self.workspace}")
        if action.boundary_note:
            lines.append(f"boundary: {action.boundary_note}")
        self.ui.console.print(Panel("\n".join(lines), title=title, border_style="yellow", box=box.ROUNDED))

    def _print_non_executable_action(self, action: ProposedAction) -> None:
        if action.action == UserAction.UNKNOWN:
            self.ui.console.out(f"next: {action.boundary_note}")
            return
        if action.user_feedback:
            self.ui.console.out(f"feedback: {action.user_feedback}")
        self.ui.console.out("next: revision/redesign apply flow is not implemented yet")
        self.ui.console.out("note: locked MissionSpec, MissionCapsule, and GoalContract were not modified")

    def _confirm(self, action: ProposedAction) -> bool:
        answer = input(f"Run {action.action.value}? [y/N] ").strip().casefold()
        return answer in {"y", "yes", "是", "确认", "运行", "执行"}

    def _design_summary(self, status: dict[str, Any]) -> str:
        design = status.get("design", {})
        return (
            f"{design.get('state', 'missing')} "
            f"locked={design.get('locked', False)} "
            f"contract={design.get('contract_path') or '-'}"
        )

    def _mission_summary(self, status: dict[str, Any]) -> str:
        mission = status.get("mission", {})
        intent = mission.get("intent_summary") or "-"
        return f"{mission.get('state', 'missing')} path={mission.get('path') or '-'} intent={intent}"

    def _run_summary(self, status: dict[str, Any]) -> str:
        run = status.get("run", {})
        return f"{run.get('state', 'missing')} run_id={run.get('run_id') or '-'} mode={run.get('mode') or '-'}"

    def _verification_summary(self, status: dict[str, Any]) -> str:
        verification = status.get("verification", {})
        return (
            f"{verification.get('state', 'missing')} "
            f"status={verification.get('status') or '-'} "
            f"hard={verification.get('hard_validator_passed', 0)}/{verification.get('hard_validator_total', 0)}"
        )

    def _redesign_summary(self, status: dict[str, Any]) -> str:
        redesign = status.get("redesign", {})
        return f"{redesign.get('state', 'missing')} route={redesign.get('reviewer_route') or '-'}"

    def _attempt_summary(self, status: dict[str, Any]) -> str:
        attempts = status.get("attempt_history", {})
        return f"{attempts.get('state', 'missing')} count={attempts.get('count', 0)} latest={attempts.get('latest_path') or '-'}"
