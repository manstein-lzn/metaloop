from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from metaloop_core.schemas import (
    ENGINEERING_CHANGE_TYPES,
    ENGINEERING_GOVERNANCE_SCHEMA,
    V2_ENGINEERING_GOVERNANCE_SCHEMA,
    V2_GOVERNANCE_REF_ROLES,
)


def build_locked_file(workspace: str | Path, ref: str) -> dict[str, str]:
    root = Path(workspace).expanduser().resolve()
    path, safe_ref = _resolve_ref(root, ref)
    if not path.is_file():
        raise ValueError(f"governance ref is not a file: {safe_ref}")
    return {"ref": safe_ref, "sha256": _sha256_file(path)}


def validate_engineering_governance(payload: Any) -> list[str]:
    if payload is None:
        return []
    if not isinstance(payload, dict):
        return ["engineering_governance must be an object"]

    errors: list[str] = []
    if payload.get("schema") != ENGINEERING_GOVERNANCE_SCHEMA:
        errors.append(f"engineering_governance.schema must be {ENGINEERING_GOVERNANCE_SCHEMA}")
    if payload.get("version") != "1.0":
        errors.append("engineering_governance.version must be 1.0")
    if payload.get("change_type") not in ENGINEERING_CHANGE_TYPES:
        errors.append(f"engineering_governance.change_type must be one of {sorted(ENGINEERING_CHANGE_TYPES)}")

    errors.extend(_validate_locked_file(payload.get("governing_document"), "engineering_governance.governing_document"))
    module_contracts = payload.get("module_contracts")
    if not isinstance(module_contracts, list) or not module_contracts:
        errors.append("engineering_governance.module_contracts must be a non-empty list")
    else:
        for index, item in enumerate(module_contracts):
            errors.extend(_validate_locked_file(item, f"engineering_governance.module_contracts[{index}]"))

    allowed_paths = payload.get("allowed_paths")
    if not isinstance(allowed_paths, list) or not allowed_paths:
        errors.append("engineering_governance.allowed_paths must be a non-empty list")
    elif not all(_is_safe_relative_ref(item) for item in allowed_paths):
        errors.append("engineering_governance.allowed_paths must contain safe workspace-relative paths")

    migration_plan = payload.get("migration_plan")
    if payload.get("change_type") == "redesign":
        errors.extend(_validate_locked_file(migration_plan, "engineering_governance.migration_plan"))
    elif migration_plan is not None:
        errors.append("engineering_governance.migration_plan is only valid for redesign")
    return errors


def verify_engineering_governance(workspace: str | Path, payload: Any) -> list[str]:
    errors = validate_engineering_governance(payload)
    if errors or payload is None:
        return errors

    root = Path(workspace).expanduser().resolve()
    locked_files = [payload["governing_document"], *payload["module_contracts"]]
    if payload.get("migration_plan") is not None:
        locked_files.append(payload["migration_plan"])
    for item in locked_files:
        try:
            path, safe_ref = _resolve_ref(root, item["ref"])
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"governance ref is missing: {safe_ref}")
            continue
        if _sha256_file(path) != item["sha256"]:
            errors.append(f"governance ref hash drifted: {safe_ref}")
    return errors


def build_v2_governance(
    workspace: str | Path,
    *,
    change_kind: str,
    stable_inputs: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
    managed_outputs: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
    allowed_paths: list[str] | tuple[str, ...] = (),
    migration_plan: str | None = None,
) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    payload = {
        "schema": V2_ENGINEERING_GOVERNANCE_SCHEMA,
        "version": "1.0",
        "change_kind": change_kind,
        "stable_inputs": [_build_v2_locked_ref(root, role, path) for role, path in stable_inputs],
        "managed_outputs": [_build_v2_output_ref(role, path) for role, path in managed_outputs],
        "allowed_paths": [Path(path).as_posix() for path in allowed_paths],
        "migration_plan": _build_v2_locked_ref(root, "migration_plan", migration_plan) if migration_plan else None,
    }
    errors = validate_v2_governance(payload)
    if errors:
        raise ValueError("invalid V2 governance: " + "; ".join(errors))
    return payload


def normalize_legacy_governance(payload: Any) -> dict[str, Any] | None:
    if payload is None:
        return None
    errors = validate_engineering_governance(payload)
    if errors:
        raise ValueError("invalid legacy engineering governance: " + "; ".join(errors))
    stable_inputs = [
        _legacy_locked_ref("governing_document", payload["governing_document"]),
        *(_legacy_locked_ref("module_contract", item) for item in payload["module_contracts"]),
    ]
    migration_plan = payload.get("migration_plan")
    return {
        "schema": V2_ENGINEERING_GOVERNANCE_SCHEMA,
        "version": "1.0",
        "change_kind": payload["change_type"],
        "stable_inputs": stable_inputs,
        "managed_outputs": [],
        "allowed_paths": list(payload["allowed_paths"]),
        "migration_plan": _legacy_locked_ref("migration_plan", migration_plan) if migration_plan else None,
    }


def validate_v2_governance(payload: Any) -> list[str]:
    if payload is None:
        return []
    if not isinstance(payload, dict):
        return ["governance must be an object"]

    errors: list[str] = []
    if payload.get("schema") != V2_ENGINEERING_GOVERNANCE_SCHEMA:
        errors.append(f"governance.schema must be {V2_ENGINEERING_GOVERNANCE_SCHEMA}")
    if payload.get("version") != "1.0":
        errors.append("governance.version must be 1.0")
    if payload.get("change_kind") not in ENGINEERING_CHANGE_TYPES:
        errors.append(f"governance.change_kind must be one of {sorted(ENGINEERING_CHANGE_TYPES)}")

    stable_inputs = payload.get("stable_inputs")
    managed_outputs = payload.get("managed_outputs")
    if not isinstance(stable_inputs, list):
        errors.append("governance.stable_inputs must be a list")
        stable_inputs = []
    else:
        for index, item in enumerate(stable_inputs):
            errors.extend(_validate_v2_ref(item, f"governance.stable_inputs[{index}]", locked=True))
    if not isinstance(managed_outputs, list):
        errors.append("governance.managed_outputs must be a list")
        managed_outputs = []
    else:
        for index, item in enumerate(managed_outputs):
            errors.extend(_validate_v2_ref(item, f"governance.managed_outputs[{index}]", locked=False))
    if not stable_inputs and not managed_outputs:
        errors.append("governance requires at least one stable input or managed output")

    allowed_paths = payload.get("allowed_paths")
    if not isinstance(allowed_paths, list) or not allowed_paths:
        errors.append("governance.allowed_paths must be a non-empty list")
        allowed_paths = []
    elif not all(_is_safe_relative_ref(item) for item in allowed_paths):
        errors.append("governance.allowed_paths must contain safe workspace-relative paths")

    seen: set[str] = set()
    for field, refs in [("stable_inputs", stable_inputs), ("managed_outputs", managed_outputs)]:
        for index, item in enumerate(refs):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            path = Path(item["path"]).as_posix()
            if path in seen:
                errors.append(f"governance.{field}[{index}].path duplicates another governance ref")
            seen.add(path)
    for index, item in enumerate(managed_outputs):
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            if allowed_paths and not any(_path_within(item["path"], allowed) for allowed in allowed_paths):
                errors.append(f"governance.managed_outputs[{index}].path must be within allowed_paths")

    migration_plan = payload.get("migration_plan")
    if payload.get("change_kind") == "redesign":
        errors.extend(_validate_v2_ref(migration_plan, "governance.migration_plan", locked=True, expected_role="migration_plan"))
    elif migration_plan is not None:
        errors.append("governance.migration_plan is only valid for redesign")
    return errors


def verify_v2_governance(
    workspace: str | Path,
    payload: Any,
    *,
    evidence_paths: set[str] | None = None,
    require_managed_outputs: bool = False,
) -> list[str]:
    errors = validate_v2_governance(payload)
    if errors or payload is None:
        return errors
    root = Path(workspace).expanduser().resolve()
    locked_refs = list(payload["stable_inputs"])
    if payload.get("migration_plan") is not None:
        locked_refs.append(payload["migration_plan"])
    for item in locked_refs:
        path = root / item["path"]
        if not path.is_file():
            errors.append(f"governance stable input is missing: {item['path']}")
        elif _sha256_file(path) != item["sha256"]:
            errors.append(f"governance stable input drifted: {item['path']}")
    if require_managed_outputs:
        normalized_evidence = {Path(item).as_posix() for item in evidence_paths or set()}
        for item in payload["managed_outputs"]:
            path = root / item["path"]
            if not path.is_file():
                errors.append(f"governance managed output is missing: {item['path']}")
            elif item["path"] not in normalized_evidence:
                errors.append(f"governance managed output is not Attempt evidence: {item['path']}")
    return errors


def summarize_v2_governance(workspace: str | Path, payload: Any) -> dict[str, Any] | None:
    if payload is None:
        return None
    shape_errors = validate_v2_governance(payload)
    live_errors = verify_v2_governance(workspace, payload) if not shape_errors else []
    return {
        "schema": payload.get("schema") if isinstance(payload, dict) else None,
        "change_kind": payload.get("change_kind") if isinstance(payload, dict) else None,
        "stable_input_paths": [item.get("path") for item in payload.get("stable_inputs", []) if isinstance(item, dict)],
        "managed_output_paths": [item.get("path") for item in payload.get("managed_outputs", []) if isinstance(item, dict)],
        "allowed_paths": list(payload.get("allowed_paths", [])) if isinstance(payload, dict) else [],
        "migration_plan_path": (
            payload.get("migration_plan", {}).get("path")
            if isinstance(payload, dict) and isinstance(payload.get("migration_plan"), dict)
            else None
        ),
        "stable_inputs_fresh": not shape_errors and not live_errors,
        "errors": [*shape_errors, *live_errors],
    }


def _validate_locked_file(value: Any, field: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{field} must be an object"]
    errors: list[str] = []
    if not _is_safe_relative_ref(value.get("ref")):
        errors.append(f"{field}.ref must be a safe workspace-relative path")
    sha256 = value.get("sha256")
    if not _is_sha256(sha256):
        errors.append(f"{field}.sha256 must be a sha256: digest")
    return errors


def _build_v2_locked_ref(root: Path, role: str, ref: str) -> dict[str, str]:
    _validate_role(role)
    path, safe_ref = _resolve_ref(root, ref)
    if not path.is_file():
        raise ValueError(f"governance ref is not a file: {safe_ref}")
    return {"role": role, "path": safe_ref, "sha256": _sha256_file(path)}


def _build_v2_output_ref(role: str, ref: str) -> dict[str, str]:
    _validate_role(role)
    if not _is_safe_relative_ref(ref):
        raise ValueError("governance output must be a safe workspace-relative path")
    return {"role": role, "path": Path(ref).as_posix()}


def _legacy_locked_ref(role: str, value: dict[str, str]) -> dict[str, str]:
    return {"role": role, "path": value["ref"], "sha256": value["sha256"]}


def _validate_v2_ref(
    value: Any,
    field: str,
    *,
    locked: bool,
    expected_role: str | None = None,
) -> list[str]:
    if not isinstance(value, dict):
        return [f"{field} must be an object"]
    errors: list[str] = []
    role = value.get("role")
    if role not in V2_GOVERNANCE_REF_ROLES:
        errors.append(f"{field}.role must be one of {sorted(V2_GOVERNANCE_REF_ROLES)}")
    elif expected_role and role != expected_role:
        errors.append(f"{field}.role must be {expected_role}")
    if not _is_safe_relative_ref(value.get("path")):
        errors.append(f"{field}.path must be a safe workspace-relative path")
    if locked and not _is_sha256(value.get("sha256")):
        errors.append(f"{field}.sha256 must be a sha256: digest")
    unexpected = set(value) - ({"role", "path", "sha256"} if locked else {"role", "path"})
    if unexpected:
        errors.append(f"{field} has unsupported fields: {sorted(unexpected)}")
    return errors


def _validate_role(role: str) -> None:
    if role not in V2_GOVERNANCE_REF_ROLES:
        raise ValueError(f"governance role must be one of {sorted(V2_GOVERNANCE_REF_ROLES)}")


def _path_within(path: str, allowed: str) -> bool:
    path_parts = Path(path).parts
    allowed_parts = Path(allowed).parts
    return len(path_parts) >= len(allowed_parts) and path_parts[: len(allowed_parts)] == allowed_parts


def _resolve_ref(root: Path, ref: str) -> tuple[Path, str]:
    if not _is_safe_relative_ref(ref):
        raise ValueError("governance ref must be a safe workspace-relative path")
    safe_ref = Path(ref).as_posix()
    path = (root / safe_ref).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"governance ref escapes workspace: {safe_ref}")
    return path, safe_ref


def _is_safe_relative_ref(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and path.as_posix() not in {"", "."}


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        return False
    return all(character in "0123456789abcdef" for character in value[7:])
