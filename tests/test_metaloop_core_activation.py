from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from metaloop_core.activation import activate_once, activation_lease_path, plan_activation
from metaloop_core.control import write_control_request
from metaloop_core.routing import job_envelope_hash


def _job_envelope() -> dict:
    envelope = {
        "schema": "metaloop.job_envelope",
        "version": "1.0",
        "job_id": "job-activation-001",
        "parent_job_id": None,
        "created_at": "2026-05-12T00:00:00Z",
        "assigned_role": "worker",
        "attempt": 1,
        "retry_count": 0,
        "policy_version": "1.0",
        "intent": {
            "commander_intent": "Handle the delivered work unit.",
            "global_blackboard_ref": "./global_blackboard.json",
            "blackboard_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        },
        "payload": {
            "input_capsule_path": "./mission_capsule.json",
            "capsule_hash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        },
        "contract": {
            "expected_outputs": [{"path": "result.json", "kind": "artifact", "hash": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}],
            "handoff_policy": {
                "on_success": {"action": "dispatch", "next_role": "reviewer"},
                "on_repair": {"action": "loop_back", "max_retries": 3},
                "on_redesign": {"action": "route_to", "next_role": "designer"},
                "on_blocked": {"action": "escalate", "notify": "human_operator"},
                "on_human_acceptance": {"action": "suspend", "notify": "human_operator"},
                "on_contract_defect": {"action": "route_to", "next_role": "designer"},
            },
        },
    }
    envelope["envelope_hash"] = job_envelope_hash(envelope)
    return envelope


def _write_envelope(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "job_envelope.json").write_text(json.dumps(_job_envelope(), indent=2), encoding="utf-8")


def test_plan_activation_is_read_only_and_reports_ready_node(tmp_path) -> None:
    node = tmp_path / "worker"
    _write_envelope(node)

    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    result = plan_activation(tmp_path, worker_command="python worker.py")
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    assert before == after
    assert result["schema"] == "metaloop.activation_result"
    assert result["dry_run"] is True
    assert result["counts"]["ready"] == 1
    assert result["nodes"][0]["workspace"] == str(node.resolve())
    assert result["nodes"][0]["action"] == "ready"
    assert result["nodes"][0]["idempotency_key"].startswith("sha256:")


def test_activate_once_without_worker_command_writes_readiness_result(tmp_path) -> None:
    node = tmp_path / "worker"
    _write_envelope(node)

    result = activate_once(tmp_path, write=True)

    assert result["counts"]["no_worker_command"] == 1
    assert (tmp_path / ".metaloop" / "activation_result.json").exists()
    assert not activation_lease_path(node).exists()


def test_activate_once_respects_pending_controls(tmp_path) -> None:
    node = tmp_path / "worker"
    _write_envelope(node)
    write_control_request(node, control_type="halt", reason="Pause before starting the next attempt.")

    result = activate_once(tmp_path, worker_command="printf started > marker.txt", dry_run=False)

    assert result["counts"]["blocked_by_control"] == 1
    assert not (node / "marker.txt").exists()
    assert not activation_lease_path(node).exists()


def test_activate_once_runs_explicit_worker_command_and_records_lease(tmp_path) -> None:
    node = tmp_path / "worker"
    _write_envelope(node)

    result = activate_once(tmp_path, worker_command="printf started > marker.txt", dry_run=False, timeout=10)
    lease = json.loads(activation_lease_path(node).read_text(encoding="utf-8"))
    events = (node / ".metaloop" / "event_log.jsonl").read_text(encoding="utf-8")

    assert result["counts"]["started"] == 1
    assert (node / "marker.txt").read_text(encoding="utf-8") == "started"
    assert lease["schema"] == "metaloop.activation_lease"
    assert lease["status"] == "completed"
    assert "Activation started" in events


def test_activate_once_skips_active_lease(tmp_path) -> None:
    node = tmp_path / "worker"
    _write_envelope(node)
    lease_path = activation_lease_path(node)
    lease_path.parent.mkdir(parents=True)
    lease_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.activation_lease",
                "version": "1.0",
                "lease_id": "lease-active",
                "created_at": datetime.now(UTC).isoformat(),
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "workspace": str(node),
                "status": "active",
            }
        ),
        encoding="utf-8",
    )

    result = activate_once(tmp_path, worker_command="printf started > marker.txt", dry_run=False)

    assert result["counts"]["lease_active"] == 1
    assert not (node / "marker.txt").exists()
