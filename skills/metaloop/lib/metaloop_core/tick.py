from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metaloop_core.capsule import update_capsule_status
from metaloop_core.event_log import EventLog
from metaloop_core.ids import utc_now
from metaloop_core.routing import route_workspace, validate_job_envelope
from metaloop_core.schemas import TICK_RESULT_SCHEMA


def tick_workspace(
    *,
    envelope_path: str | Path,
    workspace: str | Path = ".",
    downstream_envelopes: dict[str, dict[str, Any]] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Apply one deterministic routing tick.

    The router remains pure; this function is the thin effect handler. It
    performs local file effects only and exits after one step.
    """

    root = Path(workspace).expanduser().resolve()
    envelope = _read_json(Path(envelope_path))
    route = route_workspace(envelope_path, root)
    result = {
        "schema": TICK_RESULT_SCHEMA,
        "version": "1.0",
        "created_at": utc_now(),
        "workspace": str(root),
        "envelope_path": str(Path(envelope_path).expanduser().resolve()),
        "route": route,
        "effects": [],
    }
    if not write:
        return result

    effects = _apply_route_effects(
        root,
        envelope if isinstance(envelope, dict) else {},
        route,
        downstream_envelopes=downstream_envelopes or {},
    )
    result["effects"] = effects
    write_tick_result(root, result)
    _append_tick_event(root, route, effects)
    return result


def write_tick_result(workspace: str | Path, result: dict[str, Any]) -> Path:
    path = Path(workspace).expanduser().resolve() / ".metaloop" / "tick_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _apply_route_effects(
    workspace: Path,
    envelope: dict[str, Any],
    route: dict[str, Any],
    *,
    downstream_envelopes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    action = str(route.get("action") or "")
    if action == "dispatch":
        return [_dispatch_effect(workspace, envelope, route, downstream_envelopes=downstream_envelopes)]
    if action == "loop_back":
        update_capsule_status(workspace, "repair_required", str(route.get("reason") or "Tick requested repair loop-back."))
        return [_write_marker(workspace, "loop_back_request.json", envelope, route)]
    if action == "route_to":
        update_capsule_status(workspace, "redesign_required", str(route.get("reason") or "Tick requested redesign or handoff."))
        return [_write_marker(workspace, "route_to_request.json", envelope, route)]
    if action == "escalate":
        update_capsule_status(workspace, "blocked", str(route.get("reason") or "Tick escalated this node."))
        return [_write_marker(workspace, "blocked.json", envelope, route)]
    if action == "suspend":
        return [_write_marker(workspace, "suspended.json", envelope, route)]
    if action in {"wait", "diagnose", "error"}:
        return [_write_marker(workspace, f"{action}.json", envelope, route)]
    return [_write_marker(workspace, "unknown_route.json", envelope, route)]


def _dispatch_effect(
    workspace: Path,
    envelope: dict[str, Any],
    route: dict[str, Any],
    *,
    downstream_envelopes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    target = _route_target(route)
    if not target:
        return _write_marker(workspace, "dispatch_missing_target.json", envelope, route)
    downstream = downstream_envelopes.get(target)
    if downstream is None:
        return _write_outbox(workspace, target, envelope, route)
    target_workspace_value = downstream.get("workspace")
    target_workspace = Path(str(target_workspace_value)).expanduser() if isinstance(target_workspace_value, str) and target_workspace_value else None
    target_envelope = downstream.get("envelope")
    errors = validate_job_envelope(target_envelope)
    if target_workspace is None or not isinstance(target_envelope, dict) or errors:
        effect = _write_marker(workspace, f"dispatch_invalid_{target}.json", envelope, route)
        effect["errors"] = errors or ["downstream workspace or envelope is invalid"]
        return effect
    target_workspace.mkdir(parents=True, exist_ok=True)
    path = target_workspace / "job_envelope.json"
    path.write_text(json.dumps(target_envelope, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"type": "dispatch_written", "target": target, "path": str(path)}


def _write_outbox(workspace: Path, target: str, envelope: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    safe_target = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in target)
    path = workspace / ".metaloop" / "outbox" / f"{safe_target}.json"
    payload = {
        "created_at": utc_now(),
        "target": target,
        "source_job_id": envelope.get("job_id", ""),
        "route": route,
        "source_envelope": {
            "job_id": envelope.get("job_id", ""),
            "assigned_role": envelope.get("assigned_role", ""),
            "envelope_hash": envelope.get("envelope_hash", ""),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"type": "outbox_written", "target": target, "path": str(path)}


def _write_marker(workspace: Path, filename: str, envelope: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    path = workspace / ".metaloop" / filename
    payload = {
        "created_at": utc_now(),
        "source_job_id": envelope.get("job_id", ""),
        "route": route,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"type": "marker_written", "path": str(path)}


def _append_tick_event(workspace: Path, route: dict[str, Any], effects: list[dict[str, Any]]) -> None:
    action = str(route.get("action") or "error")
    event_type = {
        "dispatch": "handoff",
        "loop_back": "repair",
        "route_to": "redesign",
        "escalate": "blocker",
        "suspend": "decision",
        "diagnose": "observation",
        "wait": "note",
        "error": "blocker",
    }.get(action, "note")
    EventLog(workspace).append(
        event_type=event_type,
        agent="tick",
        summary=f"Tick action {action}: {route.get('reason') or 'no reason'}",
        evidence=[str(effect.get("path")) for effect in effects if effect.get("path")],
        decision=action,
        next_action=str(_route_target(route) or ""),
    )


def _route_target(route: dict[str, Any]) -> str:
    for key in ["target", "target_role", "next_role", "notify"]:
        value = route.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
