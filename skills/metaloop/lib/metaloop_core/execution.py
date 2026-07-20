from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metaloop_core.ids import new_id, utc_now
from metaloop_core.schemas import EXECUTION_REPORT_SCHEMA
from metaloop_core.specs import hash_object


def execution_report_path(workspace: str | Path = ".") -> Path:
    return Path(workspace).expanduser().resolve() / ".metaloop" / "execution_report.json"


def load_execution_report(workspace: str | Path = ".") -> dict[str, Any] | None:
    path = execution_report_path(workspace)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_execution_report(workspace: str | Path, report: dict[str, Any]) -> Path:
    path = execution_report_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def build_execution_report(
    *,
    workspace: str | Path,
    capsule: dict[str, Any],
    status: str,
    commands: list[dict[str, Any]] | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    report = {
        "schema": EXECUTION_REPORT_SCHEMA,
        "version": "1.0",
        "execution_id": new_id("execution"),
        "created_at": utc_now(),
        "workspace": str(Path(workspace).expanduser().resolve()),
        "capsule_id": capsule.get("capsule_id"),
        "capsule_revision": capsule.get("revision"),
        "status": status,
        "commands": commands or [],
        "evidence": evidence or [],
    }
    report["execution_hash"] = hash_object(report, "execution_hash")
    return report


def validate_execution_report(payload: Any, capsule: dict[str, Any]) -> list[str]:
    if not isinstance(payload, dict):
        return ["execution_report.json is missing or is not a JSON object"]
    errors: list[str] = []
    if payload.get("schema") != EXECUTION_REPORT_SCHEMA:
        errors.append(f"schema must be {EXECUTION_REPORT_SCHEMA}")
    if not isinstance(payload.get("execution_id"), str) or not payload.get("execution_id"):
        errors.append("execution_report execution_id must be a non-empty string")
    if payload.get("execution_hash") != hash_object(payload, "execution_hash"):
        errors.append("execution_report execution_hash does not match report content")
    if payload.get("capsule_id") != capsule.get("capsule_id"):
        errors.append("execution_report capsule_id does not match Mission Capsule")
    if payload.get("capsule_revision") != capsule.get("revision"):
        errors.append("execution_report capsule_revision does not match Mission Capsule")
    if payload.get("status") not in {"completed", "failed", "blocked"}:
        errors.append("execution_report status is invalid")
    if not isinstance(payload.get("commands"), list):
        errors.append("execution_report commands must be a list")
    if not isinstance(payload.get("evidence"), list):
        errors.append("execution_report evidence must be a list")
    return errors


def load_valid_execution_report(workspace: str | Path, capsule: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    report = load_execution_report(workspace)
    errors = validate_execution_report(report, capsule)
    if errors:
        return None, errors
    return report, []
