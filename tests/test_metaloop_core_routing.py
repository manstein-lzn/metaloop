from __future__ import annotations

import json
from pathlib import Path

from metaloop_core.routing import job_envelope_hash, route_next_hop, route_workspace, validate_global_blackboard, validate_job_envelope


def _job_envelope(*, retry_count: int = 0) -> dict:
    envelope = {
        "schema": "metaloop.job_envelope",
        "version": "1.0",
        "job_id": "job-001",
        "parent_job_id": None,
        "created_at": "2026-05-12T00:00:00Z",
        "assigned_role": "role_primary",
        "attempt": 1,
        "retry_count": retry_count,
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


def _blackboard() -> dict:
    return {
        "schema": "metaloop.global_blackboard",
        "version": "1.0",
        "project_name": "Generic_Project",
        "last_updated": "2026-05-12T00:00:00Z",
        "global_definitions": {
            "domain_terms": "./docs/domain_terms.md",
            "tech_stack": ["Python", "Tooling", "Storage", "UI"],
        },
        "facts": [
            {
                "id": "fact-001",
                "status": "locked",
                "statement": "The shared contract is locked.",
                "ref": "./contracts/shared_contract.json",
                "hash": "sha256:4444444444444444444444444444444444444444444444444444444444444444",
                "source_job_id": "job-001",
                "updated_at": "2026-05-12T00:00:00Z",
            }
        ],
        "architectural_decisions": [
            {
                "id": "ADR-001",
                "decision": "Route handoffs through explicit envelopes.",
                "rationale": "The control layer must stay deterministic and auditable.",
            }
        ],
    }


def test_job_envelope_validation_accepts_locked_hash_and_policy() -> None:
    envelope = _job_envelope()

    assert validate_job_envelope(envelope) == []
    assert envelope["envelope_hash"].startswith("sha256:")


def test_global_blackboard_validation_accepts_fact_registry() -> None:
    assert validate_global_blackboard(_blackboard()) == []


def test_route_next_hop_dispatches_successful_verified_job() -> None:
    route = route_next_hop(
        envelope=_job_envelope(),
        verification_result={"status": "completed_verified"},
        adaptive_loop={"iterations": [{"decision": "continue"}]},
    )

    assert route["action"] == "dispatch"
    assert route["next_role"] == "role_secondary"
    assert route["verification_status"] == "completed_verified"


def test_route_next_hop_routes_failed_repair_with_retry_increment() -> None:
    route = route_next_hop(
        envelope=_job_envelope(retry_count=1),
        verification_result={"status": "failed"},
        adaptive_loop={"iterations": [{"decision": "repair"}]},
    )

    assert route["action"] == "loop_back"
    assert route["retry_count_increment"] is True
    assert route["max_retries"] == 3


def test_route_next_hop_routes_failed_redesign_to_architect() -> None:
    route = route_next_hop(
        envelope=_job_envelope(),
        verification_result={"status": "failed"},
        adaptive_loop={"iterations": [{"decision": "redesign"}]},
    )

    assert route["action"] == "route_to"
    assert route["next_role"] == "role_architect"


def test_route_next_hop_honors_user_authority_review_and_contract_defect() -> None:
    acceptance = route_next_hop(
        envelope=_job_envelope(),
        verification_result={"status": "human_acceptance_required"},
        adaptive_loop=None,
    )
    review = route_next_hop(
        envelope=_job_envelope(),
        verification_result={"status": "review_required"},
        adaptive_loop=None,
    )
    defect = route_next_hop(
        envelope=_job_envelope(),
        verification_result={"status": "unsupported_verification_spec"},
        adaptive_loop=None,
    )

    assert acceptance["action"] == "suspend"
    assert acceptance["notify"] == "human_operator"
    assert review["action"] == "suspend"
    assert review["verification_status"] == "review_required"
    assert defect["action"] == "route_to"
    assert defect["next_role"] == "role_design"


def test_route_workspace_reads_artifacts_without_mutating_workspace(tmp_path) -> None:
    envelope = _job_envelope()
    envelope_path = tmp_path / "job_envelope.json"
    envelope_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    (metaloop_dir / "verification_result.json").write_text(json.dumps({"status": "completed_verified"}), encoding="utf-8")

    route = route_workspace(envelope_path, tmp_path)

    assert route["action"] == "dispatch"
    assert (tmp_path / ".metaloop" / "verification_result.json").exists()
