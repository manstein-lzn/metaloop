#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CAPSULE_SCHEMA = "metaloop.lightweight_capsule"
ADAPTIVE_LOOP_SCHEMA = "metaloop.adaptive_goal_loop"
ADAPTIVE_ITERATION_SCHEMA = "metaloop.adaptive_goal_iteration"
EXECUTION_REPORT_SCHEMA = "metaloop.lightweight_execution_report"
EXTENSION_SPEC_SCHEMA = "metaloop.extension_spec"
VERIFICATION_SPEC_SCHEMA = "metaloop.verification_spec"
VERIFICATION_SCHEMA = "metaloop.lightweight_verification_result"
THREAD_REGISTRY_SCHEMA = "metaloop.thread_registry"
EVENT_SCHEMA = "metaloop.event"
JOB_ENVELOPE_SCHEMA = "metaloop.job_envelope"
GLOBAL_BLACKBOARD_SCHEMA = "metaloop.global_blackboard"
TICK_RESULT_SCHEMA = "metaloop.tick_result"
DISPATCH_MAP_SCHEMA = "metaloop.dispatch_map"
RELAY_RESULT_SCHEMA = "metaloop.relay_result"
NODE_SUMMARY_SCHEMA = "metaloop.node_summary"
GLOBAL_SUMMARY_SCHEMA = "metaloop.global_summary"
CONTROL_REQUEST_SCHEMA = "metaloop.control_request"
ACTIVATION_RESULT_SCHEMA = "metaloop.activation_result"
ACTIVATION_LEASE_SCHEMA = "metaloop.activation_lease"

CAPSULE_STATUSES = {"designed", "running", "executed", "repair_required", "redesign_required", "blocked", "completed"}
ADAPTIVE_LOOP_STATUSES = {"active", "completed", "stopped", "blocked"}
ADAPTIVE_DECISIONS = {"complete", "continue", "repair", "redesign", "pivot", "stop", "escalate"}
EVALUATION_STATUSES = {"satisfied", "not_satisfied", "partial", "unknown", "blocked", "invalid_goal"}
THREAD_STATUSES = {"active", "paused", "closed", "handoff_required"}
CANONICAL_THREAD_TYPES = {"interface", "design", "worker", "reviewer", "verifier"}
EVENT_TYPES = {"observation", "decision", "action", "blocker", "handoff", "verification", "repair", "redesign", "note"}
ROUTE_ACTIONS = {"dispatch", "loop_back", "route_to", "escalate", "suspend", "wait", "diagnose", "error"}
ROUTABLE_VERIFICATION_STATUSES = {
    "completed_verified",
    "execution_incomplete",
    "failed",
    "human_acceptance_required",
    "invalid_capsule",
    "missing_execution_report",
    "missing_verification_plan",
    "unsupported_verification_spec",
}
KNOWN_EXECUTABLE_VALIDATORS = {
    "artifact_hash",
    "command",
    "file_contains",
    "file_exists",
    "forbidden_path",
    "json_field_exists",
    "json_metric_gate",
}
KNOWN_MANUAL_VALIDATORS = {"forbidden_claim", "manual_acceptance", "resource_gate"}
KNOWN_VALIDATORS = KNOWN_EXECUTABLE_VALIDATORS | KNOWN_MANUAL_VALIDATORS
MODES = {"executable", "manual", "unsupported"}
SEVERITIES = {"blocking", "advisory"}
CONTROL_TYPES = {"halt", "resource_approval", "inject_fact", "revise_contract_request"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lightweight MetaLoop kernel bundled inside the Codex skill.")
    parser.add_argument("--workspace", default=".", help="Workspace root to govern.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Inspect lightweight MetaLoop state.")
    status_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    observe_parser = subparsers.add_parser("observe", help="Print read-only node or root summaries.")
    observe_parser.add_argument("--scope", choices=["node", "root"], default="node", help="Observe one node or a root containing node workspaces.")
    observe_parser.add_argument("--root", help="Root path for --scope root. Defaults to --workspace.")
    observe_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    control_parser = subparsers.add_parser("control", help="Write or inspect explicit control intent files.")
    control_subparsers = control_parser.add_subparsers(dest="control_command", required=True)

    control_write_parser = control_subparsers.add_parser("write", help="Write one .metaloop/control/*.json request.")
    control_write_parser.add_argument("--type", required=True, choices=sorted(CONTROL_TYPES), help="Control request type.")
    control_write_parser.add_argument("--reason", required=True, help="Why this control is requested.")
    control_write_parser.add_argument("--created-by", default="human", help="Actor writing the request.")
    control_write_parser.add_argument("--payload-json", default="{}", help="Optional JSON object payload.")
    control_write_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    control_list_parser = control_subparsers.add_parser("list", help="List control files for this workspace.")
    control_list_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    activate_parser = subparsers.add_parser("activate", help="Run one bounded activation scan and exit.")
    activate_parser.add_argument("--root", help="Root containing node workspaces. Defaults to --workspace.")
    activate_parser.add_argument("--worker-command", default="", help="Explicit command to run in ready node workspaces.")
    activate_parser.add_argument("--execute", action="store_true", help="Run the worker command. Without this, activation is dry-run.")
    activate_parser.add_argument("--timeout", type=int, default=600, help="Timeout per worker command in seconds.")
    activate_parser.add_argument("--lease-seconds", type=int, default=3600, help="Activation lease duration.")
    activate_parser.add_argument("--max-activations", type=int, default=1, help="Maximum ready nodes to execute in this pass.")
    activate_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    design_parser = subparsers.add_parser("design", help="Write a locked lightweight Mission Capsule.")
    design_parser.add_argument("--intent", required=True, help="Clarified user intent.")
    design_parser.add_argument("--context", action="append", default=[], help="Background/context note. Repeatable.")
    design_parser.add_argument("--rationale", action="append", default=[], help="Design rationale or tradeoff. Repeatable.")
    design_parser.add_argument("--constraint", action="append", default=[], help="Constraint. Repeatable.")
    design_parser.add_argument("--non-goal", action="append", default=[], help="Explicit non-goal. Repeatable.")
    design_parser.add_argument("--acceptance", action="append", default=[], help="Manual/soft acceptance criterion. Repeatable.")
    design_parser.add_argument("--file-exists", action="append", default=[], help="Validator: required file path. Repeatable.")
    design_parser.add_argument("--file-contains", action="append", default=[], help="Validator JSON: path plus contains/not_contains. Repeatable.")
    design_parser.add_argument("--json-field-exists", action="append", default=[], help="Validator JSON: path plus field. Repeatable.")
    design_parser.add_argument("--json-metric-gate", action="append", default=[], help="Validator JSON: path, metric, operator, threshold. Repeatable.")
    design_parser.add_argument("--artifact-hash", action="append", default=[], help="Validator JSON: path plus sha256. Repeatable.")
    design_parser.add_argument("--forbidden-claim", action="append", default=[], help="Manual validator JSON or claim string. Repeatable.")
    design_parser.add_argument("--resource-gate", action="append", default=[], help="Manual validator JSON. Repeatable.")
    design_parser.add_argument("--validator", action="append", default=[], help="Raw validator JSON object. Repeatable.")
    design_parser.add_argument(
        "--command",
        action="append",
        default=[],
        dest="validation_commands",
        help="Validator command. Repeatable.",
    )
    design_parser.add_argument("--forbidden-path", action="append", default=[], help="Path that must not exist/be modified. Repeatable.")
    design_parser.add_argument("--evidence", action="append", default=[], help="Required evidence note. Repeatable.")
    design_parser.add_argument("--extension-spec", help="Path to a JSON ExtensionSpec to lock into the Mission Capsule.")
    design_parser.add_argument("--verification-spec", help="Path to a JSON VerificationSpec to lock into the Mission Capsule.")
    design_parser.add_argument("--risk-check", action="append", default=[], help="Review risk check. Repeatable.")
    design_parser.add_argument("--review-question", action="append", default=[], help="Review question before lock. Repeatable.")
    design_parser.add_argument("--known-gap", action="append", default=[], help="Known verification gap. Repeatable.")
    design_parser.add_argument("--allow-lightweight-extension", action="store_true", help="Allow non-generic extension without risk checks.")
    design_parser.add_argument(
        "--allow-manual-only",
        action="store_true",
        help="Allow a capsule whose acceptance requires human review and has no executable validators.",
    )
    design_parser.add_argument("--revision-reason", help="Reason for replacing an existing locked capsule.")
    design_parser.add_argument("--force", action="store_true", help="Create a new revision when a capsule exists.")

    run_parser = subparsers.add_parser("run", help="Run command(s) around the locked Mission Capsule and write an ExecutionReport.")
    run_parser.add_argument("--command", action="append", required=True, dest="run_commands", help="Command to run from the workspace. Repeatable.")
    run_parser.add_argument("--evidence", action="append", default=[], help="Evidence note produced during execution. Repeatable.")
    run_parser.add_argument("--timeout", type=int, default=600, help="Timeout per command in seconds.")
    run_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    verify_parser = subparsers.add_parser("verify", help="Verify the current lightweight Mission Capsule.")
    verify_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    mark_parser = subparsers.add_parser("mark", help="Mark capsule status without mutating locked contract fields.")
    mark_parser.add_argument("--status", required=True, choices=sorted(CAPSULE_STATUSES))
    mark_parser.add_argument("--reason", default="", help="Reason for status transition.")

    adaptive_parser = subparsers.add_parser("adaptive", help="Inspect or update the generic Adaptive Goal Loop state.")
    adaptive_subparsers = adaptive_parser.add_subparsers(dest="adaptive_command", required=True)

    adaptive_status_parser = adaptive_subparsers.add_parser("status", help="Inspect .metaloop/adaptive_loop.json.")
    adaptive_status_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    adaptive_init_parser = adaptive_subparsers.add_parser("init", help="Create or replace the Adaptive Goal Loop state.")
    adaptive_init_parser.add_argument("--goal", required=True, help="Stable target for the goal-seeking loop.")
    adaptive_init_parser.add_argument("--current-plan", required=True, help="Current plan before the next attempt.")
    adaptive_init_parser.add_argument("--constraint", action="append", default=[], help="Constraint. Repeatable.")
    adaptive_init_parser.add_argument("--success-criterion", action="append", default=[], help="Success criterion. Repeatable.")
    adaptive_init_parser.add_argument("--known-fact", action="append", default=[], help="Known fact. Repeatable.")
    adaptive_init_parser.add_argument("--open-question", action="append", default=[], help="Open question. Repeatable.")
    adaptive_init_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    adaptive_record_parser = adaptive_subparsers.add_parser("record", help="Append one observe/evaluate/diagnose/decide iteration.")
    adaptive_record_parser.add_argument("--plan", required=True, help="Plan that was attempted.")
    adaptive_record_parser.add_argument("--rationale", default="", help="Why this attempt was worth running.")
    adaptive_record_parser.add_argument("--observation", required=True, help="Observed result from this attempt.")
    adaptive_record_parser.add_argument("--evaluation-status", required=True, choices=sorted(EVALUATION_STATUSES), help="Evaluation against locked criteria.")
    adaptive_record_parser.add_argument("--diagnosis", required=True, help="Why the result did or did not satisfy the goal.")
    adaptive_record_parser.add_argument("--decision", choices=sorted(ADAPTIVE_DECISIONS), help="Override automatic next decision.")
    adaptive_record_parser.add_argument("--next-plan", required=True, help="Next plan grounded in this attempt's evidence.")
    adaptive_record_parser.add_argument("--evidence", action="append", default=[], help="Evidence path, metric, or observation. Repeatable.")
    adaptive_record_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    threads_parser = subparsers.add_parser("threads", help="Inspect or update the persistent agent thread registry.")
    threads_subparsers = threads_parser.add_subparsers(dest="threads_command", required=True)

    threads_status_parser = threads_subparsers.add_parser("status", help="Inspect registered MetaLoop agent threads.")
    threads_status_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    register_parser = threads_subparsers.add_parser("register", help="Register or replace one long-running agent thread.")
    register_parser.add_argument("--role", required=True, help="Workspace-local role id, e.g. interface, design, worker-main, reviewer.")
    register_parser.add_argument("--thread-id", required=True, help="Persistent Codex thread id for this role.")
    register_parser.add_argument("--role-type", default="worker", help="Canonical role type: interface/design/worker/reviewer/verifier or custom slug.")
    register_parser.add_argument("--agent-name", default="", help="Human-readable agent label.")
    register_parser.add_argument("--responsibility", action="append", default=[], help="Responsibility boundary. Repeatable.")
    register_parser.add_argument("--context-policy", default="persistent_thread_plus_metaloop_artifacts", help="How this agent should preserve context.")
    register_parser.add_argument("--note", action="append", default=[], help="Audit note. Repeatable.")
    register_parser.add_argument("--status", default="active", choices=sorted(THREAD_STATUSES), help="Initial thread status.")

    update_thread_parser = threads_subparsers.add_parser("update", help="Update one registered agent thread without changing its role contract.")
    update_thread_parser.add_argument("--role", required=True, help="Workspace-local role id to update.")
    update_thread_parser.add_argument("--thread-id", help="New persistent thread id, if the agent was intentionally reset.")
    update_thread_parser.add_argument("--status", choices=sorted(THREAD_STATUSES), help="New thread status.")
    update_thread_parser.add_argument("--note", action="append", default=[], help="Audit note. Repeatable.")

    event_parser = subparsers.add_parser("event", help="Append or inspect lightweight long-task events.")
    event_subparsers = event_parser.add_subparsers(dest="event_command", required=True)

    append_event_parser = event_subparsers.add_parser("append", help="Append a structured event to .metaloop/event_log.jsonl.")
    append_event_parser.add_argument("--type", required=True, choices=sorted(EVENT_TYPES), help="Event type.")
    append_event_parser.add_argument("--agent", default="", help="Agent role or thread role that produced the event.")
    append_event_parser.add_argument("--summary", required=True, help="Concise event summary.")
    append_event_parser.add_argument("--evidence", action="append", default=[], help="Evidence path, command, or observation. Repeatable.")
    append_event_parser.add_argument("--decision", default="", help="Decision made by this event, when applicable.")
    append_event_parser.add_argument("--next-action", default="", help="Suggested next action, when applicable.")
    append_event_parser.add_argument("--thread-role", default="", help="Thread registry role associated with this event.")
    append_event_parser.add_argument("--thread-id", default="", help="Persistent thread id associated with this event.")
    append_event_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    list_event_parser = event_subparsers.add_parser("list", help="List recent events from .metaloop/event_log.jsonl.")
    list_event_parser.add_argument("--limit", type=int, default=10, help="Number of recent events to show.")
    list_event_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    tick_parser = subparsers.add_parser("tick", help="Apply one local routable-work-unit effect step and exit.")
    tick_parser.add_argument("--envelope", default="job_envelope.json", help="Path to job_envelope.json, relative to workspace by default.")
    tick_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    relay_parser = subparsers.add_parser("relay", help="Deliver local outbox records using a static dispatch map and exit.")
    relay_parser.add_argument("--dispatch-map", required=True, help="Path to dispatch_map.json, relative to workspace by default.")
    relay_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    args = parser.parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    if args.command == "status":
        return _status(workspace, as_json=args.json)
    if args.command == "observe":
        return _observe(workspace, args)
    if args.command == "control":
        return _control(workspace, args)
    if args.command == "activate":
        return _activate(workspace, args)
    if args.command == "design":
        return _design(workspace, args)
    if args.command == "run":
        return _run(workspace, args)
    if args.command == "verify":
        return _verify(workspace, as_json=args.json)
    if args.command == "mark":
        return _mark(workspace, args.status, args.reason)
    if args.command == "adaptive":
        return _adaptive(workspace, args)
    if args.command == "threads":
        return _threads(workspace, args)
    if args.command == "event":
        return _event(workspace, args)
    if args.command == "tick":
        return _tick(workspace, args)
    if args.command == "relay":
        return _relay(workspace, args)
    return 2


def _status(workspace: Path, *, as_json: bool) -> int:
    status = _read_status(workspace)
    if as_json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return 0
    print(f"workspace: {workspace}")
    print(f"capsule: {status['capsule']['state']} path={status['capsule'].get('path') or '-'}")
    print(f"current_status: {status['capsule'].get('current_status') or '-'}")
    print(f"execution: {status['execution']['state']} status={status['execution'].get('status') or '-'}")
    print(f"verification: {status['verification']['state']} status={status['verification'].get('status') or '-'}")
    print(f"adaptive_loop: {status['adaptive_loop']['state']} status={status['adaptive_loop'].get('status') or '-'}")
    print(f"threads: {status['threads']['state']} count={status['threads'].get('count', 0)}")
    print(f"events: {status['events']['state']} count={status['events'].get('count', 0)}")
    print(f"next_action: {status['next_action']}")
    return 0


def _observe(workspace: Path, args: argparse.Namespace) -> int:
    if args.scope == "root":
        root = Path(args.root).expanduser().resolve() if args.root else workspace
        payload = _observe_root(root)
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0
        print(f"root: {payload['root']}")
        print(f"nodes: {payload['node_count']}")
        print(f"outbox: {payload['outbox_count']} inbox: {payload['inbox_count']}")
        for node in payload["nodes"]:
            waiting = f" waiting_on={node.get('waiting_on')}" if node.get("waiting_on") else ""
            print(f"- {node.get('node_id')}: status={node.get('status')}{waiting} workspace={node.get('workspace')}")
        return 0
    payload = _observe_node(workspace)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(f"node: {payload['node_id']}")
    print(f"workspace: {payload['workspace']}")
    print(f"status: {payload['status']}")
    print(f"goal: {payload.get('goal') or '-'}")
    print(f"current_plan: {payload.get('current_plan') or '-'}")
    print(f"waiting_on: {payload.get('waiting_on') or '-'}")
    print(f"outbox: {payload['outbox_count']} inbox: {payload['inbox_count']}")
    return 0


def _control(workspace: Path, args: argparse.Namespace) -> int:
    if args.control_command == "write":
        return _control_write(workspace, args)
    if args.control_command == "list":
        return _control_list(workspace, as_json=args.json)
    return 2


def _control_write(workspace: Path, args: argparse.Namespace) -> int:
    reason = args.reason.strip()
    if not reason:
        print("control_invalid: --reason must be non-empty", file=sys.stderr)
        return 1
    payload = _parse_control_payload(args.payload_json)
    if not isinstance(payload, dict):
        print("control_invalid: --payload-json must be a JSON object", file=sys.stderr)
        return 1
    request = {
        "schema": CONTROL_REQUEST_SCHEMA,
        "version": "1.0",
        "control_id": _new_id("control"),
        "created_at": _now(),
        "created_by": args.created_by.strip() or "human",
        "type": args.type,
        "reason": reason,
        "payload": payload,
        "status": "pending",
    }
    path = _control_request_path(workspace, args.type)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
    _append_event(
        workspace,
        {
            "schema": EVENT_SCHEMA,
            "version": "1.0",
            "event_id": _new_id("event"),
            "created_at": _now(),
            "workspace": str(workspace),
            "capsule_id": _current_capsule_id(workspace),
            "type": "decision",
            "agent": request["created_by"],
            "thread_role": "",
            "thread_id": "",
            "summary": f"Control request {args.type}: {reason}",
            "evidence": [str(path)],
            "decision": args.type,
            "next_action": "worker_or_activator_must_process_control_at_safe_point",
        },
    )
    if args.json:
        print(json.dumps(request, indent=2, ensure_ascii=False))
    else:
        print(f"control: {args.type}")
        print(f"status: pending")
        print(f"path: {path}")
    return 0


def _control_list(workspace: Path, *, as_json: bool) -> int:
    requests = _load_control_requests(workspace)
    payload = {"state": "ready", "path": str(_control_dir(workspace)), "requests": requests}
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(f"controls: {len(requests)} path={_control_dir(workspace)}")
    for request in requests:
        print(f"- {request.get('type')}: status={request.get('status')} reason={request.get('reason')}")
    return 0


def _activate(workspace: Path, args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve() if args.root else workspace
    result = _activate_once(
        root,
        worker_command=args.worker_command.strip(),
        dry_run=not args.execute,
        timeout=args.timeout,
        lease_seconds=args.lease_seconds,
        max_activations=args.max_activations,
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        mode = "execute" if args.execute else "dry-run"
        print(f"activate: {mode}")
        print(f"root: {result['root']}")
        print(f"counts: {result['counts']}")
        print(f"result: {_activation_result_path(root)}")
    return 0 if not result["counts"].get("failed") else 1


def _adaptive(workspace: Path, args: argparse.Namespace) -> int:
    if args.adaptive_command == "status":
        return _adaptive_status(workspace, as_json=args.json)
    if args.adaptive_command == "init":
        return _adaptive_init(workspace, args)
    if args.adaptive_command == "record":
        return _adaptive_record(workspace, args)
    return 2


def _adaptive_status(workspace: Path, *, as_json: bool) -> int:
    state = _load_adaptive_loop(workspace)
    errors = _validate_adaptive_loop(state)
    if errors:
        if as_json:
            print(json.dumps({"state": "invalid", "errors": errors}, indent=2, ensure_ascii=False))
        else:
            print("adaptive_loop: invalid")
            for error in errors:
                print(f"- {error}")
        return 1
    if state is None:
        payload = {"state": "missing", "path": str(_adaptive_loop_path(workspace))}
        if as_json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("adaptive_loop: missing")
            print(f"path: {_adaptive_loop_path(workspace)}")
        return 0
    if as_json:
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return 0
    print("adaptive_loop: ready")
    print(f"path: {_adaptive_loop_path(workspace)}")
    print(f"status: {state.get('status')}")
    print(f"goal: {state.get('goal')}")
    print(f"current_plan: {state.get('current_plan')}")
    print(f"iterations: {len(state.get('iterations', []))}")
    return 0


def _adaptive_init(workspace: Path, args: argparse.Namespace) -> int:
    errors = []
    if not args.goal.strip():
        errors.append("--goal must be non-empty")
    if not args.current_plan.strip():
        errors.append("--current-plan must be non-empty")
    if errors:
        print("adaptive_init_invalid:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    now = _now()
    state = {
        "schema": ADAPTIVE_LOOP_SCHEMA,
        "version": "1.0",
        "loop_id": _new_id("loop"),
        "created_at": now,
        "updated_at": now,
        "goal": args.goal.strip(),
        "status": "active",
        "current_plan": args.current_plan.strip(),
        "constraints": _clean_strings(args.constraint),
        "success_criteria": _clean_strings(args.success_criterion),
        "known_facts": _clean_strings(args.known_fact),
        "open_questions": _clean_strings(args.open_question),
        "iterations": [],
    }
    errors = _validate_adaptive_loop(state)
    if errors:
        print("adaptive_init_invalid:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    _write_adaptive_loop(workspace, state)
    if args.json:
        print(json.dumps(state, indent=2, ensure_ascii=False))
    else:
        print("adaptive_loop: initialized")
        print(f"status: {state['status']}")
        print(f"path: {_adaptive_loop_path(workspace)}")
    return 0


def _adaptive_record(workspace: Path, args: argparse.Namespace) -> int:
    state = _load_adaptive_loop(workspace)
    errors = _validate_adaptive_loop(state)
    if state is None or errors:
        print("No valid adaptive loop found. Run adaptive init first.", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    decision = args.decision or _decide_next(args.evaluation_status, diagnosis=args.diagnosis, next_plan=args.next_plan)
    iteration = {
        "schema": ADAPTIVE_ITERATION_SCHEMA,
        "version": "1.0",
        "iteration_id": _new_id("iteration"),
        "created_at": _now(),
        "goal": state["goal"],
        "plan": args.plan.strip(),
        "rationale": args.rationale.strip(),
        "observation": args.observation.strip(),
        "evaluation_status": args.evaluation_status,
        "diagnosis": args.diagnosis.strip(),
        "decision": decision,
        "next_plan": args.next_plan.strip(),
        "evidence": _clean_strings(args.evidence),
    }
    errors = _validate_adaptive_iteration(iteration)
    if errors:
        print("adaptive_record_invalid:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    state["iterations"].append(iteration)
    state["updated_at"] = _now()
    state["current_plan"] = iteration["next_plan"]
    state["status"] = _adaptive_status_after_decision(decision)
    _write_adaptive_loop(workspace, state)
    if args.json:
        print(json.dumps(state, indent=2, ensure_ascii=False))
    else:
        print("adaptive_loop: recorded")
        print(f"decision: {decision}")
        print(f"status: {state['status']}")
        print(f"iterations: {len(state['iterations'])}")
    return 0


def _threads(workspace: Path, args: argparse.Namespace) -> int:
    if args.threads_command == "status":
        return _threads_status(workspace, as_json=args.json)
    if args.threads_command == "register":
        return _threads_register(workspace, args)
    if args.threads_command == "update":
        return _threads_update(workspace, args)
    return 2


def _threads_status(workspace: Path, *, as_json: bool) -> int:
    registry = _load_thread_registry(workspace)
    errors = _validate_thread_registry(registry)
    if errors:
        if as_json:
            print(json.dumps({"state": "invalid", "errors": errors}, indent=2, ensure_ascii=False))
        else:
            print("threads: invalid")
            for error in errors:
                print(f"- {error}")
        return 1
    if registry is None:
        payload = {"state": "missing", "path": str(_thread_registry_path(workspace)), "agents": {}}
        if as_json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("threads: missing")
            print(f"path: {_thread_registry_path(workspace)}")
        return 0
    if as_json:
        print(json.dumps(registry, indent=2, ensure_ascii=False))
        return 0
    agents = registry.get("agents", {})
    print("threads: ready")
    print(f"path: {_thread_registry_path(workspace)}")
    print(f"count: {len(agents)}")
    for role, agent in sorted(agents.items()):
        thread_id = str(agent.get("thread_id") or "")
        print(
            f"- {role}: type={agent.get('role_type') or '-'} "
            f"status={agent.get('status') or '-'} thread={_short_thread_id(thread_id)}"
        )
    return 0


def _threads_register(workspace: Path, args: argparse.Namespace) -> int:
    registry = _ensure_thread_registry(workspace)
    errors = _validate_thread_role_input(args.role, args.role_type, args.thread_id)
    if errors:
        print("thread_register_invalid:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    role = args.role.strip()
    agents = registry.setdefault("agents", {})
    previous = agents.get(role)
    now = _now()
    responsibilities = list(args.responsibility) or _default_responsibilities(args.role_type, role)
    history = list(previous.get("history", [])) if isinstance(previous, dict) else []
    history.append(
        {
            "event": "registered" if previous is None else "replaced",
            "thread_id": args.thread_id,
            "status": args.status,
            "notes": list(args.note),
            "at": now,
        }
    )
    agents[role] = {
        "role": role,
        "role_type": args.role_type.strip(),
        "thread_id": args.thread_id.strip(),
        "agent_name": args.agent_name.strip(),
        "responsibilities": responsibilities,
        "context_policy": args.context_policy.strip(),
        "status": args.status,
        "current_capsule_id": _current_capsule_id(workspace),
        "last_handoff_artifact": ".metaloop/mission_capsule.json" if _load_capsule(workspace) else "",
        "notes": list(args.note),
        "created_at": previous.get("created_at", now) if isinstance(previous, dict) else now,
        "updated_at": now,
        "history": history,
    }
    _write_thread_registry(workspace, registry)
    print(f"thread: {role}")
    print(f"status: {args.status}")
    print(f"registry: {_thread_registry_path(workspace)}")
    return 0


def _threads_update(workspace: Path, args: argparse.Namespace) -> int:
    registry = _load_thread_registry(workspace)
    errors = _validate_thread_registry(registry)
    if registry is None or errors:
        print("No valid thread registry found.", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    role = args.role.strip()
    agents = registry.setdefault("agents", {})
    agent = agents.get(role)
    if not isinstance(agent, dict):
        print(f"thread_not_found: {role}", file=sys.stderr)
        return 1
    if args.thread_id is not None and not args.thread_id.strip():
        print("thread_id must be non-empty when provided", file=sys.stderr)
        return 1
    if args.thread_id:
        agent["thread_id"] = args.thread_id.strip()
    if args.status:
        agent["status"] = args.status
    if args.note:
        agent.setdefault("notes", []).extend(args.note)
    agent["current_capsule_id"] = _current_capsule_id(workspace)
    if _load_capsule(workspace):
        agent["last_handoff_artifact"] = ".metaloop/mission_capsule.json"
    agent["updated_at"] = _now()
    agent.setdefault("history", []).append(
        {
            "event": "updated",
            "thread_id": agent.get("thread_id", ""),
            "status": agent.get("status", ""),
            "notes": list(args.note),
            "at": agent["updated_at"],
        }
    )
    _write_thread_registry(workspace, registry)
    print(f"thread: {role}")
    print(f"status: {agent.get('status')}")
    print(f"registry: {_thread_registry_path(workspace)}")
    return 0


def _event(workspace: Path, args: argparse.Namespace) -> int:
    if args.event_command == "append":
        return _event_append(workspace, args)
    if args.event_command == "list":
        return _event_list(workspace, limit=args.limit, as_json=args.json)
    return 2


def _event_append(workspace: Path, args: argparse.Namespace) -> int:
    summary = args.summary.strip()
    if not summary:
        print("event_invalid: --summary must be non-empty", file=sys.stderr)
        return 1
    event = {
        "schema": EVENT_SCHEMA,
        "version": "1.0",
        "event_id": _new_id("event"),
        "created_at": _now(),
        "workspace": str(workspace),
        "capsule_id": _current_capsule_id(workspace),
        "type": args.type,
        "agent": args.agent.strip(),
        "thread_role": args.thread_role.strip(),
        "thread_id": args.thread_id.strip() or _thread_id_for_role(workspace, args.thread_role.strip() or args.agent.strip()),
        "summary": summary,
        "evidence": list(args.evidence),
        "decision": args.decision.strip(),
        "next_action": args.next_action.strip(),
    }
    errors = _validate_event(event)
    if errors:
        print("event_invalid:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    _append_event(workspace, event)
    if args.json:
        print(json.dumps(event, indent=2, ensure_ascii=False))
    else:
        print(f"event: {event['event_id']}")
        print(f"type: {event['type']}")
        print(f"summary: {event['summary']}")
        print(f"log: {_event_log_path(workspace)}")
    return 0


def _event_list(workspace: Path, *, limit: int, as_json: bool) -> int:
    events, errors = _read_events(workspace)
    if errors:
        if as_json:
            print(json.dumps({"state": "invalid", "errors": errors}, indent=2, ensure_ascii=False))
        else:
            print("events: invalid")
            for error in errors:
                print(f"- {error}")
        return 1
    if limit < 1:
        limit = 1
    recent = events[-limit:]
    if as_json:
        print(json.dumps({"state": "ready", "path": str(_event_log_path(workspace)), "events": recent}, indent=2, ensure_ascii=False))
        return 0
    print(f"events: ready count={len(events)} path={_event_log_path(workspace)}")
    for event in recent:
        agent = event.get("agent") or event.get("thread_role") or "-"
        print(f"- {event.get('created_at')} {event.get('type')} agent={agent}: {event.get('summary')}")
    return 0


def _tick(workspace: Path, args: argparse.Namespace) -> int:
    envelope_path = _resolve_workspace_path(workspace, args.envelope)
    envelope = _read_json(envelope_path)
    route = _route_workspace(workspace, envelope_path)
    effects = _apply_tick_effects(workspace, envelope if isinstance(envelope, dict) else {}, route)
    result = {
        "schema": TICK_RESULT_SCHEMA,
        "version": "1.0",
        "created_at": _now(),
        "workspace": str(workspace),
        "envelope_path": str(envelope_path),
        "route": route,
        "effects": effects,
    }
    _metaloop_dir(workspace).mkdir(parents=True, exist_ok=True)
    (_metaloop_dir(workspace) / "tick_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    _append_tick_event(workspace, route, effects)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"tick: {route.get('action')}")
        print(f"reason: {route.get('reason') or '-'}")
        print(f"result: {_metaloop_dir(workspace) / 'tick_result.json'}")
    return 0 if route.get("action") not in {"error"} else 1


def _relay(workspace: Path, args: argparse.Namespace) -> int:
    dispatch_map_path = _resolve_workspace_path(workspace, args.dispatch_map)
    dispatch_map = _read_json(dispatch_map_path)
    errors = _validate_dispatch_map(dispatch_map)
    outbox_items = _load_outbox_items(workspace)
    result = {
        "schema": RELAY_RESULT_SCHEMA,
        "version": "1.0",
        "created_at": _now(),
        "workspace": str(workspace),
        "dispatch_map_path": str(dispatch_map_path),
        "dispatch_map_errors": errors,
        "counts": {"scanned": len(outbox_items), "delivered": 0, "failed": 0, "needs_design": 0, "skipped": 0},
        "deliveries": [],
    }
    if errors:
        result["status"] = "invalid_dispatch_map"
    else:
        routes = dispatch_map.get("routes", []) if isinstance(dispatch_map, dict) else []
        for item in outbox_items:
            delivery = _relay_item(workspace, dispatch_map_path.parent, item, routes)
            result["deliveries"].append(delivery)
            status = delivery.get("status")
            if status in result["counts"]:
                result["counts"][status] += 1
        result["status"] = _relay_status(result["counts"])
    _metaloop_dir(workspace).mkdir(parents=True, exist_ok=True)
    (_metaloop_dir(workspace) / "relay_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"relay: {result['status']}")
        print(f"delivered: {result['counts']['delivered']}")
        print(f"needs_design: {result['counts']['needs_design']}")
        print(f"failed: {result['counts']['failed']}")
        print(f"result: {_metaloop_dir(workspace) / 'relay_result.json'}")
    return 0 if result["status"] in {"completed", "idle"} else 1


def _design(workspace: Path, args: argparse.Namespace) -> int:
    root = _metaloop_dir(workspace)
    capsule_path = root / "mission_capsule.json"
    previous_capsule = _load_capsule(workspace)
    if capsule_path.exists() and not args.force:
        print(f"capsule_exists: {capsule_path}", file=sys.stderr)
        print("Use --force with --revision-reason to create a new revision.", file=sys.stderr)
        return 1
    if capsule_path.exists() and args.force and not args.revision_reason:
        print("revision_reason_required: use --revision-reason when replacing a locked capsule.", file=sys.stderr)
        return 1

    extension_spec, extension_errors = _build_extension_spec(args)
    verification_spec, spec_errors = _build_verification_spec(args, extension_spec)
    review = _build_verification_review(args, extension_spec)
    errors = [
        *extension_errors,
        *spec_errors,
        *_validate_design_input(args, extension_spec, verification_spec, review),
    ]
    if errors:
        print("design_invalid:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    root.mkdir(parents=True, exist_ok=True)
    if previous_capsule is not None:
        _archive_capsule(workspace, previous_capsule)
    capsule = _build_capsule(workspace, args, extension_spec, verification_spec, review, previous_capsule)
    capsule_path.write_text(json.dumps(capsule, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"capsule: {capsule_path}")
    print("status: designed")
    print(f"revision: {capsule['revision']}")
    return 0


def _run(workspace: Path, args: argparse.Namespace) -> int:
    capsule, errors = _load_valid_capsule(workspace)
    if capsule is None:
        print("No valid Mission Capsule found.", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if capsule.get("current_status") == "redesign_required":
        print("Mission Capsule requires redesign before execution.", file=sys.stderr)
        return 1

    _update_capsule_status(workspace, "running", "Executing through lightweight skill kernel.")
    command_results = []
    for command in args.run_commands:
        command_results.append(_run_command(workspace, command, timeout=args.timeout))
        if not command_results[-1]["passed"]:
            break

    completed = all(result["passed"] for result in command_results)
    report = {
        "schema": EXECUTION_REPORT_SCHEMA,
        "version": "1.0",
        "created_at": _now(),
        "workspace": str(workspace),
        "capsule_id": capsule["capsule_id"],
        "capsule_revision": capsule["revision"],
        "status": "completed" if completed else "failed",
        "commands": command_results,
        "evidence": args.evidence,
    }
    _metaloop_dir(workspace).mkdir(parents=True, exist_ok=True)
    (_metaloop_dir(workspace) / "execution_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _update_capsule_status(workspace, "executed" if completed else "blocked", "ExecutionReport written by lightweight skill kernel.")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"execution: {report['status']}")
        print(f"report: {_metaloop_dir(workspace) / 'execution_report.json'}")
    return 0 if completed else 1


def _verify(workspace: Path, *, as_json: bool) -> int:
    capsule, errors = _load_valid_capsule(workspace)
    if capsule is None:
        result = _verification_result("invalid_capsule", "No valid Mission Capsule found.", [], [], errors=errors)
        return _print_verification(result, as_json=as_json, exit_code=1)

    execution_report, execution_errors = _load_valid_execution_report(workspace, capsule)
    if execution_report is None:
        result = _verification_result(
            "missing_execution_report",
            "No valid ExecutionReport found; run through the lightweight kernel before verification.",
            [],
            [],
            errors=execution_errors,
            capsule=capsule,
        )
        _write_verification_result(workspace, result)
        return _print_verification(result, as_json=as_json, exit_code=1)
    if execution_report.get("status") != "completed":
        result = _verification_result("execution_incomplete", "ExecutionReport is not completed.", [], [], errors=execution_errors, capsule=capsule)
        _write_verification_result(workspace, result)
        return _print_verification(result, as_json=as_json, exit_code=1)

    hard_results, forbidden_results, manual_results, unsupported_results, warnings = _run_verification_spec(workspace, capsule["verification_spec"])
    all_executable_results = [*hard_results, *forbidden_results]
    blocking_failures = [result for result in all_executable_results if result.get("severity") == "blocking" and not result.get("passed")]
    blocking_manual = [result for result in manual_results if result.get("severity") == "blocking"]
    blocking_unsupported = [result for result in unsupported_results if result.get("severity") == "blocking"]
    review = capsule.get("verification_review", {})
    if review.get("known_gaps"):
        warnings.extend({"type": "known_gap", "message": item} for item in review["known_gaps"])

    if blocking_failures:
        status = "failed"
        reason = "One or more executable blocking validators failed."
    elif blocking_unsupported:
        status = "unsupported_verification_spec"
        reason = "One or more blocking validators require unsupported verification."
    elif blocking_manual:
        status = "human_acceptance_required"
        reason = "One or more blocking validators require human review."
    elif not all_executable_results:
        status = "missing_verification_plan"
        reason = "No executable validators found; add executable checks before automated completion."
    else:
        status = "completed_verified"
        reason = "All executable blocking validators passed."

    result = _verification_result(
        status,
        reason,
        hard_results,
        forbidden_results,
        execution_report_status=execution_report.get("status"),
        manual_results=manual_results,
        unsupported_results=unsupported_results,
        warnings=warnings,
        capsule=capsule,
    )
    _write_verification_result(workspace, result)
    if status == "completed_verified":
        _update_capsule_status(workspace, "completed", reason)
    return _print_verification(result, as_json=as_json, exit_code=0 if status == "completed_verified" else 1)


def _mark(workspace: Path, status: str, reason: str) -> int:
    capsule, errors = _load_valid_capsule(workspace)
    if capsule is None:
        print("No valid Mission Capsule found.", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    _update_capsule_status(workspace, status, reason)
    print(f"status: {status}")
    if reason:
        print(f"reason: {reason}")
    return 0


def _build_capsule(
    workspace: Path,
    args: argparse.Namespace,
    extension_spec: dict[str, Any],
    verification_spec: dict[str, Any],
    review: dict[str, Any],
    previous_capsule: dict[str, Any] | None,
) -> dict[str, Any]:
    acceptance = []
    for text in args.acceptance:
        acceptance.append({"type": "manual", "description": text})
    for validator in verification_spec.get("validators", []):
        validator_type = validator.get("type")
        if validator_type == "file_exists":
            acceptance.append({"type": "file_exists", "description": f"{validator.get('path')} exists", "target": validator.get("path")})
        elif validator_type == "command":
            acceptance.append({"type": "command", "description": f"Command succeeds: {validator.get('command')}", "command": validator.get("command")})
        elif validator_type == "json_metric_gate":
            acceptance.append({"type": "json_metric_gate", "description": _describe_json_metric_gate(validator), "gate": validator})
    revision = int(previous_capsule.get("revision", 0)) + 1 if previous_capsule else 1
    return {
        "schema": CAPSULE_SCHEMA,
        "version": "1.0",
        "capsule_id": _new_id("capsule"),
        "revision": revision,
        "previous_capsule_id": previous_capsule.get("capsule_id") if previous_capsule else None,
        "revision_reason": args.revision_reason or "",
        "created_at": _now(),
        "updated_at": _now(),
        "locked_at": _now(),
        "workspace": str(workspace),
        "locked": True,
        "intent": args.intent,
        "context": args.context,
        "design_rationale": args.rationale,
        "constraints": args.constraint,
        "non_goals": args.non_goal,
        "acceptance_criteria": acceptance,
        "forbidden_paths": args.forbidden_path,
        "evidence_requirements": args.evidence,
        "extension_spec": extension_spec,
        "verification_spec": verification_spec,
        "verification_plan": {"hard_validators": _legacy_hard_validators(verification_spec)},
        "verification_review": review,
        "current_status": "designed",
        "status_history": [{"status": "designed", "reason": "Capsule locked by lightweight kernel.", "at": _now()}],
    }


def _run_validator(workspace: Path, validator: dict[str, Any]) -> dict[str, Any]:
    validator_type = str(validator.get("type") or "")
    mode = _validator_mode(validator)
    severity = _validator_severity(validator)
    base = {"type": validator_type, "mode": mode, "severity": severity}
    if mode != "executable":
        return {**base, "passed": False, "message": f"{mode} validator requires non-executable review"}
    if validator_type not in KNOWN_EXECUTABLE_VALIDATORS:
        return {**base, "passed": False, "message": "unsupported executable validator"}
    if validator_type == "file_exists":
        target = str(validator.get("path") or validator.get("target") or "")
        exists = bool(target) and (workspace / target).exists()
        return {**base, "target": target, "passed": exists, "message": "exists" if exists else "missing"}
    if validator_type == "command":
        command = str(validator.get("command") or "")
        if not command:
            return {**base, "command": command, "passed": False, "message": "empty command"}
        return {**base, **_run_command(workspace, command, timeout=120)}
    if validator_type == "forbidden_path":
        target = str(validator.get("path") or validator.get("target") or "")
        exists = bool(target) and (workspace / target).exists()
        return {**base, "target": target, "passed": not exists, "message": "absent" if not exists else "forbidden path exists"}
    if validator_type == "json_metric_gate":
        return {**base, **_run_json_metric_gate(workspace, validator)}
    if validator_type == "json_field_exists":
        return {**base, **_run_json_field_exists(workspace, validator)}
    if validator_type == "file_contains":
        return {**base, **_run_file_contains(workspace, validator)}
    if validator_type == "artifact_hash":
        return {**base, **_run_artifact_hash(workspace, validator)}
    return {**base, "passed": False, "message": "unknown validator"}


def _run_verification_spec(
    workspace: Path,
    spec: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    hard_results: list[dict[str, Any]] = []
    forbidden_results: list[dict[str, Any]] = []
    manual_results: list[dict[str, Any]] = []
    unsupported_results: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for validator in spec.get("validators", []):
        mode = _validator_mode(validator)
        severity = _validator_severity(validator)
        validator_type = str(validator.get("type") or "")
        if mode == "manual":
            result = _manual_result(validator, "manual validator requires human review")
            (warnings if severity == "advisory" else manual_results).append(result)
            continue
        if mode == "unsupported":
            result = _unsupported_result(validator, "validator is locked but unsupported by this kernel")
            (warnings if severity == "advisory" else unsupported_results).append(result)
            continue
        if validator_type not in KNOWN_EXECUTABLE_VALIDATORS:
            result = _unsupported_result(validator, "executable validator is not implemented by this kernel")
            (warnings if severity == "advisory" else unsupported_results).append(result)
            continue
        result = _run_validator(workspace, validator)
        if severity == "advisory":
            if not result.get("passed"):
                warnings.append(result)
            continue
        if validator_type == "forbidden_path":
            forbidden_results.append(result)
        else:
            hard_results.append(result)
    for gate in spec.get("resource_gates", []):
        result = _resource_gate_result(gate)
        if result["severity"] == "advisory":
            warnings.append(result)
        else:
            manual_results.append(result)
    return hard_results, forbidden_results, manual_results, unsupported_results, warnings


def _run_json_metric_gate(workspace: Path, validator: dict[str, Any]) -> dict[str, Any]:
    path = str(validator.get("path") or "")
    metric = str(validator.get("metric") or "")
    operator = str(validator.get("operator") or "")
    threshold = validator.get("threshold")
    payload = _read_json(workspace / path)
    if not isinstance(payload, dict):
        return {"path": path, "metric": metric, "passed": False, "message": "JSON artifact missing or invalid"}
    found, value = _lookup_metric(payload, metric)
    if not found:
        return {"path": path, "metric": metric, "passed": False, "message": "metric missing"}
    try:
        passed = _compare_metric(value, operator, threshold)
    except (TypeError, ValueError):
        return {
            "path": path,
            "metric": metric,
            "operator": operator,
            "threshold": threshold,
            "actual": value,
            "passed": False,
            "message": "metric comparison failed",
        }
    return {"path": path, "metric": metric, "operator": operator, "threshold": threshold, "actual": value, "passed": passed}


def _run_json_field_exists(workspace: Path, validator: dict[str, Any]) -> dict[str, Any]:
    path = str(validator.get("path") or "")
    field = str(validator.get("field") or validator.get("metric") or "")
    payload = _read_json(workspace / path)
    if not isinstance(payload, dict):
        return {"path": path, "field": field, "passed": False, "message": "JSON artifact missing or invalid"}
    found, value = _lookup_metric(payload, field)
    return {"path": path, "field": field, "passed": found, "actual": value if found else None, "message": "field exists" if found else "field missing"}


def _run_file_contains(workspace: Path, validator: dict[str, Any]) -> dict[str, Any]:
    path = str(validator.get("path") or "")
    required = validator.get("contains")
    forbidden = validator.get("not_contains")
    try:
        text = (workspace / path).read_text(encoding="utf-8")
    except OSError:
        return {"path": path, "passed": False, "message": "file missing or unreadable"}
    if isinstance(required, str) and required not in text:
        return {"path": path, "contains": required, "passed": False, "message": "required text missing"}
    if isinstance(forbidden, str) and forbidden in text:
        return {"path": path, "not_contains": forbidden, "passed": False, "message": "forbidden text present"}
    return {"path": path, "contains": required, "not_contains": forbidden, "passed": True}


def _run_artifact_hash(workspace: Path, validator: dict[str, Any]) -> dict[str, Any]:
    path = str(validator.get("path") or "")
    expected = str(validator.get("sha256") or "")
    artifact = workspace / path
    try:
        actual = "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()
    except OSError:
        return {"path": path, "expected": expected, "passed": False, "message": "artifact missing or unreadable"}
    expected_normalized = expected if expected.startswith("sha256:") else f"sha256:{expected}"
    return {"path": path, "expected": expected_normalized, "actual": actual, "passed": actual == expected_normalized}


def _manual_result(validator: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "type": validator.get("type"),
        "mode": _validator_mode(validator),
        "severity": _validator_severity(validator),
        "passed": False,
        "message": message,
        "description": validator.get("description", ""),
    }


def _unsupported_result(validator: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "type": validator.get("type"),
        "mode": _validator_mode(validator),
        "severity": _validator_severity(validator),
        "passed": False,
        "message": message,
        "description": validator.get("description", ""),
    }


def _resource_gate_result(gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "resource_gate",
        "mode": _validator_mode(gate, default="manual"),
        "severity": _validator_severity(gate),
        "resource": gate.get("resource", ""),
        "requires_user_confirmation": bool(gate.get("requires_user_confirmation", True)),
        "passed": False,
        "message": gate.get("reason") or "resource gate requires confirmation",
    }


def _run_command(workspace: Path, command: str, *, timeout: int) -> dict[str, Any]:
    if not command:
        return {"command": command, "passed": False, "message": "empty command"}
    try:
        completed = subprocess.run(command, cwd=workspace, shell=True, text=True, capture_output=True, timeout=timeout, check=False)
        return {
            "command": command,
            "passed": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "passed": False,
            "exit_code": None,
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "message": f"timeout after {timeout}s",
        }


def _observe_node(workspace: Path) -> dict[str, Any]:
    capsule = _read_json(_metaloop_dir(workspace) / "mission_capsule.json")
    execution = _read_json(_metaloop_dir(workspace) / "execution_report.json")
    verification = _read_json(_metaloop_dir(workspace) / "verification_result.json")
    adaptive = _read_json(_adaptive_loop_path(workspace))
    tick = _read_json(_metaloop_dir(workspace) / "tick_result.json")
    relay = _read_json(_metaloop_dir(workspace) / "relay_result.json")
    envelope = _read_json(workspace / "job_envelope.json")
    events, _ = _read_events(workspace)
    pending_controls = [str(item.get("type") or "") for item in _pending_control_requests(workspace)]
    latest_iteration = _latest_adaptive_iteration(adaptive)
    return {
        "schema": NODE_SUMMARY_SCHEMA,
        "version": "1.0",
        "created_at": _now(),
        "workspace": str(workspace),
        "node_id": _summary_node_id(workspace, capsule, envelope),
        "status": _summary_status(capsule, verification, execution),
        "goal": _summary_goal(capsule, envelope, adaptive),
        "current_plan": str(adaptive.get("current_plan") or "") if isinstance(adaptive, dict) else "",
        "best_metric": verification.get("best_metric") if isinstance(verification, dict) and isinstance(verification.get("best_metric"), dict) else None,
        "last_event": _event_summary(events[-1] if events else None),
        "last_verification": _verification_summary(verification),
        "adaptive_decision": str(latest_iteration.get("decision") or "") if latest_iteration else "",
        "waiting_on": _summary_waiting_on(verification, pending_controls),
        "outbox_count": _count_json_files(_metaloop_dir(workspace) / "outbox"),
        "inbox_count": _count_json_files(_metaloop_dir(workspace) / "inbox"),
        "pending_controls": pending_controls,
        "last_tick_action": _nested_string(tick, ["route", "action"]),
        "last_relay_status": str(relay.get("status") or "") if isinstance(relay, dict) else "",
        "updated_at": _latest_mtime(
            [
                _metaloop_dir(workspace) / "mission_capsule.json",
                _metaloop_dir(workspace) / "verification_result.json",
                _adaptive_loop_path(workspace),
                _event_log_path(workspace),
                workspace / "job_envelope.json",
            ]
        ),
    }


def _observe_root(root: Path) -> dict[str, Any]:
    nodes = [_observe_node(path) for path in _node_workspaces(root)]
    counts: dict[str, int] = {}
    for node in nodes:
        status = str(node.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {
        "schema": GLOBAL_SUMMARY_SCHEMA,
        "version": "1.0",
        "created_at": _now(),
        "root": str(root),
        "node_count": len(nodes),
        "status_counts": counts,
        "blocked_nodes": [node for node in nodes if node.get("status") in {"blocked", "human_acceptance_required"} or node.get("waiting_on")],
        "outbox_count": sum(int(node.get("outbox_count") or 0) for node in nodes),
        "inbox_count": sum(int(node.get("inbox_count") or 0) for node in nodes),
        "nodes": nodes,
    }


def _activate_once(
    root: Path,
    *,
    worker_command: str,
    dry_run: bool,
    timeout: int,
    lease_seconds: int,
    max_activations: int,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    started = 0
    now = datetime.now(timezone.utc)
    for node in _node_workspaces(root):
        candidate = _activation_candidate(node, worker_command=worker_command, lease_seconds=lease_seconds, now=now)
        if candidate["action"] != "ready":
            nodes.append(candidate)
            continue
        if not worker_command:
            nodes.append({**candidate, "action": "no_worker_command", "reason": "No worker command was supplied; activation only reports readiness."})
            continue
        if dry_run:
            nodes.append(candidate)
            continue
        if started >= max(0, max_activations):
            nodes.append({**candidate, "reason": "Activation limit reached for this pass."})
            continue
        nodes.append(_run_activation_worker(candidate, worker_command=worker_command, timeout=timeout, lease_seconds=lease_seconds))
        started += 1
    result = _activation_result(root, worker_command=worker_command, dry_run=dry_run, nodes=nodes)
    path = _activation_result_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _activation_candidate(workspace: Path, *, worker_command: str, lease_seconds: int, now: datetime) -> dict[str, Any]:
    envelope_path = workspace / "job_envelope.json"
    summary = _observe_node(workspace)
    base = {
        "workspace": str(workspace),
        "node_id": summary.get("node_id") or workspace.name,
        "status": summary.get("status") or "missing",
        "pending_controls": summary.get("pending_controls") or [],
        "job_envelope_path": str(envelope_path),
        "lease_path": str(_activation_lease_path(workspace)),
        "worker_command": worker_command,
    }
    envelope = _read_json(envelope_path)
    if not isinstance(envelope, dict):
        return {**base, "action": "skipped_no_envelope", "reason": "No job_envelope.json is available."}
    errors = _validate_job_envelope(envelope)
    envelope_hash = str(envelope.get("envelope_hash") or _job_envelope_hash(envelope))
    idempotency_key = _hash_object({"workspace": str(workspace), "envelope_hash": envelope_hash, "worker_command": worker_command}, "idempotency_key")
    base = {**base, "envelope_hash": envelope_hash, "idempotency_key": idempotency_key}
    if errors:
        return {**base, "action": "failed", "reason": "job_envelope.json is invalid.", "errors": errors}
    controls = _pending_control_requests(workspace)
    if controls:
        return {
            **base,
            "action": "blocked_by_control",
            "reason": "Pending control files must be processed before activation.",
            "pending_controls": [str(item.get("type") or "") for item in controls],
        }
    lease = _active_activation_lease(workspace, now)
    if lease is not None:
        return {**base, "action": "lease_active", "reason": "An activation lease is still active.", "lease": lease}
    return {**base, "action": "ready", "reason": "Envelope is ready for one-shot activation."}


def _run_activation_worker(candidate: dict[str, Any], *, worker_command: str, timeout: int, lease_seconds: int) -> dict[str, Any]:
    workspace = Path(str(candidate["workspace"]))
    lease = _write_activation_lease(workspace, candidate, lease_seconds=lease_seconds)
    command_result = _run_command(workspace, worker_command, timeout=timeout)
    action = "started" if command_result.get("passed") else "failed"
    reason = "Worker command completed." if command_result.get("passed") else "Worker command failed."
    updated_lease = dict(lease)
    updated_lease["status"] = "completed" if command_result.get("passed") else "failed"
    updated_lease["completed_at"] = _now()
    _activation_lease_path(workspace).write_text(json.dumps(updated_lease, indent=2, ensure_ascii=False), encoding="utf-8")
    _append_event(
        workspace,
        {
            "schema": EVENT_SCHEMA,
            "version": "1.0",
            "event_id": _new_id("event"),
            "created_at": _now(),
            "workspace": str(workspace),
            "capsule_id": _current_capsule_id(workspace),
            "type": "action" if command_result.get("passed") else "blocker",
            "agent": "activation",
            "thread_role": "",
            "thread_id": "",
            "summary": f"Activation {action}: {reason}",
            "evidence": [str(_activation_lease_path(workspace))],
            "decision": action,
            "next_action": "worker_must_write_execution_report_and_verify" if command_result.get("passed") else "inspect_worker_command_failure",
        },
    )
    return {**candidate, "action": action, "reason": reason, "lease": lease, "command_result": command_result}


def _activation_result(root: Path, *, worker_command: str, dry_run: bool, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for node in nodes:
        action = str(node.get("action") or "unknown")
        counts[action] = counts.get(action, 0) + 1
    return {
        "schema": ACTIVATION_RESULT_SCHEMA,
        "version": "1.0",
        "activation_id": _new_id("activation"),
        "created_at": _now(),
        "root": str(root),
        "dry_run": dry_run,
        "worker_command": worker_command,
        "counts": counts,
        "nodes": nodes,
    }


def _read_status(workspace: Path) -> dict[str, Any]:
    capsule_path = _metaloop_dir(workspace) / "mission_capsule.json"
    adaptive_path = _adaptive_loop_path(workspace)
    execution_path = _metaloop_dir(workspace) / "execution_report.json"
    verification_path = _metaloop_dir(workspace) / "verification_result.json"
    threads_path = _thread_registry_path(workspace)
    event_path = _event_log_path(workspace)
    capsule = _read_json(capsule_path)
    adaptive_loop = _read_json(adaptive_path)
    execution = _read_json(execution_path)
    verification = _read_json(verification_path)
    threads = _read_json(threads_path)
    events, event_errors = _read_events(workspace)
    capsule_state = {"state": "missing", "path": None, "current_status": None}
    if isinstance(capsule, dict):
        capsule_errors = _validate_capsule(capsule)
        capsule_state = {
            "state": "invalid" if capsule_errors else "ready",
            "path": str(capsule_path),
            "current_status": capsule.get("current_status"),
            "locked": capsule.get("locked", False),
            "intent": capsule.get("intent", ""),
            "revision": capsule.get("revision"),
            "errors": capsule_errors,
        }
    adaptive_state = {"state": "missing", "path": str(adaptive_path), "status": None}
    if isinstance(adaptive_loop, dict):
        adaptive_errors = _validate_adaptive_loop(adaptive_loop)
        adaptive_state = {
            "state": "invalid" if adaptive_errors else "ready",
            "path": str(adaptive_path),
            "status": adaptive_loop.get("status"),
            "goal": adaptive_loop.get("goal", ""),
            "current_plan": adaptive_loop.get("current_plan", ""),
            "iterations": len(adaptive_loop.get("iterations", [])) if isinstance(adaptive_loop.get("iterations"), list) else 0,
            "errors": adaptive_errors,
        }
    execution_state = {"state": "missing", "path": None, "status": None}
    if isinstance(execution, dict):
        execution_state = {"state": "ready", "path": str(execution_path), "status": execution.get("status")}
    verification_state = {"state": "missing", "path": None, "status": None}
    if isinstance(verification, dict):
        verification_state = {"state": "ready", "path": str(verification_path), "status": verification.get("status")}
    threads_state = {"state": "missing", "path": str(threads_path), "count": 0}
    if isinstance(threads, dict):
        thread_errors = _validate_thread_registry(threads)
        agents = threads.get("agents", {}) if isinstance(threads.get("agents"), dict) else {}
        threads_state = {
            "state": "invalid" if thread_errors else "ready",
            "path": str(threads_path),
            "count": len(agents),
            "roles": sorted(agents),
            "errors": thread_errors,
        }
    events_state = {
        "state": "invalid" if event_errors else ("ready" if event_path.exists() else "missing"),
        "path": str(event_path),
        "count": len(events),
        "latest": events[-1] if events else None,
        "errors": event_errors,
    }
    status = {
        "workspace": str(workspace),
        "capsule": capsule_state,
        "adaptive_loop": adaptive_state,
        "execution": execution_state,
        "verification": verification_state,
        "threads": threads_state,
        "events": events_state,
    }
    status["next_action"] = _next_action(status)
    return status


def _next_action(status: dict[str, Any]) -> str:
    capsule_status = status["capsule"].get("current_status")
    verification_status = status["verification"].get("status")
    if status["capsule"]["state"] == "missing":
        return "Run design before execution."
    if status["capsule"]["state"] == "invalid":
        return "Repair or redesign invalid Mission Capsule before execution."
    if capsule_status == "redesign_required":
        return "Collect user feedback and revise the Mission Capsule."
    if status["execution"]["state"] == "missing":
        return "Run execution through the lightweight kernel before verification."
    if verification_status == "unsupported_verification_spec":
        return "Add extension support or redesign unsupported blocking validators."
    if verification_status == "missing_verification_plan":
        return "Add executable validators before claiming automated completion."
    if verification_status == "human_acceptance_required":
        return "Ask the user for manual acceptance or revise acceptance criteria."
    if verification_status == "completed_verified":
        return "Complete or ask for final human acceptance."
    if verification_status == "failed":
        return "Classify as repair or redesign before continuing."
    return "Execute with Codex around the locked Mission Capsule, then verify."


def _verification_result(
    status: str,
    reason: str,
    hard_results: list[dict[str, Any]],
    forbidden_results: list[dict[str, Any]],
    *,
    execution_report_status: str | None = None,
    manual_results: list[dict[str, Any]] | None = None,
    unsupported_results: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    errors: list[str] | None = None,
    capsule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extension_spec = capsule.get("extension_spec", {}) if capsule else {}
    verification_spec = capsule.get("verification_spec", {}) if capsule else {}
    return {
        "schema": VERIFICATION_SCHEMA,
        "version": "1.0",
        "created_at": _now(),
        "status": status,
        "reason": reason,
        "capsule_id": capsule.get("capsule_id") if capsule else None,
        "capsule_revision": capsule.get("revision") if capsule else None,
        "execution_report_status": execution_report_status,
        "extension_domain": extension_spec.get("domain"),
        "extension_hash": extension_spec.get("extension_hash"),
        "verification_spec_domain": verification_spec.get("domain"),
        "verification_spec_hash": verification_spec.get("spec_hash"),
        "errors": errors or [],
        "warnings": warnings or [],
        "hard_validator_results": hard_results,
        "forbidden_path_results": forbidden_results,
        "manual_validator_results": manual_results or [],
        "unsupported_validator_results": unsupported_results or [],
    }


def _write_verification_result(workspace: Path, result: dict[str, Any]) -> None:
    _metaloop_dir(workspace).mkdir(parents=True, exist_ok=True)
    (_metaloop_dir(workspace) / "verification_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _print_verification(result: dict[str, Any], *, as_json: bool, exit_code: int) -> int:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"verification: {result['status']}")
        print(f"reason: {result['reason']}")
    return exit_code


def _load_capsule(workspace: Path) -> dict[str, Any] | None:
    payload = _read_json(_metaloop_dir(workspace) / "mission_capsule.json")
    return payload if isinstance(payload, dict) else None


def _load_valid_capsule(workspace: Path) -> tuple[dict[str, Any] | None, list[str]]:
    payload = _read_json(_metaloop_dir(workspace) / "mission_capsule.json")
    errors = _validate_capsule(payload)
    if errors:
        return None, errors
    return payload, []


def _load_valid_execution_report(workspace: Path, capsule: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    payload = _read_json(_metaloop_dir(workspace) / "execution_report.json")
    errors = _validate_execution_report(payload, capsule)
    if errors:
        return None, errors
    return payload, []


def _build_extension_spec(args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    if args.extension_spec:
        payload = _read_json(Path(args.extension_spec).expanduser())
        if not isinstance(payload, dict):
            return {}, ["--extension-spec must point to a JSON object"]
        spec = _normalize_extension_spec(payload)
    else:
        spec = _default_extension_spec(args)
    spec["extension_hash"] = _hash_object(spec, "extension_hash")
    return spec, _validate_extension_spec(spec, allow_lightweight=args.allow_lightweight_extension)


def _default_extension_spec(args: argparse.Namespace) -> dict[str, Any]:
    risk_checks = list(args.risk_check)
    review_questions = list(args.review_question)
    return {
        "schema": EXTENSION_SPEC_SCHEMA,
        "version": "1.0",
        "domain": "generic",
        "purpose": "Generic local task verification.",
        "validator_types": [
            {"type": item, "mode": "executable", "description": f"Bundled generic {item} validator."}
            for item in sorted(KNOWN_EXECUTABLE_VALIDATORS)
        ]
        + [
            {"type": item, "mode": "manual", "description": f"Bundled generic {item} protocol."}
            for item in sorted(KNOWN_MANUAL_VALIDATORS)
        ],
        "risk_checks": risk_checks,
        "review_questions": review_questions,
        "known_gaps": list(args.known_gap),
    }


def _normalize_extension_spec(payload: dict[str, Any]) -> dict[str, Any]:
    spec = dict(payload)
    spec.setdefault("schema", EXTENSION_SPEC_SCHEMA)
    spec.setdefault("version", "1.0")
    spec.setdefault("domain", "generic")
    spec.setdefault("purpose", "")
    spec.setdefault("validator_types", [])
    spec.setdefault("risk_checks", [])
    spec.setdefault("review_questions", [])
    spec.setdefault("known_gaps", [])
    return spec


def _build_verification_spec(args: argparse.Namespace, extension_spec: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors = []
    if args.verification_spec:
        payload = _read_json(Path(args.verification_spec).expanduser())
        if not isinstance(payload, dict):
            return {}, ["--verification-spec must point to a JSON object"]
        spec = dict(payload)
        spec.setdefault("schema", VERIFICATION_SPEC_SCHEMA)
        spec.setdefault("version", "1.0")
        spec.setdefault("domain", extension_spec.get("domain", "generic"))
        spec.setdefault("extension", extension_spec.get("domain", "generic"))
        spec.setdefault("extension_version", extension_spec.get("version", "1.0"))
        spec.setdefault("validators", [])
        spec.setdefault("evidence_requirements", list(args.evidence))
        spec.setdefault("resource_gates", [])
    else:
        spec = {
            "schema": VERIFICATION_SPEC_SCHEMA,
            "version": "1.0",
            "domain": extension_spec.get("domain", "generic"),
            "extension": extension_spec.get("domain", "generic"),
            "extension_version": extension_spec.get("version", "1.0"),
            "validators": [],
            "evidence_requirements": list(args.evidence),
            "resource_gates": [],
        }
        for text in args.acceptance:
            spec["validators"].append(_normalize_validator({"type": "manual_acceptance", "description": text}, default_mode="manual"))
        for path in args.file_exists:
            spec["validators"].append(_normalize_validator({"type": "file_exists", "path": path}))
        for command in args.validation_commands:
            spec["validators"].append(_normalize_validator({"type": "command", "command": command}))
        for path in args.forbidden_path:
            spec["validators"].append(_normalize_validator({"type": "forbidden_path", "path": path}))
        for raw in args.file_contains:
            spec["validators"].append(_normalize_validator(_parse_json_or_error(raw, "--file-contains", errors, default_type="file_contains")))
        for raw in args.json_field_exists:
            spec["validators"].append(_normalize_validator(_parse_json_or_error(raw, "--json-field-exists", errors, default_type="json_field_exists")))
        for raw in args.json_metric_gate:
            spec["validators"].append(_normalize_validator(_parse_json_or_error(raw, "--json-metric-gate", errors, default_type="json_metric_gate")))
        for raw in args.artifact_hash:
            spec["validators"].append(_normalize_validator(_parse_json_or_error(raw, "--artifact-hash", errors, default_type="artifact_hash")))
        for raw in args.forbidden_claim:
            spec["validators"].append(_normalize_validator(_parse_claim_validator(raw, errors)))
        for raw in args.resource_gate:
            spec["resource_gates"].append(_normalize_validator(_parse_json_or_error(raw, "--resource-gate", errors, default_type="resource_gate"), default_mode="manual"))
        for raw in args.validator:
            spec["validators"].append(_normalize_validator(_parse_json_or_error(raw, "--validator", errors)))
    spec["extension_hash"] = extension_spec.get("extension_hash")
    spec["spec_hash"] = _hash_object(spec, "spec_hash")
    return spec, [*errors, *_validate_verification_spec(spec, extension_spec=extension_spec)]


def _parse_json_or_error(raw: str, label: str, errors: list[str], *, default_type: str | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        errors.append(f"{label} must be valid JSON")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"{label} must be a JSON object")
        return {}
    if default_type:
        payload.setdefault("type", default_type)
    return payload


def _parse_claim_validator(raw: str, errors: list[str]) -> dict[str, Any]:
    stripped = raw.strip()
    if stripped.startswith("{"):
        payload = _parse_json_or_error(raw, "--forbidden-claim", errors, default_type="forbidden_claim")
    else:
        payload = {"type": "forbidden_claim", "claim": raw}
    payload.setdefault("mode", "manual")
    payload.setdefault("severity", "blocking")
    return payload


def _normalize_validator(payload: dict[str, Any], *, default_mode: str | None = None) -> dict[str, Any]:
    validator = dict(payload)
    validator_type = validator.get("type")
    if "mode" not in validator:
        if default_mode:
            validator["mode"] = default_mode
        elif validator_type in KNOWN_EXECUTABLE_VALIDATORS:
            validator["mode"] = "executable"
        elif validator_type in KNOWN_MANUAL_VALIDATORS:
            validator["mode"] = "manual"
        else:
            validator["mode"] = "unsupported"
    validator.setdefault("severity", "blocking")
    return validator


def _build_verification_review(args: argparse.Namespace, extension_spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "risk_checks": list(args.risk_check) or list(extension_spec.get("risk_checks", [])),
        "review_questions": list(args.review_question) or list(extension_spec.get("review_questions", [])),
        "known_gaps": list(args.known_gap) or list(extension_spec.get("known_gaps", [])),
        "review_status": "pending" if (args.known_gap or extension_spec.get("known_gaps")) else "not_required",
    }


def _validate_design_input(
    args: argparse.Namespace,
    extension_spec: dict[str, Any],
    verification_spec: dict[str, Any],
    review: dict[str, Any],
) -> list[str]:
    errors = []
    if not args.intent.strip():
        errors.append("intent is required")
    if not args.rationale:
        errors.append("at least one --rationale is required before locking a Mission Capsule")
    if not args.non_goal:
        errors.append("at least one --non-goal is required before locking a Mission Capsule")
    validators = verification_spec.get("validators", []) if isinstance(verification_spec, dict) else []
    resource_gates = verification_spec.get("resource_gates", []) if isinstance(verification_spec, dict) else []
    if not (args.acceptance or validators or resource_gates):
        errors.append("at least one acceptance criterion or validator is required")
    executable_validators = [item for item in validators if _validator_mode(item) == "executable"]
    if not executable_validators and not args.allow_manual_only:
        errors.append("at least one executable validator is required, or pass --allow-manual-only explicitly")
    if extension_spec.get("domain") != "generic" and not args.allow_lightweight_extension:
        if not (review.get("risk_checks") or review.get("review_questions")):
            errors.append("task-specific extensions require risk checks or review questions")
    return errors


def _validate_capsule(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["mission_capsule.json is missing or is not a JSON object"]
    errors = []
    if payload.get("schema") != CAPSULE_SCHEMA:
        errors.append(f"schema must be {CAPSULE_SCHEMA}")
    for key in ["version", "capsule_id", "created_at", "updated_at", "locked_at", "workspace", "intent", "current_status"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    if not isinstance(payload.get("revision"), int) or payload.get("revision", 0) < 1:
        errors.append("revision must be a positive integer")
    if payload.get("locked") is not True:
        errors.append("locked must be true")
    if payload.get("current_status") not in CAPSULE_STATUSES:
        errors.append("current_status is not a known capsule status")
    for key in ["context", "design_rationale", "constraints", "non_goals", "acceptance_criteria", "forbidden_paths", "evidence_requirements", "status_history"]:
        if not isinstance(payload.get(key), list):
            errors.append(f"{key} must be a list")
    extension = payload.get("extension_spec", {}) if isinstance(payload.get("extension_spec"), dict) else {}
    verification = payload.get("verification_spec", {}) if isinstance(payload.get("verification_spec"), dict) else {}
    extension_errors = _validate_extension_spec(extension, allow_lightweight=True)
    spec_errors = _validate_verification_spec(verification, extension_spec=extension)
    errors.extend(extension_errors)
    errors.extend(spec_errors)
    if extension.get("extension_hash") and verification.get("extension_hash") and extension["extension_hash"] != verification["extension_hash"]:
        errors.append("verification_spec.extension_hash does not match extension_spec.extension_hash")
    if not isinstance(payload.get("verification_review"), dict):
        errors.append("verification_review must be an object")
    return errors


def _validate_extension_spec(payload: Any, *, allow_lightweight: bool) -> list[str]:
    if not isinstance(payload, dict):
        return ["extension_spec must be an object"]
    errors = []
    if payload.get("schema") != EXTENSION_SPEC_SCHEMA:
        errors.append(f"extension_spec.schema must be {EXTENSION_SPEC_SCHEMA}")
    for key in ["version", "domain", "purpose", "extension_hash"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"extension_spec.{key} must be a non-empty string")
    for key in ["validator_types", "risk_checks", "review_questions", "known_gaps"]:
        if not isinstance(payload.get(key), list):
            errors.append(f"extension_spec.{key} must be a list")
    if isinstance(payload.get("validator_types"), list):
        for index, validator_type in enumerate(payload["validator_types"]):
            if not isinstance(validator_type, dict):
                errors.append(f"extension_spec.validator_types[{index}] must be an object")
                continue
            if not isinstance(validator_type.get("type"), str) or not validator_type.get("type"):
                errors.append(f"extension_spec.validator_types[{index}].type must be a non-empty string")
            if validator_type.get("mode") not in MODES:
                errors.append(f"extension_spec.validator_types[{index}].mode must be one of {sorted(MODES)}")
    if isinstance(payload.get("extension_hash"), str) and payload.get("extension_hash") != _hash_object(payload, "extension_hash"):
        errors.append("extension_spec.extension_hash does not match locked extension content")
    if payload.get("domain") != "generic" and not allow_lightweight:
        if not (payload.get("risk_checks") or payload.get("review_questions")):
            errors.append("task-specific extension_spec requires risk_checks or review_questions")
    return errors


def _validate_verification_spec(payload: Any, *, extension_spec: dict[str, Any] | None = None) -> list[str]:
    if not isinstance(payload, dict):
        return ["verification_spec must be an object"]
    errors = []
    if payload.get("schema") != VERIFICATION_SPEC_SCHEMA:
        errors.append(f"verification_spec.schema must be {VERIFICATION_SPEC_SCHEMA}")
    for key in ["version", "domain", "extension", "extension_version", "extension_hash", "spec_hash"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"verification_spec.{key} must be a non-empty string")
    if isinstance(payload.get("spec_hash"), str) and payload.get("spec_hash") != _hash_object(payload, "spec_hash"):
        errors.append("verification_spec.spec_hash does not match locked spec content")
    validators = payload.get("validators")
    if not isinstance(validators, list):
        errors.append("verification_spec.validators must be a list")
        return errors
    for index, validator in enumerate(validators):
        if not isinstance(validator, dict):
            errors.append(f"verification_spec.validators[{index}] must be an object")
            continue
        errors.extend(_validate_validator_shape(validator, index, extension_spec=extension_spec))
    for key in ["evidence_requirements", "resource_gates"]:
        if not isinstance(payload.get(key), list):
            errors.append(f"verification_spec.{key} must be a list")
    for index, gate in enumerate(payload.get("resource_gates", [])):
        if not isinstance(gate, dict):
            errors.append(f"verification_spec.resource_gates[{index}] must be an object")
            continue
        errors.extend(_validate_validator_shape(gate, index, prefix="verification_spec.resource_gates", extension_spec=extension_spec))
    return errors


def _validate_validator_shape(
    validator: dict[str, Any],
    index: int,
    *,
    prefix: str = "verification_spec.validators",
    extension_spec: dict[str, Any] | None = None,
) -> list[str]:
    errors = []
    validator_type = validator.get("type")
    if not isinstance(validator_type, str) or not validator_type:
        errors.append(f"{prefix}[{index}].type must be a non-empty string")
    mode = validator.get("mode")
    severity = validator.get("severity")
    if mode not in MODES:
        errors.append(f"{prefix}[{index}].mode must be one of {sorted(MODES)}")
    if severity not in SEVERITIES:
        errors.append(f"{prefix}[{index}].severity must be one of {sorted(SEVERITIES)}")
    if isinstance(validator_type, str) and validator_type:
        errors.extend(_validate_validator_declared_by_extension(validator_type, mode, index, prefix=prefix, extension_spec=extension_spec))
    if validator_type in {"file_exists", "forbidden_path"} and not isinstance(validator.get("path"), str):
        errors.append(f"{prefix}[{index}].path must be a string")
    if validator_type == "command" and not isinstance(validator.get("command"), str):
        errors.append(f"{prefix}[{index}].command must be a string")
    if validator_type == "json_metric_gate":
        errors.extend(_validate_json_metric_gate(validator, index, prefix=prefix))
    if validator_type == "json_field_exists":
        if not isinstance(validator.get("path"), str):
            errors.append(f"{prefix}[{index}].path must be a string")
        if not isinstance(validator.get("field"), str):
            errors.append(f"{prefix}[{index}].field must be a string")
    if validator_type == "file_contains":
        if not isinstance(validator.get("path"), str):
            errors.append(f"{prefix}[{index}].path must be a string")
        if not isinstance(validator.get("contains", ""), str) and not isinstance(validator.get("not_contains", ""), str):
            errors.append(f"{prefix}[{index}] requires contains or not_contains string")
    if validator_type == "artifact_hash":
        if not isinstance(validator.get("path"), str):
            errors.append(f"{prefix}[{index}].path must be a string")
        if not isinstance(validator.get("sha256"), str):
            errors.append(f"{prefix}[{index}].sha256 must be a string")
    return errors


def _validate_validator_declared_by_extension(
    validator_type: str,
    mode: Any,
    index: int,
    *,
    prefix: str,
    extension_spec: dict[str, Any] | None,
) -> list[str]:
    if not extension_spec:
        return []
    validator_types = extension_spec.get("validator_types")
    if not isinstance(validator_types, list):
        return []
    allowed_modes = {
        item.get("mode")
        for item in validator_types
        if isinstance(item, dict) and item.get("type") == validator_type and item.get("mode") in MODES
    }
    if not allowed_modes:
        return [f"{prefix}[{index}].type is not declared by extension_spec.validator_types"]
    if mode in MODES and mode not in allowed_modes:
        return [f"{prefix}[{index}].mode is not declared for this validator type by extension_spec.validator_types"]
    return []


def _validate_json_metric_gate(validator: dict[str, Any], index: int, *, prefix: str = "verification_spec.validators") -> list[str]:
    errors = []
    if not isinstance(validator.get("path"), str):
        errors.append(f"{prefix}[{index}].path must be a string")
    if not isinstance(validator.get("metric"), str):
        errors.append(f"{prefix}[{index}].metric must be a string")
    if validator.get("operator") not in {">", ">=", "<", "<=", "==", "!="}:
        errors.append(f"{prefix}[{index}].operator is unsupported")
    if "threshold" not in validator:
        errors.append(f"{prefix}[{index}].threshold is required")
    return errors


def _validate_execution_report(payload: Any, capsule: dict[str, Any]) -> list[str]:
    if not isinstance(payload, dict):
        return ["execution_report.json is missing or is not a JSON object"]
    errors = []
    if payload.get("schema") != EXECUTION_REPORT_SCHEMA:
        errors.append(f"schema must be {EXECUTION_REPORT_SCHEMA}")
    if payload.get("capsule_id") != capsule.get("capsule_id"):
        errors.append("execution_report capsule_id does not match Mission Capsule")
    if payload.get("capsule_revision") != capsule.get("revision"):
        errors.append("execution_report capsule_revision does not match Mission Capsule")
    if payload.get("status") not in {"completed", "failed", "blocked"}:
        errors.append("execution_report status is invalid")
    if not isinstance(payload.get("commands"), list):
        errors.append("execution_report commands must be a list")
    if not isinstance(payload.get("evidence"), list):
        errors.append("execution_report evidence must be a list")
    return errors


def _legacy_hard_validators(spec: dict[str, Any]) -> list[dict[str, Any]]:
    validators = []
    for validator in spec.get("validators", []):
        if _validator_mode(validator) != "executable":
            continue
        validator_type = validator.get("type")
        if validator_type == "file_exists":
            validators.append({"type": "file_exists", "target": validator.get("path", "")})
        elif validator_type == "command":
            validators.append({"type": "command", "command": validator.get("command", "")})
        elif validator_type in {"json_metric_gate", "json_field_exists", "file_contains", "artifact_hash"}:
            validators.append(dict(validator))
    return validators


def _describe_json_metric_gate(gate: dict[str, Any]) -> str:
    return f"JSON metric gate: {gate.get('path')} {gate.get('metric')} {gate.get('operator')} {gate.get('threshold')}"


def _lookup_metric(payload: dict[str, Any], metric: str) -> tuple[bool, Any]:
    current: Any = payload
    for part in metric.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


def _compare_metric(value: Any, operator: str, threshold: Any) -> bool:
    if operator in {">", ">=", "<", "<="}:
        left = float(value)
        right = float(threshold)
        if operator == ">":
            return left > right
        if operator == ">=":
            return left >= right
        if operator == "<":
            return left < right
        return left <= right
    if operator == "==":
        return value == threshold
    if operator == "!=":
        return value != threshold
    raise ValueError(f"unsupported operator: {operator}")


def _validator_mode(validator: dict[str, Any], *, default: str | None = None) -> str:
    value = validator.get("mode") or default
    if isinstance(value, str) and value in MODES:
        return value
    validator_type = validator.get("type")
    if validator_type in KNOWN_EXECUTABLE_VALIDATORS:
        return "executable"
    if validator_type in KNOWN_MANUAL_VALIDATORS:
        return "manual"
    return "unsupported"


def _validator_severity(validator: dict[str, Any]) -> str:
    value = validator.get("severity")
    return value if isinstance(value, str) and value in SEVERITIES else "blocking"


def _hash_object(payload: dict[str, Any], hash_key: str) -> str:
    normalized = dict(payload)
    normalized.pop(hash_key, None)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _archive_capsule(workspace: Path, capsule: dict[str, Any]) -> None:
    revisions_dir = _metaloop_dir(workspace) / "revisions"
    revisions_dir.mkdir(parents=True, exist_ok=True)
    revision = _safe_revision(capsule.get("revision"))
    capsule_id = _safe_archive_component(str(capsule.get("capsule_id") or "unknown"))
    validation_errors = _validate_capsule(capsule)
    if validation_errors:
        capsule = {**capsule, "archived_validation_errors": validation_errors}
    archive_path = revisions_dir / f"capsule-v{revision}-{capsule_id}.json"
    archive_path.write_text(json.dumps(capsule, indent=2, ensure_ascii=False), encoding="utf-8")


def _safe_revision(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _safe_archive_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._-")
    return (safe or "unknown")[:80]


def _update_capsule_status(workspace: Path, status: str, reason: str) -> None:
    path = _metaloop_dir(workspace) / "mission_capsule.json"
    capsule = _load_capsule(workspace)
    if capsule is None:
        return
    capsule["current_status"] = status
    capsule["updated_at"] = _now()
    capsule.setdefault("status_history", []).append({"status": status, "reason": reason, "at": _now()})
    path.write_text(json.dumps(capsule, indent=2, ensure_ascii=False), encoding="utf-8")


def _thread_registry_path(workspace: Path) -> Path:
    return _metaloop_dir(workspace) / "threads.json"


def _load_thread_registry(workspace: Path) -> dict[str, Any] | None:
    payload = _read_json(_thread_registry_path(workspace))
    return payload if isinstance(payload, dict) else None


def _ensure_thread_registry(workspace: Path) -> dict[str, Any]:
    registry = _load_thread_registry(workspace)
    if registry is not None and not _validate_thread_registry(registry):
        return registry
    now = _now()
    return {
        "schema": THREAD_REGISTRY_SCHEMA,
        "version": "1.0",
        "workspace": str(workspace),
        "created_at": now,
        "updated_at": now,
        "coordination_rule": "Persistent agent threads may keep their own context; shared operational truth is .metaloop artifacts.",
        "agents": {},
    }


def _write_thread_registry(workspace: Path, registry: dict[str, Any]) -> None:
    registry["updated_at"] = _now()
    registry.setdefault("schema", THREAD_REGISTRY_SCHEMA)
    registry.setdefault("version", "1.0")
    registry.setdefault("workspace", str(workspace))
    registry.setdefault("coordination_rule", "Persistent agent threads may keep their own context; shared operational truth is .metaloop artifacts.")
    registry.setdefault("agents", {})
    _metaloop_dir(workspace).mkdir(parents=True, exist_ok=True)
    _thread_registry_path(workspace).write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")


def _validate_thread_registry(payload: Any) -> list[str]:
    if payload is None:
        return []
    if not isinstance(payload, dict):
        return ["threads.json is not a JSON object"]
    errors = []
    if payload.get("schema") != THREAD_REGISTRY_SCHEMA:
        errors.append(f"schema must be {THREAD_REGISTRY_SCHEMA}")
    for key in ["version", "workspace", "created_at", "updated_at", "coordination_rule"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    agents = payload.get("agents")
    if not isinstance(agents, dict):
        errors.append("agents must be an object")
        return errors
    for role, agent in agents.items():
        if not isinstance(role, str) or not role:
            errors.append("agent role keys must be non-empty strings")
            continue
        if not isinstance(agent, dict):
            errors.append(f"agents.{role} must be an object")
            continue
        errors.extend(_validate_thread_agent(role, agent))
    return errors


def _validate_thread_agent(role: str, agent: dict[str, Any]) -> list[str]:
    errors = []
    if agent.get("role") != role:
        errors.append(f"agents.{role}.role must match registry key")
    for key in ["role_type", "thread_id", "status", "created_at", "updated_at", "context_policy"]:
        if not isinstance(agent.get(key), str) or not agent.get(key):
            errors.append(f"agents.{role}.{key} must be a non-empty string")
    if agent.get("status") not in THREAD_STATUSES:
        errors.append(f"agents.{role}.status must be one of {sorted(THREAD_STATUSES)}")
    for key in ["responsibilities", "notes", "history"]:
        if not isinstance(agent.get(key), list):
            errors.append(f"agents.{role}.{key} must be a list")
    return errors


def _validate_thread_role_input(role: str, role_type: str, thread_id: str) -> list[str]:
    errors = []
    if not _is_safe_role_slug(role):
        errors.append("--role must be a non-empty slug using letters, numbers, dot, underscore, or hyphen")
    if not _is_safe_role_slug(role_type):
        errors.append("--role-type must be a non-empty slug using letters, numbers, dot, underscore, or hyphen")
    if not thread_id.strip():
        errors.append("--thread-id is required")
    return errors


def _is_safe_role_slug(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value.strip()))


def _default_responsibilities(role_type: str, role: str) -> list[str]:
    normalized = role_type if role_type in CANONICAL_THREAD_TYPES else role
    defaults = {
        "interface": ["Talk with the user and map intent to MetaLoop protocol actions without executing unchecked work."],
        "design": ["Explore requirements deeply and draft Mission Capsule plus VerificationSpec before execution."],
        "worker": ["Execute implementation against the locked capsule without weakening verification."],
        "reviewer": ["Review evidence and contract fit independently from worker self-report."],
        "verifier": ["Run locked validators and classify completion, repair, redesign, or limitation status."],
    }
    return defaults.get(normalized, ["Maintain a persistent Codex thread for this bounded MetaLoop responsibility."])


def _current_capsule_id(workspace: Path) -> str:
    capsule = _load_capsule(workspace)
    if not isinstance(capsule, dict):
        return ""
    value = capsule.get("capsule_id")
    return value if isinstance(value, str) else ""


def _short_thread_id(thread_id: str) -> str:
    if len(thread_id) <= 18:
        return thread_id or "-"
    return f"{thread_id[:8]}...{thread_id[-8:]}"


def _control_dir(workspace: Path) -> Path:
    return _metaloop_dir(workspace) / "control"


def _control_request_path(workspace: Path, control_type: str) -> Path:
    return _control_dir(workspace) / f"{control_type}.json"


def _load_control_requests(workspace: Path) -> list[dict[str, Any]]:
    control_dir = _control_dir(workspace)
    if not control_dir.exists():
        return []
    requests = []
    for path in sorted(control_dir.glob("*.json")):
        payload = _read_json(path)
        if isinstance(payload, dict):
            payload["path"] = str(path)
            requests.append(payload)
    return requests


def _pending_control_requests(workspace: Path) -> list[dict[str, Any]]:
    return [request for request in _load_control_requests(workspace) if request.get("status") == "pending"]


def _parse_control_payload(raw: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _node_workspaces(root: Path) -> list[Path]:
    candidates = []
    if (root / ".metaloop").exists() or (root / "job_envelope.json").exists():
        candidates.append(root)
    if root.exists():
        for child in sorted(root.iterdir()):
            if child.is_dir() and ((child / ".metaloop").exists() or (child / "job_envelope.json").exists()):
                candidates.append(child)
    return candidates


def _summary_node_id(workspace: Path, capsule: Any, envelope: Any) -> str:
    for payload, key in [(envelope, "job_id"), (capsule, "capsule_id"), (capsule, "mission_id")]:
        if isinstance(payload, dict) and isinstance(payload.get(key), str) and payload[key]:
            return payload[key]
    return workspace.name


def _summary_status(capsule: Any, verification: Any, execution: Any) -> str:
    if isinstance(verification, dict) and isinstance(verification.get("status"), str) and verification["status"]:
        return verification["status"]
    if isinstance(execution, dict) and isinstance(execution.get("status"), str) and execution["status"]:
        return execution["status"]
    if isinstance(capsule, dict) and isinstance(capsule.get("current_status"), str) and capsule["current_status"]:
        return capsule["current_status"]
    return "missing"


def _summary_goal(capsule: Any, envelope: Any, adaptive: Any) -> str:
    for payload, keys in [
        (capsule, ["intent", "goal", "objective"]),
        (envelope, ["intent.commander_intent"]),
        (adaptive, ["goal"]),
    ]:
        if not isinstance(payload, dict):
            continue
        for key in keys:
            value = _nested_string(payload, key.split("."))
            if value:
                return value
    return ""


def _latest_adaptive_iteration(adaptive: Any) -> dict[str, Any] | None:
    if not isinstance(adaptive, dict) or not isinstance(adaptive.get("iterations"), list) or not adaptive["iterations"]:
        return None
    latest = adaptive["iterations"][-1]
    return latest if isinstance(latest, dict) else None


def _event_summary(event: Any) -> dict[str, str] | None:
    if not isinstance(event, dict):
        return None
    return {
        "created_at": str(event.get("created_at") or ""),
        "type": str(event.get("type") or ""),
        "agent": str(event.get("agent") or ""),
        "summary": str(event.get("summary") or ""),
    }


def _verification_summary(verification: Any) -> dict[str, Any] | None:
    if not isinstance(verification, dict):
        return None
    return {
        "status": str(verification.get("status") or ""),
        "reason": str(verification.get("reason") or ""),
        "hard_failures": _count_failed(verification.get("hard_validator_results")),
        "manual_blockers": _count_blocking(verification.get("manual_validator_results")),
        "unsupported_blockers": _count_blocking(verification.get("unsupported_validator_results")),
    }


def _summary_waiting_on(verification: Any, pending_controls: list[str]) -> str:
    if pending_controls:
        return "control"
    status = str(verification.get("status") or "") if isinstance(verification, dict) else ""
    if status == "human_acceptance_required":
        return "human_acceptance"
    if status in {"missing_execution_report", "execution_incomplete"}:
        return "execution"
    if status in {"missing_verification_plan", "unsupported_verification_spec", "invalid_capsule"}:
        return "design"
    return ""


def _count_json_files(path: Path) -> int:
    return len(list(path.glob("*.json"))) if path.exists() else 0


def _count_failed(items: Any) -> int:
    return sum(1 for item in items if isinstance(item, dict) and item.get("passed") is False) if isinstance(items, list) else 0


def _count_blocking(items: Any) -> int:
    if not isinstance(items, list):
        return 0
    return sum(1 for item in items if isinstance(item, dict) and item.get("severity") == "blocking" and item.get("passed") is False)


def _nested_string(payload: Any, keys: list[str]) -> str:
    value = payload
    for key in keys:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return value if isinstance(value, str) else ""


def _latest_mtime(paths: list[Path]) -> str:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return ""
    latest = max(existing, key=lambda item: item.stat().st_mtime)
    return datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc).isoformat()


def _activation_result_path(root: Path) -> Path:
    return _metaloop_dir(root) / "activation_result.json"


def _activation_lease_path(workspace: Path) -> Path:
    return _metaloop_dir(workspace) / "activation" / "lease.json"


def _active_activation_lease(workspace: Path, now: datetime) -> dict[str, Any] | None:
    lease = _read_json(_activation_lease_path(workspace))
    if not isinstance(lease, dict) or lease.get("status") != "active":
        return None
    expires_at = _parse_datetime(str(lease.get("expires_at") or ""))
    if expires_at is None or expires_at <= now:
        return None
    return lease


def _write_activation_lease(workspace: Path, candidate: dict[str, Any], *, lease_seconds: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    lease = {
        "schema": ACTIVATION_LEASE_SCHEMA,
        "version": "1.0",
        "lease_id": _new_id("lease"),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=max(1, lease_seconds))).isoformat(),
        "workspace": str(workspace),
        "job_envelope_path": candidate.get("job_envelope_path", ""),
        "envelope_hash": candidate.get("envelope_hash", ""),
        "idempotency_key": candidate.get("idempotency_key", ""),
        "status": "active",
    }
    path = _activation_lease_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lease, indent=2, ensure_ascii=False), encoding="utf-8")
    return lease


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _event_log_path(workspace: Path) -> Path:
    return _metaloop_dir(workspace) / "event_log.jsonl"


def _append_event(workspace: Path, event: dict[str, Any]) -> None:
    _metaloop_dir(workspace).mkdir(parents=True, exist_ok=True)
    with _event_log_path(workspace).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _read_events(workspace: Path) -> tuple[list[dict[str, Any]], list[str]]:
    path = _event_log_path(workspace)
    if not path.exists():
        return [], []
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [f"event_log unreadable: {exc}"]
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"event_log line {index}: invalid JSON: {exc.msg}")
            continue
        event_errors = _validate_event(payload)
        if event_errors:
            errors.extend(f"event_log line {index}: {error}" for error in event_errors)
            continue
        events.append(payload)
    return events, errors


def _validate_event(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["event must be a JSON object"]
    errors = []
    if payload.get("schema") != EVENT_SCHEMA:
        errors.append(f"schema must be {EVENT_SCHEMA}")
    for key in ["version", "event_id", "created_at", "workspace", "type", "summary"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    if payload.get("type") not in EVENT_TYPES:
        errors.append(f"type must be one of {sorted(EVENT_TYPES)}")
    for key in ["capsule_id", "agent", "thread_role", "thread_id", "decision", "next_action"]:
        if not isinstance(payload.get(key, ""), str):
            errors.append(f"{key} must be a string")
    if not isinstance(payload.get("evidence"), list):
        errors.append("evidence must be a list")
    elif not all(isinstance(item, str) for item in payload.get("evidence", [])):
        errors.append("evidence items must be strings")
    return errors


def _thread_id_for_role(workspace: Path, role: str) -> str:
    if not role:
        return ""
    registry = _load_thread_registry(workspace)
    if not isinstance(registry, dict):
        return ""
    agents = registry.get("agents")
    if not isinstance(agents, dict):
        return ""
    agent = agents.get(role)
    if not isinstance(agent, dict):
        return ""
    thread_id = agent.get("thread_id")
    return thread_id if isinstance(thread_id, str) else ""


def _resolve_workspace_path(workspace: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (workspace / path).resolve()


def _route_workspace(workspace: Path, envelope_path: Path) -> dict[str, Any]:
    envelope = _read_json(envelope_path)
    if not isinstance(envelope, dict):
        return {"action": "error", "reason": "Job envelope is missing or invalid JSON."}
    verification = _read_json(_metaloop_dir(workspace) / "verification_result.json")
    adaptive_loop = _load_adaptive_loop(workspace)
    return _route_next_hop(envelope, verification, adaptive_loop)


def _route_next_hop(envelope: dict[str, Any], verification: dict[str, Any] | None, adaptive_loop: dict[str, Any] | None) -> dict[str, Any]:
    envelope_errors = _validate_job_envelope(envelope)
    if envelope_errors:
        return {"action": "error", "reason": "Invalid job envelope.", "errors": envelope_errors}
    if verification is None:
        return {"action": "wait", "reason": "VerificationResult is not available."}
    status = str(verification.get("status") or "")
    decision = _latest_adaptive_decision(adaptive_loop)
    policy = envelope["contract"]["handoff_policy"]
    base = {"verification_status": status, "adaptive_decision": decision}
    if status not in ROUTABLE_VERIFICATION_STATUSES:
        return {**base, "action": "error", "reason": f"Unknown verification status: {status}"}
    if status == "completed_verified":
        return {**base, **_policy_action(policy, "on_success", "Completed verified; dispatching according to policy.")}
    if status == "human_acceptance_required":
        return {**base, **_policy_action(policy, "on_human_acceptance", "Human acceptance is required.")}
    if status in {"missing_execution_report", "execution_incomplete"}:
        return {**base, "action": "wait", "reason": "Execution has not produced a completed report yet."}
    if status in {"missing_verification_plan", "unsupported_verification_spec", "invalid_capsule"}:
        return {**base, **_policy_action(policy, "on_contract_defect", "Contract or verification spec must be redesigned.")}
    if decision == "escalate":
        return {**base, **_policy_action(policy, "on_blocked", "Adaptive loop escalated the node.")}
    if status == "failed" and decision == "repair":
        retry_count = envelope.get("retry_count") if isinstance(envelope.get("retry_count"), int) else 0
        max_retries = policy.get("on_repair", {}).get("max_retries")
        max_retries = max_retries if isinstance(max_retries, int) and max_retries >= 0 else 0
        if retry_count >= max_retries:
            return {**base, **_policy_action(policy, "on_blocked", "Repair retry limit reached.")}
        return {**base, **_policy_action(policy, "on_repair", "Verification failed and the node diagnosed a repair path."), "retry_count_increment": True}
    if status == "failed" and decision in {"redesign", "pivot"}:
        return {**base, **_policy_action(policy, "on_redesign", "Verification failed and the node requires redesign or pivot.")}
    if status == "failed":
        return {**base, "action": "diagnose", "reason": "Verification failed; record adaptive diagnosis before routing."}
    return {**base, "action": "error", "reason": "Unhandled route state."}


def _apply_tick_effects(workspace: Path, envelope: dict[str, Any], route: dict[str, Any]) -> list[dict[str, Any]]:
    action = str(route.get("action") or "")
    if action == "dispatch":
        target = _route_target(route)
        if not target:
            return [_write_tick_marker(workspace, "dispatch_missing_target.json", envelope, route)]
        return [_write_tick_outbox(workspace, target, envelope, route)]
    if action == "loop_back":
        _update_capsule_status(workspace, "repair_required", str(route.get("reason") or "Tick requested repair loop-back."))
        return [_write_tick_marker(workspace, "loop_back_request.json", envelope, route)]
    if action == "route_to":
        _update_capsule_status(workspace, "redesign_required", str(route.get("reason") or "Tick requested redesign or handoff."))
        return [_write_tick_marker(workspace, "route_to_request.json", envelope, route)]
    if action == "escalate":
        _update_capsule_status(workspace, "blocked", str(route.get("reason") or "Tick escalated this node."))
        return [_write_tick_marker(workspace, "blocked.json", envelope, route)]
    if action == "suspend":
        return [_write_tick_marker(workspace, "suspended.json", envelope, route)]
    if action in {"wait", "diagnose", "error"}:
        return [_write_tick_marker(workspace, f"{action}.json", envelope, route)]
    return [_write_tick_marker(workspace, "unknown_route.json", envelope, route)]


def _write_tick_outbox(workspace: Path, target: str, envelope: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    safe_target = re.sub(r"[^A-Za-z0-9_.-]+", "_", target).strip("._-") or "target"
    path = _metaloop_dir(workspace) / "outbox" / f"{safe_target}.json"
    payload = {
        "created_at": _now(),
        "target": target,
        "source_job_id": envelope.get("job_id", ""),
        "route": route,
        "source_envelope": {
            "job_id": envelope.get("job_id", ""),
            "assigned_role": envelope.get("assigned_role", ""),
            "envelope_hash": envelope.get("envelope_hash", ""),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"type": "outbox_written", "target": target, "path": str(path)}


def _write_tick_marker(workspace: Path, filename: str, envelope: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    path = _metaloop_dir(workspace) / filename
    payload = {"created_at": _now(), "source_job_id": envelope.get("job_id", ""), "route": route}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"type": "marker_written", "path": str(path)}


def _append_tick_event(workspace: Path, route: dict[str, Any], effects: list[dict[str, Any]]) -> None:
    action = str(route.get("action") or "error")
    event_type = {
        "dispatch": "handoff",
        "loop_back": "repair",
        "route_to": "redesign",
        "escalate": "blocker",
        "suspend": "decision",
        "diagnose": "observation",
        "wait": "note",
        "error": "blocker",
    }.get(action, "note")
    event = {
        "schema": EVENT_SCHEMA,
        "version": "1.0",
        "event_id": _new_id("event"),
        "created_at": _now(),
        "workspace": str(workspace),
        "capsule_id": _current_capsule_id(workspace),
        "type": event_type,
        "agent": "tick",
        "thread_role": "",
        "thread_id": "",
        "summary": f"Tick action {action}: {route.get('reason') or 'no reason'}",
        "evidence": [str(effect.get("path")) for effect in effects if effect.get("path")],
        "decision": action,
        "next_action": str(_route_target(route) or ""),
    }
    _append_event(workspace, event)


def _load_outbox_items(workspace: Path) -> list[dict[str, Any]]:
    outbox_dir = _metaloop_dir(workspace) / "outbox"
    if not outbox_dir.exists():
        return []
    items = []
    for path in sorted(outbox_dir.glob("*.json")):
        payload = _read_json(path)
        if isinstance(payload, dict):
            payload["__path__"] = str(path)
            items.append(payload)
    return items


def _relay_item(workspace: Path, dispatch_root: Path, item: dict[str, Any], routes: list[dict[str, Any]]) -> dict[str, Any]:
    target = str(item.get("target") or "")
    source_job_id = str(item.get("source_job_id") or "")
    outbox_path_value = str(item.get("__path__") or "")
    base = {"delivery_id": _new_id("delivery"), "created_at": _now(), "source_job_id": source_job_id, "target": target, "outbox_path": outbox_path_value}
    if not target:
        return {**base, "status": "failed", "reason": "Outbox item is missing target."}
    if item.get("delivery_status") == "delivered":
        return {**base, "status": "skipped", "reason": "Outbox item was already delivered."}
    route = _dispatch_route_for_target(routes, target)
    if route is None:
        return {**base, "status": "needs_design", "reason": f"No dispatch route found for target {target}."}
    template_path = _resolve_relative(dispatch_root, route.get("envelope_template"))
    if template_path is None:
        return {**base, "status": "needs_design", "reason": f"No envelope template configured for target {target}."}
    template = _read_json(template_path)
    if not isinstance(template, dict):
        return {**base, "status": "failed", "reason": f"Envelope template is missing or invalid: {template_path}."}
    envelope, envelope_errors = _build_downstream_envelope(template, item, route, dispatch_root, workspace)
    if envelope_errors:
        return {**base, "status": "failed", "reason": "Invalid downstream envelope.", "errors": envelope_errors}
    target_workspace = _resolve_target_workspace(workspace, route.get("workspace"))
    if target_workspace is None:
        return {**base, "status": "failed", "reason": f"Invalid target workspace for target {target}."}
    target_job_path = target_workspace / "job_envelope.json"
    inbox_path = target_workspace / ".metaloop" / "inbox" / f"{source_job_id or target}.json"
    delivery_record_path = _metaloop_dir(workspace) / "relay" / f"{source_job_id or target}_{target}.json"
    target_workspace.mkdir(parents=True, exist_ok=True)
    target_job_path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False), encoding="utf-8")
    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    inbox_path.write_text(
        json.dumps(
            {
                "created_at": _now(),
                "delivery_id": base["delivery_id"],
                "source_job_id": source_job_id,
                "target": target,
                "source_outbox_path": outbox_path_value,
                "target_job_envelope_path": str(target_job_path),
                "envelope_hash": envelope.get("envelope_hash", ""),
                "route": item.get("route", {}),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    delivery = {**base, "status": "delivered", "target_job_envelope_path": str(target_job_path), "inbox_path": str(inbox_path), "delivery_record_path": str(delivery_record_path), "envelope_hash": envelope.get("envelope_hash", "")}
    delivery_record_path.parent.mkdir(parents=True, exist_ok=True)
    delivery_record_path.write_text(json.dumps(delivery, indent=2, ensure_ascii=False), encoding="utf-8")
    if outbox_path_value:
        outbox_path = Path(outbox_path_value)
        updated_item = dict(item)
        updated_item.pop("__path__", None)
        updated_item["delivery_status"] = "delivered"
        updated_item["delivered_at"] = _now()
        updated_item["delivery_id"] = base["delivery_id"]
        updated_item["delivery_path"] = str(delivery_record_path)
        updated_item["target_job_envelope_path"] = str(target_job_path)
        outbox_path.write_text(json.dumps(updated_item, indent=2, ensure_ascii=False), encoding="utf-8")
    return delivery


def _build_downstream_envelope(template: dict[str, Any], item: dict[str, Any], route: dict[str, Any], dispatch_root: Path, source_workspace: Path) -> tuple[dict[str, Any], list[str]]:
    envelope = json.loads(json.dumps(template))
    source_envelope = item.get("source_envelope") if isinstance(item.get("source_envelope"), dict) else {}
    source_job_id = str(item.get("source_job_id") or "")
    envelope["schema"] = envelope.get("schema") or JOB_ENVELOPE_SCHEMA
    envelope["version"] = str(envelope.get("version") or "1.0")
    envelope["job_id"] = str(envelope.get("job_id") or _new_id("job"))
    envelope["parent_job_id"] = source_job_id or envelope.get("parent_job_id")
    envelope["created_at"] = _now()
    envelope["assigned_role"] = str(route.get("role") or route.get("target") or envelope.get("assigned_role") or "")
    envelope["attempt"] = _coerce_nonnegative_int(envelope.get("attempt"), default=1, minimum=1)
    envelope["retry_count"] = _coerce_nonnegative_int(envelope.get("retry_count"), default=0, minimum=0)
    envelope["policy_version"] = str(envelope.get("policy_version") or "1.0")
    envelope.setdefault("intent", {})
    envelope.setdefault("payload", {})
    envelope.setdefault("contract", {})
    if not isinstance(envelope["intent"], dict) or not isinstance(envelope["payload"], dict) or not isinstance(envelope["contract"], dict):
        return envelope, ["intent, payload, and contract must be objects"]
    blackboard_path = _resolve_relative(dispatch_root, route.get("blackboard_path"))
    if blackboard_path is not None:
        if not blackboard_path.exists():
            return envelope, [f"blackboard_path not found: {route.get('blackboard_path')}"]
        envelope["intent"]["global_blackboard_ref"] = str(route.get("blackboard_path"))
        envelope["intent"]["blackboard_hash"] = _sha256_file(blackboard_path)
    envelope["upstream"] = {
        "source_job_id": source_job_id,
        "source_workspace": str(source_workspace),
        "source_outbox_target": str(item.get("target") or ""),
        "source_envelope_hash": str(source_envelope.get("envelope_hash") or ""),
    }
    envelope["envelope_hash"] = _job_envelope_hash(envelope)
    return envelope, _validate_job_envelope(envelope)


def _validate_dispatch_map(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["dispatch_map must be a JSON object"]
    errors = []
    if payload.get("schema") != DISPATCH_MAP_SCHEMA:
        errors.append(f"schema must be {DISPATCH_MAP_SCHEMA}")
    if not isinstance(payload.get("version"), str) or not payload.get("version"):
        errors.append("version must be a non-empty string")
    routes = payload.get("routes")
    if not isinstance(routes, list):
        errors.append("routes must be a list")
        return errors
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            errors.append(f"routes[{index}] must be an object")
            continue
        for key in ["target", "workspace", "role"]:
            if not isinstance(route.get(key), str) or not route.get(key):
                errors.append(f"routes[{index}].{key} must be a non-empty string")
    return errors


def _validate_job_envelope(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["job_envelope must be a JSON object"]
    errors = []
    if payload.get("schema") != JOB_ENVELOPE_SCHEMA:
        errors.append(f"schema must be {JOB_ENVELOPE_SCHEMA}")
    for key in ["version", "job_id", "created_at", "assigned_role", "policy_version", "envelope_hash"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    if not isinstance(payload.get("attempt"), int) or payload.get("attempt", 0) < 1:
        errors.append("attempt must be at least 1")
    if not isinstance(payload.get("retry_count"), int) or payload.get("retry_count", -1) < 0:
        errors.append("retry_count must be a non-negative integer")
    intent = payload.get("intent")
    if not isinstance(intent, dict):
        errors.append("intent must be an object")
    else:
        for key in ["commander_intent", "global_blackboard_ref", "blackboard_hash"]:
            if not isinstance(intent.get(key), str) or not intent.get(key):
                errors.append(f"intent.{key} must be a non-empty string")
    contract = payload.get("contract")
    if not isinstance(contract, dict):
        errors.append("contract must be an object")
    else:
        expected_outputs = contract.get("expected_outputs")
        if not isinstance(expected_outputs, list) or not expected_outputs:
            errors.append("contract.expected_outputs must be a non-empty list")
        policy = contract.get("handoff_policy")
        if not isinstance(policy, dict):
            errors.append("contract.handoff_policy must be an object")
        else:
            for key in ["on_success", "on_repair", "on_redesign", "on_blocked", "on_human_acceptance", "on_contract_defect"]:
                if not isinstance(policy.get(key), dict):
                    errors.append(f"contract.handoff_policy.{key} must be an object")
    if isinstance(payload.get("envelope_hash"), str) and payload.get("envelope_hash") != _job_envelope_hash(payload):
        errors.append("envelope_hash does not match envelope content")
    return errors


def _job_envelope_hash(envelope: dict[str, Any]) -> str:
    return _hash_object(envelope, "envelope_hash")


def _latest_adaptive_decision(state: dict[str, Any] | None) -> str:
    if not isinstance(state, dict) or not isinstance(state.get("iterations"), list) or not state["iterations"]:
        return ""
    latest = state["iterations"][-1]
    if not isinstance(latest, dict):
        return ""
    decision = latest.get("decision")
    return decision if isinstance(decision, str) and decision in ADAPTIVE_DECISIONS else ""


def _policy_action(policy: dict[str, Any], key: str, reason: str) -> dict[str, Any]:
    item = policy.get(key, {})
    action = item.get("action")
    result = {"action": action if action in ROUTE_ACTIONS else "error", "reason": reason}
    for target_key in ["target", "target_role", "next_role", "notify"]:
        if isinstance(item.get(target_key), str) and item[target_key]:
            result[target_key] = item[target_key]
    if isinstance(item.get("max_retries"), int):
        result["max_retries"] = item["max_retries"]
    return result


def _route_target(route: dict[str, Any]) -> str:
    for key in ["target", "target_role", "next_role", "notify"]:
        value = route.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _dispatch_route_for_target(routes: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
    for route in routes:
        if isinstance(route, dict) and str(route.get("target") or "") == target:
            return route
    return None


def _resolve_relative(base: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _resolve_target_workspace(workspace: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (workspace / path).resolve()


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _coerce_nonnegative_int(value: Any, *, default: int, minimum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= minimum else default


def _relay_status(counts: dict[str, int]) -> str:
    if counts.get("failed", 0) > 0:
        return "partial_failed"
    if counts.get("needs_design", 0) > 0 and counts.get("delivered", 0) == 0:
        return "needs_design"
    if counts.get("delivered", 0) > 0 and counts.get("needs_design", 0) == 0:
        return "completed"
    if counts.get("delivered", 0) > 0:
        return "partial"
    return "idle"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _adaptive_loop_path(workspace: Path) -> Path:
    return _metaloop_dir(workspace) / "adaptive_loop.json"


def _load_adaptive_loop(workspace: Path) -> dict[str, Any] | None:
    payload = _read_json(_adaptive_loop_path(workspace))
    return payload if isinstance(payload, dict) else None


def _write_adaptive_loop(workspace: Path, state: dict[str, Any]) -> None:
    _metaloop_dir(workspace).mkdir(parents=True, exist_ok=True)
    _adaptive_loop_path(workspace).write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _validate_adaptive_loop(payload: Any) -> list[str]:
    if payload is None:
        return []
    if not isinstance(payload, dict):
        return ["adaptive_loop.json is not a JSON object"]
    errors = []
    if payload.get("schema") != ADAPTIVE_LOOP_SCHEMA:
        errors.append(f"schema must be {ADAPTIVE_LOOP_SCHEMA}")
    for key in ["version", "loop_id", "created_at", "updated_at", "goal", "status", "current_plan"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    if payload.get("status") not in ADAPTIVE_LOOP_STATUSES:
        errors.append(f"status must be one of {sorted(ADAPTIVE_LOOP_STATUSES)}")
    for key in ["constraints", "success_criteria", "known_facts", "open_questions", "iterations"]:
        if not isinstance(payload.get(key), list):
            errors.append(f"{key} must be a list")
    for index, iteration in enumerate(payload.get("iterations", [])):
        errors.extend(f"iterations[{index}].{error}" for error in _validate_adaptive_iteration(iteration))
    return errors


def _validate_adaptive_iteration(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["iteration must be a JSON object"]
    errors = []
    if payload.get("schema") != ADAPTIVE_ITERATION_SCHEMA:
        errors.append(f"schema must be {ADAPTIVE_ITERATION_SCHEMA}")
    for key in ["version", "iteration_id", "created_at", "goal", "plan", "observation", "evaluation_status", "diagnosis", "decision", "next_plan"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    if payload.get("evaluation_status") not in EVALUATION_STATUSES:
        errors.append(f"evaluation_status must be one of {sorted(EVALUATION_STATUSES)}")
    if payload.get("decision") not in ADAPTIVE_DECISIONS:
        errors.append(f"decision must be one of {sorted(ADAPTIVE_DECISIONS)}")
    if not isinstance(payload.get("evidence"), list):
        errors.append("evidence must be a list")
    elif not all(isinstance(item, str) for item in payload.get("evidence", [])):
        errors.append("evidence items must be strings")
    return errors


def _decide_next(evaluation_status: str, *, diagnosis: str = "", next_plan: str = "") -> str:
    text = f"{diagnosis} {next_plan}".lower()
    if evaluation_status == "satisfied":
        return "complete"
    if evaluation_status == "invalid_goal":
        return "redesign"
    if evaluation_status == "blocked":
        return "escalate" if any(term in text for term in ["permission", "resource", "approval", "gpu", "blocked"]) else "stop"
    if any(term in text for term in ["pivot", "wrong direction", "目标不对", "方向不对"]):
        return "pivot"
    if any(term in text for term in ["contract", "acceptance", "验收", "scope", "目标"]):
        return "redesign"
    if any(term in text for term in ["bug", "regression", "implementation", "修复", "错误"]):
        return "repair"
    return "continue"


def _adaptive_status_after_decision(decision: str) -> str:
    if decision == "complete":
        return "completed"
    if decision == "stop":
        return "stopped"
    if decision == "escalate":
        return "blocked"
    return "active"


def _clean_strings(values: list[str] | tuple[str, ...]) -> list[str]:
    return [item.strip() for item in values if isinstance(item, str) and item.strip()]


def _metaloop_dir(workspace: Path) -> Path:
    return workspace / ".metaloop"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{_now().replace(':', '').replace('.', '')}"


if __name__ == "__main__":
    raise SystemExit(main())
