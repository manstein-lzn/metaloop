from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import atexit
import itertools
import json
from pathlib import Path
import shlex
import sys
import termios
import threading
import textwrap
import time
import tty
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from metaloop.co_design import CoDesignQuestion, MissionSpecReview
from metaloop.schemas import KernelState, MissionSpec

try:
    import readline
except ImportError:  # pragma: no cover - readline is Unix-oriented.
    readline = None

_READLINE_CONFIGURED = False
_EDITOR_KEY_BINDINGS: KeyBindings | None = None


class MetaLoopUI:
    def __init__(self, *, stderr: bool = False) -> None:
        self.console = Console(stderr=stderr, highlight=False)
        self.error_console = Console(stderr=True, highlight=False)
        self._active_activity: ActivityReporter | None = None
        self._prompt_session: PromptSession | None = None
        _configure_readline()

    def print_error(self, message: str) -> None:
        self.error_console.print(Panel(str(message), title="MetaLoop Error", border_style="red", box=box.ROUNDED))

    def print_json_error(self, title: str, payload: str) -> None:
        self.error_console.print(Panel(Syntax(payload, "json", word_wrap=True), title=title, border_style="red", box=box.ROUNDED))

    def print_status(self, message: str) -> None:
        self.console.print(Text(message, style="dim"))

    @contextmanager
    def activity(self, message: str) -> Iterator[ActivityReporter]:
        reporter = ActivityReporter(self, message)
        previous_activity = self._active_activity
        self._active_activity = reporter
        reporter.update(message)
        try:
            yield reporter
        finally:
            reporter.stop(final=True)
            self._active_activity = previous_activity

    @contextmanager
    def run_progress(self, message: str) -> Iterator[RunProgressReporter]:
        reporter = RunProgressReporter(self, message)
        previous_activity = self._active_activity
        self._active_activity = None
        reporter.start()
        try:
            yield reporter
        finally:
            reporter.stop(final=True)
            self._active_activity = previous_activity

    def ask_question(self, question: CoDesignQuestion) -> str:
        self._pause_activity()
        title = _question_title(question.question_id)
        body = Text(question.prompt, style="bold")
        if question.reason:
            body.append(f"\n\nWhy: {question.reason}", style="dim")
        if question.help_text:
            body.append(f"\nHint: {question.help_text}", style="dim")
        self.console.print(Panel(body, title=title, border_style="cyan", box=box.ROUNDED))

        if not question.options:
            return self._ask("Answer").strip()

        selection = self._select_option(question.options)
        if selection == len(question.options):
            return self._ask("请输入你的想法").strip()
        if selection is not None:
            return question.options[selection]
        return self._ask_option_fallback(question.options)

    def print_design_start(self, workspace: str, interviewer: str) -> None:
        body = Table.grid(padding=(0, 2))
        body.add_column(style="dim", no_wrap=True)
        body.add_column()
        body.add_row("workspace", str(Path(workspace).expanduser().resolve()))
        body.add_row("co-designer", interviewer)
        body.add_row("flow", "goal -> options -> mission draft -> reviewer gate")
        self.console.print(Panel(body, title="MetaLoop Co-Design", subtitle="Mission design before execution", border_style="blue", box=box.ROUNDED))
        if interviewer == "codex":
            self.print_status("Co-designer is analyzing the workspace and shaping the first question. This can take a moment.")

    def print_design_result(
        self,
        mission: MissionSpec,
        review: MissionSpecReview,
        output_path: Path,
        next_command: str,
        design_artifacts: dict[str, Path] | None = None,
    ) -> None:
        status = "passed" if review.passed else "needs attention"
        capsule_path = design_artifacts.get("design_capsule") if design_artifacts else None
        contract_path = design_artifacts.get("design_goal_contract") if design_artifacts else None
        readiness = "ready" if capsule_path is not None and contract_path is not None else "not compiled"
        summary = "\n".join(
            [
                f"mission: {output_path}",
                f"review: {status}",
                f"capsule_contract: {readiness}",
                f"next: {next_command}",
            ]
        )
        self.console.print(Panel(summary, title="Mission Ready", border_style="green" if review.passed else "yellow", box=box.ROUNDED))
        self.console.out(f"mission: {output_path}")
        self.console.out(f"review: {status}")
        self.console.out(f"capsule_contract: {readiness}")
        if capsule_path is not None:
            self.console.out(f"design_capsule: {capsule_path}")
        if contract_path is not None:
            self.console.out(f"design_goal_contract: {contract_path}")
        self.console.out(f"next: {next_command}")
        self.console.print(self._mission_table(mission))
        review_style = "green" if review.passed else "yellow"
        self.console.print(self._review_panel(review, border_style=review_style))

    def print_design_review(self, review_markdown: str, artifacts: dict[str, Path] | None = None) -> None:
        artifact_lines = []
        if artifacts:
            for key in ("design_draft", "design_review", "design_decisions", "design_transcript"):
                path = artifacts.get(key)
                if path is not None:
                    artifact_lines.append(f"{key}: {path}")
        if artifact_lines:
            self.console.print(
                Panel("\n".join(artifact_lines), title="Co-Design v2 Artifacts", border_style="blue", box=box.ROUNDED)
            )
        self.console.print(Panel(Markdown(review_markdown), title="Human Design Review", border_style="cyan", box=box.ROUNDED))

    def ask_design_review_action(self, round_index: int) -> str:
        self._pause_activity()
        prompt = (
            "Type approve/lock/完成/确认 to lock, or write feedback for another design round.\n\n"
            "Enter submits. Alt+Enter inserts a newline. Paste works as normal."
        )
        self.console.print(Panel(prompt, title=f"Design Refinement Round {round_index}", border_style="cyan", box=box.ROUNDED))
        while True:
            action = self._ask_editor("Design review").strip()
            if not action:
                self.print_status("No input submitted. Type approve/lock to finish, or enter feedback and press Enter.")
                continue
            return action

    def choose_mission(self, candidates: list[Path]) -> str:
        self.console.print(Panel("Multiple mission files found in this workspace.", title="Select Mission", border_style="yellow", box=box.ROUNDED))
        table = Table(show_header=True, box=box.SIMPLE_HEAVY, expand=True)
        table.add_column("#", style="cyan", no_wrap=True, width=4)
        table.add_column("Mission file")
        for index, candidate in enumerate(candidates, start=1):
            table.add_row(str(index), str(candidate))
        self.console.print(table)
        while True:
            choice = self._ask("Mission number").strip()
            try:
                selected = int(choice)
            except ValueError:
                self.print_error("Please enter a number.")
                continue
            if 1 <= selected <= len(candidates):
                return str(candidates[selected - 1])
            self.print_error("Selection out of range.")

    def print_run_summary(self, state: KernelState) -> None:
        status_style = {
            "completed": "green",
            "failed": "red",
            "blocked": "yellow",
            "proposed_next_task": "cyan",
        }.get(state.status.value, "white")
        overview = Table.grid(padding=(0, 2))
        overview.add_column(style="dim", no_wrap=True)
        overview.add_column()
        overview.add_row("run_id", state.mission.run_id)
        overview.add_row("status", f"[{status_style}]{state.status.value}[/{status_style}]")
        overview.add_row("events", str(len(state.events)))
        overview.add_row("intent", state.mission.intent)
        self.console.print(Panel(overview, title="Run Summary", border_style=status_style, box=box.ROUNDED))
        self.console.out(f"status: {state.status.value}")
        if state.plan is not None:
            self.console.print(self._plan_table(state))
        if state.review_results:
            self.console.print(self._review_results_table(state))
        if state.next_task_proposal is not None:
            self.console.print(
                Panel(
                    Syntax(json.dumps(state.next_task_proposal.model_dump(), indent=2, ensure_ascii=False), "json", word_wrap=True),
                    title="Next Task Proposal",
                    border_style="cyan",
                    box=box.ROUNDED,
                )
            )
        if state.failure_report is not None:
            self.console.print(
                Panel(
                    Syntax(json.dumps(state.failure_report.model_dump(), indent=2, ensure_ascii=False), "json", word_wrap=True),
                    title="Blocked Report" if state.failure_report.recoverable else "Failure Report",
                    border_style="yellow" if state.failure_report.recoverable else "red",
                    box=box.ROUNDED,
                )
            )
            recovery = _recovery_hint(state)
            if recovery:
                self.console.print(Panel(recovery, title="Suggested Recovery", border_style="yellow", box=box.ROUNDED))

    def print_runs(self, runs: list[dict[str, Any]]) -> None:
        if not runs:
            self.console.print(Panel("No runs found.", title="Runs", border_style="dim"))
            return
        table = Table(title="MetaLoop Runs", box=box.SIMPLE_HEAVY, expand=True)
        table.add_column("Run ID", style="cyan")
        table.add_column("Status")
        table.add_column("Updated")
        for run in runs:
            table.add_row(str(run["run_id"]), str(run["status"]), str(run["updated_at"]))
        self.console.print(table)

    def print_events(self, events) -> None:
        table = Table(title="Run Events", box=box.SIMPLE_HEAVY, expand=True)
        table.add_column("Created", style="dim")
        table.add_column("Event")
        table.add_column("Node")
        table.add_column("Step")
        for event in events:
            table.add_row(event.created_at, event.event_type, event.node or "", event.step_id or "")
        self.console.print(table)

    def print_show_summary(self, state: KernelState) -> None:
        self.print_run_summary(state)

    def _ask(self, label: str, *, default: str | None = None) -> str:
        self._pause_activity()
        prompt = label
        if default is not None:
            prompt = f"{prompt} [{default}]"
        value = input(f"{prompt}: ")
        if not value.strip() and default is not None:
            return default
        return value

    def _ask_editor(self, label: str) -> str:
        self._pause_activity()
        if not sys.stdin.isatty():
            return input(f"{label}: ")
        session = self._get_prompt_session()
        return session.prompt(
            [("class:prompt", f"{label}: ")],
            multiline=True,
            key_bindings=_submit_enter_key_bindings(),
            prompt_continuation="... ",
            bottom_toolbar=HTML("<style bg='ansiblack' fg='ansiwhite'> Enter submits | Alt+Enter inserts newline | Ctrl+C cancels </style>"),
        )

    def _get_prompt_session(self) -> PromptSession:
        if self._prompt_session is None:
            history_path = Path.home() / ".metaloop" / "input_history"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            self._prompt_session = PromptSession(
                history=FileHistory(str(history_path)),
                enable_history_search=True,
                complete_while_typing=False,
                style=_prompt_style(),
            )
        return self._prompt_session

    def _select_option(self, options: list[str]) -> int | None:
        self._pause_activity()
        if not self.console.is_terminal or not sys.stdin.isatty():
            return None
        entries = [*options, "Other / 手动输入"]
        selected = 0
        rendered_lines = 0
        try:
            while True:
                rendered_lines = self._render_option_selector(entries, selected, previous_lines=rendered_lines)
                try:
                    key = _read_key()
                except OSError:
                    return None
                if key in {"up", "left", "k"}:
                    selected = (selected - 1) % len(entries)
                elif key in {"down", "right", "j"}:
                    selected = (selected + 1) % len(entries)
                elif key in {"enter", "\n", "\r"}:
                    self._render_option_selector(entries, selected, previous_lines=rendered_lines, final=True)
                    return selected
                elif key.isdigit():
                    index = int(key) - 1
                    if 0 <= index < len(entries):
                        self._render_option_selector(entries, index, previous_lines=rendered_lines, final=True)
                        return index
                elif key in {"q", "escape"}:
                    self._render_option_selector(entries, len(options), previous_lines=rendered_lines, final=True)
                    return len(options)
        finally:
            self.console.file.write("\x1b[?25h")
            self.console.file.flush()

    def _ask_option_fallback(self, options: list[str]) -> str:
        table = self._option_table([*options, "Other / 手动输入"], selected_index=None)
        self.console.print(table)
        self.console.print(Text("Type a number and press Enter. Enter accepts the recommended option.", style="dim"))
        other_index = len(options) + 1
        value = self._ask("Choose", default="1").strip()
        if value.isdigit():
            selected = int(value)
            if 1 <= selected <= len(options):
                return options[selected - 1]
            if selected == other_index:
                return self._ask("请输入你的想法").strip()
        return value

    def _option_table(self, entries: list[str], selected_index: int | None) -> Table:
        table = Table(show_header=True, box=box.SIMPLE_HEAVY, expand=True)
        table.add_column("", width=2, no_wrap=True)
        table.add_column("#", style="cyan", no_wrap=True, width=4)
        table.add_column("Suggested answer", overflow="fold", ratio=1)
        table.add_column("Fit", style="dim", no_wrap=True)
        for index, option in enumerate(entries):
            marker = ">" if selected_index == index else ""
            fit = "recommended" if index == 0 else "custom" if index == len(entries) - 1 else "alternative"
            style = "bold reverse" if selected_index == index else "bold" if index == 0 else "dim" if fit == "custom" else ""
            table.add_row(marker, str(index + 1), option, fit, style=style)
        return table

    def _render_option_selector(
        self,
        entries: list[str],
        selected_index: int,
        *,
        previous_lines: int = 0,
        final: bool = False,
    ) -> int:
        if previous_lines:
            self.console.file.write(f"\x1b[{previous_lines}A\r\x1b[J")
        self.console.file.write("\x1b[?25l")
        lines = self._option_selector_lines(entries, selected_index, final=final)
        for text, style in lines:
            self.console.print(Text(text, style=style), soft_wrap=True)
        self.console.file.flush()
        return len(lines)

    def _option_selector_lines(self, entries: list[str], selected_index: int, *, final: bool = False) -> list[tuple[str, str]]:
        width = max(32, min(self.console.width, 120))
        option_width = max(20, width - 12)
        title = "Selected answer:" if final else "Use ↑/↓ to choose, Enter to confirm, number keys for quick select, Esc for manual input."
        lines: list[tuple[str, str]] = [
            (line, "dim")
            for line in textwrap.wrap(title, width=max(20, width - 2), break_long_words=True)
        ]
        for index, option in enumerate(entries):
            marker = ">" if index == selected_index else " "
            wrapped = textwrap.wrap(option, width=option_width, break_long_words=True, replace_whitespace=False) or [""]
            fit = "recommended" if index == 0 else "custom" if index == len(entries) - 1 else "alternative"
            style = "reverse bold" if index == selected_index else "bold" if index == 0 else "dim" if fit == "custom" else ""
            lines.append((f"{marker} {index + 1}. {wrapped[0]}", style))
            for extra in wrapped[1:]:
                lines.append((f"     {extra}", style))
        return lines

    def _mission_table(self, mission: MissionSpec) -> Table:
        table = Table(title="Mission Summary", box=box.SIMPLE_HEAVY, expand=True)
        table.add_column("Area", style="cyan", no_wrap=True)
        table.add_column("Details")
        table.add_row("Intent", mission.intent)
        table.add_row("Deliverables", "\n".join(mission.deliverables) if mission.deliverables else "None")
        criteria = "\n".join(
            f"{criterion.description} [{criterion.validation_type}]"
            for criterion in mission.acceptance_criteria
        )
        table.add_row("Acceptance", criteria)
        table.add_row("Workspace", mission.policy.workspace_root)
        table.add_row("Risk", mission.policy.risk_level.value)
        return table

    def _pause_activity(self) -> None:
        if self._active_activity is not None:
            self._active_activity.pause()

    def _review_panel(self, review: MissionSpecReview, *, border_style: str) -> Panel:
        if not review.findings:
            return Panel("No reviewer findings.", title="Mission Review", border_style=border_style, box=box.ROUNDED)
        table = Table(show_header=True, box=box.SIMPLE, expand=True)
        table.add_column("Severity", no_wrap=True)
        table.add_column("Finding")
        table.add_column("Recommendation")
        for finding in review.findings:
            style = "red" if finding.severity == "blocking" else "yellow" if finding.severity == "warning" else "dim"
            table.add_row(f"[{style}]{finding.severity}[/{style}]", finding.message, finding.recommendation)
        return Panel(table, title="Mission Review", border_style=border_style, box=box.ROUNDED)

    def _plan_table(self, state: KernelState) -> Table:
        table = Table(title="Execution Plan", box=box.SIMPLE_HEAVY, expand=True)
        table.add_column("#", style="cyan", width=4, no_wrap=True)
        table.add_column("Step")
        table.add_column("Expected Artifacts")
        for index, step in enumerate(state.plan.steps, start=1):
            table.add_row(str(index), step.title, "\n".join(step.expected_artifacts) or "-")
        return table

    def _review_results_table(self, state: KernelState) -> Table:
        table = Table(title="Reviewer Decisions", box=box.SIMPLE_HEAVY, expand=True)
        table.add_column("Step", style="dim")
        table.add_column("Passed", no_wrap=True)
        table.add_column("Route")
        table.add_column("Notes")
        for review in _condense_reviews(state.review_results):
            passed = "[green]yes[/green]" if review.passed else "[red]no[/red]"
            table.add_row(review.step_id, passed, review.route.value, review.notes or "")
        return table


def _question_title(question_id: str) -> str:
    labels = {
        "intent": "Mission Goal",
        "deliverables": "Deliverables",
        "criteria": "Acceptance Criteria",
        "file_exists": "File Validation",
        "file_contains": "Content Validation",
        "audience": "Audience",
        "constraints": "Constraints",
        "out_of_scope": "Out Of Scope",
    }
    return labels.get(question_id, question_id.replace("_", " ").title())


def _condense_reviews(reviews):
    condensed = []
    for review in reviews:
        if condensed and _same_review(condensed[-1], review):
            continue
        condensed.append(review)
    return condensed


def _same_review(left, right) -> bool:
    return (
        left.step_id == right.step_id
        and left.passed == right.passed
        and left.route == right.route
        and left.notes == right.notes
    )


def _recovery_hint(state: KernelState) -> str:
    report = state.failure_report
    if report is None:
        return ""
    message = report.message.lower()
    workspace = shlex.quote(str(Path(state.mission.policy.workspace_root).expanduser()))
    run_id = shlex.quote(state.mission.run_id)
    lines = []
    if "bwrap" in message or "loopback" in message or "operation not permitted" in message:
        lines.extend(
            [
                "Codex sandbox failed before it could run workspace commands.",
                "Try resuming without the bubblewrap sandbox:",
                f"metaloop resume {run_id} --sandbox danger-full-access --approval never --no-output-schema",
                "",
                "Also make sure you are running from the intended project directory, or pass the workspace explicitly:",
                f"cd {workspace}",
                "metaloop run --sandbox danger-full-access --approval never --no-output-schema",
            ]
        )
    elif "approval" in message or "auth" in message:
        lines.extend(
            [
                "The worker needs permission that the current approval policy did not allow.",
                f"metaloop resume {run_id} --approval on-request --no-output-schema",
            ]
        )
    elif "budget" in report.error_type.lower() or "budget" in message or "token budget exceeded" in message:
        lines.append("The run exhausted a configured budget before the mission could finish.")
        if "token" in message:
            current_limit = state.mission.budget.max_tokens
            suggested_tokens = (
                max(current_limit * 2, state.budget_usage.tokens + 20_000)
                if current_limit is not None
                else max(state.budget_usage.tokens + 20_000, 150_000)
            )
            lines.extend(
                [
                    "Resume with a larger explicit token cap, or omit --max-tokens for unlimited tokens:",
                    f"metaloop resume {run_id} --max-tokens {suggested_tokens} --no-output-schema",
                ]
            )
        else:
            lines.append("Resume with a larger relevant budget, or simplify the MissionSpec.")
    elif report.recommended_next_step:
        lines.append(report.recommended_next_step)
    return "\n".join(lines)


class ActivityReporter:
    _FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, ui: MetaLoopUI, message: str) -> None:
        self.ui = ui
        self.message = message
        self._last_message = ""
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._closed = False

    def update(self, message: str) -> None:
        if self._closed:
            return
        with self._lock:
            self.message = message
        if self.ui.console.is_terminal and sys.stdout.isatty():
            self._start()
            return
        if message != self._last_message:
            self._last_message = message
            self.ui.print_status(message)

    def pause(self) -> None:
        self._stop_spinner(clear=True)

    def stop(self, *, final: bool = False) -> None:
        if final:
            self._closed = True
        self._stop_spinner(clear=True)

    def _start(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _stop_spinner(self, *, clear: bool) -> None:
        if not self._running:
            return
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        self._running = False
        self._thread = None
        if clear and self.ui.console.is_terminal:
            self.ui.console.file.write("\r\x1b[K")
            self.ui.console.file.flush()

    def _spin(self) -> None:
        for frame in itertools.cycle(self._FRAMES):
            if self._stop_event.is_set():
                break
            with self._lock:
                message = self.message
            self.ui.console.file.write("\r\x1b[K" + self._format_line(frame, message))
            self.ui.console.file.flush()
            time.sleep(0.09)

    def _format_line(self, frame: str, message: str) -> str:
        width = max(20, self.ui.console.width)
        text = f"{frame} {message}"
        if len(text) > width - 1:
            return text[: max(0, width - 2)] + "…"
        return text


class RunProgressReporter:
    _FRAMES = ActivityReporter._FRAMES

    def __init__(self, ui: MetaLoopUI, message: str) -> None:
        self.ui = ui
        self.message = message
        self._start_time = time.monotonic()
        self._seq = 0
        self._last_message = ""
        self._lock = threading.Lock()
        self._render_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._closed = False

    def start(self) -> None:
        body = Table.grid(padding=(0, 2))
        body.add_column(style="dim", no_wrap=True)
        body.add_column()
        body.add_row("progress", "persistent event stream")
        body.add_row("details", ".metaloop/run.json and .metaloop/runs/<run_id>/codex_events.jsonl")
        self.ui.console.print(Panel(body, title="MetaLoop Run Monitor", border_style="blue", box=box.ROUNDED))
        self.update(self.message)

    def update(self, message: str) -> None:
        if self._closed:
            return
        clean_message = _normalize_progress_message(message)
        with self._lock:
            self.message = clean_message
        if clean_message != self._last_message:
            self._last_message = clean_message
            self._print_event(clean_message)
        if self._is_interactive_terminal():
            self._start_spinner()

    def stop(self, *, final: bool = False) -> None:
        if final:
            self._closed = True
        self._stop_spinner(clear=True)

    def _print_event(self, message: str) -> None:
        with self._render_lock:
            if self._is_interactive_terminal():
                self.ui.console.file.write("\r\x1b[K")
                self.ui.console.file.flush()
            self._seq += 1
            elapsed = _format_elapsed(time.monotonic() - self._start_time)
            phase = _progress_phase(message)
            text = Text()
            text.append(f"{self._seq:02d}", style="cyan")
            text.append(f"  {elapsed}", style="dim")
            text.append(f"  {phase:<10}", style=_progress_phase_style(phase))
            text.append(f"  {message}")
            self.ui.console.print(text, soft_wrap=True)

    def _start_spinner(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _stop_spinner(self, *, clear: bool) -> None:
        if not self._running:
            return
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        self._running = False
        self._thread = None
        if clear and self._is_interactive_terminal():
            with self._render_lock:
                self.ui.console.file.write("\r\x1b[K")
                self.ui.console.file.flush()

    def _spin(self) -> None:
        for frame in itertools.cycle(self._FRAMES):
            if self._stop_event.is_set():
                break
            with self._lock:
                message = self.message
            line = self._format_live_line(frame, message)
            with self._render_lock:
                self.ui.console.file.write("\r\x1b[K" + line)
                self.ui.console.file.flush()
            time.sleep(0.15)

    def _format_live_line(self, frame: str, message: str) -> str:
        elapsed = _format_elapsed(time.monotonic() - self._start_time)
        text = f"{frame} running {elapsed} | {message}"
        width = max(20, self.ui.console.width)
        if len(text) > width - 1:
            return text[: max(0, width - 2)] + "…"
        return text

    def _is_interactive_terminal(self) -> bool:
        return self.ui.console.is_terminal and hasattr(self.ui.console.file, "isatty") and self.ui.console.file.isatty()


def _normalize_progress_message(message: str) -> str:
    return " ".join(str(message).split()) or "working"


def _progress_phase(message: str) -> str:
    lower = message.lower()
    if "started" in lower or "starting" in lower:
        return "status"
    if "compil" in lower or "contract" in lower or "artifact" in lower:
        return "prepare"
    if "repair" in lower or "fix" in lower:
        return "repair"
    if "verif" in lower or "validator" in lower or "evidence" in lower:
        return "verify"
    if "review" in lower or "route" in lower:
        return "review"
    if "codex" in lower or "worker" in lower or "agent" in lower or "command" in lower:
        return "execute"
    if "finish" in lower or "complete" in lower or "failed" in lower or "blocked" in lower:
        return "final"
    return "status"


def _progress_phase_style(phase: str) -> str:
    return {
        "prepare": "blue",
        "execute": "cyan",
        "review": "magenta",
        "repair": "yellow",
        "verify": "green",
        "final": "bold",
    }.get(phase, "dim")


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _read_key() -> str:
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        char = sys.stdin.read(1)
        if char == "\x1b":
            second = sys.stdin.read(1)
            if second == "[":
                third = sys.stdin.read(1)
                return {
                    "A": "up",
                    "B": "down",
                    "C": "right",
                    "D": "left",
                }.get(third, "escape")
            return "escape"
        if char in {"\r", "\n"}:
            return "enter"
        return char
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _submit_enter_key_bindings() -> KeyBindings:
    global _EDITOR_KEY_BINDINGS
    if _EDITOR_KEY_BINDINGS is not None:
        return _EDITOR_KEY_BINDINGS
    bindings = KeyBindings()

    @bindings.add("c-m", eager=True)
    def _(event) -> None:
        event.app.exit(result=event.app.current_buffer.text)

    @bindings.add("escape", "c-m", eager=True)
    def _(event) -> None:
        event.current_buffer.insert_text("\n")

    _EDITOR_KEY_BINDINGS = bindings
    return bindings


def _prompt_style() -> Style:
    return Style.from_dict(
        {
            "prompt": "bold ansicyan",
            "bottom-toolbar": "bg:ansiblack ansiwhite",
        }
    )


def _configure_readline() -> None:
    global _READLINE_CONFIGURED
    if _READLINE_CONFIGURED or readline is None or not sys.stdin.isatty():
        return
    _READLINE_CONFIGURED = True
    try:
        readline.parse_and_bind("set editing-mode emacs")
        readline.parse_and_bind("set enable-keypad on")
        readline.set_history_length(500)
        history_path = Path.home() / ".local" / "share" / "metaloop" / "input_history"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        if history_path.exists():
            readline.read_history_file(str(history_path))
        atexit.register(readline.write_history_file, str(history_path))
    except OSError:
        return
