from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

from metaloop_core.schemas import (
    ASSURANCE_TIERS,
    AUTHORITIES,
    CHANGE_KINDS,
    CONTRACT_SCHEMA,
    CONTRACT_VERSION,
    LEGACY_CONTRACT_VERSION,
    SCOPE_ROLES,
)


def normalize_contract(workspace: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    if not isinstance(payload, dict):
        raise ValueError("contract must be an object")
    content = deepcopy(payload)
    content["schema"] = CONTRACT_SCHEMA
    content["version"] = CONTRACT_VERSION
    content["assurance"] = _normalize_assurance(content.get("assurance"))
    scope = dict(content.get("execution_scope") or {})
    scope["paths"] = [_safe_relative(path, "execution_scope.paths") for path in scope.get("paths", [])]
    stable_inputs = []
    for item in scope.get("stable_inputs", []):
        stable_inputs.append(_normalize_ref(root, item, stable=True))
    managed_outputs = []
    for item in scope.get("managed_outputs", []):
        managed_outputs.append(_normalize_ref(root, item, stable=False))
    scope["stable_inputs"] = stable_inputs
    scope["managed_outputs"] = managed_outputs
    change_kind = scope.get("change_kind")
    if change_kind is not None and change_kind not in CHANGE_KINDS:
        raise ValueError(f"execution_scope.change_kind must be one of {sorted(CHANGE_KINDS)}")
    migration = scope.get("migration_plan")
    if change_kind == "redesign":
        if not migration:
            raise ValueError("redesign requires execution_scope.migration_plan")
        scope["migration_plan"] = _normalize_ref(root, migration, stable=True, role="migration_plan")
    elif migration is not None:
        raise ValueError("execution_scope.migration_plan is only valid for redesign")
    content["execution_scope"] = scope
    return content


def validate_contract(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["contract must be an object"]
    errors: list[str] = []
    if payload.get("schema") != CONTRACT_SCHEMA:
        errors.append(f"contract.schema must be {CONTRACT_SCHEMA}")
    version = payload.get("version")
    if version not in {LEGACY_CONTRACT_VERSION, CONTRACT_VERSION}:
        errors.append(f"contract.version must be {LEGACY_CONTRACT_VERSION} or {CONTRACT_VERSION}")
    for key in ("goal", "rationale", "constraints", "non_goals", "acceptance_criteria", "verification_spec", "protocol_shape"):
        if key not in payload:
            errors.append(f"contract.{key} is required")
    for key in ("rationale", "constraints", "non_goals", "acceptance_criteria"):
        if key in payload and not isinstance(payload[key], list):
            errors.append(f"contract.{key} must be a list")
    assurance = payload.get("assurance")
    if version == CONTRACT_VERSION and not isinstance(assurance, dict):
        errors.append("contract.assurance is required for contract version 1.1")
    if assurance is not None:
        errors.extend(_validate_assurance(assurance))
    verification = payload.get("verification_spec")
    if not isinstance(verification, dict):
        errors.append("contract.verification_spec must be an object")
    else:
        validators = verification.get("validators", [])
        if not isinstance(validators, list):
            errors.append("verification_spec.validators must be a list")
        else:
            for index, validator in enumerate(validators):
                label = f"verification_spec.validators[{index}]"
                if not isinstance(validator, dict):
                    errors.append(f"{label} must be an object")
                    continue
                kind = validator.get("type")
                mode = validator.get("mode", "executable")
                if kind not in {"command", "file_exists", "artifact_hash", "manual_acceptance"}:
                    errors.append(f"{label}.type is unsupported")
                if mode not in {"executable", "manual"}:
                    errors.append(f"{label}.mode must be executable or manual")
                if validator.get("type") == "manual_acceptance" and mode != "manual":
                    errors.append(f"{label} manual_acceptance validators require mode=manual")
                if mode == "manual" and kind != "manual_acceptance":
                    errors.append(f"{label} mode=manual requires type=manual_acceptance")
                if kind == "command" and (not isinstance(validator.get("command"), str) or not validator["command"].strip()):
                    errors.append(f"{label}.command must be a non-empty string")
                if kind == "command":
                    timeout = validator.get("timeout", 600)
                    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
                        errors.append(f"{label}.timeout must be a positive integer")
                if kind in {"file_exists", "artifact_hash"}:
                    path = validator.get("path")
                    if not isinstance(path, str) or not path.strip():
                        errors.append(f"{label}.path must be a non-empty string")
                    elif not _is_safe_relative(path):
                        errors.append(f"{label}.path must be a safe workspace-relative path")
                if kind == "artifact_hash" and not _is_sha256(validator.get("sha256")):
                    errors.append(f"{label}.sha256 must be a sha256 digest")
                if validator.get("authority") == "user":
                    errors.append(
                        f"{label} cannot grant user authority; reserve final user authority in contract.assurance"
                    )
                elif mode == "manual" and validator.get("authority") not in {None, "reviewer"}:
                    errors.append(f"{label}.authority must be reviewer for manual validation")
                elif mode != "manual" and validator.get("authority") is not None:
                    errors.append(f"{label}.authority is only valid for manual validation")
                if validator.get("requires_user_confirmation"):
                    errors.append(
                        f"{label} cannot require user confirmation; reserve final user authority in contract.assurance"
                    )
        if not isinstance(verification.get("resource_gates", []), list):
            errors.append("verification_spec.resource_gates must be a list")
        else:
            for index, gate in enumerate(verification["resource_gates"]):
                if not isinstance(gate, dict):
                    errors.append(f"verification_spec.resource_gates[{index}] must be an object")
                    continue
                if gate.get("requires_user_confirmation"):
                    errors.append(
                        f"verification_spec.resource_gates[{index}] cannot require user confirmation; reserve final user authority in contract.assurance"
                    )
    scope = payload.get("execution_scope", {})
    if not isinstance(scope, dict):
        errors.append("contract.execution_scope must be an object")
        return errors
    if not isinstance(scope.get("paths", []), list):
        errors.append("execution_scope.paths must be a list")
    for key in ("stable_inputs", "managed_outputs"):
        if not isinstance(scope.get(key, []), list):
            errors.append(f"execution_scope.{key} must be a list")
    change_kind = scope.get("change_kind")
    if change_kind is not None and change_kind not in CHANGE_KINDS:
        errors.append("execution_scope.change_kind is invalid")
    if change_kind == "redesign" and not isinstance(scope.get("migration_plan"), dict):
        errors.append("redesign requires execution_scope.migration_plan")
    if change_kind != "redesign" and scope.get("migration_plan") is not None:
        errors.append("execution_scope.migration_plan is only valid for redesign")
    for collection, field in ((scope.get("stable_inputs", []), "stable_inputs"), (scope.get("managed_outputs", []), "managed_outputs")):
        for index, item in enumerate(collection):
            if not isinstance(item, dict):
                errors.append(f"execution_scope.{field}[{index}] must be an object")
                continue
            if not _is_safe_relative(item.get("path")):
                errors.append(f"execution_scope.{field}[{index}].path must be workspace-relative")
            if field == "stable_inputs" and not _is_sha256(item.get("sha256")):
                errors.append(f"execution_scope.{field}[{index}].sha256 must be a sha256 digest")
            if item.get("role") not in SCOPE_ROLES:
                errors.append(f"execution_scope.{field}[{index}].role is invalid")
    return errors


def verify_stable_inputs(workspace: str | Path, payload: dict[str, Any]) -> list[str]:
    errors = validate_contract(payload)
    if errors:
        return errors
    root = Path(workspace).expanduser().resolve()
    refs = list(payload.get("execution_scope", {}).get("stable_inputs", []))
    migration = payload.get("execution_scope", {}).get("migration_plan")
    if migration:
        refs.append(migration)
    for item in refs:
        path = root / item["path"]
        if not path.is_file():
            errors.append(f"stable input missing: {item['path']}")
        elif _file_hash(path) != item["sha256"]:
            errors.append(f"stable input hash drifted: {item['path']}")
    return errors


def managed_output_paths(payload: dict[str, Any]) -> list[str]:
    return [str(item["path"]) for item in payload.get("execution_scope", {}).get("managed_outputs", [])]


def contract_assurance(payload: dict[str, Any]) -> dict[str, Any]:
    """Return normalized assurance while preserving legacy v3 behavior."""

    assurance = payload.get("assurance")
    if not isinstance(assurance, dict):
        return _legacy_assurance()
    errors = _validate_assurance(assurance)
    if errors:
        if payload.get("version") == CONTRACT_VERSION:
            raise ValueError("; ".join(errors))
        return _legacy_assurance()
    return {
        "tier": assurance["tier"],
        "trigger_ids": list(assurance.get("trigger_ids", [])),
        "rationale": list(assurance.get("rationale", [])),
        "required_authorities": list(assurance.get("required_authorities", [])),
        "resolved_trigger_ids": list(assurance.get("resolved_trigger_ids", [])),
        "resolution_evaluation_id": assurance.get("resolution_evaluation_id"),
    }


def _legacy_assurance() -> dict[str, Any]:
    return {
        "tier": "legacy",
        "trigger_ids": [],
        "rationale": [],
        "required_authorities": [],
        "resolved_trigger_ids": [],
        "resolution_evaluation_id": None,
    }


def contract_hash(payload: dict[str, Any]) -> str:
    return _digest(payload)


def _normalize_assurance(value: Any) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("contract.assurance must be an object")
    tier = str(value.get("tier") or "durable_routine")
    if tier not in ASSURANCE_TIERS:
        raise ValueError(f"contract.assurance.tier must be one of {sorted(ASSURANCE_TIERS)}")
    trigger_ids = _normalized_strings(value.get("trigger_ids", []), "contract.assurance.trigger_ids")
    rationale = _normalized_strings(value.get("rationale", []), "contract.assurance.rationale")
    if tier == "durable_routine" and not rationale:
        rationale = ["Routine durable work with mechanically decidable acceptance."]
    authorities = set(_normalized_strings(value.get("required_authorities", []), "contract.assurance.required_authorities"))
    if not authorities.issubset(AUTHORITIES):
        raise ValueError(f"contract.assurance.required_authorities must contain only {sorted(AUTHORITIES)}")
    if tier == "high_assurance":
        authorities.add("reviewer")
    resolution_evaluation_id = value.get("resolution_evaluation_id")
    if resolution_evaluation_id is not None and (not isinstance(resolution_evaluation_id, str) or not resolution_evaluation_id.strip()):
        raise ValueError("contract.assurance.resolution_evaluation_id must be a non-empty string")
    return {
        "tier": tier,
        "trigger_ids": trigger_ids,
        "rationale": rationale,
        "required_authorities": sorted(authorities),
        "resolved_trigger_ids": _normalized_strings(value.get("resolved_trigger_ids", []), "contract.assurance.resolved_trigger_ids"),
        "resolution_evaluation_id": resolution_evaluation_id,
    }


def _validate_assurance(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["contract.assurance must be an object"]
    errors: list[str] = []
    tier = value.get("tier")
    if tier not in ASSURANCE_TIERS:
        errors.append(f"contract.assurance.tier must be one of {sorted(ASSURANCE_TIERS)}")
    for key in ("trigger_ids", "rationale", "required_authorities", "resolved_trigger_ids"):
        items = value.get(key, [])
        if not isinstance(items, list) or any(not isinstance(item, str) or not item.strip() for item in items):
            errors.append(f"contract.assurance.{key} must be a list of non-empty strings")
    authorities = value.get("required_authorities", [])
    if isinstance(authorities, list) and not set(authorities).issubset(AUTHORITIES):
        errors.append(f"contract.assurance.required_authorities must contain only {sorted(AUTHORITIES)}")
    if tier in {"governed", "high_assurance"} and not value.get("rationale"):
        errors.append(f"{tier} requires assurance rationale")
    if tier == "high_assurance":
        if "reviewer" not in authorities:
            errors.append("high_assurance requires reviewer authority")
        if not value.get("trigger_ids"):
            errors.append("high_assurance requires at least one trigger_id")
    resolution_id = value.get("resolution_evaluation_id")
    if resolution_id is not None and (not isinstance(resolution_id, str) or not resolution_id.strip()):
        errors.append("contract.assurance.resolution_evaluation_id must be a non-empty string")
    resolved = value.get("resolved_trigger_ids", [])
    if resolved and not resolution_id:
        errors.append("resolved_trigger_ids require resolution_evaluation_id")
    if resolution_id and not resolved:
        errors.append("resolution_evaluation_id requires resolved_trigger_ids")
    return errors


def _normalized_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{label} must contain non-empty strings")
        normalized.append(item.strip())
    return sorted(set(normalized))


def _normalize_ref(root: Path, item: Any, *, stable: bool, role: str | None = None) -> dict[str, Any]:
    if isinstance(item, str):
        item = {"path": item}
    if not isinstance(item, dict):
        raise ValueError("execution scope references must be objects or paths")
    path = _safe_relative(item.get("path"), "execution scope reference")
    resolved_role = role or item.get("role")
    if resolved_role not in SCOPE_ROLES:
        raise ValueError(f"invalid execution scope role: {resolved_role}")
    output = {"role": resolved_role, "path": path}
    if stable:
        candidate = root / path
        if not candidate.is_file():
            raise ValueError(f"stable input is not a file: {path}")
        output["sha256"] = item.get("sha256") or _file_hash(candidate)
    return output


def _safe_relative(value: Any, label: str = "path") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty workspace-relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or ".metaloop" in path.parts or path.as_posix() in {"", "."}:
        raise ValueError(f"{label} must be a safe workspace-relative path")
    return path.as_posix()


def _is_safe_relative(value: Any) -> bool:
    try:
        _safe_relative(value)
        return True
    except ValueError:
        return False


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(char in "0123456789abcdef" for char in value[7:])


def _digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(data).hexdigest()
