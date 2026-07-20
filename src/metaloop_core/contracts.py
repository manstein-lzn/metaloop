from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from metaloop_core.schemas import CHANGE_KINDS, CONTRACT_SCHEMA, SCOPE_ROLES


def normalize_contract(workspace: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    if not isinstance(payload, dict):
        raise ValueError("contract must be an object")
    content = dict(payload)
    content["schema"] = CONTRACT_SCHEMA
    content["version"] = "1.0"
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
    if payload.get("version") != "1.0":
        errors.append("contract.version must be 1.0")
    for key in ("goal", "rationale", "constraints", "non_goals", "acceptance_criteria", "verification_spec", "protocol_shape"):
        if key not in payload:
            errors.append(f"contract.{key} is required")
    for key in ("rationale", "constraints", "non_goals", "acceptance_criteria"):
        if key in payload and not isinstance(payload[key], list):
            errors.append(f"contract.{key} must be a list")
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


def contract_hash(payload: dict[str, Any]) -> str:
    return _digest(payload)


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
    if path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
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
