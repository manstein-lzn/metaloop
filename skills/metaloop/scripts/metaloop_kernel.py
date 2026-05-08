#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CAPSULE_SCHEMA = "metaloop.lightweight_capsule"
EXECUTION_REPORT_SCHEMA = "metaloop.lightweight_execution_report"
EXTENSION_SPEC_SCHEMA = "metaloop.extension_spec"
VERIFICATION_SPEC_SCHEMA = "metaloop.verification_spec"
VERIFICATION_SCHEMA = "metaloop.lightweight_verification_result"

CAPSULE_STATUSES = {"designed", "running", "executed", "repair_required", "redesign_required", "blocked", "completed"}
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lightweight MetaLoop kernel bundled inside the Codex skill.")
    parser.add_argument("--workspace", default=".", help="Workspace root to govern.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Inspect lightweight MetaLoop state.")
    status_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

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

    args = parser.parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    if args.command == "status":
        return _status(workspace, as_json=args.json)
    if args.command == "design":
        return _design(workspace, args)
    if args.command == "run":
        return _run(workspace, args)
    if args.command == "verify":
        return _verify(workspace, as_json=args.json)
    if args.command == "mark":
        return _mark(workspace, args.status, args.reason)
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
    print(f"next_action: {status['next_action']}")
    return 0


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


def _read_status(workspace: Path) -> dict[str, Any]:
    capsule_path = _metaloop_dir(workspace) / "mission_capsule.json"
    execution_path = _metaloop_dir(workspace) / "execution_report.json"
    verification_path = _metaloop_dir(workspace) / "verification_result.json"
    capsule = _read_json(capsule_path)
    execution = _read_json(execution_path)
    verification = _read_json(verification_path)
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
    execution_state = {"state": "missing", "path": None, "status": None}
    if isinstance(execution, dict):
        execution_state = {"state": "ready", "path": str(execution_path), "status": execution.get("status")}
    verification_state = {"state": "missing", "path": None, "status": None}
    if isinstance(verification, dict):
        verification_state = {"state": "ready", "path": str(verification_path), "status": verification.get("status")}
    status = {"workspace": str(workspace), "capsule": capsule_state, "execution": execution_state, "verification": verification_state}
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


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _metaloop_dir(workspace: Path) -> Path:
    return workspace / ".metaloop"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{_now().replace(':', '').replace('.', '')}"


if __name__ == "__main__":
    raise SystemExit(main())
