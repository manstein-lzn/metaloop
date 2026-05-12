from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metaloop_core.event_log import EventLog
from metaloop_core.ids import new_id, utc_now
from metaloop_core.schemas import CONTROL_REQUEST_SCHEMA, CONTROL_TYPES


def write_control_request(
    workspace: str | Path,
    *,
    control_type: str,
    reason: str,
    created_by: str = "human",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write an explicit control intent file and append an audit event.

    This does not mutate capsules, kill processes, or dispatch work. Workers
    and activators must read these files at safe points.
    """

    if control_type not in CONTROL_TYPES:
        raise ValueError(f"unknown control type: {control_type}")
    reason = reason.strip()
    if not reason:
        raise ValueError("reason must be non-empty")
    root = Path(workspace).expanduser().resolve()
    request = {
        "schema": CONTROL_REQUEST_SCHEMA,
        "version": "1.0",
        "control_id": new_id("control"),
        "created_at": utc_now(),
        "created_by": created_by.strip() or "human",
        "type": control_type,
        "reason": reason,
        "payload": payload or {},
        "status": "pending",
    }
    path = control_request_path(root, control_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
    EventLog(root).append(
        event_type="decision",
        agent=request["created_by"],
        summary=f"Control request {control_type}: {reason}",
        evidence=[str(path)],
        decision=control_type,
        next_action="worker_or_activator_must_process_control_at_safe_point",
    )
    return request


def control_request_path(workspace: str | Path, control_type: str) -> Path:
    return Path(workspace).expanduser().resolve() / ".metaloop" / "control" / f"{control_type}.json"


def load_control_requests(workspace: str | Path) -> list[dict[str, Any]]:
    control_dir = Path(workspace).expanduser().resolve() / ".metaloop" / "control"
    if not control_dir.exists():
        return []
    requests: list[dict[str, Any]] = []
    for path in sorted(control_dir.glob("*.json")):
        payload = _read_json(path)
        if isinstance(payload, dict):
            payload["path"] = str(path)
            requests.append(payload)
    return requests


def pending_control_requests(workspace: str | Path) -> list[dict[str, Any]]:
    return [request for request in load_control_requests(workspace) if request.get("status") == "pending"]


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
