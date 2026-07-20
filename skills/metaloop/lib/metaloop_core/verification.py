from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from metaloop_core.capsule import load_valid_capsule, update_capsule_status
from metaloop_core.execution import load_execution_report, load_valid_execution_report
from metaloop_core.ids import new_id, utc_now
from metaloop_core.schemas import REVIEW_RESULT_SCHEMA, VERIFICATION_SCHEMA
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
    review_result, review_errors = load_review_result(root, capsule, execution_report)
    review = capsule.get("verification_review", {})
    if isinstance(review, dict) and review.get("known_gaps"):
        warnings.extend({"type": "known_gap", "message": item} for item in review["known_gaps"])
    if review_errors:
        warnings.extend({"type": "review_result_invalid", "message": item} for item in review_errors)

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
        decision = str(review_result.get("decision") or "") if isinstance(review_result, dict) and not review_errors else ""
        if decision == "approved":
            status = "completed_verified"
            reason = "Executable validators passed and independent reviewer gates were approved."
        elif decision in {"rejected", "needs_changes"}:
            status = "failed"
            reason = "Independent reviewer rejected the evidence or requested changes."
        else:
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
        execution_report=execution_report,
        manual_results=manual_results,
        unsupported_results=unsupported_results,
        warnings=warnings,
        capsule=capsule,
        review_result=review_result if isinstance(review_result, dict) and not review_errors else None,
        review_errors=review_errors,
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
    execution_report: dict[str, Any] | None = None,
    manual_results: list[dict[str, Any]] | None = None,
    unsupported_results: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    errors: list[str] | None = None,
    capsule: dict[str, Any] | None = None,
    review_result: dict[str, Any] | None = None,
    review_errors: list[str] | None = None,
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
        "execution_id": execution_report.get("execution_id") if execution_report else None,
        "execution_hash": execution_report.get("execution_hash") if execution_report else None,
        "extension_domain": extension_spec.get("domain"),
        "extension_hash": extension_spec.get("extension_hash"),
        "verification_spec_domain": verification_spec.get("domain"),
        "verification_spec_hash": verification_spec.get("spec_hash"),
        "errors": errors or [],
        "warnings": warnings or [],
        "review_result": _review_result_summary(review_result),
        "review_result_errors": review_errors or [],
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


def review_result_path(workspace: str | Path = ".") -> Path:
    return Path(workspace).expanduser().resolve() / ".metaloop" / "review_result.json"


def build_review_result(
    *,
    workspace: str | Path,
    capsule: dict[str, Any],
    decision: str,
    reviewer: str,
    reviewer_role: str = "reviewer",
    evidence: list[str] | None = None,
    notes: str = "",
    execution_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verification_spec = capsule.get("verification_spec", {}) if isinstance(capsule.get("verification_spec"), dict) else {}
    report = execution_report or load_execution_report(workspace)
    return {
        "schema": REVIEW_RESULT_SCHEMA,
        "version": "1.0",
        "review_id": new_id("review"),
        "created_at": utc_now(),
        "workspace": str(Path(workspace).expanduser().resolve()),
        "capsule_id": capsule.get("capsule_id"),
        "capsule_revision": capsule.get("revision"),
        "verification_spec_hash": verification_spec.get("spec_hash"),
        "execution_id": report.get("execution_id") if isinstance(report, dict) else None,
        "execution_hash": report.get("execution_hash") if isinstance(report, dict) else None,
        "decision": decision,
        "reviewer": reviewer,
        "reviewer_role": reviewer_role,
        "evidence": list(evidence or []),
        "notes": notes,
    }


def write_review_result(workspace: str | Path, result: dict[str, Any]) -> Path:
    path = review_result_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_review_result(
    workspace: str | Path,
    capsule: dict[str, Any] | None = None,
    execution_report: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    path = review_result_path(workspace)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return None, []
    except json.JSONDecodeError as exc:
        return None, [f"review_result.json is invalid JSON: {exc}"]
    errors = validate_review_result(payload, capsule, execution_report)
    return (payload if isinstance(payload, dict) else None), errors


def validate_review_result(
    payload: Any,
    capsule: dict[str, Any] | None = None,
    execution_report: dict[str, Any] | None = None,
) -> list[str]:
    if not isinstance(payload, dict):
        return ["review_result must be a JSON object"]
    errors: list[str] = []
    if payload.get("schema") != REVIEW_RESULT_SCHEMA:
        errors.append(f"schema must be {REVIEW_RESULT_SCHEMA}")
    for key in ["version", "review_id", "created_at", "decision", "reviewer", "reviewer_role"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    if payload.get("decision") not in {"approved", "rejected", "needs_changes"}:
        errors.append("decision must be approved, rejected, or needs_changes")
    if str(payload.get("reviewer_role") or "").lower() in {"worker", "worker-main", "primary_worker"}:
        errors.append("reviewer_role must be independent from the worker role")
    if not isinstance(payload.get("evidence"), list) or not all(isinstance(item, str) and item for item in payload.get("evidence", [])):
        errors.append("evidence must be a non-empty list of strings")
    if capsule:
        verification_spec = capsule.get("verification_spec", {}) if isinstance(capsule.get("verification_spec"), dict) else {}
        if payload.get("capsule_id") != capsule.get("capsule_id"):
            errors.append("capsule_id does not match current Mission Capsule")
        if payload.get("capsule_revision") != capsule.get("revision"):
            errors.append("capsule_revision does not match current Mission Capsule")
        if payload.get("verification_spec_hash") != verification_spec.get("spec_hash"):
            errors.append("verification_spec_hash does not match current VerificationSpec")
    if execution_report:
        if payload.get("execution_id") != execution_report.get("execution_id"):
            errors.append("execution_id does not match current ExecutionReport")
        if payload.get("execution_hash") != execution_report.get("execution_hash"):
            errors.append("execution_hash does not match current ExecutionReport")
    return errors


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
    requires_user_confirmation = bool(gate.get("requires_user_confirmation", False))
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


def _review_result_summary(review_result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(review_result, dict):
        return None
    return {
        "review_id": review_result.get("review_id"),
        "decision": review_result.get("decision"),
        "reviewer": review_result.get("reviewer"),
        "reviewer_role": review_result.get("reviewer_role"),
        "execution_id": review_result.get("execution_id"),
        "execution_hash": review_result.get("execution_hash"),
        "evidence": review_result.get("evidence") if isinstance(review_result.get("evidence"), list) else [],
        "created_at": review_result.get("created_at"),
    }
