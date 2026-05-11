from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from metaloop_core.ids import new_id, utc_now
from metaloop_core.routing import job_envelope_hash, validate_job_envelope
from metaloop_core.schemas import DISPATCH_MAP_SCHEMA, RELAY_RESULT_SCHEMA


def load_dispatch_map(path: str | Path) -> dict[str, Any] | None:
    payload = _read_json(Path(path))
    return payload if isinstance(payload, dict) else None


def validate_dispatch_map(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["dispatch_map must be a JSON object"]
    errors: list[str] = []
    if payload.get("schema") != DISPATCH_MAP_SCHEMA:
        errors.append(f"schema must be {DISPATCH_MAP_SCHEMA}")
    for key in ["version", "routes"]:
        if key == "routes":
            if not isinstance(payload.get(key), list):
                errors.append("routes must be a list")
            continue
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    for index, route in enumerate(payload.get("routes", [])):
        errors.extend(_validate_route(route, index))
    return errors


def load_outbox_items(workspace: str | Path) -> list[dict[str, Any]]:
    outbox_dir = Path(workspace).expanduser().resolve() / ".metaloop" / "outbox"
    if not outbox_dir.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(outbox_dir.glob("*.json")):
        payload = _read_json(path)
        if isinstance(payload, dict):
            payload["__path__"] = str(path)
            items.append(payload)
    return items


def relay_outbox(
    *,
    workspace: str | Path,
    dispatch_map_path: str | Path,
    write: bool = True,
) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    dispatch_map_path = Path(dispatch_map_path).expanduser().resolve()
    dispatch_map = load_dispatch_map(dispatch_map_path)
    dispatch_errors = validate_dispatch_map(dispatch_map)
    outbox_items = load_outbox_items(root)
    result = {
        "schema": RELAY_RESULT_SCHEMA,
        "version": "1.0",
        "created_at": utc_now(),
        "workspace": str(root),
        "dispatch_map_path": str(dispatch_map_path),
        "dispatch_map_errors": dispatch_errors,
        "counts": {"scanned": len(outbox_items), "delivered": 0, "failed": 0, "needs_design": 0, "skipped": 0},
        "deliveries": [],
    }
    if dispatch_errors:
        result["status"] = "invalid_dispatch_map"
        if write:
            write_relay_result(root, result)
        return result

    routes = dispatch_map.get("routes", []) if isinstance(dispatch_map, dict) else []
    for item in outbox_items:
        delivery = _relay_item(root, dispatch_map_path, item, routes, write=write)
        result["deliveries"].append(delivery)
        status = delivery.get("status")
        if status in result["counts"]:
            result["counts"][status] += 1
    result["status"] = _relay_status(result["counts"])
    if write:
        write_relay_result(root, result)
    return result


def write_relay_result(workspace: str | Path, result: dict[str, Any]) -> Path:
    path = Path(workspace).expanduser().resolve() / ".metaloop" / "relay_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _relay_item(
    workspace: Path,
    dispatch_map_path: Path,
    item: dict[str, Any],
    routes: list[dict[str, Any]],
    *,
    write: bool,
) -> dict[str, Any]:
    target = str(item.get("target") or "")
    source_job_id = str(item.get("source_job_id") or "")
    outbox_path_value = str(item.get("__path__") or "")
    outbox_path = Path(outbox_path_value) if outbox_path_value else None
    route = _route_for_target(routes, target)
    base = {
        "delivery_id": new_id("delivery"),
        "created_at": utc_now(),
        "source_job_id": source_job_id,
        "target": target,
        "outbox_path": outbox_path_value,
    }
    if not target:
        return {**base, "status": "failed", "reason": "Outbox item is missing target."}
    if item.get("delivery_status") == "delivered":
        return {**base, "status": "skipped", "reason": "Outbox item was already delivered."}
    if route is None:
        return {**base, "status": "needs_design", "reason": f"No dispatch route found for target {target}."}
    template_path = _resolve_relative(dispatch_map_path.parent, route.get("envelope_template"))
    if template_path is None:
        return {**base, "status": "needs_design", "reason": f"No envelope template configured for target {target}."}
    template = _read_json(template_path)
    if not isinstance(template, dict):
        return {**base, "status": "failed", "reason": f"Envelope template is missing or invalid: {template_path}."}
    envelope, envelope_errors = _build_downstream_envelope(template, item, route, dispatch_map_path.parent, workspace)
    if envelope_errors:
        return {**base, "status": "failed", "reason": "Invalid downstream envelope.", "errors": envelope_errors}

    target_workspace = _resolve_target_workspace(workspace, route.get("workspace"))
    if target_workspace is None:
        return {**base, "status": "failed", "reason": f"Invalid target workspace for target {target}."}

    target_job_path = target_workspace / "job_envelope.json"
    inbox_path = target_workspace / ".metaloop" / "inbox" / f"{source_job_id or target}.json"
    delivery_record_path = workspace / ".metaloop" / "relay" / f"{source_job_id or target}_{target}.json"

    if write:
        target_workspace.mkdir(parents=True, exist_ok=True)
        target_job_path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False), encoding="utf-8")
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        inbox_payload = {
            "created_at": utc_now(),
            "delivery_id": base["delivery_id"],
            "source_job_id": source_job_id,
            "target": target,
            "source_outbox_path": outbox_path_value,
            "target_job_envelope_path": str(target_job_path),
            "envelope_hash": envelope.get("envelope_hash", ""),
            "route": item.get("route", {}),
        }
        inbox_path.write_text(json.dumps(inbox_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        delivery_record_path.parent.mkdir(parents=True, exist_ok=True)
        delivery_record = {**base, "status": "delivered", "target_job_envelope_path": str(target_job_path), "inbox_path": str(inbox_path), "envelope_hash": envelope.get("envelope_hash", "")}
        delivery_record_path.write_text(json.dumps(delivery_record, indent=2, ensure_ascii=False), encoding="utf-8")
        if outbox_path is not None:
            updated_item = dict(item)
            updated_item.pop("__path__", None)
            updated_item["delivery_status"] = "delivered"
            updated_item["delivered_at"] = utc_now()
            updated_item["delivery_id"] = base["delivery_id"]
            updated_item["delivery_path"] = str(delivery_record_path)
            updated_item["target_job_envelope_path"] = str(target_job_path)
            outbox_path.write_text(json.dumps(updated_item, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        **base,
        "status": "delivered",
        "target_job_envelope_path": str(target_job_path),
        "inbox_path": str(inbox_path),
        "delivery_record_path": str(delivery_record_path),
        "envelope_hash": envelope.get("envelope_hash", ""),
    }


def _build_downstream_envelope(
    template: dict[str, Any],
    outbox_item: dict[str, Any],
    route: dict[str, Any],
    dispatch_root: Path,
    source_workspace: Path,
) -> tuple[dict[str, Any], list[str]]:
    envelope = copy.deepcopy(template)
    if not isinstance(envelope, dict):
        return {}, ["envelope template must be an object"]

    source_envelope = outbox_item.get("source_envelope") if isinstance(outbox_item.get("source_envelope"), dict) else {}
    target_role = str(route.get("role") or route.get("target") or "")
    source_job_id = str(outbox_item.get("source_job_id") or "")
    now = utc_now()

    envelope["schema"] = envelope.get("schema") or "metaloop.job_envelope"
    envelope["version"] = str(envelope.get("version") or "1.0")
    envelope["job_id"] = str(envelope.get("job_id") or new_id("job"))
    envelope["parent_job_id"] = source_job_id or envelope.get("parent_job_id")
    envelope["created_at"] = now
    envelope["assigned_role"] = target_role or str(envelope.get("assigned_role") or "")
    attempt, attempt_error = _coerce_int(envelope.get("attempt"), default=1, minimum=1, field="attempt")
    retry_count, retry_error = _coerce_int(envelope.get("retry_count"), default=0, minimum=0, field="retry_count")
    if attempt_error or retry_error:
        return envelope, [error for error in [attempt_error, retry_error] if error]
    envelope["attempt"] = attempt
    envelope["retry_count"] = retry_count
    envelope["policy_version"] = str(envelope.get("policy_version") or "1.0")

    if not isinstance(envelope.get("intent"), dict):
        envelope["intent"] = {}
    if not isinstance(envelope.get("payload"), dict):
        envelope["payload"] = {}
    if not isinstance(envelope.get("contract"), dict):
        envelope["contract"] = {}

    blackboard_path_value = route.get("blackboard_path")
    if isinstance(blackboard_path_value, str) and blackboard_path_value:
        blackboard_path = _resolve_relative(dispatch_root, blackboard_path_value)
        if blackboard_path is None or not blackboard_path.exists():
            return envelope, [f"blackboard_path not found: {blackboard_path_value}"]
        envelope["intent"]["global_blackboard_ref"] = blackboard_path_value
        envelope["intent"]["blackboard_hash"] = _sha256_file(blackboard_path)
    else:
        envelope["intent"].setdefault("global_blackboard_ref", str(envelope["intent"].get("global_blackboard_ref") or ""))
        envelope["intent"].setdefault("blackboard_hash", str(envelope["intent"].get("blackboard_hash") or ""))

    envelope["upstream"] = {
        "source_job_id": source_job_id,
        "source_workspace": str(source_workspace),
        "source_outbox_target": str(outbox_item.get("target") or ""),
        "source_envelope_hash": str(source_envelope.get("envelope_hash") or ""),
        "route": {
            "target": route.get("target", ""),
            "role": route.get("role", ""),
            "workspace": route.get("workspace", ""),
        },
    }
    envelope["envelope_hash"] = job_envelope_hash(envelope)
    return envelope, validate_job_envelope(envelope)


def _route_for_target(routes: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
    for route in routes:
        if isinstance(route, dict) and str(route.get("target") or "") == target:
            return route
    return None


def _validate_route(route: Any, index: int) -> list[str]:
    if not isinstance(route, dict):
        return [f"routes[{index}] must be an object"]
    errors: list[str] = []
    for key in ["target", "workspace", "role"]:
        if not isinstance(route.get(key), str) or not route.get(key):
            errors.append(f"routes[{index}].{key} must be a non-empty string")
    for key in ["envelope_template", "blackboard_path"]:
        if key in route and route.get(key) is not None and not isinstance(route.get(key), str):
            errors.append(f"routes[{index}].{key} must be a string or null")
    return errors


def _resolve_relative(base_dir: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else (base_dir / path).resolve()


def _resolve_target_workspace(source_workspace: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else (source_workspace / path).resolve()


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _coerce_int(value: Any, *, default: int, minimum: int, field: str) -> tuple[int, str]:
    if value is None or value == "":
        return default, ""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default, f"{field} must be an integer"
    if number < minimum:
        return default, f"{field} must be at least {minimum}"
    return number, ""


def _relay_status(counts: dict[str, int]) -> str:
    if counts.get("failed", 0) > 0:
        return "partial_failed"
    if counts.get("needs_design", 0) > 0 and counts.get("delivered", 0) == 0:
        return "needs_design"
    if counts.get("delivered", 0) > 0 and counts.get("needs_design", 0) == 0:
        return "completed"
    if counts.get("delivered", 0) > 0:
        return "partial"
    return "idle"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
