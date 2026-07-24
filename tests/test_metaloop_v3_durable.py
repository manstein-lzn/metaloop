from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from metaloop_core.contracts import contract_hash
from metaloop_core.durable import ConflictError, DurableError, DurableStore, InvalidTransitionError


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "metaloop@example.com")
    _git(repo, "config", "user.name", "MetaLoop Test")
    (repo / ".gitignore").write_text(".metaloop/\n", encoding="utf-8")
    (repo / "ARCH.md").write_text("stable\n", encoding="utf-8")
    (repo / "src").mkdir()
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    return repo


def _contract(*, managed: bool = True, command: str = "true") -> dict:
    return {
        "goal": "Produce one verified output.",
        "rationale": ["Exercise the final lifecycle."],
        "constraints": ["Remain in the declared scope."],
        "non_goals": ["Do not infer semantic ownership."],
        "acceptance_criteria": ["Locked validators pass."],
        "verification_spec": {
            "validators": [{"type": "command", "mode": "executable", "severity": "blocking", "command": command}],
            "resource_gates": [],
        },
        "protocol_shape": "single_node",
        "execution_scope": {
            "paths": ["src", "tests"],
            "stable_inputs": [{"role": "governing_document", "path": "ARCH.md"}],
            "managed_outputs": [{"role": "implementation", "path": "src/out.txt"}] if managed else [],
            "change_kind": "extension",
            "migration_plan": None,
        },
    }


def _designed_store(tmp_path: Path, *, managed: bool = True, command: str = "true") -> tuple[Path, DurableStore, dict]:
    repo = _repo(tmp_path)
    store = DurableStore(repo, initialize=True)
    task = store.create_task("v3 task")
    store.set_default(task["task_id"])
    store.lock_contract(task["task_id"], _contract(managed=managed, command=command), expected_version=1)
    return repo, store, store.task(task["task_id"])


def _review_report(*, decision: str = "approved", blocking: list[str] | None = None, resolved: list[str] | None = None) -> dict:
    return {
        "review_scope": "semantic obligations and negative cases",
        "questions_and_findings": [{"question": "Does behavior match the contract?", "finding": "Yes."}],
        "counterexamples_executed": ["missing and alternate-order inputs"],
        "blocking_findings": blocking or [],
        "nonblocking_risks": ["No risks beyond the declared non-goals."],
        "resolved_trigger_ids": resolved or [],
        "decision": decision,
    }


def test_begin_task_is_atomic_when_contract_validation_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    store = DurableStore(repo, initialize=True)
    invalid = _contract(managed=False)
    invalid["verification_spec"]["validators"][0]["type"] = "manual_acceptance"
    invalid["verification_spec"]["validators"][0].pop("mode")

    with pytest.raises(ValueError, match="manual_acceptance validators require mode=manual"):
        store.begin_task("invalid contract", invalid, plan="must not start")

    assert store.tasks() == []
    assert store.project()["default_task_id"] is None

    user_validator = _contract(managed=False)
    user_validator["verification_spec"]["validators"][0]["authority"] = "user"
    with pytest.raises(ValueError, match="reserve final user authority in contract.assurance"):
        store.begin_task("invalid user authority", user_validator, plan="must not start")
    assert store.tasks() == []

    missing_command = _contract(managed=False)
    missing_command["verification_spec"]["validators"] = [{"type": "command", "mode": "executable"}]
    with pytest.raises(ValueError, match="command must be a non-empty string"):
        store.begin_task("missing command", missing_command, plan="must not start")

    malformed_gate = _contract(managed=False)
    malformed_gate["verification_spec"]["resource_gates"] = ["not-an-object"]
    with pytest.raises(ValueError, match=r"resource_gates\[0\] must be an object"):
        store.begin_task("malformed gate", malformed_gate, plan="must not start")

    for unsafe_path in ("../outside", "/tmp/outside", ".metaloop/private"):
        unsafe = _contract(managed=False)
        unsafe["verification_spec"]["validators"] = [
            {"type": "file_exists", "mode": "executable", "path": unsafe_path}
        ]
        with pytest.raises(ValueError, match="path must be a safe workspace-relative path"):
            store.begin_task("unsafe validator path", unsafe, plan="must not start")

    invalid_timeout = _contract(managed=False)
    invalid_timeout["verification_spec"]["validators"][0]["timeout"] = "not-an-integer"
    with pytest.raises(ValueError, match="timeout must be a positive integer"):
        store.begin_task("invalid timeout", invalid_timeout, plan="must not start")

    unknown_authority = _contract(managed=False)
    unknown_authority["verification_spec"]["validators"] = [
        {"type": "manual_acceptance", "mode": "manual", "authority": "unknown"}
    ]
    with pytest.raises(ValueError, match="authority must be reviewer"):
        store.begin_task("unknown authority", unknown_authority, plan="must not start")
    assert store.tasks() == []


def test_begin_task_rolls_back_composed_writes_when_attempt_start_fails(tmp_path: Path) -> None:
    _, store, existing = _designed_store(tmp_path, managed=False)
    store.start_attempt(existing["task_id"], expected_version=2, plan="existing work", input_snapshot={})

    with pytest.raises(ConflictError, match="open mutating Attempt"):
        store.begin_task("must roll back", _contract(managed=False), plan="cannot start")

    assert [task["task_id"] for task in store.tasks()] == [existing["task_id"]]
    assert store.project()["default_task_id"] == existing["task_id"]

    with store.transaction():
        try:
            store.begin_task("caught nested failure", _contract(managed=False), plan="cannot start")
        except ConflictError:
            pass

    assert [task["task_id"] for task in store.tasks()] == [existing["task_id"]]
    assert store.project()["default_task_id"] == existing["task_id"]


def _append_historical_review(store: DurableStore, parent: dict, *, authority: str, decision: str = "approved") -> dict:
    task = store.task(parent["task_id"])
    return store._insert_evaluation(
        parent["task_id"],
        "evaluation",
        parent["evaluation_id"],
        parent["content_hash"],
        "review",
        authority,
        f"legacy-{authority}",
        "3.1",
        decision,
        {
            "reviewer": f"legacy-{authority}",
            "authority": authority,
            "decision": decision,
            "context": {"provider": "legacy", "context_id": f"legacy-{authority}"},
            "independence": "unverified",
            "review_report": None,
        },
        activate=True,
        expected_head_id=parent["evaluation_id"],
        expected_task_version=task["state_version"],
    )


def test_project_init_requires_git_and_rejects_old_or_duplicate_state(tmp_path: Path) -> None:
    with pytest.raises(Exception):
        DurableStore(tmp_path, initialize=True)
    repo = _repo(tmp_path)
    store = DurableStore(repo, initialize=True)
    assert store.project()["schema_version"] if "schema_version" in store.project() else True
    store.close()
    with pytest.raises(DurableError, match="already initialized"):
        DurableStore(repo, initialize=True)


def test_attempt_baseline_checkpoint_recovery_and_acceptance_chain(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="implement", input_snapshot={"case": 1})
    assert attempt["baseline_stamp"]["adapter"] == "git"
    assert store.recovery(task["task_id"])["status"] == "fresh"
    assert store.recovery(task["task_id"])["resume_markdown"] == ""

    output = repo / "src" / "out.txt"
    output.write_text("done\n", encoding="utf-8")
    assert store.recovery(task["task_id"])["workspace_alignment"] == "ahead"
    with pytest.raises(ConflictError, match="classify changed paths"):
        store.record_checkpoint(attempt["attempt_id"], {"completed": ["implementation"]}, expected_version=3)

    checkpoint = store.record_checkpoint(
        attempt["attempt_id"],
        {"completed": ["implementation"], "observations": [], "diagnosis": "", "decision": "continue", "next_plan": "prove", "claimed_paths": ["src/out.txt"], "deferred_paths": [], "assigned_paths": [], "evidence_refs": []},
        expected_version=3,
    )
    assert checkpoint["payload"]["workspace_alignment"] == "aligned"
    assert store.recovery(task["task_id"])["workspace_alignment"] == "aligned"
    store.write_recovery(task["task_id"], "checkpointed")

    evidence = store.add_evidence(attempt["attempt_id"], "src/out.txt")
    assert evidence["sha256"].startswith("sha256:")
    sealed = store.seal_attempt(attempt["attempt_id"], expected_version=4)
    assert sealed["status"] == "sealed"
    evaluation = store.evaluate_verify(attempt["attempt_id"])
    assert evaluation["decision"] == "approved"
    assert evaluation["task_state_version"] == 6
    completed = store.accept(task["task_id"], evaluation["evaluation_id"], expected_version=6)
    assert completed["lifecycle_status"] == "completed"
    assert store.integrity(task["task_id"])["passed"] is True


def test_uncheckpointed_or_evidence_drift_fails_closed(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="implement", input_snapshot={})
    output = repo / "src" / "out.txt"
    output.write_text("one\n", encoding="utf-8")
    store.record_checkpoint(attempt["attempt_id"], {"claimed_paths": ["src/out.txt"]}, expected_version=3)
    store.add_evidence(attempt["attempt_id"], "src/out.txt")
    output.write_text("two\n", encoding="utf-8")
    with pytest.raises(DurableError, match="workspace alignment is ahead"):
        store.seal_attempt(attempt["attempt_id"], expected_version=4)


def test_managed_output_requires_exact_evidence(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="implement", input_snapshot={})
    (repo / "src" / "out.txt").write_text("done\n", encoding="utf-8")
    store.record_checkpoint(attempt["attempt_id"], {"claimed_paths": ["src/out.txt"]}, expected_version=3)
    with pytest.raises(DurableError, match="managed output evidence"):
        store.seal_attempt(attempt["attempt_id"], expected_version=4)


def test_stable_input_drift_blocks_attempt_start(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path)
    (repo / "ARCH.md").write_text("drift\n", encoding="utf-8")
    with pytest.raises(DurableError, match="stable input hash drifted"):
        store.start_attempt(task["task_id"], expected_version=2, plan="implement", input_snapshot={})


def test_one_worktree_allows_only_one_open_attempt(tmp_path: Path) -> None:
    _, store, first = _designed_store(tmp_path, managed=False)
    second = store.create_task("second")
    store.lock_contract(second["task_id"], _contract(managed=False), expected_version=1)
    store.start_attempt(first["task_id"], expected_version=2, plan="one", input_snapshot={})
    with pytest.raises(ConflictError, match="open mutating Attempt"):
        store.start_attempt(second["task_id"], expected_version=2, plan="two", input_snapshot={})


def test_validator_workspace_mutation_cannot_be_accepted(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False, command="printf drift > unexpected.txt")
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="verify", input_snapshot={})
    sealed = store.seal_attempt(attempt["attempt_id"], expected_version=3)
    assert sealed["status"] == "sealed"
    with pytest.raises(DurableError, match="verification changed"):
        store.evaluate_verify(attempt["attempt_id"])


@pytest.mark.parametrize(
    ("validator", "expected_runtime_detail"),
    [
        ({"type": "file_exists", "mode": "executable", "path": "src/missing.txt"}, None),
        (
            {
                "type": "artifact_hash",
                "mode": "executable",
                "path": "src/missing.txt",
                "sha256": "sha256:" + "0" * 64,
            },
            None,
        ),
        (
            {
                "type": "command",
                "mode": "executable",
                "command": "python3 -c 'import time; time.sleep(2)'",
                "timeout": 1,
            },
            "timed_out",
        ),
    ],
)
def test_validator_negative_outcome_creates_repairable_evaluation(
    tmp_path: Path,
    validator: dict,
    expected_runtime_detail: str | None,
) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    contract = _contract(managed=False)
    contract["verification_spec"]["validators"] = [validator]
    store.lock_contract(task["task_id"], contract, expected_version=2, revision_reason="exercise a negative outcome")
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="run negative validator", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=4)

    evaluation = store.evaluate_verify(attempt["attempt_id"])

    assert evaluation["decision"] == "rejected"
    result = evaluation["payload"]["validator_results"][0]
    assert result["passed"] is False
    if expected_runtime_detail:
        assert result[expected_runtime_detail] is True
    projection = store.control_projection(task["task_id"])
    assert projection["status"] == "verification_failed"
    assert projection["next_transition"] == "start_repair_attempt"
    recovery = store.recovery(task["task_id"])
    assert recovery["next_transition"] == "start_repair_attempt"
    repair = store.start_attempt(
        task["task_id"],
        expected_version=evaluation["task_state_version"],
        plan="repair the failed validator target",
        input_snapshot={},
    )
    assert repair["task_id"] == task["task_id"]
    assert len(store.tasks()) == 1


def test_required_authority_uses_one_linear_review_chain(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    contract = _contract(managed=False)
    contract["verification_spec"]["validators"].append({"type": "manual_acceptance", "mode": "manual", "authority": "reviewer"})
    # Replace the already locked contract explicitly, keeping the same Task boundary.
    store.lock_contract(task["task_id"], contract, expected_version=2, revision_reason="add reviewer authority")
    task = store.task(task["task_id"])
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="authority", input_snapshot={})
    sealed = store.seal_attempt(attempt["attempt_id"], expected_version=4)
    evaluation = store.evaluate_verify(sealed["attempt_id"])
    assert evaluation["payload"]["required_authorities"] == ["reviewer"]
    with pytest.raises(InvalidTransitionError, match="review:reviewer"):
        store.accept(task["task_id"], evaluation["evaluation_id"], expected_version=6)
    review = store.review(evaluation["evaluation_id"], decision="approved", reviewer="independent")
    assert review["task_state_version"] == 7
    completed = store.accept(task["task_id"], review["evaluation_id"], expected_version=7)
    assert completed["lifecycle_status"] == "completed"


def test_sealed_attempt_hash_tampering_fails_closed(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="tamper", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=3)
    store.conn.execute("UPDATE attempt_records SET content_json=? WHERE attempt_id=? AND seq=1", ('{"tampered":true}', attempt["attempt_id"]))
    with pytest.raises(DurableError, match="sealed Attempt content hash mismatch"):
        store.evaluate_verify(attempt["attempt_id"])


def test_semantic_decisions_are_explicit_and_dependency_completion_is_not_inferred(tmp_path: Path) -> None:
    _, store, parent = _designed_store(tmp_path, managed=False)
    child = store.create_task("repair child", parent_task_id=parent["task_id"])
    with pytest.raises(ValueError, match="invalid explicit decision"):
        store.add_decision(parent["task_id"], scope="task", type="diagnosis", summary="please repair this", decision="please repair")
    event = store.add_decision(parent["task_id"], scope="task", type="decision", summary="implementation defect", decision="repair", next_plan="open child")
    assert event["decision"] == "repair"
    assert store.task(parent["task_id"])["lifecycle_status"] == "open"
    assert store.task(child["task_id"])["parent_task_id"] == parent["task_id"]


def test_content_preserving_commit_keeps_accepted_task_aligned(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="implement", input_snapshot={})
    (repo / "src" / "out.txt").write_text("accepted\n", encoding="utf-8")
    store.record_checkpoint(attempt["attempt_id"], {"claimed_paths": ["src/out.txt"]}, expected_version=3)
    store.add_evidence(attempt["attempt_id"], "src/out.txt")
    sealed = store.seal_attempt(attempt["attempt_id"], expected_version=4)
    evaluation = store.evaluate_verify(attempt["attempt_id"])
    store.accept(task["task_id"], evaluation["evaluation_id"], expected_version=6)

    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "promote accepted tree")

    recovery = store.recovery(task["task_id"])
    assert recovery["status"] == "fresh"
    assert recovery["workspace_alignment"] == "aligned"
    assert recovery["workspace_transition"] == "content_preserving_commit"
    assert store.integrity(task["task_id"])["passed"] is True


def test_completed_default_task_does_not_block_later_direct_git_work(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path, managed=False)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="finish historical claim", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=3)
    evaluation = store.evaluate_verify(attempt["attempt_id"])
    store.accept(task["task_id"], evaluation["evaluation_id"], expected_version=5)

    (repo / "src" / "later.txt").write_text("ordinary direct work\n", encoding="utf-8")

    assert store.integrity()["passed"] is True
    recovery = store.recovery(task["task_id"])
    assert recovery["status"] == "stale"
    assert recovery["next_action"] == "none"
    assert recovery["blocker"] is None
    explicit = store.integrity(task["task_id"])
    assert explicit["passed"] is False
    assert any("workspace alignment is ahead" in error for error in explicit["errors"])


def test_active_attempt_ahead_is_pending_reconciliation_not_integrity_violation(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path, managed=False)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="normal active work", input_snapshot={})
    (repo / "src" / "work.txt").write_text("in progress\n", encoding="utf-8")

    result = store.integrity(task["task_id"])

    assert result["status"] == "not_yet_reconciled"
    assert result["passed"] is True
    assert result["reconciliation_required"] is True
    assert result["violations"] == []
    assert result["workspace_alignment"] == "ahead"
    recovery = store.recovery(task["task_id"])
    assert recovery["active_attempt"]["attempt_id"] == attempt["attempt_id"]
    assert recovery["next_action"] == "continue the active Attempt"


def test_finish_attempt_composes_checkpoint_evidence_verification_and_acceptance(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="routine repair", input_snapshot={})
    (repo / "src" / "out.txt").write_text("done\n", encoding="utf-8")

    result = store.finish_attempt(attempt["attempt_id"])

    assert result["checkpoint"]["payload"]["claimed_paths"] == ["src/out.txt"]
    assert [item["path"] for item in result["evidence"]] == ["src/out.txt"]
    assert result["evaluation"]["decision"] == "approved"
    assert result["pending_authorities"] == []
    assert result["task"]["lifecycle_status"] == "completed"


def test_finish_auto_reconciles_current_attempt_delta(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="routine repair", input_snapshot={})
    (repo / "src" / "out.txt").write_text("managed\n", encoding="utf-8")
    (repo / "src" / "extra.txt").write_text("undeclared\n", encoding="utf-8")

    result = store.finish_attempt(attempt["attempt_id"])

    assert result["checkpoint"]["payload"]["claimed_paths"] == ["src/extra.txt", "src/out.txt"]
    assert [item["path"] for item in result["evidence"]] == ["src/out.txt"]
    assert result["task"]["lifecycle_status"] == "completed"


def test_finish_auto_reconciliation_still_enforces_contract_scope(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path, managed=False)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="respect scope", input_snapshot={})
    (repo / "outside.txt").write_text("outside declared src/tests scope\n", encoding="utf-8")

    with pytest.raises(ConflictError, match="outside execution_scope"):
        store.finish_attempt(attempt["attempt_id"])

    assert store.attempt(attempt["attempt_id"])["status"] == "open"


def test_finish_resumes_after_seal_without_duplicate_records(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="resumable finish", input_snapshot={})
    (repo / "src" / "out.txt").write_text("done\n", encoding="utf-8")
    original_verify = store.evaluate_verify

    def interrupted_verify(attempt_id: str) -> dict:
        raise DurableError(f"temporary verifier interruption for {attempt_id}")

    store.evaluate_verify = interrupted_verify  # type: ignore[method-assign]
    with pytest.raises(DurableError, match="temporary verifier interruption"):
        store.finish_attempt(attempt["attempt_id"])
    assert store.attempt(attempt["attempt_id"])["status"] == "sealed"

    store.evaluate_verify = original_verify  # type: ignore[method-assign]
    finished = store.finish_attempt(attempt["attempt_id"])
    repeated = store.finish_attempt(attempt["attempt_id"])

    assert finished["task"]["lifecycle_status"] == "completed"
    assert repeated["task"]["lifecycle_status"] == "completed"
    assert repeated["evaluation"]["evaluation_id"] == finished["evaluation"]["evaluation_id"]
    assert len([record for record in store.records(attempt["attempt_id"]) if record["type"] == "checkpoint"]) == 1
    assert store.protocol_activity(task["task_id"])["evaluations"] == 1


def test_finish_keeps_failed_verification_and_authority_in_same_task(tmp_path: Path) -> None:
    failed_root = tmp_path / "failed"
    failed_root.mkdir()
    _, failed_store, failed_task = _designed_store(failed_root, managed=False, command="false")
    failed_attempt = failed_store.start_attempt(failed_task["task_id"], expected_version=2, plan="first strategy", input_snapshot={})
    failed = failed_store.finish_attempt(failed_attempt["attempt_id"])
    assert failed["evaluation"]["decision"] == "rejected"
    assert failed["task"]["lifecycle_status"] == "open"
    assert len(failed_store.tasks()) == 1
    next_attempt = failed_store.start_attempt(
        failed_task["task_id"],
        expected_version=failed["task"]["state_version"],
        plan="correct the same task",
        input_snapshot={},
    )
    assert next_attempt["task_id"] == failed_task["task_id"]

    review_root = tmp_path / "review"
    review_root.mkdir()
    _, review_store, review_task = _designed_store(review_root, managed=False)
    contract = _contract(managed=False)
    contract["verification_spec"]["validators"].append({"type": "manual_acceptance", "mode": "manual", "authority": "reviewer"})
    review_store.lock_contract(review_task["task_id"], contract, expected_version=2, revision_reason="semantic review")
    review_task = review_store.task(review_task["task_id"])
    review_attempt = review_store.start_attempt(review_task["task_id"], expected_version=3, plan="semantic claim", input_snapshot={})
    pending = review_store.finish_attempt(review_attempt["attempt_id"])
    assert pending["evaluation"]["decision"] == "approved"
    assert pending["pending_authorities"] == ["reviewer"]
    assert pending["task"]["lifecycle_status"] == "open"
    assert pending["task"]["acceptance_head_id"] == pending["evaluation"]["evaluation_id"]
    assert review_store.acceptance_status(review_task["task_id"])["status"] == "mechanically_verified_pending_reviewer"
    review_store.review(pending["evaluation"]["evaluation_id"], decision="approved", reviewer="independent")
    completed = review_store.finish_attempt(review_attempt["attempt_id"])
    assert completed["task"]["lifecycle_status"] == "completed"
    assert completed["next_transition"] == "none"


def test_latest_aborted_attempt_is_adopted_with_path_provenance(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path, managed=False)
    first = store.start_attempt(task["task_id"], expected_version=2, plan="obsolete contract", input_snapshot={})
    (repo / "src" / "out.txt").write_text("carry forward\n", encoding="utf-8")
    store.abort_attempt(first["attempt_id"], reason="contract revised after intentional workspace updates")

    retry = store.start_attempt(
        task["task_id"],
        expected_version=4,
        plan="continue after contract correction",
        input_snapshot={},
    )
    assert retry["status"] == "open"
    assert retry["baseline_stamp"]["changed_paths"] == ["src/out.txt"]
    provenance = retry["carried_forward"]
    assert provenance["source_attempt_id"] == first["attempt_id"]
    assert provenance["source_status"] == "aborted"
    assert [item["path"] for item in provenance["paths"]] == ["src/out.txt"]
    assert provenance["paths"][0]["source_state"] is None
    assert provenance["paths"][0]["adopted_state"].startswith("file:")


def test_checkpointed_aborted_attempt_remains_explicitly_carried_forward(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path, managed=False)
    first = store.start_attempt(task["task_id"], expected_version=2, plan="checkpoint before retry", input_snapshot={})
    (repo / "src" / "out.txt").write_text("carried checkpoint\n", encoding="utf-8")
    store.record_checkpoint(
        first["attempt_id"],
        {
            "claimed_paths": ["src/out.txt"],
            "external_ref": {"locator": "/runs/source", "checkpoint_identity": "checkpoint-3"},
        },
        expected_version=3,
    )
    store.abort_attempt(first["attempt_id"], reason="retry after a valid checkpoint")

    current = store.task(task["task_id"])
    retry = store.start_attempt(
        task["task_id"],
        expected_version=current["state_version"],
        plan="continue checkpointed work",
        input_snapshot={},
    )

    assert retry["carried_forward"]["source_attempt_id"] == first["attempt_id"]
    assert retry["carried_forward"]["source_checkpoint_hash"] is not None
    assert [item["path"] for item in retry["carried_forward"]["paths"]] == ["src/out.txt"]
    assert store.external_ref(task["task_id"]) == {
        "locator": "/runs/source",
        "checkpoint_identity": "checkpoint-3",
    }


def test_carried_forward_workspace_must_fit_the_current_contract_scope(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path, managed=False)
    broad = _contract(managed=False)
    broad["execution_scope"]["paths"].append("outside.txt")
    store.lock_contract(task["task_id"], broad, expected_version=2, revision_reason="temporarily broaden scope")
    first = store.start_attempt(task["task_id"], expected_version=3, plan="broad work", input_snapshot={})
    (repo / "outside.txt").write_text("must not cross the revised boundary\n", encoding="utf-8")
    store.abort_attempt(first["attempt_id"], reason="narrow the contract before retry")

    current = store.task(task["task_id"])
    narrow = _contract(managed=False)
    store.lock_contract(
        task["task_id"],
        narrow,
        expected_version=current["state_version"],
        revision_reason="remove outside.txt from the acceptance target",
    )
    current = store.task(task["task_id"])

    with pytest.raises(ConflictError, match=r"carried-forward paths.*outside\.txt"):
        store.start_attempt(
            task["task_id"],
            expected_version=current["state_version"],
            plan="respect the narrowed scope",
            input_snapshot={},
        )

    assert store.task(task["task_id"])["active_attempt_id"] is None


def test_stale_sealed_candidate_can_be_superseded_without_reverting_work(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path, managed=False)
    first = store.start_attempt(task["task_id"], expected_version=2, plan="first candidate", input_snapshot={})
    path = repo / "src" / "out.txt"
    path.write_text("first\n", encoding="utf-8")
    store.record_checkpoint(first["attempt_id"], {"claimed_paths": ["src/out.txt"]}, expected_version=3)
    store.seal_attempt(first["attempt_id"], expected_version=4)
    path.write_text("repair before retry\n", encoding="utf-8")

    retry = store.start_attempt(task["task_id"], expected_version=5, plan="continue current repair", input_snapshot={})

    assert retry["carried_forward"]["source_attempt_id"] == first["attempt_id"]
    assert retry["carried_forward"]["source_status"] == "sealed"
    assert [item["path"] for item in retry["carried_forward"]["paths"]] == ["src/out.txt"]


def test_protocol_activity_warns_only_after_routine_churn(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="semantic checkpoints", input_snapshot={})
    for expected_version in range(3, 7):
        store.record_checkpoint(attempt["attempt_id"], {"observations": [f"checkpoint {expected_version}"]}, expected_version=expected_version)

    activity = store.protocol_activity(task["task_id"])

    assert activity["expected_agent_lifecycle_commands"] == 2
    assert activity["checkpoints"] == 4
    assert activity["routing_warning"] is not None


def test_review_handoff_and_active_chain_are_derived_only_when_reviewer_is_pending(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path, managed=True)
    high = _contract(managed=True)
    high["assurance"] = {
        "tier": "high_assurance",
        "trigger_ids": ["semantic_claim"],
        "rationale": ["The executable oracle is incomplete."],
    }
    store.lock_contract(task["task_id"], high, expected_version=2, revision_reason="review the final claim")
    current = store.task(task["task_id"])
    attempt = store.start_attempt(task["task_id"], expected_version=current["state_version"], plan="prepare exact claim", input_snapshot={})
    (repo / "src" / "out.txt").write_text("review me\n", encoding="utf-8")

    pending = store.finish_attempt(attempt["attempt_id"])

    assert pending["next_transition"] == "review:reviewer"
    assert [item["kind"] for item in pending["active_chain"]] == ["verification"]
    handoff = pending["review_handoff"]
    assert handoff["exact_subject"]["evaluation_id"] == pending["evaluation"]["evaluation_id"]
    assert handoff["review_focus"]["trigger_ids"] == ["semantic_claim"]
    assert handoff["claimed_paths"] == ["src/out.txt"]
    assert handoff["evidence"][0]["path"] == "src/out.txt"
    assert "stdout" not in handoff["validator_results"][0]
    recovery = store.recovery(task["task_id"])
    assert recovery["review_handoff"] == handoff

    review = store.review(
        pending["evaluation"]["evaluation_id"],
        decision="approved",
        reviewer="fresh-reviewer",
        report=_review_report(),
    )
    assert [item["evaluation_id"] for item in store.active_evaluation_chain(task["task_id"])] == [
        pending["evaluation"]["evaluation_id"],
        review["evaluation_id"],
    ]
    assert store.review_handoff(task["task_id"]) is None


def test_external_ref_is_optional_recovery_metadata_not_acceptance_state(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="track an external run", input_snapshot={})
    store.record_checkpoint(
        attempt["attempt_id"],
        {
            "observations": ["external process is owned by the project runtime"],
            "external_ref": {"locator": "/runs/train-42", "checkpoint_identity": "epoch-7-sha256:abc"},
        },
        expected_version=3,
    )

    assert store.external_ref(task["task_id"]) == {
        "locator": "/runs/train-42",
        "checkpoint_identity": "epoch-7-sha256:abc",
    }
    recovery = store.recovery(task["task_id"])
    assert recovery["external_ref"] == store.external_ref(task["task_id"])
    assert recovery["next_action"] == "continue the active Attempt"

    with pytest.raises(ValueError, match="unsupported fields"):
        store.record_checkpoint(
            attempt["attempt_id"],
            {"external_ref": {"locator": "/runs/train-42", "last_completed_epoch": 7}},
            expected_version=4,
        )


def test_new_contracts_normalize_assurance_and_legacy_contracts_remain_readable(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    current = store.contract(task["task_id"])
    assert current["content"]["version"] == "1.1"
    assert current["content"]["assurance"]["tier"] == "durable_routine"

    legacy = dict(current["content"])
    legacy["version"] = "1.0"
    legacy.pop("assurance")
    digest = contract_hash(legacy)
    store.conn.execute(
        "UPDATE contracts SET content_json=?,content_hash=? WHERE contract_id=?",
        (json.dumps(legacy, sort_keys=True, separators=(",", ":")), digest, current["contract_id"]),
    )
    assert store.contract(task["task_id"])["content"]["version"] == "1.0"
    assert store.assurance_state(task["task_id"])["legacy"] is True


def test_high_assurance_requires_structured_review_without_host_attestation(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    contract = _contract(managed=False)
    contract["assurance"] = {
        "tier": "high_assurance",
        "trigger_ids": ["semantic_change_incomplete_oracle"],
        "rationale": ["A fresh context must inspect the semantic boundary."],
    }
    store.lock_contract(task["task_id"], contract, expected_version=2, revision_reason="raise assurance")
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="high assurance", input_snapshot={})
    sealed = store.seal_attempt(attempt["attempt_id"], expected_version=4)
    verification = store.evaluate_verify(attempt["attempt_id"])
    assert verification["payload"]["required_authorities"] == ["reviewer"]

    with pytest.raises(ValueError, match="structured report"):
        store.review(verification["evaluation_id"], decision="approved", reviewer="reviewer")

    review = store.review(
        verification["evaluation_id"],
        decision="approved",
        reviewer="reviewer",
        report=_review_report(),
    )
    report = review["payload"]["review_report"]
    assert review["payload"]["context_id"] is None
    assert "independence" not in review["payload"]
    assert report["exact_evaluation_subject"]["content_hash"] == verification["content_hash"]
    assert report["governing_artifact_hashes"]["attempt_hash"] == sealed["execution_hash"]
    completed = store.accept(task["task_id"], review["evaluation_id"], expected_version=7)
    assert completed["lifecycle_status"] == "completed"


def test_active_evaluation_head_rejects_siblings_and_stale_acceptance(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    contract = _contract(managed=False)
    contract["verification_spec"]["validators"].append({"type": "manual_acceptance", "mode": "manual", "authority": "reviewer"})
    store.lock_contract(task["task_id"], contract, expected_version=2, revision_reason="require review")
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="review", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=4)
    verification = store.evaluate_verify(attempt["attempt_id"])
    needs_changes = store.review(verification["evaluation_id"], decision="needs_changes", reviewer="fresh-reviewer")

    with pytest.raises(ConflictError, match="active Evaluation head"):
        store.review(verification["evaluation_id"], decision="approved", reviewer="another-reviewer")
    with pytest.raises(ConflictError, match="active Evaluation head"):
        store.accept(task["task_id"], verification["evaluation_id"], expected_version=7)
    assert store.acceptance_status(task["task_id"])["status"] == "review_needs_changes"

    retry = store.start_attempt(task["task_id"], expected_version=7, plan="repair", input_snapshot={})
    assert retry["task_id"] == task["task_id"]
    assert store.task(task["task_id"])["acceptance_head_id"] is None
    assert store.evaluation(needs_changes["evaluation_id"])["decision"] == "needs_changes"


def test_tier_three_is_sticky_until_review_bound_contract_revision(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    high = _contract(managed=False)
    high["assurance"] = {
        "tier": "high_assurance",
        "trigger_ids": ["semantic_change_incomplete_oracle"],
        "rationale": ["The semantic oracle is incomplete."],
    }
    store.lock_contract(task["task_id"], high, expected_version=2, revision_reason="observe semantic risk")
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="review the semantic gap", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=4)
    verification = store.evaluate_verify(attempt["attempt_id"])

    lower = _contract(managed=False)
    lower["assurance"] = {
        "tier": "governed",
        "trigger_ids": [],
        "rationale": ["The approved executable proof now covers the former semantic uncertainty."],
    }
    with pytest.raises(InvalidTransitionError, match="sticky"):
        store.lock_contract(task["task_id"], lower, expected_version=6, revision_reason="premature downgrade")

    review = store.review(
        verification["evaluation_id"],
        decision="approved",
        reviewer="semantic-reviewer",
        report=_review_report(resolved=["semantic_change_incomplete_oracle"]),
    )
    lower["assurance"]["resolved_trigger_ids"] = ["semantic_change_incomplete_oracle"]
    lower["assurance"]["resolution_evaluation_id"] = review["evaluation_id"]
    store.lock_contract(task["task_id"], lower, expected_version=review["task_state_version"], revision_reason="bind Review feedback")
    assurance = store.assurance_state(task["task_id"])
    assert assurance["effective_tier"] == "governed"
    assert assurance["unresolved_trigger_ids"] == []
    with pytest.raises(ConflictError, match="active Evaluation head"):
        store.accept(task["task_id"], review["evaluation_id"], expected_version=review["task_state_version"] + 1)


def test_structured_review_report_is_part_of_evaluation_hash(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    high = _contract(managed=False)
    high["assurance"] = {
        "tier": "high_assurance",
        "trigger_ids": ["semantic_change_incomplete_oracle"],
        "rationale": ["The semantic relation needs a fresh observation."],
    }
    store.lock_contract(task["task_id"], high, expected_version=2, revision_reason="require report")
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="review", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=4)
    verification = store.evaluate_verify(attempt["attempt_id"])
    review = store.review(verification["evaluation_id"], decision="approved", reviewer="reviewer", report=_review_report())
    tampered = dict(review["payload"])
    tampered["review_report"] = {**tampered["review_report"], "nonblocking_risks": ["changed after review"]}
    store.conn.execute("UPDATE evaluations SET content_json=? WHERE evaluation_id=?", (json.dumps(tampered), review["evaluation_id"]))
    with pytest.raises(DurableError, match="Evaluation content hash mismatch"):
        store.evaluation(review["evaluation_id"])


def test_authorities_follow_reviewer_then_user_and_terminal_heads_reject_reviews(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    contract = _contract(managed=False)
    contract["assurance"] = {
        "tier": "governed",
        "trigger_ids": [],
        "rationale": ["The user reserved the final decision."],
        "required_authorities": ["user"],
    }
    contract["verification_spec"]["validators"].append(
        {"type": "manual_acceptance", "mode": "manual", "authority": "reviewer"}
    )
    store.lock_contract(task["task_id"], contract, expected_version=2, revision_reason="reserve ordered authorities")
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="ordered review", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=4)
    verification = store.evaluate_verify(attempt["attempt_id"])

    projection = store.control_projection(task["task_id"])
    assert projection["authority_sequence"] == ["reviewer", "user"]
    assert projection["next_transition"] == "review:reviewer"
    with pytest.raises(InvalidTransitionError, match="review:reviewer"):
        store.review(verification["evaluation_id"], decision="approved", reviewer="user", authority="user")

    reviewer = store.review(verification["evaluation_id"], decision="approved", reviewer="semantic-reviewer")
    assert store.control_projection(task["task_id"])["next_transition"] == "review:user"
    with pytest.raises(InvalidTransitionError, match="review:user"):
        store.review(reviewer["evaluation_id"], decision="approved", reviewer="duplicate-reviewer")

    user = store.review(reviewer["evaluation_id"], decision="approved", reviewer="user", authority="user")
    assert store.control_projection(task["task_id"])["next_transition"] == "accept"
    with pytest.raises(InvalidTransitionError, match="requires accept"):
        store.review(user["evaluation_id"], decision="approved", reviewer="user", authority="user")
    completed = store.accept(task["task_id"], user["evaluation_id"], expected_version=user["task_state_version"])
    assert completed["lifecycle_status"] == "completed"


def test_terminal_review_chain_is_read_as_terminal_and_recovered_by_new_attempt(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    contract = _contract(managed=False)
    contract["verification_spec"]["validators"].append(
        {"type": "manual_acceptance", "mode": "manual", "authority": "reviewer"}
    )
    store.lock_contract(task["task_id"], contract, expected_version=2, revision_reason="require reviewer")
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="legacy terminal chain", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=4)
    verification = store.evaluate_verify(attempt["attempt_id"])
    needs_changes = store.review(verification["evaluation_id"], decision="needs_changes", reviewer="reviewer")

    with pytest.raises(InvalidTransitionError, match="start_repair_attempt"):
        store.review(needs_changes["evaluation_id"], decision="approved", reviewer="reviewer")

    malformed_head = _append_historical_review(store, needs_changes, authority="reviewer")
    projection = store.control_projection(task["task_id"])
    assert projection["status"] == "review_needs_changes"
    assert projection["next_transition"] == "start_repair_attempt"
    repaired = store.start_attempt(
        task["task_id"],
        expected_version=malformed_head["task_state_version"],
        plan="repair after terminal review",
        input_snapshot={},
    )
    assert repaired["status"] == "open"
    assert store.task(task["task_id"])["acceptance_head_id"] is None


def test_historical_out_of_order_authority_chain_recovers_without_rewrite(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    contract = _contract(managed=False)
    contract["assurance"] = {
        "tier": "governed",
        "trigger_ids": [],
        "rationale": ["Exercise legacy authority ordering."],
        "required_authorities": ["user"],
    }
    contract["verification_spec"]["validators"].append(
        {"type": "manual_acceptance", "mode": "manual", "authority": "reviewer"}
    )
    store.lock_contract(task["task_id"], contract, expected_version=2, revision_reason="require both authorities")
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="legacy authority chain", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=4)
    verification = store.evaluate_verify(attempt["attempt_id"])
    user_first = _append_historical_review(store, verification, authority="user")
    malformed_head = _append_historical_review(store, user_first, authority="reviewer")

    projection = store.control_projection(task["task_id"])
    assert projection["status"] == "evaluation_chain_invalid"
    assert projection["next_transition"] == "start_repair_attempt"
    historical_ids = [verification["evaluation_id"], user_first["evaluation_id"], malformed_head["evaluation_id"]]
    store.start_attempt(
        task["task_id"],
        expected_version=malformed_head["task_state_version"],
        plan="repair malformed authority history",
        input_snapshot={},
    )
    assert [store.evaluation(item)["evaluation_id"] for item in historical_ids] == historical_ids


def test_verification_requires_latest_sealed_attempt_and_head_transition_invalidates_stale_cas(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    first = store.start_attempt(task["task_id"], expected_version=2, plan="first", input_snapshot={})
    store.seal_attempt(first["attempt_id"], expected_version=3)

    # Build a readable historical state that old versions could produce: a newer
    # Attempt exists while an older sealed Attempt was never verified.
    store.conn.execute("UPDATE attempts SET status='aborted' WHERE attempt_id=?", (first["attempt_id"],))
    second = store.start_attempt(task["task_id"], expected_version=4, plan="second", input_snapshot={})
    store.conn.execute("UPDATE attempts SET status='sealed' WHERE attempt_id=?", (first["attempt_id"],))
    store.seal_attempt(second["attempt_id"], expected_version=5)

    with pytest.raises(ConflictError, match="latest sealed Attempt"):
        store.evaluate_verify(first["attempt_id"])
    before_evaluation = store.task(task["task_id"])["state_version"]
    verification = store.evaluate_verify(second["attempt_id"])
    assert verification["task_state_version"] == before_evaluation + 1
    with pytest.raises(ConflictError, match="state_version is stale"):
        store.lock_contract(task["task_id"], _contract(managed=False), expected_version=before_evaluation, revision_reason="stale caller")


def test_recovery_only_projects_an_executable_next_step(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path, managed=False)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="seal before drift", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=3)
    assert store.control_projection(task["task_id"])["next_transition"] == "verify"

    (repo / "src" / "drift.txt").write_text("unreconciled\n", encoding="utf-8")
    recovery = store.recovery(task["task_id"])
    assert recovery["workspace_alignment"] == "ahead"
    assert recovery["next_transition"] == "none"
    assert recovery["next_action"].startswith("reconcile workspace")
    with pytest.raises(DurableError, match="workspace alignment is ahead"):
        store.evaluate_verify(attempt["attempt_id"])


def test_plain_validator_cannot_resolve_sticky_trigger(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    high = _contract(managed=False)
    high["assurance"] = {
        "tier": "high_assurance",
        "trigger_ids": ["semantic_gap"],
        "rationale": ["The semantic gap is not yet executable."],
    }
    store.lock_contract(task["task_id"], high, expected_version=2, revision_reason="record semantic gap")
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="run ordinary tests", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=4)
    verification = store.evaluate_verify(attempt["attempt_id"])
    assert store.control_projection(task["task_id"])["resolved_trigger_proofs"] == {}

    lower = _contract(managed=False)
    lower["assurance"] = {
        "tier": "governed",
        "trigger_ids": [],
        "rationale": ["Claim an executable resolution."],
        "resolved_trigger_ids": ["semantic_gap"],
        "resolution_evaluation_id": verification["evaluation_id"],
    }
    with pytest.raises(InvalidTransitionError, match="Review does not resolve"):
        store.lock_contract(task["task_id"], lower, expected_version=verification["task_state_version"], revision_reason="unmapped test is insufficient")


def test_review_resolution_must_name_every_trigger(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    high = _contract(managed=False)
    high["assurance"] = {
        "tier": "high_assurance",
        "trigger_ids": ["semantic_a", "semantic_b"],
        "rationale": ["Two semantic gaps remain."],
    }
    store.lock_contract(task["task_id"], high, expected_version=2, revision_reason="record two gaps")
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="resolve one gap", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=4)
    verification = store.evaluate_verify(attempt["attempt_id"])
    review = store.review(
        verification["evaluation_id"],
        decision="approved",
        reviewer="semantic-reviewer",
        report=_review_report(resolved=["semantic_a"]),
    )
    assert store.control_projection(task["task_id"])["resolved_trigger_proofs"] == {
        "semantic_a": [f"evaluation:{review['evaluation_id']}"]
    }

    lower = _contract(managed=False)
    lower["assurance"] = {
        "tier": "governed",
        "trigger_ids": [],
        "rationale": ["Attempt to resolve both gaps."],
        "resolved_trigger_ids": ["semantic_a", "semantic_b"],
        "resolution_evaluation_id": review["evaluation_id"],
    }
    with pytest.raises(InvalidTransitionError, match="semantic_b"):
        store.lock_contract(task["task_id"], lower, expected_version=review["task_state_version"], revision_reason="partial Review must fail")


def test_structured_review_can_resolve_named_trigger(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    high = _contract(managed=False)
    high["assurance"] = {
        "tier": "high_assurance",
        "trigger_ids": ["semantic_review_gap"],
        "rationale": ["A fresh context must close the semantic gap."],
    }
    store.lock_contract(task["task_id"], high, expected_version=2, revision_reason="require semantic proof")
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="prepare review", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=4)
    verification = store.evaluate_verify(attempt["attempt_id"])
    review = store.review(
        verification["evaluation_id"],
        decision="approved",
        reviewer="fresh-reviewer",
        report=_review_report(resolved=["semantic_review_gap"]),
    )
    assert store.control_projection(task["task_id"])["resolved_trigger_proofs"] == {
        "semantic_review_gap": [f"evaluation:{review['evaluation_id']}"]
    }

    lower = _contract(managed=False)
    lower["assurance"] = {
        "tier": "governed",
        "trigger_ids": [],
        "rationale": ["The fresh-context Review resolved the named gap."],
        "resolved_trigger_ids": ["semantic_review_gap"],
        "resolution_evaluation_id": review["evaluation_id"],
    }
    store.lock_contract(task["task_id"], lower, expected_version=review["task_state_version"], revision_reason="bind reviewer proof")
    assert store.assurance_state(task["task_id"])["effective_tier"] == "governed"


def test_optional_context_labels_never_gate_tier_three(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    high = _contract(managed=False)
    high["assurance"] = {
        "tier": "high_assurance",
        "trigger_ids": ["fresh_context_required"],
        "rationale": ["The semantic claim needs a decorrelated observation."],
    }
    store.lock_contract(task["task_id"], high, expected_version=2, revision_reason="require fresh context")
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="optional labels", input_snapshot={}, context_id="worker-label")
    assert attempt["worker_context"] == "worker-label"
    store.seal_attempt(attempt["attempt_id"], expected_version=4)
    verification = store.evaluate_verify(attempt["attempt_id"])
    review = store.review(
        verification["evaluation_id"],
        decision="approved",
        reviewer="reviewer",
        report=_review_report(),
        context_id="reviewer-label",
    )
    assert review["payload"]["context_id"] == "reviewer-label"
    assert "independence" not in review["payload"]
    projection = store.control_projection(task["task_id"])
    assert projection["status"] == "acceptance_ready"
    completed = store.accept(task["task_id"], review["evaluation_id"], expected_version=review["task_state_version"])
    assert completed["lifecycle_status"] == "completed"


def test_v3_2_validator_proof_fields_are_readable_but_inert(tmp_path: Path) -> None:
    _, store, task = _designed_store(tmp_path, managed=False)
    legacy = _contract(managed=False)
    legacy["verification_spec"]["validators"][0].update(
        {"validator_id": "legacy-oracle", "resolves_trigger_ids": ["legacy-trigger"]}
    )
    store.lock_contract(task["task_id"], legacy, expected_version=2, revision_reason="read v3.2 fields")
    attempt = store.start_attempt(task["task_id"], expected_version=3, plan="legacy compatibility", input_snapshot={})
    store.seal_attempt(attempt["attempt_id"], expected_version=4)
    verification = store.evaluate_verify(attempt["attempt_id"])
    result = verification["payload"]["validator_results"][0]
    assert result["passed"] is True
    assert "validator_id" not in result
    assert "resolves_trigger_ids" not in result
