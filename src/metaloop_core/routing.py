from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metaloop_core.adaptive_loop import load_adaptive_loop
from metaloop_core.schemas import (
    ADAPTIVE_DECISIONS,
    GLOBAL_BLACKBOARD_SCHEMA,
    JOB_ENVELOPE_SCHEMA,
    ROUTABLE_VERIFICATION_STATUSES,
    ROUTE_ACTIONS,
)
from metaloop_core.specs import hash_object


def job_envelope_hash(envelope: dict[str, Any]) -> str:
    return hash_object(envelope, "envelope_hash")


def validate_job_envelope(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["job_envelope must be a JSON object"]
    errors: list[str] = []
    if payload.get("schema") != JOB_ENVELOPE_SCHEMA:
        errors.append(f"schema must be {JOB_ENVELOPE_SCHEMA}")
    for key in ["version", "job_id", "created_at", "assigned_role", "policy_version", "envelope_hash"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    if "parent_job_id" in payload and payload.get("parent_job_id") is not None and not isinstance(payload.get("parent_job_id"), str):
        errors.append("parent_job_id must be a string or null")
    for key in ["attempt", "retry_count"]:
        if not isinstance(payload.get(key), int) or payload.get(key, -1) < 0:
            errors.append(f"{key} must be a non-negative integer")
    if isinstance(payload.get("attempt"), int) and payload.get("attempt", 0) < 1:
        errors.append("attempt must be at least 1")
    intent = payload.get("intent")
    if not isinstance(intent, dict):
        errors.append("intent must be an object")
    else:
        for key in ["commander_intent", "global_blackboard_ref", "blackboard_hash"]:
            if not isinstance(intent.get(key), str) or not intent.get(key):
                errors.append(f"intent.{key} must be a non-empty string")
        if isinstance(intent.get("blackboard_hash"), str) and not _is_sha256_ref(intent["blackboard_hash"]):
            errors.append("intent.blackboard_hash must be a sha256: reference")
    envelope_payload = payload.get("payload")
    if not isinstance(envelope_payload, dict):
        errors.append("payload must be an object")
    else:
        for key in ["input_capsule_path", "capsule_hash"]:
            if not isinstance(envelope_payload.get(key), str) or not envelope_payload.get(key):
                errors.append(f"payload.{key} must be a non-empty string")
        if isinstance(envelope_payload.get("capsule_hash"), str) and not _is_sha256_ref(envelope_payload["capsule_hash"]):
            errors.append("payload.capsule_hash must be a sha256: reference")
    contract = payload.get("contract")
    if not isinstance(contract, dict):
        errors.append("contract must be an object")
    else:
        errors.extend(_validate_expected_outputs(contract.get("expected_outputs")))
        errors.extend(_validate_handoff_policy(contract.get("handoff_policy")))
    if isinstance(payload.get("envelope_hash"), str) and payload.get("envelope_hash") != job_envelope_hash(payload):
        errors.append("envelope_hash does not match envelope content")
    return errors


def validate_global_blackboard(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["global_blackboard must be a JSON object"]
    errors: list[str] = []
    if payload.get("schema") != GLOBAL_BLACKBOARD_SCHEMA:
        errors.append(f"schema must be {GLOBAL_BLACKBOARD_SCHEMA}")
    for key in ["version", "project_name", "last_updated"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    if not isinstance(payload.get("global_definitions"), dict):
        errors.append("global_definitions must be an object")
    facts = payload.get("facts")
    if not isinstance(facts, list):
        errors.append("facts must be a list")
    else:
        for index, fact in enumerate(facts):
            errors.extend(_validate_blackboard_fact(fact, index))
    decisions = payload.get("architectural_decisions")
    if not isinstance(decisions, list):
        errors.append("architectural_decisions must be a list")
    else:
        for index, decision in enumerate(decisions):
            if not isinstance(decision, dict):
                errors.append(f"architectural_decisions[{index}] must be an object")
                continue
            for key in ["id", "decision", "rationale"]:
                if not isinstance(decision.get(key), str) or not decision.get(key):
                    errors.append(f"architectural_decisions[{index}].{key} must be a non-empty string")
    return errors


def route_next_hop(
    *,
    envelope: dict[str, Any],
    verification_result: dict[str, Any] | None,
    adaptive_loop: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the next control action without performing side effects."""

    envelope_errors = validate_job_envelope(envelope)
    if envelope_errors:
        return {"action": "error", "reason": "Invalid job envelope.", "errors": envelope_errors}
    if verification_result is None:
        return {"action": "wait", "reason": "VerificationResult is not available."}

    status = str(verification_result.get("status") or "")
    decision = latest_adaptive_decision(adaptive_loop)
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
        if _retry_count(envelope) >= _max_retries(policy):
            return {**base, **_policy_action(policy, "on_blocked", "Repair retry limit reached.")}
        return {**base, **_policy_action(policy, "on_repair", "Verification failed and the node diagnosed a repair path."), "retry_count_increment": True}
    if status == "failed" and decision in {"redesign", "pivot"}:
        return {**base, **_policy_action(policy, "on_redesign", "Verification failed and the node requires redesign or pivot.")}
    if status == "failed":
        return {**base, "action": "diagnose", "reason": "Verification failed; record adaptive diagnosis before routing."}
    return {**base, "action": "error", "reason": "Unhandled route state."}


def route_workspace(envelope_path: str | Path, workspace: str | Path = ".") -> dict[str, Any]:
    """Read local artifacts and route without mutating the workspace."""

    root = Path(workspace).expanduser().resolve()
    envelope = _read_json(Path(envelope_path))
    verification = _read_json(root / ".metaloop" / "verification_result.json")
    adaptive_loop = load_adaptive_loop(root)
    if not isinstance(envelope, dict):
        return {"action": "error", "reason": "Job envelope is missing or invalid JSON."}
    return route_next_hop(envelope=envelope, verification_result=verification, adaptive_loop=adaptive_loop)


def latest_adaptive_decision(adaptive_loop: dict[str, Any] | None) -> str:
    if not isinstance(adaptive_loop, dict):
        return ""
    iterations = adaptive_loop.get("iterations")
    if not isinstance(iterations, list) or not iterations:
        return ""
    latest = iterations[-1]
    if not isinstance(latest, dict):
        return ""
    decision = latest.get("decision")
    return decision if isinstance(decision, str) and decision in ADAPTIVE_DECISIONS else ""


def _validate_expected_outputs(payload: Any) -> list[str]:
    if not isinstance(payload, list) or not payload:
        return ["contract.expected_outputs must be a non-empty list"]
    errors: list[str] = []
    for index, artifact in enumerate(payload):
        if not isinstance(artifact, dict):
            errors.append(f"contract.expected_outputs[{index}] must be an object")
            continue
        for key in ["path", "kind"]:
            if not isinstance(artifact.get(key), str) or not artifact.get(key):
                errors.append(f"contract.expected_outputs[{index}].{key} must be a non-empty string")
        if "hash" in artifact and artifact.get("hash") is not None and (not isinstance(artifact.get("hash"), str) or not _is_sha256_ref(artifact["hash"])):
            errors.append(f"contract.expected_outputs[{index}].hash must be a sha256: reference or null")
    return errors


def _validate_handoff_policy(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["contract.handoff_policy must be an object"]
    errors: list[str] = []
    for key in ["on_success", "on_repair", "on_redesign", "on_blocked", "on_human_acceptance", "on_contract_defect"]:
        if not isinstance(payload.get(key), dict):
            errors.append(f"contract.handoff_policy.{key} must be an object")
            continue
        action = payload[key].get("action")
        if action not in ROUTE_ACTIONS:
            errors.append(f"contract.handoff_policy.{key}.action must be one of {sorted(ROUTE_ACTIONS)}")
    return errors


def _validate_blackboard_fact(fact: Any, index: int) -> list[str]:
    if not isinstance(fact, dict):
        return [f"facts[{index}] must be an object"]
    errors: list[str] = []
    for key in ["id", "status", "statement", "source_job_id", "updated_at"]:
        if not isinstance(fact.get(key), str) or not fact.get(key):
            errors.append(f"facts[{index}].{key} must be a non-empty string")
    if fact.get("status") not in {"draft", "locked", "deprecated", "superseded"}:
        errors.append(f"facts[{index}].status is invalid")
    if "ref" in fact and fact.get("ref") is not None and not isinstance(fact.get("ref"), str):
        errors.append(f"facts[{index}].ref must be a string or null")
    if "hash" in fact and fact.get("hash") is not None and (not isinstance(fact.get("hash"), str) or not _is_sha256_ref(fact["hash"])):
        errors.append(f"facts[{index}].hash must be a sha256: reference or null")
    return errors


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


def _max_retries(policy: dict[str, Any]) -> int:
    value = policy.get("on_repair", {}).get("max_retries")
    return value if isinstance(value, int) and value >= 0 else 0


def _retry_count(envelope: dict[str, Any]) -> int:
    value = envelope.get("retry_count")
    return value if isinstance(value, int) and value >= 0 else 0


def _is_sha256_ref(value: str) -> bool:
    return value.startswith("sha256:") and len(value) > len("sha256:")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
