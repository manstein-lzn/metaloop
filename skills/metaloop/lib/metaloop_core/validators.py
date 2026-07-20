from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from metaloop_core.schemas import KNOWN_EXECUTABLE_VALIDATORS
from metaloop_core.specs import validator_mode, validator_severity


def file_exists(workspace: str | Path, relative_path: str) -> bool:
    return (Path(workspace).expanduser().resolve() / relative_path).exists()


def file_contains(workspace: str | Path, relative_path: str, text: str) -> bool:
    try:
        return text in (Path(workspace).expanduser().resolve() / relative_path).read_text(encoding="utf-8")
    except OSError:
        return False


def run_validator(workspace: str | Path, validator: dict[str, Any], *, timeout: int = 120) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    validator_type = str(validator.get("type") or "")
    mode = validator_mode(validator)
    severity = validator_severity(validator)
    base = {"type": validator_type, "mode": mode, "severity": severity}
    if mode != "executable":
        return {**base, "passed": False, "message": f"{mode} validator requires non-executable review"}
    if validator_type not in KNOWN_EXECUTABLE_VALIDATORS:
        return {**base, "passed": False, "message": "unsupported executable validator"}
    if validator_type == "file_exists":
        target = str(validator.get("path") or validator.get("target") or "")
        exists = bool(target) and (root / target).exists()
        return {**base, "target": target, "passed": exists, "message": "exists" if exists else "missing"}
    if validator_type == "command":
        command = str(validator.get("command") or "")
        if not command:
            return {**base, "command": command, "passed": False, "message": "empty command"}
        return {**base, **run_command(root, command, timeout=timeout)}
    if validator_type == "forbidden_path":
        target = str(validator.get("path") or validator.get("target") or "")
        exists = bool(target) and (root / target).exists()
        return {**base, "target": target, "passed": not exists, "message": "absent" if not exists else "forbidden path exists"}
    if validator_type == "json_metric_gate":
        return {**base, **run_json_metric_gate(root, validator)}
    if validator_type == "json_field_exists":
        return {**base, **run_json_field_exists(root, validator)}
    if validator_type == "file_contains":
        return {**base, **run_file_contains(root, validator)}
    if validator_type == "artifact_hash":
        return {**base, **run_artifact_hash(root, validator)}
    return {**base, "passed": False, "message": "unknown validator"}


def run_command(workspace: str | Path, command: str, *, timeout: int = 120) -> dict[str, Any]:
    if not command:
        return {"command": command, "passed": False, "message": "empty command"}
    try:
        completed = subprocess.run(command, cwd=Path(workspace), shell=True, text=True, capture_output=True, timeout=timeout, check=False)
        return {
            "command": command,
            "passed": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "passed": False,
            "exit_code": None,
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "message": f"timeout after {timeout}s",
        }


def run_json_metric_gate(workspace: str | Path, validator: dict[str, Any]) -> dict[str, Any]:
    path = str(validator.get("path") or "")
    metric = str(validator.get("metric") or "")
    operator = str(validator.get("operator") or "")
    threshold = validator.get("threshold")
    payload = _read_json(Path(workspace) / path)
    if not isinstance(payload, dict):
        return {"path": path, "metric": metric, "passed": False, "message": "JSON artifact missing or invalid"}
    found, value = lookup_metric(payload, metric)
    if not found:
        return {"path": path, "metric": metric, "passed": False, "message": "metric missing"}
    try:
        passed = compare_metric(value, operator, threshold)
    except (TypeError, ValueError):
        return {"path": path, "metric": metric, "operator": operator, "threshold": threshold, "actual": value, "passed": False, "message": "metric comparison failed"}
    return {"path": path, "metric": metric, "operator": operator, "threshold": threshold, "actual": value, "passed": passed}


def run_json_field_exists(workspace: str | Path, validator: dict[str, Any]) -> dict[str, Any]:
    path = str(validator.get("path") or "")
    field = str(validator.get("field") or validator.get("metric") or "")
    payload = _read_json(Path(workspace) / path)
    if not isinstance(payload, dict):
        return {"path": path, "field": field, "passed": False, "message": "JSON artifact missing or invalid"}
    found, value = lookup_metric(payload, field)
    return {"path": path, "field": field, "passed": found, "actual": value if found else None, "message": "field exists" if found else "field missing"}


def run_file_contains(workspace: str | Path, validator: dict[str, Any]) -> dict[str, Any]:
    path = str(validator.get("path") or "")
    required = validator.get("contains")
    forbidden = validator.get("not_contains")
    try:
        text = (Path(workspace) / path).read_text(encoding="utf-8")
    except OSError:
        return {"path": path, "passed": False, "message": "file missing or unreadable"}
    if isinstance(required, str) and required not in text:
        return {"path": path, "contains": required, "passed": False, "message": "required text missing"}
    if isinstance(forbidden, str) and forbidden in text:
        return {"path": path, "not_contains": forbidden, "passed": False, "message": "forbidden text present"}
    return {"path": path, "contains": required, "not_contains": forbidden, "passed": True}


def run_artifact_hash(workspace: str | Path, validator: dict[str, Any]) -> dict[str, Any]:
    path = str(validator.get("path") or "")
    expected = str(validator.get("sha256") or "")
    artifact = Path(workspace) / path
    try:
        actual = "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()
    except OSError:
        return {"path": path, "expected": expected, "passed": False, "message": "artifact missing or unreadable"}
    expected_normalized = expected if expected.startswith("sha256:") else f"sha256:{expected}"
    return {"path": path, "expected": expected_normalized, "actual": actual, "passed": actual == expected_normalized}


def lookup_metric(payload: dict[str, Any], metric: str) -> tuple[bool, Any]:
    current: Any = payload
    for part in metric.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


def compare_metric(value: Any, operator: str, threshold: Any) -> bool:
    if operator in {">", ">=", "<", "<="}:
        left = float(value)
        right = float(threshold)
        if operator == ">":
            return left > right
        if operator == ">=":
            return left >= right
        if operator == "<":
            return left < right
        return left <= right
    if operator == "==":
        return value == threshold
    if operator == "!=":
        return value != threshold
    raise ValueError(f"unsupported operator: {operator}")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
