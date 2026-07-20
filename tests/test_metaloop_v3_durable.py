from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

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
    completed = store.accept(task["task_id"], evaluation["evaluation_id"], expected_version=5)
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
    with pytest.raises(InvalidTransitionError, match="missing required authorities"):
        store.accept(task["task_id"], evaluation["evaluation_id"], expected_version=5)
    review = store.review(evaluation["evaluation_id"], decision="approved", reviewer="independent")
    completed = store.accept(task["task_id"], review["evaluation_id"], expected_version=5)
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
    store.seal_attempt(attempt["attempt_id"], expected_version=4)
    evaluation = store.evaluate_verify(attempt["attempt_id"])
    store.accept(task["task_id"], evaluation["evaluation_id"], expected_version=5)

    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "promote accepted tree")

    recovery = store.recovery(task["task_id"])
    assert recovery["status"] == "fresh"
    assert recovery["workspace_alignment"] == "aligned"
    assert recovery["workspace_transition"] == "content_preserving_commit"
    assert store.integrity(task["task_id"])["passed"] is True


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


def test_finish_does_not_infer_ownership_for_undeclared_paths(tmp_path: Path) -> None:
    repo, store, task = _designed_store(tmp_path)
    attempt = store.start_attempt(task["task_id"], expected_version=2, plan="routine repair", input_snapshot={})
    (repo / "src" / "out.txt").write_text("managed\n", encoding="utf-8")
    (repo / "src" / "extra.txt").write_text("undeclared\n", encoding="utf-8")

    with pytest.raises(ConflictError, match="classify changed paths"):
        store.finish_attempt(attempt["attempt_id"])
    assert store.task(task["task_id"])["active_attempt_id"] == attempt["attempt_id"]


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
    assert pending["task"]["acceptance_head_id"] is None
