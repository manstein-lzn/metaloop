from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import subprocess
from typing import Any

from metaloop_core.control import pending_control_requests
from metaloop_core.event_log import EventLog
from metaloop_core.ids import new_id, utc_now
from metaloop_core.observe import observe_node
from metaloop_core.routing import job_envelope_hash, validate_job_envelope
from metaloop_core.schemas import ACTIVATION_LEASE_SCHEMA, ACTIVATION_RESULT_SCHEMA
from metaloop_core.specs import hash_object


def plan_activation(
    root: str | Path,
    *,
    worker_command: str | None = None,
    lease_seconds: int = 3600,
) -> dict[str, Any]:
    """Return a read-only activation plan for MetaLoop node workspaces."""

    base = Path(root).expanduser().resolve()
    nodes = [
        _candidate_for_workspace(path, worker_command=worker_command or "", lease_seconds=lease_seconds, now=_now_datetime())
        for path in _node_workspaces(base)
    ]
    return _activation_result(base, worker_command=worker_command or "", dry_run=True, nodes=nodes)


def activate_once(
    root: str | Path,
    *,
    worker_command: str | None = None,
    dry_run: bool = True,
    timeout: int = 600,
    lease_seconds: int = 3600,
    max_activations: int = 1,
    write: bool = True,
) -> dict[str, Any]:
    """Run one bounded activation pass.

    Activation is a thin wrapper. It checks envelopes, controls, and leases,
    optionally runs an explicit worker command, records the result, and exits.
    It does not design tasks, call Codex, mutate contracts, or route work.
    """

    base = Path(root).expanduser().resolve()
    now = _now_datetime()
    nodes: list[dict[str, Any]] = []
    started = 0
    for workspace in _node_workspaces(base):
        candidate = _candidate_for_workspace(workspace, worker_command=worker_command or "", lease_seconds=lease_seconds, now=now)
        if candidate["action"] != "ready":
            nodes.append(candidate)
            continue
        if not worker_command:
            candidate["action"] = "no_worker_command"
            candidate["reason"] = "No worker command was supplied; activation only reports readiness."
            nodes.append(candidate)
            continue
        if dry_run:
            nodes.append(candidate)
            continue
        if started >= max(0, max_activations):
            candidate["reason"] = "Activation limit reached for this pass."
            nodes.append(candidate)
            continue
        nodes.append(_run_worker(candidate, worker_command=worker_command, timeout=timeout, lease_seconds=lease_seconds))
        started += 1

    result = _activation_result(base, worker_command=worker_command or "", dry_run=dry_run, nodes=nodes)
    if write:
        write_activation_result(base, result)
    return result


def write_activation_result(root: str | Path, result: dict[str, Any]) -> Path:
    path = Path(root).expanduser().resolve() / ".metaloop" / "activation_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def activation_result_path(root: str | Path) -> Path:
    return Path(root).expanduser().resolve() / ".metaloop" / "activation_result.json"


def activation_lease_path(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve() / ".metaloop" / "activation" / "lease.json"


def _activation_result(root: Path, *, worker_command: str, dry_run: bool, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for node in nodes:
        action = str(node.get("action") or "unknown")
        counts[action] = counts.get(action, 0) + 1
    return {
        "schema": ACTIVATION_RESULT_SCHEMA,
        "version": "1.0",
        "activation_id": new_id("activation"),
        "created_at": utc_now(),
        "root": str(root),
        "dry_run": dry_run,
        "worker_command": worker_command,
        "counts": counts,
        "nodes": nodes,
    }


def _candidate_for_workspace(workspace: Path, *, worker_command: str, lease_seconds: int, now: datetime) -> dict[str, Any]:
    envelope_path = workspace / "job_envelope.json"
    summary = observe_node(workspace)
    base = {
        "workspace": str(workspace),
        "node_id": summary.get("node_id") or workspace.name,
        "status": summary.get("status") or "missing",
        "pending_controls": summary.get("pending_controls") or [],
        "job_envelope_path": str(envelope_path),
        "lease_path": str(activation_lease_path(workspace)),
        "worker_command": worker_command,
    }
    envelope = _read_json(envelope_path)
    if not isinstance(envelope, dict):
        return {**base, "action": "skipped_no_envelope", "reason": "No job_envelope.json is available."}
    errors = validate_job_envelope(envelope)
    envelope_hash = str(envelope.get("envelope_hash") or job_envelope_hash(envelope))
    idempotency_key = hash_object(
        {"workspace": str(workspace), "envelope_hash": envelope_hash, "worker_command": worker_command},
        "idempotency_key",
    )
    base = {**base, "envelope_hash": envelope_hash, "idempotency_key": idempotency_key}
    if errors:
        return {**base, "action": "failed", "reason": "job_envelope.json is invalid.", "errors": errors}
    controls = pending_control_requests(workspace)
    if controls:
        return {
            **base,
            "action": "blocked_by_control",
            "reason": "Pending control files must be processed before activation.",
            "pending_controls": [str(item.get("type") or "") for item in controls],
        }
    lease = _active_lease(workspace, now)
    if lease is not None:
        return {**base, "action": "lease_active", "reason": "An activation lease is still active.", "lease": lease}
    return {**base, "action": "ready", "reason": "Envelope is ready for one-shot activation."}


def _run_worker(candidate: dict[str, Any], *, worker_command: str, timeout: int, lease_seconds: int) -> dict[str, Any]:
    workspace = Path(str(candidate["workspace"]))
    lease = _write_lease(workspace, candidate, lease_seconds=lease_seconds)
    try:
        completed = subprocess.run(worker_command, cwd=workspace, shell=True, text=True, capture_output=True, timeout=timeout, check=False)
        command_result = {
            "command": worker_command,
            "passed": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        command_result = {
            "command": worker_command,
            "passed": False,
            "exit_code": None,
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "message": f"timeout after {timeout}s",
        }
    action = "started" if command_result["passed"] else "failed"
    reason = "Worker command completed." if command_result["passed"] else "Worker command failed."
    _finish_lease(workspace, lease, status="completed" if command_result["passed"] else "failed")
    EventLog(workspace).append(
        event_type="action" if command_result["passed"] else "blocker",
        agent="activation",
        summary=f"Activation {action}: {reason}",
        evidence=[str(activation_lease_path(workspace))],
        decision=action,
        next_action="worker_must_write_execution_report_and_verify" if command_result["passed"] else "inspect_worker_command_failure",
    )
    return {**candidate, "action": action, "reason": reason, "lease": lease, "command_result": command_result}


def _write_lease(workspace: Path, candidate: dict[str, Any], *, lease_seconds: int) -> dict[str, Any]:
    now = _now_datetime()
    lease = {
        "schema": ACTIVATION_LEASE_SCHEMA,
        "version": "1.0",
        "lease_id": new_id("lease"),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=max(1, lease_seconds))).isoformat(),
        "workspace": str(workspace),
        "job_envelope_path": candidate.get("job_envelope_path", ""),
        "envelope_hash": candidate.get("envelope_hash", ""),
        "idempotency_key": candidate.get("idempotency_key", ""),
        "status": "active",
    }
    path = activation_lease_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lease, indent=2, ensure_ascii=False), encoding="utf-8")
    return lease


def _finish_lease(workspace: Path, lease: dict[str, Any], *, status: str) -> None:
    updated = dict(lease)
    updated["status"] = status
    updated["completed_at"] = utc_now()
    activation_lease_path(workspace).write_text(json.dumps(updated, indent=2, ensure_ascii=False), encoding="utf-8")


def _active_lease(workspace: Path, now: datetime) -> dict[str, Any] | None:
    lease = _read_json(activation_lease_path(workspace))
    if not isinstance(lease, dict) or lease.get("status") != "active":
        return None
    expires_at = _parse_datetime(str(lease.get("expires_at") or ""))
    if expires_at is None or expires_at <= now:
        return None
    return lease


def _node_workspaces(root: Path) -> list[Path]:
    candidates = []
    if (root / ".metaloop").exists() or (root / "job_envelope.json").exists():
        candidates.append(root)
    if root.exists():
        for child in sorted(root.iterdir()):
            if child.is_dir() and ((child / ".metaloop").exists() or (child / "job_envelope.json").exists()):
                candidates.append(child)
    return candidates


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _now_datetime() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
