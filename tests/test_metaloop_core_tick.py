from __future__ import annotations

import json
from pathlib import Path

from metaloop_core.routing import job_envelope_hash
from metaloop_core.tick import tick_workspace


def _job_envelope(*, job_id: str = "job-001", next_role: str = "role_secondary") -> dict:
    envelope = {
        "schema": "metaloop.job_envelope",
        "version": "1.0",
        "job_id": job_id,
        "parent_job_id": None,
        "created_at": "2026-05-12T00:00:00Z",
        "assigned_role": "role_primary",
        "attempt": 1,
        "retry_count": 0,
        "policy_version": "1.0",
        "intent": {
            "commander_intent": "Perform the next generic handoff step.",
            "global_blackboard_ref": "./global_blackboard.json",
            "blackboard_hash": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
        },
        "payload": {
            "input_capsule_path": "./tasks/task_alpha/mission_capsule.json",
            "capsule_hash": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
        },
        "contract": {
            "expected_outputs": [
                {"path": "./tasks/task_alpha/output.json", "kind": "artifact", "hash": "sha256:3333333333333333333333333333333333333333333333333333333333333333"}
            ],
            "handoff_policy": {
                "on_success": {"action": "dispatch", "next_role": next_role},
                "on_repair": {"action": "loop_back", "max_retries": 3},
                "on_redesign": {"action": "route_to", "next_role": "role_architect"},
                "on_blocked": {"action": "escalate", "notify": "human_operator"},
                "on_human_acceptance": {"action": "suspend", "notify": "human_operator"},
                "on_contract_defect": {"action": "route_to", "next_role": "role_design"},
            },
        },
    }
    envelope["envelope_hash"] = job_envelope_hash(envelope)
    return envelope


def _write_envelope(workspace: Path, envelope: dict) -> Path:
    path = workspace / "job_envelope.json"
    path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    return path


def _write_verification(workspace: Path, status: str) -> None:
    metaloop_dir = workspace / ".metaloop"
    metaloop_dir.mkdir(parents=True, exist_ok=True)
    (metaloop_dir / "verification_result.json").write_text(json.dumps({"status": status}), encoding="utf-8")


def test_tick_dispatch_writes_outbox_without_inventing_downstream_envelope(tmp_path) -> None:
    envelope_path = _write_envelope(tmp_path, _job_envelope())
    _write_verification(tmp_path, "completed_verified")

    result = tick_workspace(envelope_path=envelope_path, workspace=tmp_path)

    outbox_path = tmp_path / ".metaloop" / "outbox" / "role_secondary.json"
    assert result["route"]["action"] == "dispatch"
    assert result["effects"][0]["type"] == "outbox_written"
    assert outbox_path.exists()
    assert (tmp_path / ".metaloop" / "tick_result.json").exists()
    assert (tmp_path / ".metaloop" / "event_log.jsonl").exists()


def test_tick_dispatch_writes_explicit_downstream_envelope(tmp_path) -> None:
    envelope_path = _write_envelope(tmp_path, _job_envelope())
    _write_verification(tmp_path, "completed_verified")
    target_workspace = tmp_path / "target"
    target_envelope = _job_envelope(job_id="job-002", next_role="reviewer")

    result = tick_workspace(
        envelope_path=envelope_path,
        workspace=tmp_path,
        downstream_envelopes={"role_secondary": {"workspace": str(target_workspace), "envelope": target_envelope}},
    )

    assert result["effects"][0]["type"] == "dispatch_written"
    assert json.loads((target_workspace / "job_envelope.json").read_text(encoding="utf-8"))["job_id"] == "job-002"


def test_tick_loop_back_marks_capsule_repair_required(tmp_path) -> None:
    envelope_path = _write_envelope(tmp_path, _job_envelope())
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    (metaloop_dir / "verification_result.json").write_text(json.dumps({"status": "failed"}), encoding="utf-8")
    (metaloop_dir / "adaptive_loop.json").write_text(json.dumps({"iterations": [{"decision": "repair"}]}), encoding="utf-8")
    (metaloop_dir / "mission_capsule.json").write_text(json.dumps({"current_status": "executed", "status_history": []}), encoding="utf-8")

    result = tick_workspace(envelope_path=envelope_path, workspace=tmp_path)

    capsule = json.loads((metaloop_dir / "mission_capsule.json").read_text(encoding="utf-8"))
    assert result["route"]["action"] == "loop_back"
    assert (metaloop_dir / "loop_back_request.json").exists()
    assert capsule["current_status"] == "repair_required"


def test_tick_human_acceptance_suspends_without_capsule_mutation(tmp_path) -> None:
    envelope_path = _write_envelope(tmp_path, _job_envelope())
    _write_verification(tmp_path, "human_acceptance_required")

    result = tick_workspace(envelope_path=envelope_path, workspace=tmp_path)

    assert result["route"]["action"] == "suspend"
    assert (tmp_path / ".metaloop" / "suspended.json").exists()
