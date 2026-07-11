from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from metaloop_core.schemas import ENGINEERING_CHANGE_TYPES, ENGINEERING_GOVERNANCE_SCHEMA


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
