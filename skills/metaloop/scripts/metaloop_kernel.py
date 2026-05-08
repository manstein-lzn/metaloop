#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CAPSULE_SCHEMA = "metaloop.lightweight_capsule"
EXECUTION_REPORT_SCHEMA = "metaloop.lightweight_execution_report"
VERIFICATION_SPEC_SCHEMA = "metaloop.verification_spec"
VERIFICATION_SCHEMA = "metaloop.lightweight_verification_result"
CAPSULE_STATUSES = {"designed", "running", "executed", "repair_required", "redesign_required", "blocked", "completed"}
GENERIC_VALIDATOR_TYPES = {"file_exists", "command", "forbidden_path", "json_metric_gate"}


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
    design_parser.add_argument("--file-exists", action="append", default=[], help="Hard validator: required file path. Repeatable.")
    design_parser.add_argument(
        "--json-metric-gate",
        action="append",
        default=[],
        help='Hard validator JSON object, e.g. {"path":"summary.json","metric":"score","operator":">=","threshold":0}. Repeatable.',
    )
    design_parser.add_argument(
        "--command",
        action="append",
        default=[],
        dest="validation_commands",
        help="Hard validator command. Repeatable.",
    )
    design_parser.add_argument("--forbidden-path", action="append", default=[], help="Path that must not exist/be modified. Repeatable.")
    design_parser.add_argument("--evidence", action="append", default=[], help="Required evidence note. Repeatable.")
    design_parser.add_argument("--verification-spec", help="Path to a JSON VerificationSpec to lock into the Mission Capsule.")
    design_parser.add_argument(
        "--allow-manual-only",
        action="store_true",
        help="Allow a capsule whose acceptance requires human review and has no hard validators.",
    )
    design_parser.add_argument("--force", action="store_true", help="Overwrite an existing capsule.")

    run_parser = subparsers.add_parser("run", help="Run command(s) around the locked Mission Capsule and write an ExecutionReport.")
    run_parser.add_argument(
        "--command",
        action="append",
        required=True,
        dest="run_commands",
        help="Command to run from the workspace. Repeatable.",
    )
    run_parser.add_argument("--evidence", action="append", default=[], help="Evidence note produced during execution. Repeatable.")
    run_parser.add_argument("--timeout", type=int, default=600, help="Timeout per command in seconds.")
    run_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    verify_parser = subparsers.add_parser("verify", help="Verify the current lightweight Mission Capsule.")
    verify_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    mark_parser = subparsers.add_parser("mark", help="Mark capsule status without mutating locked contract fields.")
    mark_parser.add_argument(
        "--status",
        required=True,
        choices=sorted(CAPSULE_STATUSES),
    )
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
    if capsule_path.exists() and not args.force:
        print(f"capsule_exists: {capsule_path}", file=sys.stderr)
        print("Use --force only after explicit user confirmation.", file=sys.stderr)
        return 1
    verification_spec, spec_errors = _build_verification_spec(workspace, args)
    errors = [*spec_errors, *_validate_design_input(args, verification_spec)]
    if errors:
        print("design_invalid:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    root.mkdir(parents=True, exist_ok=True)
    capsule = _build_capsule(workspace, args, verification_spec)
    capsule_path.write_text(json.dumps(capsule, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"capsule: {capsule_path}")
    print("status: designed")
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
        "status": "completed" if completed else "failed",
        "commands": command_results,
        "evidence": args.evidence,
    }
    _metaloop_dir(workspace).mkdir(parents=True, exist_ok=True)
    (_metaloop_dir(workspace) / "execution_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _update_capsule_status(
        workspace,
        "executed" if completed else "blocked",
        "ExecutionReport written by lightweight skill kernel.",
    )
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
        )
        _write_verification_result(workspace, result)
        return _print_verification(result, as_json=as_json, exit_code=1)
    if execution_report.get("status") != "completed":
        result = _verification_result("execution_incomplete", "ExecutionReport is not completed.", [], [], errors=execution_errors)
        _write_verification_result(workspace, result)
        return _print_verification(result, as_json=as_json, exit_code=1)

    spec_errors = _validate_verification_spec(capsule.get("verification_spec"))
    if spec_errors:
        result = _verification_result("invalid_verification_spec", "VerificationSpec is invalid.", [], [], errors=spec_errors)
        _write_verification_result(workspace, result)
        return _print_verification(result, as_json=as_json, exit_code=1)

    hard_results, forbidden_results = _run_verification_spec(workspace, capsule["verification_spec"])
    all_results = [*hard_results, *forbidden_results]
    manual_acceptance = [item for item in capsule.get("acceptance_criteria", []) if item.get("type") == "manual"]
    passed = bool(all_results) and all(result["passed"] for result in all_results)
    if not all_results:
        status = "missing_verification_plan"
        reason = "No hard validators found; add command, file, or forbidden-path checks before automated completion."
    elif passed and manual_acceptance:
        status = "human_acceptance_required"
        reason = "Automated validators passed, but manual acceptance criteria still require human review."
    elif passed:
        status = "completed_verified"
        reason = "All hard validators passed."
    else:
        status = "failed"
        reason = "One or more hard validators failed."
    result = _verification_result(
        status,
        reason,
        hard_results,
        forbidden_results,
        execution_report_status=execution_report.get("status"),
        verification_spec_domain=capsule["verification_spec"].get("domain"),
        extension_hash=capsule["verification_spec"].get("extension_hash"),
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


def _build_capsule(workspace: Path, args: argparse.Namespace, verification_spec: dict[str, Any]) -> dict[str, Any]:
    acceptance = []
    for text in args.acceptance:
        acceptance.append({"type": "manual", "description": text})
    for path in args.file_exists:
        acceptance.append({"type": "file_exists", "description": f"{path} exists", "target": path})
    for command in args.validation_commands:
        acceptance.append({"type": "command", "description": f"Command succeeds: {command}", "command": command})
    for gate in verification_spec.get("validators", []):
        if gate.get("type") == "json_metric_gate":
            acceptance.append({"type": "json_metric_gate", "description": _describe_json_metric_gate(gate), "gate": gate})
    return {
        "schema": CAPSULE_SCHEMA,
        "version": "1.0",
        "capsule_id": _new_id("capsule"),
        "created_at": _now(),
        "updated_at": _now(),
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
        "verification_spec": verification_spec,
        "verification_plan": {"hard_validators": _legacy_hard_validators(verification_spec)},
        "current_status": "designed",
        "status_history": [{"status": "designed", "reason": "Capsule locked by lightweight kernel.", "at": _now()}],
    }


def _run_validator(workspace: Path, validator: dict[str, Any]) -> dict[str, Any]:
    validator_type = validator.get("type")
    if validator_type == "file_exists":
        target = str(validator.get("path") or validator.get("target") or "")
        exists = bool(target) and (workspace / target).exists()
        return {"type": "file_exists", "target": target, "passed": exists, "message": "exists" if exists else "missing"}
    if validator_type == "command":
        command = str(validator.get("command") or "")
        if not command:
            return {"type": "command", "command": command, "passed": False, "message": "empty command"}
        return {"type": "command", **_run_command(workspace, command, timeout=120)}
    if validator_type == "forbidden_path":
        target = str(validator.get("path") or validator.get("target") or "")
        exists = bool(target) and (workspace / target).exists()
        return {"type": "forbidden_path", "target": target, "passed": not exists, "message": "absent" if not exists else "forbidden path exists"}
    if validator_type == "json_metric_gate":
        return _run_json_metric_gate(workspace, validator)
    return {"type": str(validator_type), "passed": False, "message": "unknown validator"}


def _run_verification_spec(workspace: Path, spec: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hard_results = []
    forbidden_results = []
    for validator in spec.get("validators", []):
        result = _run_validator(workspace, validator)
        if validator.get("type") == "forbidden_path":
            forbidden_results.append(result)
        else:
            hard_results.append(result)
    return hard_results, forbidden_results


def _run_json_metric_gate(workspace: Path, validator: dict[str, Any]) -> dict[str, Any]:
    path = str(validator.get("path") or "")
    metric = str(validator.get("metric") or "")
    operator = str(validator.get("operator") or "")
    threshold = validator.get("threshold")
    payload = _read_json(workspace / path)
    if not isinstance(payload, dict):
        return {"type": "json_metric_gate", "path": path, "metric": metric, "passed": False, "message": "JSON artifact missing or invalid"}
    found, value = _lookup_metric(payload, metric)
    if not found:
        return {"type": "json_metric_gate", "path": path, "metric": metric, "passed": False, "message": "metric missing"}
    try:
        passed = _compare_metric(value, operator, threshold)
    except (TypeError, ValueError):
        return {
            "type": "json_metric_gate",
            "path": path,
            "metric": metric,
            "operator": operator,
            "threshold": threshold,
            "actual": value,
            "passed": False,
            "message": "metric comparison failed",
        }
    return {
        "type": "json_metric_gate",
        "path": path,
        "metric": metric,
        "operator": operator,
        "threshold": threshold,
        "actual": value,
        "passed": passed,
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
    verification_spec_domain: str | None = None,
    extension_hash: str | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema": VERIFICATION_SCHEMA,
        "version": "1.0",
        "created_at": _now(),
        "status": status,
        "reason": reason,
        "execution_report_status": execution_report_status,
        "verification_spec_domain": verification_spec_domain,
        "extension_hash": extension_hash,
        "errors": errors or [],
        "hard_validator_results": hard_results,
        "forbidden_path_results": forbidden_results,
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


def _build_verification_spec(workspace: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    errors = []
    if args.verification_spec:
        payload = _read_json(Path(args.verification_spec).expanduser())
        if not isinstance(payload, dict):
            return {}, ["--verification-spec must point to a JSON object"]
        payload.setdefault("schema", VERIFICATION_SPEC_SCHEMA)
        payload.setdefault("version", "1.0")
        payload.setdefault("domain", "generic")
        payload.setdefault("extension", "generic")
        payload.setdefault("extension_version", "1.0")
        payload.setdefault("validators", [])
        payload.setdefault("evidence_requirements", [])
        payload.setdefault("resource_gates", [])
        payload["extension_hash"] = _extension_hash(payload)
        return payload, _validate_verification_spec(payload)

    spec = {
        "schema": VERIFICATION_SPEC_SCHEMA,
        "version": "1.0",
        "domain": "generic",
        "extension": "generic",
        "extension_version": "1.0",
        "validators": [],
        "evidence_requirements": args.evidence,
        "resource_gates": [],
    }
    for path in args.file_exists:
        spec["validators"].append({"type": "file_exists", "path": path})
    for command in args.validation_commands:
        spec["validators"].append({"type": "command", "command": command})
    for path in args.forbidden_path:
        spec["validators"].append({"type": "forbidden_path", "path": path})
    for raw_gate in args.json_metric_gate:
        try:
            gate = json.loads(raw_gate)
        except json.JSONDecodeError:
            errors.append("--json-metric-gate must be valid JSON")
            continue
        if not isinstance(gate, dict):
            errors.append("--json-metric-gate must be a JSON object")
            continue
        gate["type"] = "json_metric_gate"
        spec["validators"].append(gate)
    spec["extension_hash"] = _extension_hash(spec)
    return spec, [*errors, *_validate_verification_spec(spec)]


def _validate_design_input(args: argparse.Namespace, verification_spec: dict[str, Any]) -> list[str]:
    errors = []
    if not args.intent.strip():
        errors.append("intent is required")
    if not args.rationale:
        errors.append("at least one --rationale is required before locking a Mission Capsule")
    if not args.non_goal:
        errors.append("at least one --non-goal is required before locking a Mission Capsule")
    validators = verification_spec.get("validators", []) if isinstance(verification_spec, dict) else []
    if not (args.acceptance or validators):
        errors.append("at least one acceptance criterion is required")
    has_hard_verification = bool(validators)
    if not has_hard_verification and not args.allow_manual_only:
        errors.append("at least one hard validator is required, or pass --allow-manual-only explicitly")
    return errors


def _validate_capsule(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["mission_capsule.json is missing or is not a JSON object"]
    errors = []
    if payload.get("schema") != CAPSULE_SCHEMA:
        errors.append(f"schema must be {CAPSULE_SCHEMA}")
    for key in ["version", "capsule_id", "created_at", "updated_at", "workspace", "intent", "current_status"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    if payload.get("locked") is not True:
        errors.append("locked must be true")
    if payload.get("current_status") not in CAPSULE_STATUSES:
        errors.append("current_status is not a known capsule status")
    for key in ["context", "design_rationale", "constraints", "non_goals", "acceptance_criteria", "forbidden_paths", "evidence_requirements", "status_history"]:
        if not isinstance(payload.get(key), list):
            errors.append(f"{key} must be a list")
    errors.extend(_validate_verification_spec(payload.get("verification_spec")))
    return errors


def _validate_verification_spec(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["verification_spec must be an object"]
    errors = []
    if payload.get("schema") != VERIFICATION_SPEC_SCHEMA:
        errors.append(f"verification_spec.schema must be {VERIFICATION_SPEC_SCHEMA}")
    for key in ["version", "domain", "extension", "extension_version", "extension_hash"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"verification_spec.{key} must be a non-empty string")
    if payload.get("domain") != "generic" or payload.get("extension") != "generic":
        errors.append("only the bundled generic extension is supported by this kernel version")
    if isinstance(payload.get("extension_hash"), str) and payload.get("extension_hash") != _extension_hash(payload):
        errors.append("verification_spec.extension_hash does not match locked spec content")
    validators = payload.get("validators")
    if not isinstance(validators, list):
        errors.append("verification_spec.validators must be a list")
        return errors
    for index, validator in enumerate(validators):
        if not isinstance(validator, dict):
            errors.append(f"verification_spec.validators[{index}] must be an object")
            continue
        validator_type = validator.get("type")
        if validator_type not in GENERIC_VALIDATOR_TYPES:
            errors.append(f"verification_spec.validators[{index}].type is unsupported")
            continue
        if validator_type == "file_exists" and not isinstance(validator.get("path"), str):
            errors.append(f"verification_spec.validators[{index}].path must be a string")
        if validator_type == "forbidden_path" and not isinstance(validator.get("path"), str):
            errors.append(f"verification_spec.validators[{index}].path must be a string")
        if validator_type == "command" and not isinstance(validator.get("command"), str):
            errors.append(f"verification_spec.validators[{index}].command must be a string")
        if validator_type == "json_metric_gate":
            errors.extend(_validate_json_metric_gate(validator, index))
    for key in ["evidence_requirements", "resource_gates"]:
        if not isinstance(payload.get(key), list):
            errors.append(f"verification_spec.{key} must be a list")
    return errors


def _validate_json_metric_gate(validator: dict[str, Any], index: int) -> list[str]:
    errors = []
    if not isinstance(validator.get("path"), str):
        errors.append(f"verification_spec.validators[{index}].path must be a string")
    if not isinstance(validator.get("metric"), str):
        errors.append(f"verification_spec.validators[{index}].metric must be a string")
    if validator.get("operator") not in {">", ">=", "<", "<=", "==", "!="}:
        errors.append(f"verification_spec.validators[{index}].operator is unsupported")
    if "threshold" not in validator:
        errors.append(f"verification_spec.validators[{index}].threshold is required")
    return errors


def _validate_execution_report(payload: Any, capsule: dict[str, Any]) -> list[str]:
    if not isinstance(payload, dict):
        return ["execution_report.json is missing or is not a JSON object"]
    errors = []
    if payload.get("schema") != EXECUTION_REPORT_SCHEMA:
        errors.append(f"schema must be {EXECUTION_REPORT_SCHEMA}")
    if payload.get("capsule_id") != capsule.get("capsule_id"):
        errors.append("execution_report capsule_id does not match Mission Capsule")
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
        validator_type = validator.get("type")
        if validator_type == "file_exists":
            validators.append({"type": "file_exists", "target": validator.get("path", "")})
        elif validator_type == "command":
            validators.append({"type": "command", "command": validator.get("command", "")})
        elif validator_type == "json_metric_gate":
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


def _extension_hash(spec: dict[str, Any]) -> str:
    normalized = dict(spec)
    normalized.pop("extension_hash", None)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


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
