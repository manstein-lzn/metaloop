#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CAPSULE_SCHEMA = "metaloop.lightweight_capsule"
VERIFICATION_SCHEMA = "metaloop.lightweight_verification_result"


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
        "--command",
        action="append",
        default=[],
        dest="validation_commands",
        help="Hard validator command. Repeatable.",
    )
    design_parser.add_argument("--forbidden-path", action="append", default=[], help="Path that must not exist/be modified. Repeatable.")
    design_parser.add_argument("--evidence", action="append", default=[], help="Required evidence note. Repeatable.")
    design_parser.add_argument("--force", action="store_true", help="Overwrite an existing capsule.")

    verify_parser = subparsers.add_parser("verify", help="Verify the current lightweight Mission Capsule.")
    verify_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    mark_parser = subparsers.add_parser("mark", help="Mark capsule status without mutating locked contract fields.")
    mark_parser.add_argument(
        "--status",
        required=True,
        choices=["designed", "running", "repair_required", "redesign_required", "blocked", "completed"],
    )
    mark_parser.add_argument("--reason", default="", help="Reason for status transition.")

    args = parser.parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    if args.command == "status":
        return _status(workspace, as_json=args.json)
    if args.command == "design":
        return _design(workspace, args)
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
    root.mkdir(parents=True, exist_ok=True)
    capsule = _build_capsule(workspace, args)
    capsule_path.write_text(json.dumps(capsule, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"capsule: {capsule_path}")
    print("status: designed")
    return 0


def _verify(workspace: Path, *, as_json: bool) -> int:
    capsule = _load_capsule(workspace)
    if capsule is None:
        result = _verification_result("missing", "No Mission Capsule found.", [], [])
        return _print_verification(result, as_json=as_json, exit_code=1)

    hard_results = []
    for validator in capsule.get("verification_plan", {}).get("hard_validators", []):
        hard_results.append(_run_validator(workspace, validator))
    forbidden_results = []
    for item in capsule.get("forbidden_paths", []):
        path = workspace / item
        forbidden_results.append(
            {
                "type": "forbidden_path",
                "target": item,
                "passed": not path.exists(),
                "message": "absent" if not path.exists() else "forbidden path exists",
            }
        )
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
    result = _verification_result(status, reason, hard_results, forbidden_results)
    _metaloop_dir(workspace).mkdir(parents=True, exist_ok=True)
    (_metaloop_dir(workspace) / "verification_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if status == "completed_verified":
        _update_capsule_status(workspace, "completed", reason)
    return _print_verification(result, as_json=as_json, exit_code=0 if status == "completed_verified" else 1)


def _mark(workspace: Path, status: str, reason: str) -> int:
    capsule = _load_capsule(workspace)
    if capsule is None:
        print("No Mission Capsule found.", file=sys.stderr)
        return 1
    _update_capsule_status(workspace, status, reason)
    print(f"status: {status}")
    if reason:
        print(f"reason: {reason}")
    return 0


def _build_capsule(workspace: Path, args: argparse.Namespace) -> dict[str, Any]:
    acceptance = []
    hard_validators = []
    for text in args.acceptance:
        acceptance.append({"type": "manual", "description": text})
    for path in args.file_exists:
        acceptance.append({"type": "file_exists", "description": f"{path} exists", "target": path})
        hard_validators.append({"type": "file_exists", "target": path})
    for command in args.validation_commands:
        acceptance.append({"type": "command", "description": f"Command succeeds: {command}", "command": command})
        hard_validators.append({"type": "command", "command": command})
    return {
        "schema": CAPSULE_SCHEMA,
        "version": "1.0",
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
        "verification_plan": {"hard_validators": hard_validators},
        "current_status": "designed",
        "status_history": [{"status": "designed", "reason": "Capsule locked by lightweight kernel.", "at": _now()}],
    }


def _run_validator(workspace: Path, validator: dict[str, Any]) -> dict[str, Any]:
    validator_type = validator.get("type")
    if validator_type == "file_exists":
        target = str(validator.get("target") or "")
        exists = bool(target) and (workspace / target).exists()
        return {"type": "file_exists", "target": target, "passed": exists, "message": "exists" if exists else "missing"}
    if validator_type == "command":
        command = str(validator.get("command") or "")
        if not command:
            return {"type": "command", "command": command, "passed": False, "message": "empty command"}
        completed = subprocess.run(command, cwd=workspace, shell=True, text=True, capture_output=True, timeout=120, check=False)
        return {
            "type": "command",
            "command": command,
            "passed": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    return {"type": str(validator_type), "passed": False, "message": "unknown validator"}


def _read_status(workspace: Path) -> dict[str, Any]:
    capsule_path = _metaloop_dir(workspace) / "mission_capsule.json"
    verification_path = _metaloop_dir(workspace) / "verification_result.json"
    capsule = _read_json(capsule_path)
    verification = _read_json(verification_path)
    capsule_state = {"state": "missing", "path": None, "current_status": None}
    if isinstance(capsule, dict):
        capsule_state = {
            "state": "ready",
            "path": str(capsule_path),
            "current_status": capsule.get("current_status"),
            "locked": capsule.get("locked", False),
            "intent": capsule.get("intent", ""),
        }
    verification_state = {"state": "missing", "path": None, "status": None}
    if isinstance(verification, dict):
        verification_state = {"state": "ready", "path": str(verification_path), "status": verification.get("status")}
    status = {"workspace": str(workspace), "capsule": capsule_state, "verification": verification_state}
    status["next_action"] = _next_action(status)
    return status


def _next_action(status: dict[str, Any]) -> str:
    capsule_status = status["capsule"].get("current_status")
    verification_status = status["verification"].get("status")
    if status["capsule"]["state"] == "missing":
        return "Run design before execution."
    if capsule_status == "redesign_required":
        return "Collect user feedback and revise the Mission Capsule."
    if verification_status == "missing_verification_plan":
        return "Add executable validators before claiming automated completion."
    if verification_status == "human_acceptance_required":
        return "Ask the user for manual acceptance or revise acceptance criteria."
    if verification_status == "completed_verified":
        return "Complete or ask for final human acceptance."
    if verification_status == "failed":
        return "Classify as repair or redesign before continuing."
    return "Execute with Codex around the locked Mission Capsule, then verify."


def _verification_result(status: str, reason: str, hard_results: list[dict[str, Any]], forbidden_results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": VERIFICATION_SCHEMA,
        "version": "1.0",
        "created_at": _now(),
        "status": status,
        "reason": reason,
        "hard_validator_results": hard_results,
        "forbidden_path_results": forbidden_results,
    }


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


if __name__ == "__main__":
    raise SystemExit(main())
