from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from metaloop_core.durable import DurableStateError, DurableStore


V2_COMMANDS = {"project", "task", "attempt", "evaluate", "recover"}
V2_COMPATIBLE_SURFACES = {"event", "threads"}


def register_v2_parsers(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    project = subparsers.add_parser("project", help="Manage the MetaLoop v2 durable project store.")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    project_init = project_sub.add_parser("init", help="Initialize .metaloop/metaloop.db.")
    project_init.add_argument("--project-id")
    project_sub.add_parser("status", help="Show Project and Task summaries.")
    project_sub.add_parser("export", help="Regenerate inspectable JSON/Markdown projections.")
    project_sub.add_parser("integrity", help="Run SQLite and reference-chain integrity checks.")
    migrate = project_sub.add_parser("migrate-legacy", help="Import current v1 root artifacts into one v2 Task.")
    migrate.add_argument("--title", default="Imported legacy MetaLoop mission")

    task = subparsers.add_parser("task", help="Manage durable v2 Tasks and ContractRevisions.")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_create = task_sub.add_parser("create", help="Create one Task.")
    task_create.add_argument("--title", required=True)
    task_create.add_argument("--parent-task")
    task_create.add_argument("--spawned-by-event")
    task_create.add_argument("--depends-on", action="append", default=[])
    task_create.add_argument("--task-id")
    task_sub.add_parser("list", help="List all Tasks.")
    task_show = task_sub.add_parser("show", help="Show one Task.")
    task_show.add_argument("--task", required=True)
    task_default = task_sub.add_parser("set-default", help="Set the UI/recovery default Task.")
    task_default.add_argument("--task", required=True)
    task_contract = task_sub.add_parser("contract", help="Lock an immutable ContractRevision from JSON.")
    task_contract.add_argument("--task", required=True)
    task_contract.add_argument("--expected-version", required=True, type=int)
    task_contract.add_argument("--file", required=True)
    task_transition = task_sub.add_parser("transition", help="Pause, resume, or cancel a Task.")
    task_transition.add_argument("--task", required=True)
    task_transition.add_argument("--lifecycle", required=True, choices=["open", "paused", "cancelled"])
    task_transition.add_argument("--expected-version", required=True, type=int)
    task_transition.add_argument("--reason", default="")
    task_depend = task_sub.add_parser("depend", help="Add one acyclic dependency edge.")
    task_depend.add_argument("--task", required=True)
    task_depend.add_argument("--on", required=True)
    task_depend.add_argument("--expected-version", required=True, type=int)
    task_undepend = task_sub.add_parser("undepend", help="Remove one dependency edge from an open idle Task.")
    task_undepend.add_argument("--task", required=True)
    task_undepend.add_argument("--on", required=True)
    task_undepend.add_argument("--expected-version", required=True, type=int)
    task_decision = task_sub.add_parser("decision", help="Append a Task or Project DecisionEvent.")
    task_decision.add_argument("--scope", choices=["task", "project"], default="task")
    task_decision.add_argument("--task")
    task_decision.add_argument("--type", required=True)
    task_decision.add_argument("--summary", required=True)
    task_decision.add_argument("--attempt")
    task_decision.add_argument("--evaluation")
    task_decision.add_argument("--diagnosis", default="")
    task_decision.add_argument("--decision", default="")
    task_decision.add_argument("--next-plan", default="")
    task_decision.add_argument("--supersedes")
    task_decision.add_argument("--payload-json", default="{}")
    task_assign = task_sub.add_parser("assign", help="Assign a persistent thread to a Task.")
    task_assign.add_argument("--thread", required=True)
    task_assign.add_argument("--task", required=True)
    task_return = task_sub.add_parser("return", help="Return a thread to its previous focus Task.")
    task_return.add_argument("--thread", required=True)
    task_assignments = task_sub.add_parser("assignments", help="List or show durable thread-to-Task assignments.")
    task_assignments.add_argument("--thread")

    attempt = subparsers.add_parser("attempt", help="Manage recoverable v2 Attempts.")
    attempt_sub = attempt.add_subparsers(dest="attempt_command", required=True)
    attempt_start = attempt_sub.add_parser("start", help="Start one open Attempt.")
    attempt_start.add_argument("--task", required=True)
    attempt_start.add_argument("--expected-version", required=True, type=int)
    attempt_start.add_argument("--plan", required=True)
    attempt_start.add_argument("--input-json", default="{}")
    attempt_start.add_argument("--input-file")
    attempt_start.add_argument("--actor", default="codex")
    attempt_start.add_argument("--retry-of")
    attempt_start.add_argument("--retry-reason", default="")
    attempt_record = attempt_sub.add_parser("record", help="Append an action or checkpoint to an open Attempt.")
    attempt_record.add_argument("--attempt", required=True)
    attempt_record.add_argument("--type", required=True)
    attempt_record.add_argument("--payload-json", default="{}")
    attempt_record.add_argument("--payload-file")
    attempt_evidence = attempt_sub.add_parser("evidence", help="Hash and attach an evidence file.")
    attempt_evidence.add_argument("--attempt", required=True)
    attempt_evidence.add_argument("--path", required=True)
    attempt_evidence.add_argument("--description", default="")
    attempt_evidence.add_argument("--media-type", default="application/octet-stream")
    attempt_seal = attempt_sub.add_parser("seal", help="Seal an Attempt into an immutable execution manifest.")
    attempt_seal.add_argument("--attempt", required=True)
    attempt_seal.add_argument("--expected-version", required=True, type=int)
    attempt_seal.add_argument("--outcome", default="completed")
    attempt_abort = attempt_sub.add_parser("abort", help="Abort an open Attempt.")
    attempt_abort.add_argument("--attempt", required=True)
    attempt_abort.add_argument("--expected-version", required=True, type=int)
    attempt_abort.add_argument("--reason", required=True)
    attempt_show = attempt_sub.add_parser("show", help="Show one Attempt with bounded records and evidence.")
    attempt_show.add_argument("--attempt", required=True)
    attempt_list = attempt_sub.add_parser("list", help="List recent Attempts for a Task.")
    attempt_list.add_argument("--task", required=True)
    attempt_list.add_argument("--limit", type=int, default=20)

    evaluate = subparsers.add_parser("evaluate", help="Verify, review, and accept immutable v2 subjects.")
    evaluate_sub = evaluate.add_subparsers(dest="evaluate_command", required=True)
    evaluate_verify = evaluate_sub.add_parser("verify", help="Run the locked VerificationSpec for a sealed Attempt.")
    evaluate_verify.add_argument("--attempt", required=True)
    evaluate_verify.add_argument("--evaluator", default="metaloop_kernel")
    evaluate_review = evaluate_sub.add_parser("review", help="Review one exact Evaluation hash.")
    evaluate_review.add_argument("--evaluation", required=True)
    evaluate_review.add_argument("--decision", required=True, choices=["approved", "rejected", "needs_changes"])
    evaluate_review.add_argument("--reviewer", required=True)
    evaluate_review.add_argument("--reviewer-role", default="reviewer")
    evaluate_review.add_argument("--authority", choices=["reviewer", "user"], default="reviewer")
    evaluate_review.add_argument("--notes", default="")
    evaluate_accept = evaluate_sub.add_parser("accept", help="Complete a Task through one valid terminal Evaluation chain.")
    evaluate_accept.add_argument("--task", required=True)
    evaluate_accept.add_argument("--evaluation", required=True)
    evaluate_accept.add_argument("--expected-version", required=True, type=int)
    evaluate_show = evaluate_sub.add_parser("show", help="Show one Evaluation.")
    evaluate_show.add_argument("--evaluation", required=True)
    evaluate_list = evaluate_sub.add_parser("list", help="List recent Evaluations for a Task.")
    evaluate_list.add_argument("--task", required=True)
    evaluate_list.add_argument("--limit", type=int, default=30)

    recover = subparsers.add_parser("recover", help="Read or refresh a source-bound RecoveryView.")
    recover_sub = recover.add_subparsers(dest="recover_command", required=True)
    recover_show = recover_sub.add_parser("show", help="Show the bounded recovery bundle and freshness.")
    recover_show.add_argument("--task", required=True)
    recover_write = recover_sub.add_parser("write", help="Refresh Recovery Head and resume projection.")
    recover_write.add_argument("--task", required=True)
    recover_write.add_argument("--content", default="")
    recover_write.add_argument("--from-file")


def dispatch_v2(workspace: Path, args: argparse.Namespace) -> int | None:
    has_v2 = (workspace / ".metaloop" / "metaloop.db").exists()
    if args.command not in V2_COMMANDS and not (has_v2 and args.command in V2_COMPATIBLE_SURFACES):
        return None
    store = DurableStore(workspace)
    try:
        result = _dispatch(store, args)
    except (DurableStateError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(_jsonable(result), indent=2, ensure_ascii=False))
    return 0


def _dispatch(store: DurableStore, args: argparse.Namespace) -> Any:
    if args.command == "project":
        if args.project_command == "init":
            return store.ensure_project(project_id=args.project_id)
        if args.project_command == "status":
            return {"project": store.project(), "tasks": store.list_tasks(), "integrity": store.integrity_check()}
        if args.project_command == "export":
            return {"path": str(store.export_project())}
        if args.project_command == "integrity":
            return store.integrity_check()
        if args.project_command == "migrate-legacy":
            return store.migrate_legacy(title=args.title)

    if args.command == "task":
        if args.task_command == "create":
            return store.create_task(
                title=args.title,
                parent_task_id=args.parent_task,
                spawned_by_event_id=args.spawned_by_event,
                depends_on=args.depends_on,
                task_id=args.task_id,
            )
        if args.task_command == "list":
            return store.list_tasks()
        if args.task_command == "show":
            return store.get_task(args.task)
        if args.task_command == "set-default":
            return store.set_default_task(args.task)
        if args.task_command == "contract":
            return store.lock_contract(args.task, _read_json_object(Path(args.file)), expected_version=args.expected_version)
        if args.task_command == "transition":
            return store.transition_task(args.task, lifecycle=args.lifecycle, expected_version=args.expected_version, reason=args.reason)
        if args.task_command == "depend":
            return store.add_dependency(args.task, args.on, expected_version=args.expected_version)
        if args.task_command == "undepend":
            return store.remove_dependency(args.task, args.on, expected_version=args.expected_version)
        if args.task_command == "decision":
            return store.record_decision(
                scope=args.scope,
                event_type=args.type,
                summary=args.summary,
                task_id=args.task,
                attempt_id=args.attempt,
                evaluation_id=args.evaluation,
                diagnosis=args.diagnosis,
                decision=args.decision,
                next_plan=args.next_plan,
                supersedes_event_id=args.supersedes,
                payload=_parse_json_object(args.payload_json),
            )
        if args.task_command == "assign":
            return store.assign_thread(args.thread, args.task)
        if args.task_command == "return":
            return store.return_thread(args.thread)
        if args.task_command == "assignments":
            return store.get_thread_assignment(args.thread) if args.thread else store.list_thread_assignments()

    if args.command == "attempt":
        if args.attempt_command == "start":
            snapshot = _read_json_object(Path(args.input_file)) if args.input_file else _parse_json_object(args.input_json)
            return store.start_attempt(
                args.task,
                plan=args.plan,
                input_snapshot=snapshot,
                expected_version=args.expected_version,
                actor=args.actor,
                retry_of_attempt_id=args.retry_of,
                retry_reason=args.retry_reason,
            )
        if args.attempt_command == "record":
            payload = _read_json_object(Path(args.payload_file)) if args.payload_file else _parse_json_object(args.payload_json)
            return store.append_attempt_record(args.attempt, record_type=args.type, payload=payload)
        if args.attempt_command == "evidence":
            return store.add_evidence(args.attempt, path=args.path, description=args.description, media_type=args.media_type)
        if args.attempt_command == "seal":
            return store.seal_attempt(args.attempt, expected_task_version=args.expected_version, outcome=args.outcome)
        if args.attempt_command == "abort":
            return store.abort_attempt(args.attempt, expected_task_version=args.expected_version, reason=args.reason)
        if args.attempt_command == "show":
            return store.get_attempt(args.attempt)
        if args.attempt_command == "list":
            return store.list_attempts(args.task, limit=args.limit)

    if args.command == "evaluate":
        if args.evaluate_command == "verify":
            return store.verify_attempt(args.attempt, evaluator=args.evaluator)
        if args.evaluate_command == "review":
            return store.review_evaluation(
                args.evaluation,
                decision=args.decision,
                reviewer=args.reviewer,
                reviewer_role=args.reviewer_role,
                authority=args.authority,
                notes=args.notes,
            )
        if args.evaluate_command == "accept":
            return store.accept_task(args.task, terminal_evaluation_id=args.evaluation, expected_version=args.expected_version)
        if args.evaluate_command == "show":
            return store.get_evaluation(args.evaluation)
        if args.evaluate_command == "list":
            return store.list_evaluations(args.task, limit=args.limit)

    if args.command == "recover":
        if args.recover_command == "show":
            return store.recovery(args.task)
        if args.recover_command == "write":
            content = Path(args.from_file).read_text(encoding="utf-8") if args.from_file else args.content
            return store.write_recovery(args.task, resume_markdown=content)
    if args.command == "event":
        if args.event_command == "append":
            return store.record_decision(
                scope=args.scope,
                event_type=args.type,
                summary=args.summary,
                task_id=args.task,
                attempt_id=args.attempt,
                evaluation_id=args.evaluation,
                diagnosis=args.diagnosis,
                decision=args.decision,
                next_plan=args.next_action,
                supersedes_event_id=args.supersedes,
                payload={"evidence": args.evidence, "agent": args.agent, "thread_role": args.thread_role, "thread_id": args.thread_id},
            )
        if args.event_command == "list":
            return store.list_events(task_id=args.task, scope=args.scope, limit=args.limit)
        if args.event_command == "show":
            return store.get_event(args.event)
    if args.command == "threads":
        if args.threads_command == "status":
            return store.list_thread_assignments()
        raise ValueError("v1 thread registry writes are disabled in a v2 workspace; use task assign/return")
    raise ValueError("unsupported v2 command")


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload


def _parse_json_object(raw: str) -> dict[str, Any]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("JSON value must be an object")
    return payload


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return value
