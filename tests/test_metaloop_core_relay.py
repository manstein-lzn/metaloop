from __future__ import annotations

import json
from pathlib import Path

from metaloop_core.relay import relay_outbox, validate_dispatch_map
from metaloop_core.routing import job_envelope_hash, validate_job_envelope


def _source_envelope() -> dict:
    envelope = {
        "schema": "metaloop.job_envelope",
        "version": "1.0",
        "job_id": "job-source-001",
        "parent_job_id": None,
        "created_at": "2026-05-12T00:00:00Z",
        "assigned_role": "role_primary",
        "attempt": 1,
        "retry_count": 0,
        "policy_version": "1.0",
        "intent": {
            "commander_intent": "Prepare the next generic handoff.",
            "global_blackboard_ref": "./global_blackboard.json",
            "blackboard_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        },
        "payload": {
            "input_capsule_path": "./workspace_a/mission_capsule.json",
            "capsule_hash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        },
        "contract": {
            "expected_outputs": [
                {"path": "./workspace_a/output.json", "kind": "artifact", "hash": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}
            ],
            "handoff_policy": {
                "on_success": {"action": "dispatch", "next_role": "role_secondary"},
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


def _dispatch_map(workspace: Path) -> dict:
    return {
        "schema": "metaloop.dispatch_map",
        "version": "1.0",
        "routes": [
            {
                "target": "role_secondary",
                "workspace": "../workspace_b",
                "role": "role_secondary",
                "envelope_template": "templates/role_secondary_job_envelope.json",
                "blackboard_path": "global_blackboard.json",
            }
        ],
    }


def _secondary_template() -> dict:
    return {
        "schema": "metaloop.job_envelope",
        "version": "1.0",
        "assigned_role": "role_secondary",
        "policy_version": "1.0",
        "intent": {
            "commander_intent": "Continue the generic handoff chain.",
            "global_blackboard_ref": "",
            "blackboard_hash": "",
        },
        "payload": {
            "input_capsule_path": "./workspace_b/mission_capsule.json",
            "capsule_hash": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        },
        "contract": {
            "expected_outputs": [
                {"path": "./workspace_b/output.json", "kind": "artifact", "hash": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"}
            ],
            "handoff_policy": {
                "on_success": {"action": "dispatch", "next_role": "role_tertiary"},
                "on_repair": {"action": "loop_back", "max_retries": 3},
                "on_redesign": {"action": "route_to", "next_role": "role_architect"},
                "on_blocked": {"action": "escalate", "notify": "human_operator"},
                "on_human_acceptance": {"action": "suspend", "notify": "human_operator"},
                "on_contract_defect": {"action": "route_to", "next_role": "role_design"},
            },
        },
    }


def test_validate_dispatch_map_accepts_basic_routes() -> None:
    assert validate_dispatch_map(_dispatch_map(Path("."))) == []


def test_relay_outbox_delivers_to_target_workspace_and_marks_source_outbox(tmp_path) -> None:
    source_workspace = tmp_path / "workspace_a"
    source_workspace.mkdir()
    (source_workspace / "global_blackboard.json").write_text(
        json.dumps(
            {
                "schema": "metaloop.global_blackboard",
                "version": "1.0",
                "project_name": "Generic_Project",
                "last_updated": "2026-05-12T00:00:00Z",
                "global_definitions": {},
                "facts": [],
                "architectural_decisions": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    dispatch_map_path = source_workspace / "dispatch_map.json"
    dispatch_map_path.write_text(json.dumps(_dispatch_map(source_workspace), indent=2), encoding="utf-8")
    template_path = source_workspace / "templates" / "role_secondary_job_envelope.json"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(json.dumps(_secondary_template(), indent=2), encoding="utf-8")

    outbox_dir = source_workspace / ".metaloop" / "outbox"
    outbox_dir.mkdir(parents=True, exist_ok=True)
    outbox_item = {
        "created_at": "2026-05-12T00:01:00Z",
        "target": "role_secondary",
        "source_job_id": "job-source-001",
        "route": {"action": "dispatch", "next_role": "role_secondary"},
        "source_envelope": _source_envelope(),
    }
    (outbox_dir / "role_secondary.json").write_text(json.dumps(outbox_item, indent=2), encoding="utf-8")

    result = relay_outbox(workspace=source_workspace, dispatch_map_path=dispatch_map_path)

    target_job = tmp_path / "workspace_b" / "job_envelope.json"
    inbox_path = tmp_path / "workspace_b" / ".metaloop" / "inbox" / "job-source-001.json"
    relay_result_path = source_workspace / ".metaloop" / "relay_result.json"
    updated_outbox = json.loads((outbox_dir / "role_secondary.json").read_text(encoding="utf-8"))
    envelope = json.loads(target_job.read_text(encoding="utf-8"))

    assert result["status"] == "completed"
    assert result["counts"]["delivered"] == 1
    assert validate_job_envelope(envelope) == []
    assert envelope["job_id"]
    assert envelope["parent_job_id"] == "job-source-001"
    assert envelope["assigned_role"] == "role_secondary"
    assert envelope["intent"]["global_blackboard_ref"] == "global_blackboard.json"
    assert envelope["intent"]["blackboard_hash"].startswith("sha256:")
    assert inbox_path.exists()
    assert relay_result_path.exists()
    assert updated_outbox["delivery_status"] == "delivered"
    assert updated_outbox["delivery_path"].endswith("job-source-001_role_secondary.json")


def test_relay_outbox_reports_needs_design_when_template_missing(tmp_path) -> None:
    source_workspace = tmp_path / "workspace_a"
    source_workspace.mkdir()
    dispatch_map_path = source_workspace / "dispatch_map.json"
    dispatch_map_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.dispatch_map",
                "version": "1.0",
                "routes": [
                    {"target": "role_secondary", "workspace": "workspace_b", "role": "role_secondary"}
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    outbox_dir = source_workspace / ".metaloop" / "outbox"
    outbox_dir.mkdir(parents=True, exist_ok=True)
    (outbox_dir / "role_secondary.json").write_text(
        json.dumps(
            {
                "created_at": "2026-05-12T00:01:00Z",
                "target": "role_secondary",
                "source_job_id": "job-source-002",
                "route": {"action": "dispatch", "next_role": "role_secondary"},
                "source_envelope": _source_envelope(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = relay_outbox(workspace=source_workspace, dispatch_map_path=dispatch_map_path)

    assert result["status"] == "needs_design"
    assert result["counts"]["needs_design"] == 1
    assert not (tmp_path / "workspace_b" / "job_envelope.json").exists()
