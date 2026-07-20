from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metaloop_core.engineering_governance import validate_engineering_governance, verify_engineering_governance
from metaloop_core.ids import utc_now
from metaloop_core.schemas import CAPSULE_SCHEMA, CAPSULE_STATUSES
from metaloop_core.specs import validate_extension_spec, validate_verification_spec


def load_capsule(workspace: str | Path = ".") -> dict[str, Any] | None:
    path = capsule_path(workspace)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def capsule_path(workspace: str | Path = ".") -> Path:
    return Path(workspace).expanduser().resolve() / ".metaloop" / "mission_capsule.json"


def write_capsule(workspace: str | Path, capsule: dict[str, Any]) -> Path:
    path = capsule_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(capsule, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def validate_capsule(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["mission_capsule.json is missing or is not a JSON object"]
    errors: list[str] = []
    if payload.get("schema") != CAPSULE_SCHEMA:
        errors.append(f"schema must be {CAPSULE_SCHEMA}")
    for key in ["version", "capsule_id", "created_at", "updated_at", "locked_at", "workspace", "intent", "current_status"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    if not isinstance(payload.get("revision"), int) or payload.get("revision", 0) < 1:
        errors.append("revision must be a positive integer")
    if payload.get("locked") is not True:
        errors.append("locked must be true")
    if payload.get("current_status") not in CAPSULE_STATUSES:
        errors.append("current_status is not a known capsule status")
    for key in ["context", "design_rationale", "constraints", "non_goals", "acceptance_criteria", "forbidden_paths", "evidence_requirements", "status_history"]:
        if not isinstance(payload.get(key), list):
            errors.append(f"{key} must be a list")
    extension_spec = payload.get("extension_spec") if isinstance(payload.get("extension_spec"), dict) else None
    verification_spec = payload.get("verification_spec") if isinstance(payload.get("verification_spec"), dict) else None
    if extension_spec is None:
        errors.append("extension_spec must be an object")
    else:
        errors.extend(validate_extension_spec(extension_spec, allow_lightweight=True))
    if verification_spec is None:
        errors.append("verification_spec must be an object")
    else:
        errors.extend(validate_verification_spec(verification_spec, extension_spec=extension_spec))
    if not isinstance(payload.get("verification_review"), dict):
        errors.append("verification_review must be an object")
    errors.extend(validate_engineering_governance(payload.get("engineering_governance")))
    return errors


def load_valid_capsule(workspace: str | Path = ".") -> tuple[dict[str, Any] | None, list[str]]:
    capsule = load_capsule(workspace)
    errors = validate_capsule(capsule)
    if not errors and capsule is not None:
        errors.extend(verify_engineering_governance(workspace, capsule.get("engineering_governance")))
    if errors:
        return None, errors
    return capsule, []


def update_capsule_status(workspace: str | Path, status: str, reason: str = "") -> dict[str, Any] | None:
    capsule = load_capsule(workspace)
    if capsule is None:
        return None
    capsule["current_status"] = status
    capsule["updated_at"] = utc_now()
    capsule.setdefault("status_history", []).append({"status": status, "reason": reason, "at": utc_now()})
    write_capsule(workspace, capsule)
    return capsule
