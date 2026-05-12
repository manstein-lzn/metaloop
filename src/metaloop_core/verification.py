from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from metaloop_core.capsule import load_valid_capsule, update_capsule_status
from metaloop_core.execution import load_valid_execution_report
from metaloop_core.ids import utc_now
from metaloop_core.schemas import VERIFICATION_SCHEMA
from metaloop_core.specs import validator_mode, validator_severity
from metaloop_core.validators import run_validator


@dataclass(frozen=True)
class VerificationSummary:
    status: str
    reason: str
    hard_failures: int
    manual_blockers: int
    review_blockers: int
    human_authority_blockers: int
    unsupported_blockers: int

    @property
    def completed_verified(self) -> bool:
        return self.status == "completed_verified"


def load_verification_summary(workspace: str | Path = ".") -> VerificationSummary | None:
    path = Path(workspace).expanduser().resolve() / ".metaloop" / "verification_result.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return summarize_verification_result(payload)


def summarize_verification_result(payload: dict[str, Any]) -> VerificationSummary:
    hard_results = payload.get("hard_validator_results", [])
    forbidden_results = payload.get("forbidden_path_results", [])
    manual_results = payload.get("manual_validator_results", [])
    unsupported_results = payload.get("unsupported_validator_results", [])
    executable = [*hard_results, *forbidden_results]
    return VerificationSummary(
        status=str(payload.get("status") or ""),
        reason=str(payload.get("reason") or ""),
        hard_failures=sum(1 for item in executable if isinstance(item, dict) and item.get("severity", "blocking") == "blocking" and not item.get("passed")),
        manual_blockers=sum(1 for item in manual_results if isinstance(item, dict) and item.get("severity", "blocking") == "blocking"),
        review_blockers=sum(1 for item in manual_results if isinstance(item, dict) and item.get("severity", "blocking") == "blocking" and not _requires_human_authority(item)),
        human_authority_blockers=sum(1 for item in manual_results if isinstance(item, dict) and item.get("severity", "blocking") == "blocking" and _requires_human_authority(item)),
        unsupported_blockers=sum(1 for item in unsupported_results if isinstance(item, dict) and item.get("severity", "blocking") == "blocking"),
    )


def verify_workspace(workspace: str | Path = ".", *, write: bool = True, update_status: bool = True) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    capsule, capsule_errors = load_valid_capsule(root)
    if capsule is None:
        result = verification_result("invalid_capsule", "No valid Mission Capsule found.", [], [], errors=capsule_errors)
        if write:
            write_verification_result(root, result)
        return result

    execution_report, execution_errors = load_valid_execution_report(root, capsule)
    if execution_report is None:
        result = verification_result(
            "missing_execution_report",
            "No valid ExecutionReport found; run before verification.",
            [],
            [],
            errors=execution_errors,
            capsule=capsule,
        )
        if write:
            write_verification_result(root, result)
        return result
    if execution_report.get("status") != "completed":
        result = verification_result("execution_incomplete", "ExecutionReport is not completed.", [], [], errors=execution_errors, capsule=capsule)
        if write:
            write_verification_result(root, result)
        return result

    hard_results, forbidden_results, manual_results, unsupported_results, warnings = run_verification_spec(root, capsule.get("verification_spec", {}))
    executable_results = [*hard_results, *forbidden_results]
    blocking_failures = [item for item in executable_results if item.get("severity") == "blocking" and not item.get("passed")]
    blocking_manual = [item for item in manual_results if item.get("severity") == "blocking"]
    human_authority_blockers = [item for item in blocking_manual if _requires_human_authority(item)]
    review_blockers = [item for item in blocking_manual if not _requires_human_authority(item)]
    blocking_unsupported = [item for item in unsupported_results if item.get("severity") == "blocking"]
    review = capsule.get("verification_review", {})
    if isinstance(review, dict) and review.get("known_gaps"):
        warnings.extend({"type": "known_gap", "message": item} for item in review["known_gaps"])

    if blocking_failures:
        status = "failed"
        reason = "One or more executable blocking validators failed."
    elif blocking_unsupported:
        status = "unsupported_verification_spec"
        reason = "One or more blocking validators require unsupported verification."
    elif human_authority_blockers:
        status = "human_acceptance_required"
        reason = "One or more blocking validators require user authority."
    elif review_blockers:
        status = "review_required"
        reason = "One or more blocking validators require independent reviewer judgment."
    elif not executable_results:
        status = "missing_verification_plan"
        reason = "No executable validators found; add executable checks before automated completion."
    else:
        status = "completed_verified"
        reason = "All executable blocking validators passed."

    result = verification_result(
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
    if write:
        write_verification_result(root, result)
    if update_status and status == "completed_verified":
        update_capsule_status(root, "completed", reason)
    return result


def run_verification_spec(
    workspace: str | Path,
    spec: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    hard_results: list[dict[str, Any]] = []
    forbidden_results: list[dict[str, Any]] = []
    manual_results: list[dict[str, Any]] = []
    unsupported_results: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for validator in spec.get("validators", []):
        mode = validator_mode(validator)
        severity = validator_severity(validator)
        validator_type = str(validator.get("type") or "")
        if mode == "manual":
            result = manual_result(validator, "manual validator requires independent review")
            (warnings if severity == "advisory" else manual_results).append(result)
            continue
        if mode == "unsupported":
            result = unsupported_result(validator, "validator is locked but unsupported by this kernel")
            (warnings if severity == "advisory" else unsupported_results).append(result)
            continue
        result = run_validator(workspace, validator)
        if severity == "advisory":
            if not result.get("passed"):
                warnings.append(result)
            continue
        if validator_type == "forbidden_path":
            forbidden_results.append(result)
        else:
            hard_results.append(result)
    for gate in spec.get("resource_gates", []):
        result = resource_gate_result(gate)
        if result["severity"] == "advisory":
            warnings.append(result)
        else:
            manual_results.append(result)
    return hard_results, forbidden_results, manual_results, unsupported_results, warnings


def verification_result(
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
        "created_at": utc_now(),
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


def write_verification_result(workspace: str | Path, result: dict[str, Any]) -> Path:
    path = Path(workspace).expanduser().resolve() / ".metaloop" / "verification_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def manual_result(validator: dict[str, Any], message: str) -> dict[str, Any]:
    authority = _manual_authority(validator)
    return {
        "type": validator.get("type"),
        "mode": validator_mode(validator),
        "severity": validator_severity(validator),
        "authority": authority,
        "delegable": authority != "user",
        "reviewer": "user" if authority == "user" else str(validator.get("reviewer") or "codex_reviewer"),
        "requires_user_confirmation": authority == "user",
        "passed": False,
        "message": message,
        "description": validator.get("description", ""),
    }


def unsupported_result(validator: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "type": validator.get("type"),
        "mode": validator_mode(validator),
        "severity": validator_severity(validator),
        "passed": False,
        "message": message,
        "description": validator.get("description", ""),
    }


def resource_gate_result(gate: dict[str, Any]) -> dict[str, Any]:
    requires_user_confirmation = bool(gate.get("requires_user_confirmation", True))
    return {
        "type": "resource_gate",
        "mode": validator_mode(gate, default="manual"),
        "severity": validator_severity(gate),
        "authority": "user" if requires_user_confirmation else "reviewer",
        "delegable": not requires_user_confirmation,
        "reviewer": "user" if requires_user_confirmation else str(gate.get("reviewer") or "codex_reviewer"),
        "resource": gate.get("resource", ""),
        "requires_user_confirmation": requires_user_confirmation,
        "passed": False,
        "message": gate.get("reason") or "resource gate requires confirmation",
    }


def _manual_authority(validator: dict[str, Any]) -> str:
    if bool(validator.get("requires_user_confirmation", False)):
        return "user"
    if str(validator.get("authority") or "").lower() == "user":
        return "user"
    if str(validator.get("reviewer") or "").lower() in {"user", "human", "human_operator"}:
        return "user"
    if validator.get("delegable") is False:
        return "user"
    return "reviewer"


def _requires_human_authority(result: dict[str, Any]) -> bool:
    if bool(result.get("requires_user_confirmation", False)):
        return True
    if str(result.get("authority") or "").lower() == "user":
        return True
    if str(result.get("reviewer") or "").lower() in {"user", "human", "human_operator"}:
        return True
    return result.get("delegable") is False
