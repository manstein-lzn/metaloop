from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import shlex
import sys
from pathlib import Path

from metaloop.agents import CodexRoleAgentBackend
from metaloop.codex_adapter import map_codex_event_type
from metaloop.co_design import (
    CoDesignAgentError,
    CoDesignDecision,
    CoDesignQuestion,
    CoDesignRunner,
    CoDesignSession,
    CodexCoDesignInterviewer,
    CodexCoDesignBrainstormer,
    CodexCoDesignAnswerProvider,
    InteractiveAnswerProvider,
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
from metaloop.kernel import MetaLoopKernel
from metaloop.codex_adapter import CodexExecOptions
from metaloop.capsule import MissionCapsule
from metaloop.design_store import CoDesignCheckpointStore
from metaloop.goal import DEFAULT_EXECUTION_REPORT_PATH, RedesignProposal, VerificationResult, render_goal_objective, verify_mission
from metaloop.goal_runtime import CodexExecGoalRuntimeAdapter, GoalRuntimeResult
from metaloop.mission_loader import build_mission_from_cli, load_mission_file
from metaloop.run_artifacts import StructuredRunManifest
from metaloop.schemas import new_id
from metaloop.soft_review import CodexSoftReviewer
from metaloop.storage import SQLiteRunStore
from metaloop.tui_shell import TuiShell
from metaloop.ui import MetaLoopUI
from metaloop.user_agent import CodexExecUserAgent, CodexSdkOptions, CodexSdkUserAgent, UserAgent
from metaloop.workers import CodexExecWorkerBackend


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MetaLoop Kernel local runner.")
    subparsers = parser.add_subparsers(dest="command")

    shell_parser = subparsers.add_parser("shell", help="Open the long-running MetaLoop workspace shell.")
    shell_parser.add_argument("--workspace", default=".", help="Workspace root to inspect and operate on.")
    shell_parser.add_argument(
        "--user-agent",
        choices=["sdk", "exec", "local"],
        default="sdk",
        help="User-facing shell agent. sdk is the default; exec is legacy one-shot codex exec; local is deterministic debugging.",
    )
    shell_parser.add_argument("--model", default=None, help="Codex model for --user-agent sdk or exec.")
    shell_parser.add_argument("--codex-timeout", type=int, default=300, help="Codex UserAgent timeout in seconds.")
    shell_parser.add_argument(
        "--reset-user-agent-thread",
        action="store_true",
        help="Forget the persisted Codex SDK UserAgent thread for this workspace and exit.",
    )
    shell_parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Run proposed shell actions without asking for confirmation.",
    )

    design_parser = subparsers.add_parser("design", help="Run Co-Design and write a MissionSpec file.")
    design_parser.add_argument("--intent", default="", help="Initial task intent.")
    design_parser.add_argument("--deliverable", action="append", default=[], help="Expected deliverable. Repeatable.")
    design_parser.add_argument("--criterion", action="append", default=[], help="Manual acceptance criterion. Repeatable.")
    design_parser.add_argument("--file-exists", action="append", default=[], help="Add file_exists acceptance criterion.")
    design_parser.add_argument(
        "--file-contains",
        action="append",
        default=[],
        help='Add file_contains criterion as "path::expected text". Repeatable.',
    )
    design_parser.add_argument(
        "--command",
        action="append",
        default=[],
        dest="validation_commands",
        help="Add command acceptance criterion.",
    )
    design_parser.add_argument("--schema", action="append", default=[], help="Add JSON parse acceptance criterion.")
    design_parser.add_argument("--audience", default="", help="Audience or consumer of the result.")
    design_parser.add_argument("--background", default="", help="Background context for the task.")
    design_parser.add_argument("--constraint", action="append", default=[], help="Constraint or preference. Repeatable.")
    design_parser.add_argument("--out-of-scope", action="append", default=[], help="Boundary that should not be done.")
    design_parser.add_argument("--workspace", default=".", help="Workspace root for the generated mission.")
    design_parser.add_argument(
        "--domain-profile",
        choices=["engineering_development", "algorithm_research", "codex_skill_creation", "deep_research"],
        default=None,
        help="Explicit Mission Capsule domain profile.",
    )
    design_parser.add_argument(
        "--risk-level",
        choices=["low", "medium", "high", "critical"],
        default="medium",
        help="Policy risk level for the generated mission.",
    )
    design_parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Optional token cap for the generated mission. Defaults to unlimited.",
    )
    design_parser.add_argument("--max-usd", type=float, default=2.0, help="USD budget for the generated mission.")
    design_parser.add_argument("--output", default=None, help="Output MissionSpec path.")
    design_parser.add_argument(
        "--interviewer",
        choices=["rule", "codex"],
        default=None,
        help="Co-Design interviewer backend.",
    )
    design_parser.add_argument("--interviewer-model", default=None, help="Codex model for --interviewer codex.")
    design_parser.add_argument("--interviewer-timeout", type=int, default=180, help="Codex interviewer timeout in seconds.")
    design_parser.add_argument(
        "--brainstormer",
        choices=["rule", "codex"],
        default=None,
        help="Co-Design v2 brainstorm expansion backend. Defaults to codex in an interactive terminal, otherwise rule.",
    )
    design_parser.add_argument("--max-design-rounds", type=int, default=8, help="Maximum Co-Design loop rounds.")
    design_parser.add_argument("--max-questions-per-round", type=int, default=1, help="Maximum Co-Design questions per round.")
    design_parser.add_argument("--no-interactive", action="store_true", help="Do not ask questions; fail if required fields are missing.")
    design_parser.add_argument("--no-deep", action="store_true", help="Skip deep follow-up questions in interactive mode.")
    design_parser.add_argument(
        "--autonomous",
        action="store_true",
        help="Allow the interviewer to complete core MissionSpec fields, then require reviewer approval.",
    )
    design_parser.add_argument("--strict-review", action="store_true", help="Do not write the mission if reviewer finds blocking issues.")
    design_parser.add_argument("--review-output", help="Optional path for MissionSpec review JSON.")
    design_parser.add_argument("--resume", action="store_true", help="Resume the saved Co-Design session for this workspace.")
    design_parser.add_argument("--design-state", default=None, help="Path to Co-Design checkpoint JSON.")
    design_parser.add_argument("--json", action="store_true", help="Print generated MissionSpec JSON.")

    run_parser = subparsers.add_parser("run", help="Run a MetaLoop Kernel mission.")
    run_parser.add_argument("intent", nargs="?", default=None, help="Mission intent.")
    run_parser.add_argument("--mission", help="Path to a MissionSpec JSON/YAML file.")
    run_parser.add_argument(
        "--criterion",
        default="The run reaches a structured terminal state.",
        help="Acceptance criterion description.",
    )
    run_parser.add_argument("--workspace", default=".", help="Workspace root for this run.")
    run_parser.add_argument("--db", default=".metaloop/runs.sqlite", help="SQLite run store path.")
    run_parser.add_argument("--no-store", action="store_true", help="Do not persist events/checkpoints.")
    run_parser.add_argument(
        "--mode",
        choices=["auto", "goal", "rigorous"],
        default="auto",
        help="Execution mode. auto uses goal mode for mission files and rigorous mode for legacy direct intents.",
    )
    run_parser.add_argument("--worker", choices=["dummy", "codex"], default=None, help="Worker backend.")
    run_parser.add_argument(
        "--sandbox",
        choices=["read-only", "workspace-write", "danger-full-access"],
        default="workspace-write",
        help="Codex sandbox mode when --worker codex is used.",
    )
    run_parser.add_argument(
        "--approval",
        choices=["never", "on-request", "on-failure", "untrusted"],
        default="on-request",
        help="Codex approval policy when --worker codex is used.",
    )
    run_parser.add_argument("--model", default=None, help="Codex model when --worker codex is used.")
    run_parser.add_argument("--codex-timeout", type=int, default=900, help="Codex exec timeout in seconds.")
    run_parser.add_argument("--max-tokens", type=int, default=None, help="Set a token cap for this run. Defaults to unlimited unless the mission sets one.")
    run_parser.add_argument("--max-usd", type=float, default=None, help="Override mission USD budget for this run.")
    run_parser.add_argument("--max-tool-calls", type=int, default=None, help="Override mission tool-call budget for this run.")
    run_parser.add_argument("--skip-git-repo-check", action="store_true", help="Allow Codex outside a Git repo.")
    run_parser.add_argument(
        "--no-output-schema",
        action="store_true",
        help="Do not pass --output-schema to codex exec; rely on prompt JSON and MetaLoop validation.",
    )
    run_parser.add_argument(
        "--strict-exit-code",
        action="store_true",
        help="Return 2 for proposed_next_task and 3 for blocked states.",
    )
    run_parser.add_argument("--json", action="store_true", help="Print final state as JSON.")

    compile_parser = subparsers.add_parser("compile", help="Compile a MissionSpec into a Codex-facing goal objective.")
    compile_parser.add_argument("--mission", help="Path to a MissionSpec JSON/YAML file.")
    compile_parser.add_argument("--workspace", default=".", help="Workspace root used for mission discovery.")
    compile_parser.add_argument("--output", default=None, help="Optional path for the compiled goal objective.")
    compile_parser.add_argument("--json", action="store_true", help="Print the compiled goal objective as JSON.")

    verify_parser = subparsers.add_parser("verify", help="Verify the current mission using MetaLoop acceptance checks.")
    verify_parser.add_argument("--mission", help="Path to a MissionSpec JSON/YAML file.")
    verify_parser.add_argument("--workspace", default=".", help="Workspace root used for mission discovery.")
    verify_parser.add_argument(
        "--report",
        default=".metaloop/execution_report.json",
        help="ExecutionReport path relative to the mission workspace.",
    )
    verify_parser.add_argument("--json", action="store_true", help="Print VerificationResult JSON.")

    status_parser = subparsers.add_parser("status", help="Show the current workspace MetaLoop structured status.")
    status_parser.add_argument("--workspace", default=".", help="Workspace root to inspect.")
    status_parser.add_argument("--json", action="store_true", help="Print status JSON.")

    list_parser = subparsers.add_parser("list", help="List persisted MetaLoop runs.")
    list_parser.add_argument("--db", default=".metaloop/runs.sqlite", help="SQLite run store path.")
    list_parser.add_argument("--json", action="store_true", help="Print runs as JSON.")

    show_parser = subparsers.add_parser("show", help="Show a persisted MetaLoop run.")
    show_parser.add_argument("run_id", help="Run id to inspect.")
    show_parser.add_argument("--db", default=".metaloop/runs.sqlite", help="SQLite run store path.")
    show_parser.add_argument("--events", action="store_true", help="Show event list instead of final state.")
    show_parser.add_argument("--json", action="store_true", help="Print full JSON.")

    resume_parser = subparsers.add_parser("resume", help="Resume an interrupted MetaLoop run from checkpoint.")
    resume_parser.add_argument("run_id", nargs="?", default=None, help="Run id to resume. Defaults to latest resumable run.")
    resume_parser.add_argument("--db", default=".metaloop/runs.sqlite", help="SQLite run store path.")
    resume_parser.add_argument("--workspace", default=".", help="Workspace root for goal-style resume.")
    resume_parser.add_argument(
        "--mode",
        choices=["auto", "goal", "rigorous"],
        default="auto",
        help="Resume mode. auto uses SQLite checkpoints first, then goal-style .metaloop state.",
    )
    resume_parser.add_argument("--worker", choices=["dummy", "codex"], default=None, help="Worker backend.")
    resume_parser.add_argument(
        "--sandbox",
        choices=["read-only", "workspace-write", "danger-full-access"],
        default="workspace-write",
        help="Codex sandbox mode when --worker codex is used.",
    )
    resume_parser.add_argument(
        "--approval",
        choices=["never", "on-request", "on-failure", "untrusted"],
        default="on-request",
        help="Codex approval policy when --worker codex is used.",
    )
    resume_parser.add_argument("--model", default=None, help="Codex model when --worker codex is used.")
    resume_parser.add_argument("--codex-timeout", type=int, default=900, help="Codex exec timeout in seconds.")
    resume_parser.add_argument("--max-tokens", type=int, default=None, help="Set a token cap for the resumed run. Defaults to the mission/checkpoint value.")
    resume_parser.add_argument("--max-usd", type=float, default=None, help="Override mission USD budget for resumed run.")
    resume_parser.add_argument("--max-tool-calls", type=int, default=None, help="Override mission tool-call budget for resumed run.")
    resume_parser.add_argument("--skip-git-repo-check", action="store_true", help="Allow Codex outside a Git repo.")
    resume_parser.add_argument("--no-output-schema", action="store_true", help="Do not pass --output-schema to codex exec.")
    resume_parser.add_argument("--strict-exit-code", action="store_true", help="Return strict terminal-state exit codes.")
    resume_parser.add_argument("--json", action="store_true", help="Print final state as JSON.")

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = _normalize_legacy_run(argv)
    args = build_parser().parse_args(argv)
    if args.command == "shell":
        return _shell(args)
    if args.command == "design":
        return _design(args)
    if args.command == "list":
        return _list_runs(args)
    if args.command == "show":
        return _show_run(args)
    if args.command == "resume":
        return _resume_run(args)
    if args.command == "compile":
        return _compile_goal(args)
    if args.command == "verify":
        return _verify(args)
    if args.command == "status":
        return _status_command(args)
    return _run(args)


def _normalize_legacy_run(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        return ["shell"]
    if argv[0] in {"shell", "design", "run", "compile", "verify", "status", "list", "show", "resume", "-h", "--help"}:
        return argv
    return ["run", *argv]


def _shell(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    if args.reset_user_agent_thread:
        return _reset_user_agent_thread(workspace)
    user_agent = _make_shell_user_agent(args, workspace)
    shell = TuiShell(
        workspace=workspace,
        status_reader=_read_workspace_status,
        command_runner=main,
        user_agent=user_agent,
        confirm_actions=not args.no_confirm,
    )
    return shell.run()


def _reset_user_agent_thread(workspace: Path) -> int:
    ui = MetaLoopUI()
    path = workspace / ".metaloop" / "user_agent_thread.json"
    try:
        path.unlink()
    except FileNotFoundError:
        ui.console.out(f"user_agent_thread: already_reset path={path}")
        return 0
    except OSError as exc:
        ui.print_error(f"Failed to reset user agent thread: {exc}")
        return 1
    ui.console.out(f"user_agent_thread: reset path={path}")
    return 0


def _make_shell_user_agent(args: argparse.Namespace, workspace: Path):
    if args.user_agent == "local":
        return UserAgent()
    if args.user_agent == "exec":
        return CodexExecUserAgent(
            CodexExecOptions(
                model=args.model,
                sandbox="read-only",
                approval_policy="never",
                timeout_seconds=args.codex_timeout,
                working_directory=str(workspace),
                skip_git_repo_check=True,
                use_output_schema=False,
            )
        )
    return CodexSdkUserAgent(
        CodexSdkOptions(
            model=args.model,
            timeout_seconds=args.codex_timeout,
            working_directory=str(workspace),
            skip_git_repo_check=True,
            sandbox_mode="read-only",
            approval_policy="never",
            thread_store_path=str(workspace / ".metaloop" / "user_agent_thread.json"),
        )
    )

def _design(args: argparse.Namespace) -> int:
    ui = MetaLoopUI()
    try:
        if args.json:
            args.no_interactive = True
        design_store = CoDesignCheckpointStore(_design_state_path(args))
        initial_rounds = []
        checkpoint = design_store.load() if args.resume else None
        if checkpoint is not None:
            draft = checkpoint.draft
            initial_rounds = checkpoint.rounds
        else:
            draft = build_draft_from_options(
                intent=args.intent,
                deliverables=args.deliverable,
                criteria=args.criterion,
                file_exists=args.file_exists,
                file_contains=args.file_contains,
                commands=args.validation_commands,
                schemas=args.schema,
                audience=args.audience,
                background=args.background,
                constraints=args.constraint,
                out_of_scope=args.out_of_scope,
                workspace_root=args.workspace,
                risk_level=args.risk_level,
                max_tokens=args.max_tokens,
                max_usd=args.max_usd,
                domain_profile_id=args.domain_profile,
            )
        if args.autonomous and args.no_interactive and not draft.intent.strip():
            raise ValueError("Autonomous Co-Design requires an initial --intent seed.")
        if args.interviewer is None:
            args.interviewer = "rule" if args.no_interactive else "codex"
        if not args.json:
            ui.print_design_start(args.workspace, args.interviewer)
        _bootstrap_interactive_intent(draft, args, ui)
        with _activity(ui, not args.json, "Preparing Co-Design interviewer..."):
            interviewer = _make_interviewer(args)
        answer_provider = _make_answer_provider(args, ui)
        with _activity(ui, not args.json, "Running Co-Design loop: interviewer, answers, draft update, reviewer gate...") as activity:
            runner = CoDesignRunner(
                interviewer,
                answer_provider,
                max_rounds=args.max_design_rounds,
                max_questions_per_round=args.max_questions_per_round,
                allow_core_edits=args.autonomous,
                require_clean_review=True,
                on_status=activity.update,
                on_checkpoint=design_store.save,
                initial_rounds=initial_rounds,
            )
            design_result = runner.run(draft)
        mission = design_result.mission
        review = design_result.review
        if args.review_output:
            Path(args.review_output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.review_output).write_text(review.model_dump_json(indent=2), encoding="utf-8")
        if (args.strict_review or args.autonomous) and not design_result.converged:
            ui.print_json_error("MissionSpec review failed", review_preview(review))
            return 1
        with _activity(ui, not args.json, "Expanding Co-Design: options, tradeoffs, risks, and route..."):
            brainstormer = _make_brainstormer(args)
            brainstorm = brainstormer.expand(mission, draft, review)
        decisions = []
        with _activity(ui, not args.json, "Writing Co-Design v2 draft and review artifacts..."):
            process_artifacts = write_design_process_artifacts(
                mission,
                review,
                brainstorm,
                args.workspace,
                rounds=design_result.rounds,
                decisions=decisions,
            )
        if not args.json:
            ui.print_design_review(render_design_review_markdown(mission, review, brainstorm, decisions), process_artifacts)
        mission, review, brainstorm, decisions = _interactive_design_refinement(
            args,
            ui,
            draft,
            mission,
            review,
            brainstorm,
            brainstormer,
            decisions,
            design_result.rounds,
            design_store,
        )
        if not review.passed:
            ui.print_json_error("MissionSpec review failed; refusing to lock invalid Co-Design contract", review_preview(review))
            return 1
        if brainstorm.unresolved_questions and not _has_accepted_design_decision(decisions):
            ui.print_json_error(
                "Co-Design has unresolved decisions; refusing to lock MissionSpec",
                json.dumps(
                    {
                        "unresolved_questions": brainstorm.unresolved_questions,
                        "recommended_next_step": "Run interactive `metaloop design`, resolve the open decisions, then approve/lock the design.",
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
            )
            return 1
        with _activity(ui, not args.json, "Writing MissionSpec..."):
            mission.locked = True
            output_path = write_mission(mission, _default_design_output(args))
        with _activity(ui, not args.json, "Compiling design Capsule and GoalContract preview..."):
            design_artifacts = write_design_artifacts(mission, args.workspace)
        lock = lock_design(
            mission,
            workspace_root=args.workspace,
            mission_path=output_path,
            brainstorm=brainstorm,
            decisions=decisions,
            approval_source="auto_non_interactive" if args.no_interactive or args.json else "human",
        )
        process_artifacts = write_design_process_artifacts(
            mission,
            review,
            brainstorm,
            args.workspace,
            rounds=design_result.rounds,
            decisions=decisions,
            lock=lock,
        )
        design_artifacts.update(process_artifacts)
        design_store.clear()
    except KeyboardInterrupt:
        ui.print_error(f"Co-Design interrupted. Resume with: metaloop design --resume --workspace {shlex.quote(str(args.workspace))}")
        return 130
    except CoDesignAgentError as exc:
        ui.print_error(
            "Co-Design agent failed before the design could be locked. "
            f"No MissionSpec was written. Saved progress can be resumed with: metaloop design --resume --workspace {shlex.quote(str(args.workspace))}\n\n"
            f"agent_error: {exc}\n"
            "If this repeats during brainstorming, retry with: "
            f"metaloop design --resume --workspace {shlex.quote(str(args.workspace))} --brainstormer rule"
        )
        return 1
    except ValueError as exc:
        ui.print_error(str(exc))
        return 1

    if args.json:
        print(mission.model_dump_json(indent=2))
    else:
        ui.print_design_result(mission, review, output_path, _next_run_command(output_path, args), design_artifacts)
    return 0


def _make_interviewer(args: argparse.Namespace):
    if args.interviewer == "codex":
        return CodexCoDesignInterviewer(
            CodexExecOptions(
                model=args.interviewer_model,
                sandbox="read-only",
                approval_policy="never",
                timeout_seconds=args.interviewer_timeout,
                working_directory=args.workspace,
                skip_git_repo_check=True,
                use_output_schema=False,
            ),
            autonomous=args.autonomous,
        )
    return RuleCoDesignInterviewer()


def _default_design_output(args: argparse.Namespace) -> Path | str:
    if args.output:
        return args.output
    return Path(args.workspace) / "metaloop.mission.json"


def _design_state_path(args: argparse.Namespace) -> Path:
    if args.design_state:
        return Path(args.design_state)
    return Path(args.workspace) / ".metaloop" / "design.session.json"


def _next_run_command(output_path: Path, args: argparse.Namespace) -> str:
    try:
        if args.output is None and Path(output_path).parent.resolve() == Path(args.workspace).expanduser().resolve():
            return "metaloop run"
    except OSError:
        pass
    return f"metaloop run --mission {shlex.quote(str(output_path))}"


def _make_answer_provider(args: argparse.Namespace, ui: MetaLoopUI):
    if not args.no_interactive:
        return InteractiveAnswerProvider(ui)
    if args.autonomous and args.interviewer == "codex":
        return CodexCoDesignAnswerProvider(
            CodexExecOptions(
                model=args.interviewer_model,
                sandbox="read-only",
                approval_policy="never",
                timeout_seconds=args.interviewer_timeout,
                working_directory=args.workspace,
                skip_git_repo_check=True,
                use_output_schema=False,
            )
        )
    return None


def _make_brainstormer(args: argparse.Namespace):
    if args.brainstormer is None:
        args.brainstormer = "codex" if args.interviewer == "codex" and not args.no_interactive and sys.stdin.isatty() else "rule"
    if args.brainstormer == "codex":
        return CodexCoDesignBrainstormer(
            CodexExecOptions(
                model=args.interviewer_model,
                sandbox="read-only",
                approval_policy="never",
                timeout_seconds=args.interviewer_timeout,
                working_directory=args.workspace,
                skip_git_repo_check=True,
                use_output_schema=False,
            )
        )
    return RuleCoDesignBrainstormer()


def _interactive_design_refinement(
    args: argparse.Namespace,
    ui: MetaLoopUI,
    draft,
    mission,
    review,
    brainstorm,
    brainstormer,
    decisions,
    rounds,
    design_store,
):
    if args.no_interactive or args.json or not sys.stdin.isatty():
        return mission, review, brainstorm, decisions
    reviewer = MissionSpecReviewer()
    for refinement_round in range(1, args.max_design_rounds + 1):
        action = ui.ask_design_review_action(refinement_round)
        if is_design_approval(action):
            decisions.append(
                _design_decision(
                    "accepted",
                    "Human approved and locked the Co-Design review.",
                    "User entered an explicit approve/lock command.",
                )
            )
            return mission, review, brainstorm, decisions
        ui.console.out("feedback: received")
        with _activity(ui, True, "Applying design feedback and rebuilding MissionSpec...") as activity:
            draft, decision = apply_human_design_feedback(draft, action)
            decisions.append(decision)
            design_store.save(draft, rounds)
            ui.console.out("feedback: saved")
            mission = CoDesignSession(draft).build_mission()
            activity.update("Running MissionSpec reviewer on the revised design...")
            review = reviewer.review(mission)
            activity.update("Expanding revised design options, risks, and unresolved questions...")
            brainstorm = brainstormer.expand(mission, draft, review)
            activity.update("Writing revised Co-Design artifacts...")
            process_artifacts = write_design_process_artifacts(
                mission,
                review,
                brainstorm,
                args.workspace,
                rounds=rounds,
                decisions=decisions,
            )
        ui.console.out("feedback: applied")
        ui.print_design_review(render_design_review_markdown(mission, review, brainstorm, decisions), process_artifacts)
        if (args.strict_review or args.autonomous) and not review.passed:
            ui.print_json_error("MissionSpec review failed after refinement", review_preview(review))
            raise ValueError("Co-Design refinement produced a MissionSpec that does not pass review.")
    raise ValueError("Co-Design refinement did not receive approve/lock before max design rounds.")


def _design_decision(status: str, summary: str, rationale: str):
    return CoDesignDecision(
        decision_id=f"decision_{abs(hash((summary, rationale))) % 10_000_000:07d}",
        status=status,
        summary=summary,
        rationale=rationale,
    )


def _has_accepted_design_decision(decisions: list[CoDesignDecision]) -> bool:
    return any(decision.status == "accepted" for decision in decisions)


def _bootstrap_interactive_intent(draft, args: argparse.Namespace, ui: MetaLoopUI) -> None:
    if args.no_interactive or draft.intent.strip():
        return
    answer = InteractiveAnswerProvider(ui).answer(
        CoDesignQuestion(
            question_id="intent",
            prompt="你希望 MetaLoop 帮你完成什么？",
            help_text="先用自然语言描述即可，接下来我会让 LLM 帮你一起细化方案。",
        ),
        draft,
        None,
    )
    if answer.answer.strip():
        draft.intent = answer.answer.strip()


def _run(args: argparse.Namespace) -> int:
    ui = MetaLoopUI()
    explicit_worker = args.worker is not None
    try:
        mission_file = args.mission
        if mission_file is None and args.intent is None:
            mission_file = _select_mission_file(Path(args.workspace), ui, interactive=not args.json)
        intent = args.intent or "Create a dummy artifact"
        mission = build_mission_from_cli(
            intent=intent,
            criterion=args.criterion,
            workspace=args.workspace,
            mission_file=mission_file,
        )
    except ValueError as exc:
        ui.print_error(str(exc))
        return 1
    mode = _resolve_run_mode(args, mission_file=mission_file, explicit_worker=explicit_worker)
    if mode != "goal":
        mission.run_id = new_id("run")
    _apply_budget_overrides(mission, args)
    mission.policy.workspace_root = str(Path(mission.policy.workspace_root))
    workspace = Path(mission.policy.workspace_root)

    if mode == "goal":
        return _run_goal_mode(args, mission, workspace, ui)

    if args.worker is None:
        args.worker = "codex" if mission_file is not None else "dummy"

    store = None if args.no_store else SQLiteRunStore(args.db)
    worker_backend = _make_worker_backend(args, workspace)
    role_agent_backend = _make_role_agent_backend(args, workspace)

    if args.json:
        state = MetaLoopKernel(store=store, worker_backend=worker_backend, role_agent_backend=role_agent_backend).run(mission)
    else:
        try:
            with ui.run_progress("MetaLoop rigorous run started: gateway, brainstormer, planner, worker, reviewer, scheduler.") as progress:
                store = _NotifyingRunStore(store, progress.update) if store is not None else store
                state = MetaLoopKernel(store=store, worker_backend=worker_backend, role_agent_backend=role_agent_backend).run(mission)
        except KeyboardInterrupt:
            ui.print_error("Run interrupted. Resume with: metaloop resume")
            return 130

    if args.json:
        print(state.model_dump_json(indent=2))
        return _exit_code(state, args.strict_exit_code)

    ui.print_run_summary(state)
    return _exit_code(state, args.strict_exit_code)


def _resolve_run_mode(args: argparse.Namespace, *, mission_file: str | None, explicit_worker: bool) -> str:
    if args.mode != "auto":
        return args.mode
    if mission_file is not None and not explicit_worker:
        return "goal"
    return "rigorous"


def _run_goal_mode(args: argparse.Namespace, mission, workspace: Path, ui: MetaLoopUI, *, resumed: bool = False) -> int:
    codex_options = _codex_options(args, workspace).model_copy(update={"use_output_schema": False})
    adapter = CodexExecGoalRuntimeAdapter(codex_options, soft_reviewer=CodexSoftReviewer(codex_options))
    try:
        if args.json:
            result = adapter.run(mission)
        else:
            with ui.run_progress("MetaLoop goal run started: compile contract, run Codex, verify evidence.") as progress:
                result = adapter.run(mission, on_status=progress.update)
    except KeyboardInterrupt:
        ui.print_error("Run interrupted. Re-run `metaloop run` or inspect .metaloop/run.json for the last structured state.")
        return 130

    if args.json:
        print(
            json.dumps(
                {
                    "mode": "goal",
                    "run": result.manifest.model_dump(by_alias=True),
                    "verification": result.verification.model_dump(by_alias=True),
                    "resumed": resumed,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return _goal_exit_code(result)

    _print_goal_run_summary(ui, result)
    return _goal_exit_code(result)


def _goal_exit_code(result: GoalRuntimeResult) -> int:
    if result.verification.status.value in {"failed", "blocked"}:
        return 1
    return 0


def _print_goal_run_summary(ui: MetaLoopUI, result: GoalRuntimeResult) -> None:
    verification = result.verification
    ui.console.out(f"status: {verification.status.value}")
    ui.console.out(f"run: {result.manifest.run_id}")
    ui.console.out(f"verification: {verification.status.value}")
    ui.console.out(f"reason: {verification.reason}")
    ui.console.out(
        "artifacts: "
        f"{result.manifest.mission_capsule_path}, {result.manifest.goal_contract_path}, "
        f"{result.manifest.execution_report_path}, {result.manifest.verification_result_path}"
    )


def _make_worker_backend(args: argparse.Namespace, workspace: Path):
    if args.worker != "codex":
        return None
    return CodexExecWorkerBackend(_codex_options(args, workspace))


def _make_role_agent_backend(args: argparse.Namespace, workspace: Path):
    if args.worker != "codex":
        return None
    return CodexRoleAgentBackend(_codex_options(args, workspace))


def _codex_options(args: argparse.Namespace, workspace: Path) -> CodexExecOptions:
    return CodexExecOptions(
        sandbox=args.sandbox,
        approval_policy=args.approval,
        model=args.model,
        timeout_seconds=args.codex_timeout,
        working_directory=str(workspace),
        skip_git_repo_check=args.skip_git_repo_check,
        use_output_schema=not args.no_output_schema,
    )


def _select_mission_file(workspace: Path, ui: MetaLoopUI, *, interactive: bool = True) -> str:
    candidates = _discover_mission_files(workspace)
    if not candidates:
        raise ValueError("No mission file found in this workspace. Run `metaloop design` first, or pass --mission.")
    if len(candidates) == 1:
        return str(candidates[0])
    if not interactive:
        raise ValueError("Multiple mission files found. Pass --mission when using --json.")
    return ui.choose_mission(candidates)


def _discover_mission_files(workspace: Path) -> list[Path]:
    root = workspace.expanduser().resolve()
    patterns = [
        "metaloop.mission.json",
        "metaloop.mission.yaml",
        "metaloop.mission.yml",
        "*.mission.json",
        "*.mission.yaml",
        "*.mission.yml",
        "mission.json",
        "mission.yaml",
        "mission.yml",
    ]
    seen = set()
    candidates = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(path)
    return candidates


def _exit_code(state, strict: bool) -> int:
    if state.status.value == "proposed_next_task":
        return 2 if strict else 0
    if state.status.value == "blocked":
        return 3 if strict else 0
    if state.failure_report is not None:
        return 1
    return 0


def _list_runs(args: argparse.Namespace) -> int:
    ui = MetaLoopUI()
    runs = SQLiteRunStore(args.db).list_runs()
    if args.json:
        print(json.dumps(runs, indent=2, ensure_ascii=False))
        return 0
    ui.print_runs(runs)
    return 0


def _show_run(args: argparse.Namespace) -> int:
    ui = MetaLoopUI()
    store = SQLiteRunStore(args.db)
    if args.events:
        events = store.events_for_run(args.run_id)
        if args.json:
            print(json.dumps([event.model_dump() for event in events], indent=2, ensure_ascii=False))
            return 0
        ui.print_events(events)
        return 0

    state = store.final_state(args.run_id) or store.latest_checkpoint(args.run_id)
    if state is None:
        ui.print_error(f"Run not found: {args.run_id}")
        return 1
    if args.json:
        print(state.model_dump_json(indent=2))
        return 0
    ui.print_show_summary(state)
    return 0


def _resume_run(args: argparse.Namespace) -> int:
    ui = MetaLoopUI()
    if args.mode == "goal":
        return _resume_goal_run(args, ui)
    store = SQLiteRunStore(args.db)
    run_id = args.run_id or store.latest_resumable_run_id()
    if run_id is None:
        if args.mode == "auto" and args.run_id is None and _structured_goal_run_path(Path(args.workspace)).exists():
            return _resume_goal_run(args, ui)
        ui.print_error("No resumable run found.")
        return 1
    checkpoint = store.latest_checkpoint(run_id)
    if checkpoint is None:
        ui.print_error(f"No checkpoint found for run: {run_id}")
        return 1
    if checkpoint.status.value in {"completed", "proposed_next_task"}:
        ui.print_error(f"Run is already terminal: {checkpoint.status.value}")
        return 1
    if checkpoint.status.value == "failed" and not _failed_run_is_resumable(checkpoint):
        ui.print_error(f"Run is already terminal: {checkpoint.status.value}")
        return 1

    args.worker = args.worker or "codex"
    _apply_budget_overrides(checkpoint.mission, args)
    workspace = Path(checkpoint.mission.policy.workspace_root)
    worker_backend = _make_worker_backend(args, workspace)
    role_agent_backend = _make_role_agent_backend(args, workspace)

    if args.json:
        state = MetaLoopKernel(store=store, worker_backend=worker_backend, role_agent_backend=role_agent_backend).run(checkpoint.mission)
    else:
        ui.print_status(f"Resuming run: {run_id}")
        with ui.run_progress("MetaLoop is resuming from the latest checkpoint.") as progress:
            notifying_store = _NotifyingRunStore(store, progress.update)
            state = MetaLoopKernel(store=notifying_store, worker_backend=worker_backend, role_agent_backend=role_agent_backend).run(checkpoint.mission)

    if args.json:
        print(state.model_dump_json(indent=2))
        return _exit_code(state, args.strict_exit_code)
    ui.print_run_summary(state)
    return _exit_code(state, args.strict_exit_code)


def _resume_goal_run(args: argparse.Namespace, ui: MetaLoopUI) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    run_path = _structured_goal_run_path(workspace)
    if not run_path.exists():
        ui.print_error(f"No goal-style run state found: {run_path}")
        return 1
    try:
        manifest = StructuredRunManifest.model_validate(json.loads(run_path.read_text(encoding="utf-8")))
        mission_path = _workspace_path(workspace, manifest.mission_path)
        mission = load_mission_file(mission_path)
        mission.run_id = manifest.run_id
        if mission.policy.workspace_root == ".":
            mission.policy.workspace_root = str(workspace)
        _apply_budget_overrides(mission, args)
        verification = _load_goal_verification(workspace, manifest)
        capsule = _load_goal_capsule(workspace, manifest)
        redesign = _load_goal_redesign(workspace, manifest)
    except Exception as exc:
        ui.print_error(f"Invalid goal-style run state: {exc}")
        return 1

    resume_decision = _decide_goal_resume(workspace, manifest, verification, capsule, redesign)
    if resume_decision["action"] == "redesign_required":
        if args.json:
            print(
                json.dumps(
                    {
                        "mode": "goal",
                        "run": manifest.model_dump(by_alias=True),
                        "verification": verification.model_dump(by_alias=True) if verification is not None else None,
                        "redesign": redesign.model_dump(by_alias=True) if redesign is not None else None,
                        "resumed": False,
                        "resume_decision": resume_decision,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            ui.console.out(f"status: redesign_required")
            ui.console.out(f"run: {manifest.run_id}")
            ui.console.out(f"resume: {resume_decision['message']}")
            ui.console.out(f"reason: {resume_decision['reason']}")
        return 1
    if resume_decision["action"] == "skip":
        if args.json:
            print(
                json.dumps(
                    {
                        "mode": "goal",
                        "run": manifest.model_dump(by_alias=True),
                        "verification": verification.model_dump(by_alias=True) if verification is not None else None,
                        "resumed": False,
                        "resume_decision": resume_decision,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            ui.console.out(f"status: {verification.status.value if verification is not None else manifest.status}")
            ui.console.out(f"run: {manifest.run_id}")
            ui.console.out("resume: not needed")
            ui.console.out(f"reason: {resume_decision['reason']}")
            if verification is not None and verification.reason:
                ui.console.out(f"verification_reason: {verification.reason}")
        return 0

    if not args.json:
        ui.print_status(f"Resuming goal-style run: {manifest.run_id}")
        ui.console.out(f"resume: {resume_decision['message']}")
    return _run_goal_mode(args, mission, workspace, ui, resumed=True)


def _compile_goal(args: argparse.Namespace) -> int:
    ui = MetaLoopUI()
    try:
        mission_file = args.mission or _select_mission_file(Path(args.workspace), ui, interactive=not args.json)
        mission = build_mission_from_cli(
            intent="",
            criterion="",
            workspace=args.workspace,
            mission_file=mission_file,
        )
    except ValueError as exc:
        ui.print_error(str(exc))
        return 1

    objective = render_goal_objective(mission)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(objective, encoding="utf-8")
    if args.json:
        print(json.dumps({"mission_id": mission.run_id, "goal_objective": objective}, indent=2, ensure_ascii=False))
    else:
        if args.output:
            ui.console.out(f"goal: {args.output}")
        else:
            ui.console.print(objective)
    return 0


def _verify(args: argparse.Namespace) -> int:
    ui = MetaLoopUI()
    try:
        mission_file = args.mission or _select_mission_file(Path(args.workspace), ui, interactive=not args.json)
        mission = build_mission_from_cli(
            intent="",
            criterion="",
            workspace=args.workspace,
            mission_file=mission_file,
        )
        mission, report_path = _verification_inputs_from_latest_goal_run(mission, args.report, Path(args.workspace))
        result = verify_mission(mission, report_path=report_path)
    except ValueError as exc:
        ui.print_error(str(exc))
        return 1

    if args.json:
        print(result.model_dump_json(by_alias=True, indent=2))
    else:
        ui.console.out(f"verification: {result.status.value}")
        ui.console.out(f"reason: {result.reason}")
    return 1 if result.status.value in {"failed", "blocked"} else 0


def _verification_inputs_from_latest_goal_run(mission, report_path: str, workspace: Path):
    if report_path != DEFAULT_EXECUTION_REPORT_PATH:
        return mission, report_path
    run_path = _structured_goal_run_path(workspace)
    if not run_path.exists():
        return mission, report_path
    try:
        manifest = StructuredRunManifest.model_validate(json.loads(run_path.read_text(encoding="utf-8")))
        runtime_mission_path = _workspace_path(workspace.expanduser().resolve(), manifest.mission_path)
        if not runtime_mission_path.exists():
            return mission, report_path
        runtime_mission = load_mission_file(runtime_mission_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return mission, report_path
    if runtime_mission.policy.workspace_root == ".":
        runtime_mission.policy.workspace_root = str(workspace.expanduser().resolve())
    return runtime_mission, manifest.execution_report_path or report_path


def _status_command(args: argparse.Namespace) -> int:
    ui = MetaLoopUI()
    workspace = Path(args.workspace).expanduser().resolve()
    status = _read_workspace_status(workspace)
    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return 0
    ui.console.out(f"workspace: {workspace}")
    ui.console.out(
        "design: "
        f"{status['design']['state']}"
        f" capsule={status['design'].get('capsule_path') or '-'}"
        f" contract={status['design'].get('contract_path') or '-'}"
        f" locked={status['design'].get('locked', False)}"
        f" evidence_required={status['design'].get('required_evidence_count', 0)}"
    )
    ui.console.out(
        "mission: "
        f"{status['mission']['state']}"
        f" path={status['mission'].get('path') or '-'}"
        f" intent={status['mission'].get('intent_summary') or '-'}"
        f" domain={status['mission'].get('domain_profile_id') or '-'}"
    )
    ui.console.out(
        "capsule: "
        f"{status['capsule']['state']}"
        f" lifecycle={status['capsule'].get('lifecycle_state') or '-'}"
        f" closure={status['capsule'].get('closure_outcome') or '-'}"
        f" evidence={status['capsule'].get('evidence_count', 0)}"
        f"/{status['capsule'].get('required_evidence_count', 0)}"
        f" attempts={status['capsule'].get('attempt_count', 0)}"
    )
    if status["capsule"].get("evidence_plan_summary"):
        ui.console.out(f"evidence_plan: {status['capsule']['evidence_plan_summary']}")
    if status["capsule"].get("latest_attempt"):
        latest = status["capsule"]["latest_attempt"]
        ui.console.out(
            "latest_attempt: "
            f"{latest.get('attempt_id') or '-'} "
            f"outcome={latest.get('outcome') or '-'} "
            f"commit={latest.get('commit_ref') or '-'} "
            f"changed={latest.get('changed_file_count', 0)}"
        )
    if status["capsule"].get("latest_decision_summary"):
        ui.console.out(f"capsule_decision: {status['capsule']['latest_decision_summary']}")
    ui.console.out(
        "run: "
        f"{status['run']['state']}"
        f" run_id={status['run'].get('run_id') or '-'}"
        f" mode={status['run'].get('mode') or '-'}"
        f" path={status['run'].get('path') or '-'}"
        f" attempt={status['run'].get('attempt_record_path') or '-'}"
    )
    if status["run"].get("codex_events_path"):
        ui.console.out(f"codex_events: {status['run']['codex_events_path']}")
    if status["run"].get("last_event_summary"):
        ui.console.out(f"last_event: {status['run']['last_event_summary']}")
    ui.console.out(
        "verification: "
        f"{status['verification']['state']}"
        f" status={status['verification'].get('status') or '-'}"
        f" hard={status['verification'].get('hard_validator_passed', 0)}/{status['verification'].get('hard_validator_total', 0)}"
        f" evidence={status['verification'].get('evidence_passed', 0)}/{status['verification'].get('evidence_total', 0)}"
        f" required={status['verification'].get('required_evidence_satisfied', 0)}/{status['verification'].get('required_evidence_total', 0)}"
    )
    if status["verification"].get("soft_review_route"):
        ui.console.out(f"soft_review_route: {status['verification']['soft_review_route']}")
    if status["verification"].get("reason"):
        ui.console.out(f"reason: {status['verification']['reason']}")
    ui.console.out(
        "redesign: "
        f"{status['redesign']['state']}"
        f" route={status['redesign'].get('reviewer_route') or '-'}"
        f" path={status['redesign'].get('path') or '-'}"
    )
    if status["redesign"].get("reason"):
        ui.console.out(f"redesign_reason: {status['redesign']['reason']}")
    if status["redesign"].get("contract_delta_summary"):
        ui.console.out(f"redesign_delta: {status['redesign']['contract_delta_summary']}")
    ui.console.out(
        "attempt_history: "
        f"{status['attempt_history']['state']}"
        f" count={status['attempt_history'].get('count', 0)}"
        f" latest={status['attempt_history'].get('latest_path') or '-'}"
    )
    ui.console.out(f"next_action: {status['next_action']}")
    return 0


def _read_workspace_status(workspace: Path) -> dict:
    metaloop_dir = workspace / ".metaloop"
    mission_path = workspace / "metaloop.mission.json"
    structured_mission_path = metaloop_dir / "mission.json"
    capsule_path = metaloop_dir / "mission_capsule.json"
    design_capsule_path = metaloop_dir / "design_capsule.json"
    run_path = metaloop_dir / "run.json"
    verification_path = metaloop_dir / "verification_result.json"
    redesign_path = metaloop_dir / "redesign_proposal.json"
    attempts_dir = metaloop_dir / "attempts"

    mission_state = _read_status_mission(workspace, mission_path, structured_mission_path)
    design_state = _read_status_design(design_capsule_path, metaloop_dir / "design_goal_contract.json")
    capsule_state = _read_status_capsule(capsule_path if capsule_path.exists() else design_capsule_path)
    redesign_state = _read_status_redesign(redesign_path)
    attempt_history_state = _read_status_attempt_history(attempts_dir)

    run_state = {"state": "missing"}
    if run_path.exists():
        try:
            manifest = StructuredRunManifest.model_validate(json.loads(run_path.read_text(encoding="utf-8")))
            run_state = {
                "state": manifest.status,
                "run_id": manifest.run_id,
                "mode": manifest.mode,
                "path": str(run_path),
                "codex_events_path": str(_workspace_path(workspace, manifest.codex_events_path)),
                "mission_capsule_path": manifest.mission_capsule_path,
                "execution_report_path": manifest.execution_report_path,
                "verification_result_path": manifest.verification_result_path,
                "attempt_record_path": manifest.attempt_record_path,
                "last_event_summary": _last_codex_event_summary(_workspace_path(workspace, manifest.codex_events_path)),
            }
        except Exception as exc:
            run_state = {"state": "invalid", "path": str(run_path), "error": str(exc)}

    verification_state = {"state": "missing"}
    if verification_path.exists():
        try:
            verification = VerificationResult.model_validate(json.loads(verification_path.read_text(encoding="utf-8")))
            verification_state = {
                "state": "ready",
                "status": verification.status.value,
                "reason": verification.reason,
                "path": str(verification_path),
                "hard_validator_passed": sum(1 for item in verification.hard_validator_results if item.passed),
                "hard_validator_total": len(verification.hard_validator_results),
                "evidence_passed": sum(1 for item in verification.evidence_results if item.passed),
                "evidence_total": len(verification.evidence_results),
                "required_evidence_total": verification.required_evidence_total,
                "required_evidence_satisfied": verification.required_evidence_satisfied,
                "required_evidence_summary": verification.required_evidence_summary,
                "soft_review_route": verification.soft_review_decision.route.value if verification.soft_review_decision is not None else None,
            }
        except Exception as exc:
            verification_state = {"state": "invalid", "path": str(verification_path), "error": str(exc)}
    else:
        verification_state.update(
            {
                "status": None,
                "reason": "",
                "path": None,
                "hard_validator_passed": 0,
                "hard_validator_total": 0,
                "evidence_passed": 0,
                "evidence_total": 0,
                "required_evidence_total": 0,
                "required_evidence_satisfied": 0,
                "required_evidence_summary": "",
                "soft_review_route": None,
            }
        )

    status = {
        "workspace": str(workspace),
        "design": design_state,
        "mission": mission_state,
        "capsule": capsule_state,
        "redesign": redesign_state,
        "attempt_history": attempt_history_state,
        "run": run_state,
        "verification": verification_state,
    }
    status["next_action"] = _status_next_action(status)
    return status


def _structured_goal_run_path(workspace: Path) -> Path:
    return workspace.expanduser().resolve() / ".metaloop" / "run.json"


def _workspace_path(workspace: Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return workspace / candidate


def _read_status_mission(workspace: Path, mission_path: Path, structured_mission_path: Path) -> dict:
    selected_path = None
    state = "missing"
    if mission_path.exists():
        selected_path = mission_path
        state = "ready"
    elif structured_mission_path.exists():
        selected_path = structured_mission_path
        state = "structured_only"
    mission_state = {
        "state": state,
        "path": str(selected_path) if selected_path is not None else None,
        "intent_summary": "",
        "domain_profile_id": None,
    }
    if selected_path is None:
        return mission_state
    try:
        mission = load_mission_file(selected_path)
    except Exception as exc:
        mission_state.update({"state": "invalid", "error": str(exc)})
        return mission_state
    mission_state.update(
        {
            "intent_summary": _shorten_status(mission.intent, 120),
            "domain_profile_id": mission.context.get("domain_profile_id") or mission.context.get("domain_profile"),
        }
    )
    if mission_state["domain_profile_id"] is None:
        metaloop_dir = workspace / ".metaloop"
        capsule = _load_capsule_path(metaloop_dir / "mission_capsule.json") or _load_capsule_path(metaloop_dir / "design_capsule.json")
        if capsule is not None:
            mission_state["domain_profile_id"] = capsule.domain_profile_id
    return mission_state


def _read_status_design(design_capsule_path: Path, design_contract_path: Path) -> dict:
    metaloop_dir = design_capsule_path.parent
    design_review_path = metaloop_dir / "design_review.md"
    design_lock_path = metaloop_dir / "design_lock.json"
    design_state = {
        "state": "missing",
        "capsule_path": None,
        "contract_path": str(design_contract_path) if design_contract_path.exists() else None,
        "review_path": str(design_review_path) if design_review_path.exists() else None,
        "lock_path": str(design_lock_path) if design_lock_path.exists() else None,
        "capsule_ready": False,
        "contract_ready": design_contract_path.exists(),
        "review_ready": design_review_path.exists(),
        "locked": design_lock_path.exists(),
        "domain_profile_id": None,
        "required_evidence_count": 0,
        "evidence_plan_summary": "",
    }
    capsule = _load_capsule_path(design_capsule_path)
    if capsule is None:
        if design_contract_path.exists():
            design_state["state"] = "partial"
        return design_state
    design_state.update(
        {
            "state": "ready" if design_contract_path.exists() else "capsule_only",
            "capsule_path": str(design_capsule_path),
            "capsule_ready": True,
            "domain_profile_id": capsule.domain_profile_id,
            "required_evidence_count": capsule.acceptance_contract.evidence_plan.required_count,
            "evidence_plan_summary": capsule.acceptance_contract.evidence_plan.summary,
        }
    )
    return design_state


def _read_status_capsule(capsule_path: Path) -> dict:
    capsule_state = {
        "state": "missing",
        "path": str(capsule_path),
        "lifecycle_state": None,
        "closure_outcome": None,
        "evidence_count": 0,
        "required_evidence_count": 0,
        "hard_validator_count": 0,
        "soft_review_count": 0,
        "attempt_count": 0,
        "evidence_plan_summary": "",
        "latest_attempt": None,
        "latest_decision_summary": "",
    }
    if not capsule_path.exists():
        capsule_state["path"] = None
        return capsule_state
    capsule = _load_capsule_path(capsule_path)
    if capsule is None:
        return {**capsule_state, "state": "invalid", "path": str(capsule_path)}
    latest_decision = capsule.decision_ledger[-1] if capsule.decision_ledger else None
    latest_attempt = capsule.attempt_history[-1] if capsule.attempt_history else None
    capsule_state.update(
        {
            "state": "ready",
            "path": str(capsule_path),
            "lifecycle_state": capsule.lifecycle_state.value,
            "closure_outcome": capsule.closure_outcome.value if capsule.closure_outcome is not None else None,
            "evidence_count": len(capsule.evidence_ledger),
            "required_evidence_count": capsule.acceptance_contract.evidence_plan.required_count,
            "hard_validator_count": len(capsule.acceptance_contract.verification_plan.hard_validator_ids),
            "soft_review_count": len(capsule.acceptance_contract.verification_plan.soft_review_criteria_ids),
            "attempt_count": len(capsule.attempt_history),
            "evidence_plan_summary": capsule.acceptance_contract.evidence_plan.summary,
            "latest_attempt": _status_attempt_summary(latest_attempt),
            "latest_decision_summary": _shorten_status(latest_decision.summary, 160) if latest_decision is not None else "",
        }
    )
    return capsule_state


def _status_attempt_summary(attempt) -> dict | None:
    if attempt is None:
        return None
    return {
        "attempt_id": attempt.attempt_id,
        "outcome": attempt.outcome.value,
        "commit_ref": attempt.git_commit_ref,
        "changed_file_count": len(attempt.changed_files or attempt.artifacts_produced),
        "result": attempt.result,
        "lesson": _shorten_status(attempt.lesson, 160) if attempt.lesson else "",
    }


def _read_status_attempt_history(attempts_dir: Path) -> dict:
    if not attempts_dir.exists():
        return {"state": "missing", "path": None, "count": 0, "latest_path": None}
    attempts = sorted(attempts_dir.glob("*.json"), key=lambda item: item.stat().st_mtime)
    return {
        "state": "ready",
        "path": str(attempts_dir),
        "count": len(attempts),
        "latest_path": str(attempts[-1]) if attempts else None,
    }


def _read_status_redesign(redesign_path: Path) -> dict:
    redesign_state = {
        "state": "missing",
        "path": None,
        "reviewer_route": None,
        "reason": "",
        "contract_delta": None,
        "contract_delta_summary": "",
    }
    if not redesign_path.exists():
        return redesign_state
    try:
        proposal = RedesignProposal.model_validate(json.loads(redesign_path.read_text(encoding="utf-8")))
    except Exception as exc:
        return {
            **redesign_state,
            "state": "invalid",
            "path": str(redesign_path),
            "error": str(exc),
        }
    return {
        "state": "ready",
        "path": str(redesign_path),
        "reviewer_route": proposal.reviewer_route.value,
        "reason": _shorten_status(proposal.reason, 180),
        "contract_delta": proposal.contract_delta.model_dump(),
        "contract_delta_summary": _redesign_delta_summary(proposal),
    }


def _redesign_delta_summary(proposal: RedesignProposal) -> str:
    delta = proposal.contract_delta
    counts = {
        "scope+": len(delta.added_scope),
        "scope-": len(delta.removed_scope),
        "non_goals+": len(delta.added_non_goals),
        "acceptance+": len(delta.added_acceptance),
        "acceptance~": len(delta.modified_acceptance),
        "acceptance-": len(delta.removed_acceptance),
        "authority": len(delta.authority_delta),
        "evidence": len(delta.evidence_delta),
    }
    non_zero = [f"{label}={count}" for label, count in counts.items() if count]
    return ", ".join(non_zero) if non_zero else "no structured delta items"


def _load_capsule_path(path: Path) -> MissionCapsule | None:
    try:
        return MissionCapsule.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def _load_goal_verification(workspace: Path, manifest: StructuredRunManifest) -> VerificationResult | None:
    path = _workspace_path(workspace, manifest.verification_result_path)
    if not path.exists():
        return None
    return VerificationResult.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _load_goal_capsule(workspace: Path, manifest: StructuredRunManifest) -> MissionCapsule | None:
    path = _workspace_path(workspace, manifest.mission_capsule_path)
    if not path.exists():
        return None
    return MissionCapsule.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _load_goal_redesign(workspace: Path, manifest: StructuredRunManifest) -> RedesignProposal | None:
    path = _workspace_path(workspace, manifest.redesign_proposal_path)
    if not path.exists():
        return None
    return RedesignProposal.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _goal_verification_is_terminal(verification: VerificationResult) -> bool:
    return verification.status.value in {
        "completed_verified",
        "completed_with_soft_acceptance",
        "completed_with_limitations",
        "completed_pending_human_acceptance",
    }


def _decide_goal_resume(
    workspace: Path,
    manifest: StructuredRunManifest,
    verification: VerificationResult | None,
    capsule: MissionCapsule | None,
    redesign: RedesignProposal | None,
) -> dict:
    execution_report_path = _workspace_path(workspace, manifest.execution_report_path)
    if redesign is not None or (
        capsule is not None and capsule.lifecycle_state.value == "redesign_required"
    ) or (
        verification is not None and "redesign_required" in verification.reason
    ):
        return {
            "action": "redesign_required",
            "reason": redesign.reason if redesign is not None else "redesign_required",
            "message": "redesign_required: review redesign proposal; rerun `metaloop design --resume` or create a revised mission",
        }
    if verification is not None and _goal_verification_is_terminal(verification):
        if capsule is not None and capsule.lifecycle_state.value == "closed":
            return {
                "action": "skip",
                "reason": "capsule closed with terminal successful verification",
                "message": "terminal verification and closed capsule; resume not needed",
            }
        return {
            "action": "skip",
            "reason": "terminal successful verification",
            "message": "terminal verification; resume not needed",
        }
    if capsule is not None and capsule.lifecycle_state.value == "closed" and capsule.closure_outcome is not None:
        if capsule.closure_outcome.value == "failed":
            return {
                "action": "rerun",
                "reason": "failed capsule closure",
                "message": "failed capsule closure; resume will rerun goal runtime using existing MissionSpec and structured state",
            }
    if verification is not None and verification.status.value in {"failed", "blocked"}:
        if execution_report_path.exists():
            return {
                "action": "rerun",
                "reason": f"{verification.status.value} verification",
                "message": f"{verification.status.value} verification with existing execution report; resume will rerun goal runtime using existing MissionSpec and structured state",
            }
        return {
            "action": "rerun",
            "reason": "missing execution report",
            "message": "missing execution report after failed/blocked verification; rerunning goal runtime",
        }
    if not execution_report_path.exists() and manifest.status in {"running", "failed", "blocked"}:
        return {
            "action": "rerun",
            "reason": "missing execution report",
            "message": "missing execution report; rerunning goal runtime",
        }
    if manifest.status in {"running", "failed", "blocked"}:
        return {
            "action": "rerun",
            "reason": f"incomplete run manifest: {manifest.status}",
            "message": f"incomplete run manifest ({manifest.status}); resume will rerun goal runtime using existing MissionSpec and structured state",
        }
    return {
        "action": "rerun",
        "reason": "incomplete structured state",
        "message": "incomplete structured state; resume will rerun goal runtime using existing MissionSpec and structured state",
    }


def _status_next_action(status: dict) -> str:
    mission = status["mission"]
    run = status["run"]
    verification = status["verification"]
    capsule = status["capsule"]
    redesign = status["redesign"]
    if mission["state"] == "missing":
        return "Run `metaloop design`"
    if run["state"] == "missing":
        return "Run `metaloop run`"
    if (
        redesign.get("state") == "ready"
        or capsule.get("lifecycle_state") == "redesign_required"
        or "redesign_required" in str(verification.get("reason") or "")
    ):
        return "Review redesign proposal; rerun `metaloop design --resume` or create a revised mission"
    if verification.get("status") in {
        "completed_verified",
        "completed_with_soft_acceptance",
        "completed_with_limitations",
        "completed_pending_human_acceptance",
    }:
        return "Already complete; run `metaloop verify` for details"
    if verification.get("status") in {"failed", "blocked"}:
        return "Run `metaloop resume`"
    if capsule.get("lifecycle_state") == "closed" and capsule.get("closure_outcome") == "failed":
        return "Inspect failure and rerun after fixing environment"
    if run["state"] in {"running", "failed", "blocked"}:
        return "Run `metaloop resume`"
    if verification["state"] == "missing":
        return "Run `metaloop resume`"
    return "Run `metaloop status` after the next action"


def _last_codex_event_summary(path: Path) -> str:
    if not path.exists():
        return ""
    last_event = None
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    last_event = json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return ""
    if not isinstance(last_event, dict):
        return ""
    return _codex_raw_event_summary(last_event)


def _codex_raw_event_summary(event: dict) -> str:
    mapped = map_codex_event_type(event)
    if mapped == "codex_turn_started":
        return "Codex turn started."
    if mapped == "codex_turn_completed":
        usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
        tokens = int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0)
        return f"Codex turn completed ({tokens} tokens)."
    item = event.get("item") if isinstance(event.get("item"), dict) else {}
    if mapped == "codex_command_started":
        return f"Codex running command: {_shorten_status(item.get('command') or 'command')}"
    if mapped == "codex_command_completed":
        code = item.get("exit_code")
        suffix = f" exit={code}" if code is not None else ""
        return f"Codex command completed{suffix}: {_shorten_status(item.get('command') or 'command')}"
    if mapped == "codex_file_change_completed":
        return "Codex edited files."
    if mapped == "codex_agent_message_completed":
        return f"Codex reported: {_shorten_status(item.get('text') or '')}"
    event_type = event.get("type") or event.get("event_type") or "codex event"
    return str(event_type)


def _activity(ui: MetaLoopUI, enabled: bool, message: str):
    if enabled:
        return ui.activity(message)
    return nullcontext(_SilentActivity())


def _apply_budget_overrides(mission, args: argparse.Namespace) -> None:
    if getattr(args, "max_tokens", None) is not None:
        mission.budget.max_tokens = args.max_tokens
    if getattr(args, "max_usd", None) is not None:
        mission.budget.max_usd = args.max_usd
    if getattr(args, "max_tool_calls", None) is not None:
        mission.budget.max_tool_calls = args.max_tool_calls


def _failed_run_is_resumable(state) -> bool:
    return state.failure_report is not None and state.failure_report.error_type == "budget_exceeded"


class _SilentActivity:
    def update(self, _message: str) -> None:
        return None


class _NotifyingRunStore:
    def __init__(self, store: SQLiteRunStore, on_status) -> None:
        self.store = store
        self.on_status = on_status

    def start_run(self, state):
        return self.store.start_run(state)

    def append_event(self, event, sequence: int) -> None:
        self.on_status(_event_status_message(event))
        self.store.append_event(event, sequence)

    def save_checkpoint(self, state) -> None:
        self.store.save_checkpoint(state)

    def finish_run(self, state) -> None:
        self.on_status(f"MetaLoop finished with status: {state.status.value}")
        self.store.finish_run(state)


def _event_status_message(event) -> str:
    node = event.node or "system"
    if event.event_type == "run_started":
        return "MetaLoop started."
    if event.event_type == "co_design_started":
        return "Gateway is locking and validating the mission."
    if event.event_type == "mission_locked":
        return "Mission locked. Brainstorming execution strategy..."
    if event.event_type == "node_started":
        return f"{node} is working..."
    if event.event_type == "node_completed":
        route = event.payload.get("route") if isinstance(event.payload, dict) else None
        status = event.payload.get("status") if isinstance(event.payload, dict) else None
        suffix = f" route={route}" if route else f" status={status}" if status else ""
        return f"{node} completed{suffix}."
    if event.event_type == "scheduler_routed":
        route = event.payload.get("route") if isinstance(event.payload, dict) else None
        return f"Scheduler routed: {route or 'next action'}."
    if event.event_type == "artifact_validated":
        return "Artifact validator checked acceptance criteria."
    if event.event_type.startswith("codex_"):
        detail = _codex_event_detail(event)
        return f"{node} {detail}" if detail else f"{node} Codex event: {event.event_type}."
    if event.event_type == "run_completed":
        return "Scheduler marked the run completed."
    if event.event_type == "run_failed":
        return "Scheduler marked the run failed."
    if event.event_type == "run_blocked":
        return "Run is blocked and needs intervention."
    if event.event_type == "next_task_proposed":
        return "Scheduler proposed a next task."
    if event.event_type == "run_ended":
        status = event.payload.get("status") if isinstance(event.payload, dict) else None
        return f"Run ended: {status or 'terminal'}."
    return f"{node}: {event.event_type}"


def _codex_event_detail(event) -> str:
    payload = event.payload if isinstance(event.payload, dict) else {}
    raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
    item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
    item_type = item.get("type")
    if event.event_type == "codex_turn_started":
        return "Codex turn started."
    if event.event_type == "codex_turn_completed":
        usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
        tokens = int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0)
        return f"Codex turn completed ({tokens} tokens)."
    if event.event_type == "codex_command_started":
        return f"running: {_shorten_status(item.get('command') or 'command')}"
    if event.event_type == "codex_command_completed":
        status = item.get("status") or "completed"
        code = item.get("exit_code")
        suffix = f" exit={code}" if code is not None else ""
        return f"command {status}{suffix}: {_shorten_status(item.get('command') or 'command')}"
    if event.event_type == "codex_file_change_started":
        return f"editing files: {_file_change_summary(item)}"
    if event.event_type == "codex_file_change_completed":
        return f"edited files: {_file_change_summary(item)}"
    if event.event_type == "codex_agent_message_completed":
        return f"agent responded: {_shorten_status(item.get('text') or '')}"
    if item_type:
        return f"Codex {item_type}: {event.event_type}."
    return ""


def _file_change_summary(item) -> str:
    changes = item.get("changes") if isinstance(item.get("changes"), list) else []
    paths = []
    for change in changes[:3]:
        if isinstance(change, dict) and change.get("path"):
            paths.append(str(change["path"]).rsplit("/", 1)[-1])
    if not paths:
        return "file changes"
    extra = "" if len(changes) <= 3 else f" +{len(changes) - 3}"
    return ", ".join(paths) + extra


def _shorten_status(value: str, limit: int = 96) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
