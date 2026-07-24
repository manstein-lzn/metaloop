#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from metaloop_core.durable import DurableError, DurableStore
from metaloop_core.schemas import ASSURANCE_TIERS, DECISIONS, DECISION_TYPES, PROTOCOL_VERSION, TASK_STATES
from metaloop_core.workspace import GitWorkspaceError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"MetaLoop v{PROTOCOL_VERSION} risk-proportional durable work protocol")
    parser.add_argument("--workspace", default=".", help="Git worktree governed by MetaLoop.")
    commands = parser.add_subparsers(dest="command", required=True)
    _project_parser(commands)
    _task_parser(commands)
    _attempt_parser(commands)
    _evaluation_parser(commands)
    _recovery_parser(commands)
    observe = commands.add_parser("observe", help="Read the current Project and selected Task state.")
    observe.add_argument("--task")
    observe.add_argument("--format", choices=["full", "brief"], default="full")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    try:
        if args.command == "project" and args.project_command == "init":
            store = DurableStore(workspace, initialize=True)
            _print(store.project())
            return 0
        store = DurableStore(workspace)
        result = _dispatch(store, args)
        _print(result)
        return 0
    except (DurableError, GitWorkspaceError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _project_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser("project", help="Initialize and inspect one Git-bound Project.")
    sub = parser.add_subparsers(dest="project_command", required=True)
    sub.add_parser("init", help="Initialize a clean v3 Project in this Git worktree.")
    sub.add_parser("status", help="Show Project and Task status.")
    integrity = sub.add_parser("integrity", help="Check SQLite references and selected workspace alignment.")
    integrity.add_argument("--task")
    export = sub.add_parser("export", help="Regenerate a read-only JSON projection.")
    export.add_argument("--path", default=".metaloop/export.json")


def _task_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser("task", help="Manage durable goals and immutable contracts.")
    sub = parser.add_subparsers(dest="task_command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--title", required=True)
    create.add_argument("--parent-task")
    create.add_argument("--depends-on", action="append", default=[])
    begin = sub.add_parser("begin", help="Create, contract, select, and start one Task.")
    begin.add_argument("--title", required=True)
    begin.add_argument("--contract", help="Explicit Tier 2/3 Contract JSON. Omit for a generated Tier 1 contract.")
    begin.add_argument("--check", action="append", default=[], help="Project-native command for the generated Tier 1 contract.")
    begin.add_argument("--plan", required=True)
    begin.add_argument("--input-json", default="{}")
    begin.add_argument("--input-file")
    begin.add_argument("--actor", default="codex")
    begin.add_argument("--context-id", help="Optional context label for human diagnostics.")
    begin.add_argument("--parent-task")
    begin.add_argument("--depends-on", action="append", default=[])
    begin.add_argument("--change-kind", choices=["repair", "extension", "redesign"])
    begin.add_argument("--stable-input", action="append", default=[], metavar="ROLE=PATH")
    begin.add_argument("--managed-output", action="append", default=[], metavar="ROLE=PATH")
    begin.add_argument("--allowed-path", action="append", default=[])
    begin.add_argument("--migration-plan")
    _assurance_arguments(begin)
    sub.add_parser("list")
    show = sub.add_parser("show")
    show.add_argument("--task", required=True)
    default = sub.add_parser("set-default")
    default.add_argument("--task", required=True)
    contract = sub.add_parser("contract")
    contract.add_argument("--task", required=True)
    contract.add_argument("--expected-version", required=True, type=int)
    contract.add_argument("--file", required=True)
    contract.add_argument("--revision-reason", default="")
    contract.add_argument("--change-kind", choices=["repair", "extension", "redesign"])
    contract.add_argument("--stable-input", action="append", default=[], metavar="ROLE=PATH")
    contract.add_argument("--managed-output", action="append", default=[], metavar="ROLE=PATH")
    contract.add_argument("--allowed-path", action="append", default=[])
    contract.add_argument("--migration-plan")
    _assurance_arguments(contract)
    transition = sub.add_parser("transition")
    transition.add_argument("--task", required=True)
    transition.add_argument("--expected-version", required=True, type=int)
    transition.add_argument("--state", required=True, choices=sorted(TASK_STATES - {"completed"}))
    depend = sub.add_parser("depend")
    depend.add_argument("--task", required=True)
    depend.add_argument("--on", required=True)
    depend.add_argument("--expected-version", required=True, type=int)
    decision = sub.add_parser("decision")
    decision.add_argument("--task")
    decision.add_argument("--scope", choices=["task", "project"], default="task")
    decision.add_argument("--type", required=True, choices=sorted(DECISION_TYPES))
    decision.add_argument("--summary", required=True)
    decision.add_argument("--diagnosis", default="")
    decision.add_argument("--decision", choices=sorted(DECISIONS), default="")
    decision.add_argument("--next-plan", default="")
    decision.add_argument("--payload-json", default="{}")
    assign = sub.add_parser("assign")
    assign.add_argument("--thread", required=True)
    assign.add_argument("--task", required=True)
    assign.add_argument("--role", default="worker")
    returned = sub.add_parser("return")
    returned.add_argument("--thread", required=True)
    sub.add_parser("assignments")


def _attempt_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser("attempt", help="Run one strategy and checkpoint semantic progress.")
    sub = parser.add_subparsers(dest="attempt_command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--task", required=True)
    start.add_argument("--expected-version", required=True, type=int)
    start.add_argument("--plan", required=True)
    start.add_argument("--input-json", default="{}")
    start.add_argument("--input-file")
    start.add_argument("--actor", default="codex")
    start.add_argument("--context-id", help="Optional context label for human diagnostics.")
    start.add_argument("--retry-of")
    start.add_argument("--retry-reason", default="")
    checkpoint = sub.add_parser("record-checkpoint")
    checkpoint.add_argument("--attempt", required=True)
    checkpoint.add_argument("--expected-version", required=True, type=int)
    checkpoint.add_argument("--completed", action="append", default=[])
    checkpoint.add_argument("--observation", action="append", default=[])
    checkpoint.add_argument("--diagnosis", default="")
    checkpoint.add_argument("--decision", choices=sorted(DECISIONS), default="")
    checkpoint.add_argument("--next-plan", default="")
    checkpoint.add_argument("--claimed-path", action="append", default=[])
    checkpoint.add_argument("--deferred-path", action="append", default=[], metavar="PATH=REASON")
    checkpoint.add_argument("--assigned-path", action="append", default=[], metavar="PATH=TASK")
    checkpoint.add_argument("--evidence-ref", action="append", default=[])
    checkpoint.add_argument("--external-ref", help="Optional external run or artifact locator for recovery only.")
    checkpoint.add_argument("--external-checkpoint-identity", help="Optional identity within --external-ref.")
    evidence = sub.add_parser("evidence")
    evidence.add_argument("--attempt", required=True)
    evidence.add_argument("--path", required=True)
    evidence.add_argument("--description", default="")
    finish = sub.add_parser("finish", help="Reconcile, bind managed evidence, seal, verify, and resume safely if repeated.")
    finish.add_argument("--attempt", required=True)
    finish.add_argument("--completed", action="append", default=[])
    finish.add_argument("--observation", action="append", default=[])
    finish.add_argument("--diagnosis", default="")
    finish.add_argument("--decision", choices=sorted(DECISIONS), default="complete")
    finish.add_argument("--next-plan", default="verify and accept the exact Attempt")
    finish.add_argument("--claimed-path", action="append", default=[])
    finish.add_argument("--deferred-path", action="append", default=[], metavar="PATH=REASON")
    finish.add_argument("--assigned-path", action="append", default=[], metavar="PATH=TASK")
    finish.add_argument("--evidence-ref", action="append", default=[])
    finish.add_argument("--evidence-path", action="append", default=[])
    finish.add_argument("--external-ref", help="Optional external run or artifact locator for recovery only.")
    finish.add_argument("--external-checkpoint-identity", help="Optional identity within --external-ref.")
    seal = sub.add_parser("seal")
    seal.add_argument("--attempt", required=True)
    seal.add_argument("--expected-version", required=True, type=int)
    abort = sub.add_parser("abort")
    abort.add_argument("--attempt", required=True)
    abort.add_argument("--reason", required=True)
    show = sub.add_parser("show")
    show.add_argument("--attempt", required=True)


def _evaluation_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser("evaluate", help="Verify, review, and accept immutable subjects.")
    sub = parser.add_subparsers(dest="evaluate_command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--attempt", required=True)
    review = sub.add_parser("review")
    review.add_argument("--evaluation", required=True)
    review.add_argument("--decision", choices=["approved", "rejected", "needs_changes"], required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--authority", choices=["reviewer", "user"], default="reviewer")
    review.add_argument("--context-id", help="Optional reviewer context label for human diagnostics.")
    report = review.add_mutually_exclusive_group()
    report.add_argument("--report-file")
    report.add_argument("--report-json")
    accept = sub.add_parser("accept")
    accept.add_argument("--task", required=True)
    accept.add_argument("--evaluation", required=True)
    accept.add_argument("--expected-version", required=True, type=int)
    show = sub.add_parser("show")
    show.add_argument("--evaluation", required=True)


def _recovery_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser("recover", help="Inspect or refresh a source-bound RecoveryView.")
    sub = parser.add_subparsers(dest="recover_command", required=True)
    show = sub.add_parser("show")
    show.add_argument("--task", required=True)
    write = sub.add_parser("write")
    write.add_argument("--task", required=True)
    write.add_argument("--from-file")
    write.add_argument("--content", default="")


def _dispatch(store: DurableStore, args: argparse.Namespace) -> Any:
    if args.command == "project":
        if args.project_command == "status":
            return _status(store)
        if args.project_command == "integrity":
            return store.integrity(args.task)
        if args.project_command == "export":
            projection = _status(store, full=True)
            path = (store.workspace / args.path).resolve()
            if not path.is_relative_to(store.workspace):
                raise ValueError("export path escapes workspace")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(projection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return {"path": str(path), "projection": projection}
    if args.command == "task":
        if args.task_command == "create":
            return store.create_task(args.title, parent_task_id=args.parent_task, depends_on=args.depends_on)
        if args.task_command == "begin":
            if args.contract and args.check:
                raise ValueError("task begin accepts either --contract or --check, not both")
            if any(not check.strip() for check in args.check):
                raise ValueError("task begin --check must be a non-empty command")
            contract = _read_object(args.contract) if args.contract else _routine_contract(args.title, args.check)
            _apply_scope_arguments(contract, args)
            inputs = _read_object(args.input_file) if args.input_file else json.loads(args.input_json)
            return store.begin_task(
                args.title,
                contract,
                plan=args.plan,
                input_snapshot=inputs,
                actor=args.actor,
                context_id=args.context_id,
                parent_task_id=args.parent_task,
                depends_on=args.depends_on,
            )
        if args.task_command == "list":
            return [_task_summary(store, item["task_id"]) for item in store.tasks()]
        if args.task_command == "show":
            return _task_detail(store, args.task)
        if args.task_command == "set-default":
            return store.set_default(args.task)
        if args.task_command == "contract":
            payload = _read_object(args.file)
            _apply_scope_arguments(payload, args)
            return store.lock_contract(args.task, payload, expected_version=args.expected_version, revision_reason=args.revision_reason)
        if args.task_command == "transition":
            return store.transition(args.task, args.state, expected_version=args.expected_version)
        if args.task_command == "depend":
            return store.depend(args.task, args.on, expected_version=args.expected_version)
        if args.task_command == "decision":
            return store.add_decision(args.task, scope=args.scope, type=args.type, summary=args.summary, diagnosis=args.diagnosis, decision=args.decision, next_plan=args.next_plan, payload=json.loads(args.payload_json))
        if args.task_command == "assign":
            return store.assign_thread(args.thread, args.task, role=args.role)
        if args.task_command == "return":
            return store.return_thread(args.thread)
        if args.task_command == "assignments":
            return store.assignments()
    if args.command == "attempt":
        if args.attempt_command == "start":
            inputs = _read_object(args.input_file) if args.input_file else json.loads(args.input_json)
            return store.start_attempt(args.task, expected_version=args.expected_version, plan=args.plan, input_snapshot=inputs, actor=args.actor, context_id=args.context_id, retry_of=args.retry_of, retry_reason=args.retry_reason)
        if args.attempt_command == "record-checkpoint":
            return store.record_checkpoint(args.attempt, _checkpoint_payload(args), expected_version=args.expected_version)
        if args.attempt_command == "evidence":
            return store.add_evidence(args.attempt, args.path, description=args.description)
        if args.attempt_command == "finish":
            return store.finish_attempt(
                args.attempt,
                checkpoint_payload=_checkpoint_payload(args),
                evidence_paths=args.evidence_path,
            )
        if args.attempt_command == "seal":
            return store.seal_attempt(args.attempt, expected_version=args.expected_version)
        if args.attempt_command == "abort":
            return store.abort_attempt(args.attempt, reason=args.reason)
        if args.attempt_command == "show":
            return store.attempt(args.attempt)
    if args.command == "evaluate":
        if args.evaluate_command == "verify":
            return store.evaluate_verify(args.attempt)
        if args.evaluate_command == "review":
            report = _read_object(args.report_file) if args.report_file else json.loads(args.report_json) if args.report_json else None
            return store.review(args.evaluation, decision=args.decision, reviewer=args.reviewer, authority=args.authority, report=report, context_id=args.context_id)
        if args.evaluate_command == "accept":
            return store.accept(args.task, args.evaluation, expected_version=args.expected_version)
        if args.evaluate_command == "show":
            return store.evaluation(args.evaluation)
    if args.command == "recover":
        if args.recover_command == "show":
            return store.recovery(args.task)
        if args.recover_command == "write":
            markdown = Path(args.from_file).read_text(encoding="utf-8") if args.from_file else args.content
            return store.write_recovery(args.task, markdown)
    if args.command == "observe":
        status = _status(store, full=args.format == "full", selected_task=args.task)
        return status if args.format == "full" else _brief(status)
    raise ValueError("unsupported command")


def _status(store: DurableStore, *, full: bool = False, selected_task: str | None = None) -> dict[str, Any]:
    project = store.project()
    tasks = [_task_summary(store, item["task_id"]) for item in store.tasks()]
    selected = selected_task or project.get("default_task_id")
    result: dict[str, Any] = {"project": project, "tasks": tasks, "integrity": store.integrity(selected_task)}
    if selected:
        result["selected_task"] = _task_detail(store, selected) if full else _task_summary(store, selected)
    return result


def _task_summary(store: DurableStore, task_id: str) -> dict[str, Any]:
    task = store.task(task_id)
    unresolved = [dep for dep in task["depends_on"] if store.task(dep)["lifecycle_status"] != "completed"]
    acceptance = store.acceptance_status(task_id)
    recovery = store.recovery(task_id)
    activity = store.protocol_activity(task_id)
    return {
        **task,
        "active_evaluation_head_id": task.get("acceptance_head_id"),
        "unresolved_dependencies": unresolved,
        "readiness": "completed" if task["lifecycle_status"] == "completed" else "blocked" if unresolved else "ready",
        "control_status": "blocked" if unresolved else acceptance["status"],
        "pending_authorities": acceptance["pending_authorities"],
        "authority_sequence": acceptance["authority_sequence"],
        "next_transition": "none" if unresolved else recovery["next_transition"],
        "next_action": "complete dependencies" if unresolved else recovery["next_action"],
        "blocker": "Task dependencies are incomplete." if unresolved else recovery["blocker"],
        "resolved_trigger_proofs": acceptance["resolved_trigger_proofs"],
        "assurance": acceptance["assurance"],
        "recovery_status": recovery["status"],
        "workspace_alignment": recovery["workspace_alignment"],
        "active_chain": recovery["active_chain"],
        "review_handoff": recovery["review_handoff"],
        "external_ref": recovery["external_ref"],
        "protocol_activity": activity,
        "routing_warning": activity["routing_warning"],
    }


def _task_detail(store: DurableStore, task_id: str) -> dict[str, Any]:
    task = _task_summary(store, task_id)
    task["contract"] = store.contract(task_id) if task.get("contract_head_id") else None
    task["latest_attempt"] = store.latest_attempt(task_id)
    task["recovery"] = store.recovery(task_id)
    task["decisions"] = store.decisions(task_id)
    return task


def _brief(status: dict[str, Any]) -> dict[str, Any]:
    selected = status.get("selected_task") or {}
    recovery = selected.get("recovery") or {}
    return {
        "project_id": status["project"]["project_id"],
        "schema_version": status["project"]["schema_version"],
        "task_count": len(status["tasks"]),
        "selected_task_id": selected.get("task_id"),
        "task_status": selected.get("lifecycle_status"),
        "recovery_status": recovery.get("status") or selected.get("recovery_status"),
        "workspace_alignment": recovery.get("workspace_alignment") or selected.get("workspace_alignment"),
        "integrity": status["integrity"]["passed"],
        "integrity_status": status["integrity"]["status"],
        "control_status": selected.get("control_status"),
        "pending_authorities": selected.get("pending_authorities", []),
        "authority_sequence": selected.get("authority_sequence", []),
        "next_transition": selected.get("next_transition"),
        "next_action": selected.get("next_action"),
        "blocker": selected.get("blocker"),
        "resolved_trigger_proofs": selected.get("resolved_trigger_proofs", {}),
        "assurance": selected.get("assurance"),
        "active_chain": selected.get("active_chain", []),
        "review_handoff": selected.get("review_handoff"),
        "external_ref": selected.get("external_ref"),
        "protocol_activity": selected.get("protocol_activity", {}),
        "routing_warning": selected.get("routing_warning"),
    }


def _apply_scope_arguments(payload: dict[str, Any], args: argparse.Namespace) -> None:
    scope = payload.setdefault("execution_scope", {})
    if args.change_kind:
        scope["change_kind"] = args.change_kind
    scope.setdefault("stable_inputs", [])
    scope.setdefault("managed_outputs", [])
    scope.setdefault("paths", [])
    scope["stable_inputs"].extend(_role_path(item) for item in args.stable_input)
    scope["managed_outputs"].extend(_role_path(item) for item in args.managed_output)
    scope["paths"].extend(args.allowed_path)
    if args.migration_plan:
        scope["migration_plan"] = {"role": "migration_plan", "path": args.migration_plan}
    if args.assurance_tier or args.trigger_id or args.assurance_rationale:
        assurance = payload.setdefault("assurance", {})
        if args.assurance_tier:
            assurance["tier"] = args.assurance_tier
        if args.trigger_id:
            assurance["trigger_ids"] = args.trigger_id
        if args.assurance_rationale:
            assurance["rationale"] = args.assurance_rationale


def _routine_contract(title: str, checks: list[str]) -> dict[str, Any]:
    validators = [
        {"type": "command", "mode": "executable", "severity": "blocking", "command": command.strip()}
        for command in checks
    ]
    return {
        "goal": title.strip(),
        "rationale": ["Durable recovery is needed; technical correctness remains with project-native checks."],
        "constraints": [],
        "non_goals": [],
        "acceptance_criteria": ["Declared project-native checks pass."] if validators else ["The Agent records completion of the durable goal."],
        "verification_spec": {"validators": validators, "resource_gates": []},
        "protocol_shape": "single_node",
        "assurance": {"tier": "durable_routine", "trigger_ids": [], "rationale": []},
        "execution_scope": {
            "paths": [],
            "stable_inputs": [],
            "managed_outputs": [],
        },
    }


def _assurance_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--assurance-tier", choices=sorted(ASSURANCE_TIERS))
    parser.add_argument("--trigger-id", action="append", default=[])
    parser.add_argument("--assurance-rationale", action="append", default=[])


def _role_path(value: str) -> dict[str, str]:
    if "=" not in value:
        raise ValueError("scope reference must use ROLE=PATH")
    role, path = value.split("=", 1)
    return {"role": role, "path": path}


def _pair(value: str, key: str) -> dict[str, str]:
    if "=" not in value:
        raise ValueError(f"value must use PATH={key.upper()}")
    path, detail = value.split("=", 1)
    return {"path": path, key: detail}


def _checkpoint_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "completed": args.completed,
        "observations": args.observation,
        "diagnosis": args.diagnosis,
        "decision": args.decision,
        "next_plan": args.next_plan,
        "claimed_paths": args.claimed_path,
        "deferred_paths": [_pair(item, "reason") for item in args.deferred_path],
        "assigned_paths": [_pair(item, "task_id") for item in args.assigned_path],
        "evidence_refs": args.evidence_ref,
    }
    if args.external_ref is not None or args.external_checkpoint_identity is not None:
        payload["external_ref"] = {
            "locator": args.external_ref,
            "checkpoint_identity": args.external_checkpoint_identity,
        }
    return payload


def _read_object(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON input must be an object")
    return payload


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
