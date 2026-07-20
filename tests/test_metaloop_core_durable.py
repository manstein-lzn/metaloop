from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

import pytest

from metaloop_core.cli import main as cli_main
from metaloop_core.durable import (
    ConflictError,
    DuplicateAttemptError,
    DurableStore,
    InvalidTransitionError,
    NotFoundError,
)


ROOT = Path(__file__).resolve().parents[1]


def _contract(*, manual: bool = False) -> dict:
    validator = (
        {"type": "manual_acceptance", "mode": "manual", "severity": "blocking", "description": "Independent review."}
        if manual
        else {"type": "file_exists", "mode": "executable", "severity": "blocking", "path": "result.txt"}
    )
    return {
        "goal": "Produce a verified result.",
        "constraints": [],
        "non_goals": ["Do not weaken verification."],
        "acceptance_criteria": ["Locked verification passes."],
        "verification_spec": {"validators": [validator], "resource_gates": []},
    }


def _task_with_contract(store: DurableStore, *, title: str = "Task", manual: bool = False) -> dict:
    task = store.create_task(title=title)
    store.lock_contract(task["task_id"], _contract(manual=manual), expected_version=task["state_version"])
    return store.get_task(task["task_id"])


def _sealed_attempt(store: DurableStore, task: dict, *, plan: str = "Create the result.", retry_reason: str = "") -> dict:
    attempt = store.start_attempt(
        task["task_id"],
        plan=plan,
        input_snapshot={"git": "abc123"},
        expected_version=task["state_version"],
        actor="worker",
        retry_reason=retry_reason,
    )
    store.append_attempt_record(attempt["attempt_id"], record_type="action", payload={"command": "build"})
    current = store.get_task(task["task_id"])
    return store.seal_attempt(attempt["attempt_id"], expected_task_version=current["state_version"])


def test_schema_v2_has_spawn_origin_and_event_evaluation_foreign_key(tmp_path) -> None:
    store = DurableStore(tmp_path)
    project = store.ensure_project()
    with sqlite3.connect(store.path) as connection:
        task_columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
        event_foreign_keys = {row[3] for row in connection.execute("PRAGMA foreign_key_list(decision_events)")}
    assert project["schema_version"] == 2
    assert "spawned_by_event_id" in task_columns
    assert "evaluation_id" in event_foreign_keys


def test_v2_task_attempt_evaluation_and_acceptance_chain(tmp_path) -> None:
    store = DurableStore(tmp_path)
    store.ensure_project(project_id="project_test")
    task = _task_with_contract(store)
    (tmp_path / "result.txt").write_text("ok\n", encoding="utf-8")

    attempt = _sealed_attempt(store, task)
    evaluation = store.verify_attempt(attempt["attempt_id"])
    completed = store.accept_task(
        task["task_id"],
        terminal_evaluation_id=evaluation["evaluation_id"],
        expected_version=store.get_task(task["task_id"])["state_version"],
    )

    assert evaluation["decision"] == "approved"
    assert completed["lifecycle_status"] == "completed"
    assert completed["acceptance_head_id"] == evaluation["evaluation_id"]
    assert store.integrity_check()["passed"] is True


def test_manual_verification_requires_exact_independent_review_chain(tmp_path) -> None:
    store = DurableStore(tmp_path)
    task = _task_with_contract(store, manual=True)
    attempt = _sealed_attempt(store, task)
    verification = store.verify_attempt(attempt["attempt_id"])
    assert verification["decision"] == "review_required"

    with pytest.raises(InvalidTransitionError):
        store.accept_task(
            task["task_id"],
            terminal_evaluation_id=verification["evaluation_id"],
            expected_version=store.get_task(task["task_id"])["state_version"],
        )

    review = store.review_evaluation(
        verification["evaluation_id"],
        decision="approved",
        reviewer="independent-reviewer",
    )
    completed = store.accept_task(
        task["task_id"],
        terminal_evaluation_id=review["evaluation_id"],
        expected_version=store.get_task(task["task_id"])["state_version"],
    )
    assert completed["acceptance_head_id"] == review["evaluation_id"]


def test_acceptance_fails_when_a_verified_artifact_changes(tmp_path) -> None:
    store = DurableStore(tmp_path)
    task = _task_with_contract(store)
    result_path = tmp_path / "result.txt"
    result_path.write_text("first\n", encoding="utf-8")
    attempt = _sealed_attempt(store, task)
    evaluation = store.verify_attempt(attempt["attempt_id"])
    result_path.write_text("changed\n", encoding="utf-8")

    with pytest.raises(InvalidTransitionError, match="artifact changed"):
        store.accept_task(
            task["task_id"],
            terminal_evaluation_id=evaluation["evaluation_id"],
            expected_version=store.get_task(task["task_id"])["state_version"],
        )


def test_attempt_evidence_is_revalidated_for_verification_acceptance_and_default_integrity(tmp_path) -> None:
    store = DurableStore(tmp_path)
    task = store.create_task(title="Evidence binding")
    contract = _contract()
    contract["verification_spec"]["validators"] = [
        {"type": "command", "mode": "executable", "severity": "blocking", "command": "true"}
    ]
    store.lock_contract(task["task_id"], contract, expected_version=task["state_version"])
    task = store.get_task(task["task_id"])
    result_path = tmp_path / "result.txt"
    result_path.write_text("first\n", encoding="utf-8")
    attempt = store.start_attempt(
        task["task_id"],
        plan="Capture exact evidence.",
        input_snapshot={},
        expected_version=task["state_version"],
    )
    store.add_evidence(attempt["attempt_id"], path="result.txt")
    sealed = store.seal_attempt(
        attempt["attempt_id"],
        expected_task_version=store.get_task(task["task_id"])["state_version"],
    )
    result_path.write_text("drifted\n", encoding="utf-8")
    with pytest.raises(InvalidTransitionError, match="evidence changed before verification"):
        store.verify_attempt(sealed["attempt_id"])

    result_path.write_text("first\n", encoding="utf-8")
    evaluation = store.verify_attempt(sealed["attempt_id"])
    result_path.write_text("drifted again\n", encoding="utf-8")
    with pytest.raises(InvalidTransitionError, match="evidence changed before acceptance"):
        store.accept_task(
            task["task_id"],
            terminal_evaluation_id=evaluation["evaluation_id"],
            expected_version=store.get_task(task["task_id"])["state_version"],
        )

    result_path.write_text("first\n", encoding="utf-8")
    store.accept_task(
        task["task_id"],
        terminal_evaluation_id=evaluation["evaluation_id"],
        expected_version=store.get_task(task["task_id"])["state_version"],
    )
    result_path.write_text("post-accept drift\n", encoding="utf-8")
    integrity = store.integrity_check()
    assert integrity["passed"] is False
    assert integrity["workspace_evidence"]["fresh"] is False


def test_tampered_sealed_attempt_content_blocks_verify_review_and_accept(tmp_path) -> None:
    store = DurableStore(tmp_path)
    (tmp_path / "result.txt").write_text("ok\n", encoding="utf-8")

    task = _task_with_contract(store, title="Tamper after verification")
    attempt = _sealed_attempt(store, task)
    evaluation = store.verify_attempt(attempt["attempt_id"])
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE attempt_records SET payload_json = ? WHERE attempt_id = ? AND seq = 2",
            ('{"tampered":true}', attempt["attempt_id"]),
        )
    with pytest.raises(InvalidTransitionError, match="Attempt content changed"):
        store.review_evaluation(
            evaluation["evaluation_id"],
            decision="approved",
            reviewer="independent-reviewer",
        )
    with pytest.raises(InvalidTransitionError, match="Attempt content changed"):
        store.accept_task(
            task["task_id"],
            terminal_evaluation_id=evaluation["evaluation_id"],
            expected_version=store.get_task(task["task_id"])["state_version"],
        )

    clean_task = _task_with_contract(store, title="Tamper before verification")
    clean_attempt = _sealed_attempt(store, clean_task, plan="Seal then tamper.")
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE attempt_records SET payload_json = ? WHERE attempt_id = ? AND seq = 2",
            ('{"tampered":true}', clean_attempt["attempt_id"]),
        )
    with pytest.raises(InvalidTransitionError, match="Attempt content changed before verification"):
        store.verify_attempt(clean_attempt["attempt_id"])


def test_validator_can_read_observation_without_deadlocking_evaluation(tmp_path) -> None:
    store = DurableStore(tmp_path)
    task = store.create_task(title="Nested observer")
    command = (
        f"PYTHONPATH={ROOT / 'src'} {sys.executable} -c \"from metaloop_core import observe_node; "
        "assert observe_node('.')['schema'] == 'metaloop.node_summary'\""
    )
    contract = _contract()
    contract["verification_spec"]["validators"] = [
        {"type": "command", "mode": "executable", "severity": "blocking", "command": command}
    ]
    store.lock_contract(task["task_id"], contract, expected_version=task["state_version"])
    task = store.get_task(task["task_id"])
    attempt = _sealed_attempt(store, task)

    evaluation = store.verify_attempt(attempt["attempt_id"])

    assert evaluation["decision"] == "approved"
    assert evaluation["payload"]["validator_results"][0]["passed"] is True


def test_task_mutations_use_cas_and_duplicate_attempts_require_reason(tmp_path) -> None:
    store = DurableStore(tmp_path)
    task = _task_with_contract(store)
    stale_version = task["state_version"]
    first = _sealed_attempt(store, task)

    with pytest.raises(ConflictError):
        store.transition_task(task["task_id"], lifecycle="paused", expected_version=stale_version)
    with pytest.raises(DuplicateAttemptError) as duplicate:
        store.start_attempt(
            task["task_id"],
            plan="Create the result.",
            input_snapshot={"git": "abc123"},
            expected_version=store.get_task(task["task_id"])["state_version"],
            actor="worker",
        )

    retry = store.start_attempt(
        task["task_id"],
        plan="Create the result.",
        input_snapshot={"git": "abc123"},
        expected_version=store.get_task(task["task_id"])["state_version"],
        actor="worker",
        retry_reason="Transient environment failure is now resolved.",
    )
    assert duplicate.value.attempt_id == first["attempt_id"]
    assert retry["retry_of_attempt_id"] == first["attempt_id"]


def test_recovery_detects_open_attempt_progress_and_project_decisions(tmp_path) -> None:
    store = DurableStore(tmp_path)
    task = _task_with_contract(store)
    attempt = store.start_attempt(
        task["task_id"],
        plan="Run a long implementation.",
        input_snapshot={},
        expected_version=task["state_version"],
    )
    store.write_recovery(task["task_id"], resume_markdown="# Resume\n\nContinue the open Attempt.")
    assert store.recovery(task["task_id"])["status"] == "fresh"

    store.append_attempt_record(attempt["attempt_id"], record_type="checkpoint", payload={"done": ["schema"], "next": "CLI"})
    stale = store.recovery(task["task_id"])
    assert stale["status"] == "stale"
    assert stale["active_attempt"]["records"][-1]["payload"]["next"] == "CLI"

    store.record_decision(scope="project", event_type="architecture", summary="SQLite is canonical.", decision="locked")
    delta = store.recovery(task["task_id"])["delta_events"]
    assert any(item["scope"] == "project" and item["summary"] == "SQLite is canonical." for item in delta)
    store.write_recovery(task["task_id"])
    refreshed = store.recovery(task["task_id"])
    assert refreshed["status"] == "fresh"
    assert any(item["summary"] == "SQLite is canonical." for item in refreshed["current_decisions"])
    assert "SQLite is canonical." in refreshed["resume_markdown"]
    observation = store.observation()
    assert observation["latest_event"]["summary"] == "SQLite is canonical."


def test_recovery_bundle_bounds_large_open_attempt_history(tmp_path) -> None:
    store = DurableStore(tmp_path)
    task = _task_with_contract(store)
    attempt = store.start_attempt(
        task["task_id"],
        plan="Generate many checkpoints.",
        input_snapshot={},
        expected_version=task["state_version"],
    )
    for index in range(140):
        store.append_attempt_record(attempt["attempt_id"], record_type="checkpoint", payload={"index": index})

    bundle = store.recovery(task["task_id"])
    active = bundle["active_attempt"]
    assert active["record_count"] == 141
    assert len(active["records"]) == 100
    assert active["records"][-1]["payload"]["index"] == 139


def test_recovery_bounds_payload_and_sealed_manifest_expansion(tmp_path) -> None:
    store = DurableStore(tmp_path)
    task = _task_with_contract(store)
    attempt = store.start_attempt(
        task["task_id"],
        plan="Record a large bounded checkpoint.",
        input_snapshot={"large": "x" * 20000},
        expected_version=task["state_version"],
    )
    store.append_attempt_record(attempt["attempt_id"], record_type="checkpoint", payload={"large": "y" * 20000})
    active = store.recovery(task["task_id"])["active_attempt"]
    assert active["input_snapshot"]["_truncated"] is True
    assert active["records"][-1]["payload"]["_truncated"] is True
    sealed = store.seal_attempt(
        attempt["attempt_id"],
        expected_task_version=store.get_task(task["task_id"])["state_version"],
    )
    latest = store.recovery(task["task_id"])["latest_attempts"][0]
    assert latest["manifest"]["_compact"] is True
    assert latest["manifest"]["content_hash"] == sealed["execution_hash"]


def test_dependency_branch_blocks_parent_until_child_is_accepted(tmp_path) -> None:
    store = DurableStore(tmp_path)
    child = _task_with_contract(store, title="Repair child")
    parent = store.create_task(title="Parent", depends_on=[child["task_id"]])
    store.lock_contract(parent["task_id"], _contract(), expected_version=parent["state_version"])
    parent = store.get_task(parent["task_id"])
    assert parent["readiness"] == "blocked"

    with pytest.raises(InvalidTransitionError):
        store.start_attempt(parent["task_id"], plan="Resume parent.", input_snapshot={}, expected_version=parent["state_version"])

    (tmp_path / "result.txt").write_text("ok\n", encoding="utf-8")
    child_attempt = _sealed_attempt(store, child, plan="Repair the defect.")
    child_evaluation = store.verify_attempt(child_attempt["attempt_id"])
    store.accept_task(
        child["task_id"],
        terminal_evaluation_id=child_evaluation["evaluation_id"],
        expected_version=store.get_task(child["task_id"])["state_version"],
    )

    parent = store.get_task(parent["task_id"])
    assert parent["readiness"] == "ready"
    assert parent["lifecycle_status"] == "open"


def test_dependency_completion_makes_parent_recovery_stale(tmp_path) -> None:
    store = DurableStore(tmp_path)
    child = _task_with_contract(store, title="Repair child")
    parent = store.create_task(title="Parent", depends_on=[child["task_id"]])
    store.lock_contract(parent["task_id"], _contract(), expected_version=parent["state_version"])
    store.write_recovery(parent["task_id"])
    assert store.recovery(parent["task_id"])["status"] == "fresh"

    (tmp_path / "result.txt").write_text("ok\n", encoding="utf-8")
    attempt = _sealed_attempt(store, child, plan="Repair dependency.")
    evaluation = store.verify_attempt(attempt["attempt_id"])
    store.accept_task(
        child["task_id"],
        terminal_evaluation_id=evaluation["evaluation_id"],
        expected_version=store.get_task(child["task_id"])["state_version"],
    )

    stale = store.recovery(parent["task_id"])
    assert stale["status"] == "stale"
    assert stale["task"]["readiness"] == "ready"
    assert stale["current_source"]["dependency_refs"][0]["lifecycle_status"] == "completed"


def test_dependency_cycles_are_rejected(tmp_path) -> None:
    store = DurableStore(tmp_path)
    first = store.create_task(title="First")
    second = store.create_task(title="Second", depends_on=[first["task_id"]])
    with pytest.raises(ValueError, match="cycle"):
        store.add_dependency(first["task_id"], second["task_id"], expected_version=first["state_version"])


def test_repair_origin_dependency_removal_and_thread_assignment_are_inspectable(tmp_path) -> None:
    store = DurableStore(tmp_path)
    parent = _task_with_contract(store, title="Parent")
    origin = store.record_decision(
        scope="task",
        task_id=parent["task_id"],
        event_type="defect_found",
        summary="A repair branch is required.",
    )
    child = store.create_task(
        title="Repair",
        parent_task_id=parent["task_id"],
        spawned_by_event_id=origin["event_id"],
    )
    assert store.get_task(child["task_id"])["spawned_by_event_id"] == origin["event_id"]

    parent = store.add_dependency(
        parent["task_id"],
        child["task_id"],
        expected_version=store.get_task(parent["task_id"])["state_version"],
    )
    parent = store.remove_dependency(
        parent["task_id"],
        child["task_id"],
        expected_version=parent["state_version"],
    )
    assert child["task_id"] not in parent["depends_on"]

    assigned = store.assign_thread("thread-review", child["task_id"])
    assert assigned["focus_stack"] == []
    assert store.get_thread_assignment("thread-review")["task_id"] == child["task_id"]
    assert store.list_thread_assignments()[0]["thread_id"] == "thread-review"


def test_decision_event_references_cannot_cross_task_boundaries(tmp_path) -> None:
    store = DurableStore(tmp_path)
    first = _task_with_contract(store, title="First")
    second = _task_with_contract(store, title="Second")
    attempt = store.start_attempt(
        second["task_id"],
        plan="Work on second.",
        input_snapshot={},
        expected_version=second["state_version"],
    )
    with pytest.raises(ValueError, match="different Task"):
        store.record_decision(
            scope="task",
            task_id=first["task_id"],
            attempt_id=attempt["attempt_id"],
            event_type="invalid",
            summary="Wrong subject.",
        )
    with pytest.raises(NotFoundError, match="Evaluation not found"):
        store.record_decision(
            scope="task",
            task_id=first["task_id"],
            evaluation_id="evaluation_missing",
            event_type="invalid",
            summary="Missing subject.",
        )


def test_mixed_manual_authorities_all_must_approve_one_chain(tmp_path) -> None:
    store = DurableStore(tmp_path)
    task = store.create_task(title="Mixed authority")
    contract = _contract(manual=True)
    contract["verification_spec"]["validators"].append(
        {
            "type": "manual_acceptance",
            "mode": "manual",
            "severity": "blocking",
            "authority": "user",
            "description": "User-only acceptance.",
        }
    )
    store.lock_contract(task["task_id"], contract, expected_version=task["state_version"])
    task = store.get_task(task["task_id"])
    attempt = _sealed_attempt(store, task)
    verification = store.verify_attempt(attempt["attempt_id"])
    assert verification["payload"]["required_authorities"] == ["reviewer", "user"]

    user_only = store.review_evaluation(
        verification["evaluation_id"],
        decision="approved",
        reviewer="task-owner",
        authority="user",
    )
    with pytest.raises(InvalidTransitionError, match="reviewer"):
        store.accept_task(
            task["task_id"],
            terminal_evaluation_id=user_only["evaluation_id"],
            expected_version=store.get_task(task["task_id"])["state_version"],
        )

    reviewed = store.review_evaluation(
        verification["evaluation_id"],
        decision="approved",
        reviewer="independent-reviewer",
    )
    pending_user = store.get_task(task["task_id"])
    assert pending_user["readiness"] == "waiting_review"
    assert pending_user["pending_authorities"] == ["user"]
    accepted_by_user = store.review_evaluation(
        reviewed["evaluation_id"],
        decision="approved",
        reviewer="task-owner",
        authority="user",
    )
    assert store.get_task(task["task_id"])["readiness"] == "ready_to_accept"
    completed = store.accept_task(
        task["task_id"],
        terminal_evaluation_id=accepted_by_user["evaluation_id"],
        expected_version=store.get_task(task["task_id"])["state_version"],
    )
    assert completed["lifecycle_status"] == "completed"


def test_ready_to_accept_prevents_duplicate_attempt_guidance_and_recovery_resolves_chain(tmp_path) -> None:
    store = DurableStore(tmp_path)
    task = _task_with_contract(store)
    (tmp_path / "result.txt").write_text("ok\n", encoding="utf-8")
    attempt = _sealed_attempt(store, task)
    evaluation = store.verify_attempt(attempt["attempt_id"])
    task = store.get_task(task["task_id"])
    assert task["readiness"] == "ready_to_accept"
    assert task["acceptance_candidate_id"] == evaluation["evaluation_id"]
    store.accept_task(
        task["task_id"],
        terminal_evaluation_id=evaluation["evaluation_id"],
        expected_version=task["state_version"],
    )
    store.write_recovery(task["task_id"])
    chain = store.recovery(task["task_id"])["acceptance_chain"]
    assert chain[0]["evaluation_id"] == evaluation["evaluation_id"]


def test_cancelled_task_cannot_be_revived_by_old_evaluation_and_accept_is_idempotent(tmp_path) -> None:
    store = DurableStore(tmp_path)
    task = _task_with_contract(store)
    (tmp_path / "result.txt").write_text("ok\n", encoding="utf-8")
    attempt = _sealed_attempt(store, task)
    evaluation = store.verify_attempt(attempt["attempt_id"])
    cancelled = store.transition_task(
        task["task_id"],
        lifecycle="cancelled",
        expected_version=store.get_task(task["task_id"])["state_version"],
    )
    with pytest.raises(InvalidTransitionError, match="cancelled"):
        store.accept_task(
            task["task_id"],
            terminal_evaluation_id=evaluation["evaluation_id"],
            expected_version=cancelled["state_version"],
        )

    other = _task_with_contract(store, title="Idempotent")
    attempt = _sealed_attempt(store, other, plan="Complete idempotently.")
    evaluation = store.verify_attempt(attempt["attempt_id"])
    completed = store.accept_task(
        other["task_id"],
        terminal_evaluation_id=evaluation["evaluation_id"],
        expected_version=store.get_task(other["task_id"])["state_version"],
    )
    repeated = store.accept_task(
        other["task_id"],
        terminal_evaluation_id=evaluation["evaluation_id"],
        expected_version=completed["state_version"],
    )
    assert repeated["state_version"] == completed["state_version"]


def test_legacy_migration_never_promotes_unbound_review(tmp_path) -> None:
    metaloop = tmp_path / ".metaloop"
    metaloop.mkdir()
    (metaloop / "mission_capsule.json").write_text(
        json.dumps({"intent": "Legacy task", "verification_spec": {"validators": []}}), encoding="utf-8"
    )
    (metaloop / "execution_report.json").write_text(json.dumps({"status": "completed", "commands": []}), encoding="utf-8")
    (metaloop / "verification_result.json").write_text(json.dumps({"status": "completed_verified"}), encoding="utf-8")
    (metaloop / "review_result.json").write_text(json.dumps({"decision": "approved"}), encoding="utf-8")

    store = DurableStore(tmp_path)
    migrated = store.migrate_legacy()
    evaluation = store.get_evaluation(migrated["evaluation_id"])

    assert migrated["legacy_bound"] is False
    assert evaluation["decision"] == "legacy_unbound"
    with pytest.raises(InvalidTransitionError):
        store.accept_task(
            migrated["task_id"],
            terminal_evaluation_id=evaluation["evaluation_id"],
            expected_version=store.get_task(migrated["task_id"])["state_version"],
        )


def _write_verified_v1_workspace(path: Path) -> None:
    assert cli_main(
        [
            "--workspace",
            str(path),
            "design",
            "--intent",
            "Import a valid legacy execution",
            "--rationale",
            "Exercise migration binding.",
            "--non-goal",
            "Do not trust matching strings alone.",
            "--command",
            "true",
        ]
    ) == 0
    assert cli_main(["--workspace", str(path), "run", "--command", "true"]) == 0
    assert cli_main(["--workspace", str(path), "verify", "--json"]) == 0


def test_legacy_migration_rejects_matching_forged_execution_hashes(tmp_path) -> None:
    _write_verified_v1_workspace(tmp_path)
    execution_path = tmp_path / ".metaloop" / "execution_report.json"
    verification_path = tmp_path / ".metaloop" / "verification_result.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    execution["execution_id"] = "execution_forged"
    execution["execution_hash"] = "not-a-content-hash"
    verification["execution_id"] = execution["execution_id"]
    verification["execution_hash"] = execution["execution_hash"]
    verification["status"] = "completed_verified"
    execution_path.write_text(json.dumps(execution), encoding="utf-8")
    verification_path.write_text(json.dumps(verification), encoding="utf-8")

    migrated = DurableStore(tmp_path).migrate_legacy()

    assert migrated["legacy_bound"] is False
    assert any("execution_hash" in item for item in migrated["legacy_validation"]["errors"])
    assert DurableStore(tmp_path).get_evaluation(migrated["evaluation_id"])["decision"] == "legacy_unbound"


def test_valid_legacy_migration_reverifies_and_binds_exact_execution(tmp_path) -> None:
    _write_verified_v1_workspace(tmp_path)
    store = DurableStore(tmp_path)

    migrated = store.migrate_legacy()

    assert migrated["legacy_bound"] is True
    assert migrated["legacy_validation"]["recomputed_status"] == "completed_verified"
    assert store.get_evaluation(migrated["evaluation_id"])["decision"] == "approved"
    assert store.get_task(migrated["task_id"])["readiness"] == "ready_to_accept"


def test_legacy_migration_rolls_back_partial_task_and_can_retry(tmp_path, monkeypatch) -> None:
    _write_verified_v1_workspace(tmp_path)
    store = DurableStore(tmp_path)
    original = store._insert_evaluation

    def fail_evaluation(*args, **kwargs):
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(store, "_insert_evaluation", fail_evaluation)
    with pytest.raises(RuntimeError, match="injected migration failure"):
        store.migrate_legacy()
    assert store.list_tasks() == []

    monkeypatch.setattr(store, "_insert_evaluation", original)
    migrated = store.migrate_legacy()
    assert migrated["legacy_bound"] is True


def test_exported_projections_are_rebuildable_and_source_bound(tmp_path) -> None:
    store = DurableStore(tmp_path)
    task = _task_with_contract(store)
    event = store.record_decision(
        scope="project",
        event_type="architecture",
        summary="Keep SQLite canonical.",
        decision="locked",
    )
    store.write_recovery(task["task_id"])
    target = store.export_project()

    task_dir = target / "tasks" / task["task_id"]
    head = json.loads((task_dir / "recovery_head.json").read_text(encoding="utf-8"))
    assert (target / "project.json").exists()
    assert head["status"] == "fresh"
    assert head["source_hash"]
    assert (task_dir / "resume.md").exists()
    assert any(item["event_id"] == event["event_id"] for item in json.loads((target / "events.json").read_text(encoding="utf-8")))
    assert (task_dir / "events.json").exists()
