from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from metaloop_core.event_log import EventLog
from metaloop_core.ids import utc_now
from metaloop_core.schemas import GLOBAL_SUMMARY_SCHEMA, NODE_SUMMARY_SCHEMA
from metaloop_core.control import pending_control_requests
from metaloop_core.context import context_summary


def observe_node(workspace: str | Path = ".") -> dict[str, Any]:
    """Return a read-only summary of one MetaLoop node workspace."""

    root = Path(workspace).expanduser().resolve()
    metaloop_dir = root / ".metaloop"
    capsule = _read_json(metaloop_dir / "mission_capsule.json")
    verification = _read_json(metaloop_dir / "verification_result.json")
    execution = _read_json(metaloop_dir / "execution_report.json")
    adaptive = _read_json(metaloop_dir / "adaptive_loop.json")
    tick = _read_json(metaloop_dir / "tick_result.json")
    relay = _read_json(metaloop_dir / "relay_result.json")
    envelope = _read_json(root / "job_envelope.json")
    events = EventLog(root).list(limit=1)
    latest_iteration = _latest_iteration(adaptive)
    latest_event = events[-1] if events else None
    outbox_count = _count_json_files(metaloop_dir / "outbox")
    inbox_count = _count_json_files(metaloop_dir / "inbox")
    pending_controls = sorted(str(item.get("type") or "") for item in pending_control_requests(root))
    context = context_summary(root)

    return {
        "schema": NODE_SUMMARY_SCHEMA,
        "version": "1.0",
        "created_at": utc_now(),
        "workspace": str(root),
        "node_id": _node_id(root, capsule, envelope),
        "status": _status(capsule, verification, execution),
        "goal": _goal(capsule, envelope, adaptive),
        "current_plan": _string(adaptive.get("current_plan")) if isinstance(adaptive, dict) else "",
        "best_metric": _best_metric(verification, adaptive),
        "last_event": _event_summary(latest_event),
        "last_verification": _verification_summary(verification),
        "adaptive_decision": _string(latest_iteration.get("decision")) if latest_iteration else "",
        "waiting_on": _waiting_on(verification, pending_controls),
        "outbox_count": outbox_count,
        "inbox_count": inbox_count,
        "pending_controls": pending_controls,
        "context": {
            "state": context["state"],
            "ready_count": context["ready_count"],
            "missing": context["missing"],
            "resume_brief": _context_file_state(context, "resume_brief.md"),
        },
        "last_tick_action": _nested_string(tick, ["route", "action"]),
        "last_relay_status": _string(relay.get("status")) if isinstance(relay, dict) else "",
        "updated_at": _updated_at(
            [
                metaloop_dir / "mission_capsule.json",
                metaloop_dir / "verification_result.json",
                metaloop_dir / "adaptive_loop.json",
                metaloop_dir / "event_log.jsonl",
                metaloop_dir / "context" / "resume_brief.md",
                root / "job_envelope.json",
            ]
        ),
    }


def observe_root(root: str | Path) -> dict[str, Any]:
    """Return a read-only summary for a root containing multiple node workspaces."""

    base = Path(root).expanduser().resolve()
    nodes = [observe_node(path) for path in _node_workspaces(base)]
    counts: dict[str, int] = {}
    for node in nodes:
        status = _string(node.get("status")) or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return {
        "schema": GLOBAL_SUMMARY_SCHEMA,
        "version": "1.0",
        "created_at": utc_now(),
        "root": str(base),
        "node_count": len(nodes),
        "status_counts": counts,
        "blocked_nodes": [node for node in nodes if node.get("status") in {"blocked", "human_acceptance_required", "review_required"} or node.get("waiting_on")],
        "outbox_count": sum(int(node.get("outbox_count") or 0) for node in nodes),
        "inbox_count": sum(int(node.get("inbox_count") or 0) for node in nodes),
        "nodes": nodes,
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _node_workspaces(root: Path) -> list[Path]:
    candidates = []
    if (root / ".metaloop").exists() or (root / "job_envelope.json").exists():
        candidates.append(root)
    for child in sorted(root.iterdir()) if root.exists() else []:
        if child.is_dir() and ((child / ".metaloop").exists() or (child / "job_envelope.json").exists()):
            candidates.append(child)
    return candidates


def _node_id(root: Path, capsule: dict[str, Any] | None, envelope: dict[str, Any] | None) -> str:
    for payload, key in [(envelope, "job_id"), (capsule, "capsule_id"), (capsule, "mission_id")]:
        if isinstance(payload, dict) and isinstance(payload.get(key), str) and payload[key]:
            return payload[key]
    return root.name


def _status(capsule: dict[str, Any] | None, verification: dict[str, Any] | None, execution: dict[str, Any] | None) -> str:
    if isinstance(verification, dict) and isinstance(verification.get("status"), str) and verification["status"]:
        return verification["status"]
    if isinstance(execution, dict) and isinstance(execution.get("status"), str) and execution["status"]:
        return execution["status"]
    if isinstance(capsule, dict) and isinstance(capsule.get("current_status"), str) and capsule["current_status"]:
        return capsule["current_status"]
    return "missing"


def _goal(capsule: dict[str, Any] | None, envelope: dict[str, Any] | None, adaptive: dict[str, Any] | None) -> str:
    for payload, keys in [
        (capsule, ["intent", "goal", "objective"]),
        (envelope, ["intent.commander_intent"]),
        (adaptive, ["goal"]),
    ]:
        if not isinstance(payload, dict):
            continue
        for key in keys:
            value = _nested_string(payload, key.split("."))
            if value:
                return value
    return ""


def _latest_iteration(adaptive: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(adaptive, dict):
        return None
    iterations = adaptive.get("iterations")
    if not isinstance(iterations, list) or not iterations:
        return None
    latest = iterations[-1]
    return latest if isinstance(latest, dict) else None


def _best_metric(verification: dict[str, Any] | None, adaptive: dict[str, Any] | None) -> dict[str, Any] | None:
    if isinstance(verification, dict) and isinstance(verification.get("best_metric"), dict):
        return verification["best_metric"]
    if isinstance(adaptive, dict) and isinstance(adaptive.get("best_metric"), dict):
        return adaptive["best_metric"]
    return None


def _event_summary(event: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(event, dict):
        return None
    return {
        "created_at": _string(event.get("created_at")),
        "type": _string(event.get("type")),
        "agent": _string(event.get("agent")),
        "summary": _string(event.get("summary")),
    }


def _verification_summary(verification: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(verification, dict):
        return None
    return {
        "status": _string(verification.get("status")),
        "reason": _string(verification.get("reason")),
        "hard_failures": _count_failed(verification.get("hard_validator_results")),
        "manual_blockers": _count_blocking(verification.get("manual_validator_results")),
        "review_blockers": _count_review_blocking(verification.get("manual_validator_results")),
        "human_authority_blockers": _count_human_authority_blocking(verification.get("manual_validator_results")),
        "unsupported_blockers": _count_blocking(verification.get("unsupported_validator_results")),
    }


def _waiting_on(verification: dict[str, Any] | None, pending_controls: list[str]) -> str:
    if pending_controls:
        return "control"
    status = _string(verification.get("status")) if isinstance(verification, dict) else ""
    if status == "human_acceptance_required":
        return "human_acceptance"
    if status == "review_required":
        return "review"
    if status in {"missing_execution_report", "execution_incomplete"}:
        return "execution"
    if status in {"missing_verification_plan", "unsupported_verification_spec", "invalid_capsule"}:
        return "design"
    return ""


def _count_json_files(path: Path) -> int:
    return len(list(path.glob("*.json"))) if path.exists() else 0


def _count_failed(items: Any) -> int:
    if not isinstance(items, list):
        return 0
    return sum(1 for item in items if isinstance(item, dict) and item.get("passed") is False)


def _count_blocking(items: Any) -> int:
    if not isinstance(items, list):
        return 0
    return sum(1 for item in items if isinstance(item, dict) and item.get("severity") == "blocking" and item.get("passed") is False)


def _count_review_blocking(items: Any) -> int:
    if not isinstance(items, list):
        return 0
    return sum(1 for item in items if isinstance(item, dict) and item.get("severity") == "blocking" and item.get("passed") is False and not _requires_human_authority(item))


def _count_human_authority_blocking(items: Any) -> int:
    if not isinstance(items, list):
        return 0
    return sum(1 for item in items if isinstance(item, dict) and item.get("severity") == "blocking" and item.get("passed") is False and _requires_human_authority(item))


def _requires_human_authority(item: dict[str, Any]) -> bool:
    if bool(item.get("requires_user_confirmation", False)):
        return True
    if _string(item.get("authority")).lower() == "user":
        return True
    if _string(item.get("reviewer")).lower() in {"user", "human", "human_operator"}:
        return True
    return item.get("delegable") is False


def _context_file_state(summary: dict[str, Any], name: str) -> dict[str, Any] | None:
    files = summary.get("files")
    if not isinstance(files, list):
        return None
    for item in files:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def _updated_at(paths: list[Path]) -> str:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return ""
    latest = max(existing, key=lambda item: item.stat().st_mtime)
    return datetime.fromtimestamp(latest.stat().st_mtime, UTC).isoformat()


def _nested_string(payload: dict[str, Any] | None, keys: list[str]) -> str:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return _string(value)


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""
