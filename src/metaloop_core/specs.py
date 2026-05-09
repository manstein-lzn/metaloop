from __future__ import annotations

import hashlib
import json
from typing import Any

from metaloop_core.schemas import (
    EXTENSION_SPEC_SCHEMA,
    KNOWN_EXECUTABLE_VALIDATORS,
    KNOWN_MANUAL_VALIDATORS,
    MODES,
    SEVERITIES,
    VERIFICATION_SPEC_SCHEMA,
)


def hash_object(payload: dict[str, Any], hash_key: str) -> str:
    normalized = dict(payload)
    normalized.pop(hash_key, None)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validator_mode(validator: dict[str, Any], *, default: str | None = None) -> str:
    value = validator.get("mode") or default
    if isinstance(value, str) and value in MODES:
        return value
    validator_type = validator.get("type")
    if validator_type in KNOWN_EXECUTABLE_VALIDATORS:
        return "executable"
    if validator_type in KNOWN_MANUAL_VALIDATORS:
        return "manual"
    return "unsupported"


def validator_severity(validator: dict[str, Any]) -> str:
    value = validator.get("severity")
    return value if isinstance(value, str) and value in SEVERITIES else "blocking"


def validate_extension_spec(payload: Any, *, allow_lightweight: bool = True) -> list[str]:
    if not isinstance(payload, dict):
        return ["extension_spec must be an object"]
    errors: list[str] = []
    if payload.get("schema") != EXTENSION_SPEC_SCHEMA:
        errors.append(f"extension_spec.schema must be {EXTENSION_SPEC_SCHEMA}")
    for key in ["version", "domain", "purpose", "extension_hash"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"extension_spec.{key} must be a non-empty string")
    for key in ["validator_types", "risk_checks", "review_questions", "known_gaps"]:
        if not isinstance(payload.get(key), list):
            errors.append(f"extension_spec.{key} must be a list")
    if isinstance(payload.get("extension_hash"), str) and payload.get("extension_hash") != hash_object(payload, "extension_hash"):
        errors.append("extension_spec.extension_hash does not match locked extension content")
    if payload.get("domain") != "generic" and not allow_lightweight:
        if not (payload.get("risk_checks") or payload.get("review_questions")):
            errors.append("task-specific extension_spec requires risk_checks or review_questions")
    return errors


def validate_verification_spec(payload: Any, *, extension_spec: dict[str, Any] | None = None) -> list[str]:
    if not isinstance(payload, dict):
        return ["verification_spec must be an object"]
    errors: list[str] = []
    if payload.get("schema") != VERIFICATION_SPEC_SCHEMA:
        errors.append(f"verification_spec.schema must be {VERIFICATION_SPEC_SCHEMA}")
    for key in ["version", "domain", "extension", "extension_version", "extension_hash", "spec_hash"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"verification_spec.{key} must be a non-empty string")
    if isinstance(payload.get("spec_hash"), str) and payload.get("spec_hash") != hash_object(payload, "spec_hash"):
        errors.append("verification_spec.spec_hash does not match locked spec content")
    validators = payload.get("validators")
    if not isinstance(validators, list):
        errors.append("verification_spec.validators must be a list")
        return errors
    for index, validator in enumerate(validators):
        if not isinstance(validator, dict):
            errors.append(f"verification_spec.validators[{index}] must be an object")
            continue
        errors.extend(validate_validator_shape(validator, index, extension_spec=extension_spec))
    for key in ["evidence_requirements", "resource_gates"]:
        if not isinstance(payload.get(key), list):
            errors.append(f"verification_spec.{key} must be a list")
    for index, gate in enumerate(payload.get("resource_gates", [])):
        if not isinstance(gate, dict):
            errors.append(f"verification_spec.resource_gates[{index}] must be an object")
            continue
        errors.extend(validate_validator_shape(gate, index, prefix="verification_spec.resource_gates", extension_spec=extension_spec))
    if extension_spec and payload.get("extension_hash") != extension_spec.get("extension_hash"):
        errors.append("verification_spec.extension_hash does not match extension_spec.extension_hash")
    return errors


def validate_validator_shape(
    validator: dict[str, Any],
    index: int,
    *,
    prefix: str = "verification_spec.validators",
    extension_spec: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    validator_type = validator.get("type")
    if not isinstance(validator_type, str) or not validator_type:
        errors.append(f"{prefix}[{index}].type must be a non-empty string")
    mode = validator.get("mode")
    severity = validator.get("severity")
    if mode not in MODES:
        errors.append(f"{prefix}[{index}].mode must be one of {sorted(MODES)}")
    if severity not in SEVERITIES:
        errors.append(f"{prefix}[{index}].severity must be one of {sorted(SEVERITIES)}")
    if isinstance(validator_type, str) and validator_type and extension_spec:
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
    extension_spec: dict[str, Any],
) -> list[str]:
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


def _validate_json_metric_gate(validator: dict[str, Any], index: int, *, prefix: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(validator.get("path"), str):
        errors.append(f"{prefix}[{index}].path must be a string")
    if not isinstance(validator.get("metric"), str):
        errors.append(f"{prefix}[{index}].metric must be a string")
    if validator.get("operator") not in {">", ">=", "<", "<=", "==", "!="}:
        errors.append(f"{prefix}[{index}].operator is unsupported")
    if "threshold" not in validator:
        errors.append(f"{prefix}[{index}].threshold is required")
    return errors
