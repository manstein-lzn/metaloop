from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


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


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(KERNEL), "--workspace", str(repo), *args], text=True, capture_output=True, check=False)


def _json(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_cli_runs_complete_git_aligned_task_and_blocks_drift(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    project = _json(_run(repo, "project", "init"))
    assert project["schema_version"] == 3
    task = _json(_run(repo, "task", "create", "--title", "CLI task"))
    task_id = task["task_id"]
    _json(_run(repo, "task", "set-default", "--task", task_id))

    contract = {
        "goal": "Create an output.",
        "rationale": ["Prove the installed path."],
        "constraints": ["Use the declared scope."],
        "non_goals": ["Do not touch unrelated files."],
        "acceptance_criteria": ["The command validator passes."],
        "verification_spec": {"validators": [{"type": "command", "mode": "executable", "severity": "blocking", "command": "true"}], "resource_gates": []},
        "protocol_shape": "single_node",
        "execution_scope": {
            "paths": ["src"],
            "stable_inputs": [{"role": "governing_document", "path": "ARCH.md"}],
            "managed_outputs": [{"role": "implementation", "path": "src/result.txt"}],
            "change_kind": "extension",
            "migration_plan": None,
        },
    }
    contract_path = repo / ".metaloop" / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    _json(_run(repo, "task", "contract", "--task", task_id, "--expected-version", "1", "--file", str(contract_path)))
    recovery = _json(_run(repo, "recover", "show", "--task", task_id))
    assert recovery["status"] == "fresh"
    attempt = _json(_run(repo, "attempt", "start", "--task", task_id, "--expected-version", "2", "--plan", "write result"))
    attempt_id = attempt["attempt_id"]

    (repo / "src" / "result.txt").write_text("done\n", encoding="utf-8")
    ahead = _json(_run(repo, "recover", "show", "--task", task_id))
    assert ahead["workspace_alignment"] == "ahead"
    brief = _json(_run(repo, "observe", "--task", task_id, "--format", "brief"))
    assert brief["integrity"] is True
    assert brief["integrity_status"] == "not_yet_reconciled"
    assert brief["control_status"] == "working"
    blocked = _run(repo, "attempt", "seal", "--attempt", attempt_id, "--expected-version", "3")
    assert blocked.returncode == 1
    assert "workspace alignment is ahead" in blocked.stderr

    checkpoint = _json(
        _run(
            repo,
            "attempt",
            "record-checkpoint",
            "--attempt",
            attempt_id,
            "--expected-version",
            "3",
            "--completed",
            "output",
            "--decision",
            "continue",
            "--next-plan",
            "verify",
            "--claimed-path",
            "src/result.txt",
        )
    )
    assert checkpoint["payload"]["workspace_alignment"] == "aligned"
    evidence = _json(_run(repo, "attempt", "evidence", "--attempt", attempt_id, "--path", "src/result.txt"))
    assert evidence["path"] == "src/result.txt"
    sealed = _json(_run(repo, "attempt", "seal", "--attempt", attempt_id, "--expected-version", "4"))
    evaluation = _json(_run(repo, "evaluate", "verify", "--attempt", sealed["attempt_id"]))
    completed = _json(_run(repo, "evaluate", "accept", "--task", task_id, "--evaluation", evaluation["evaluation_id"], "--expected-version", "6"))
    assert completed["lifecycle_status"] == "completed"
    integrity = _json(_run(repo, "project", "integrity", "--task", task_id))
    assert integrity["passed"] is True


def test_cli_exposes_only_final_command_families(tmp_path: Path) -> None:
    help_result = subprocess.run([sys.executable, str(KERNEL), "--help"], text=True, capture_output=True, check=False)
    assert help_result.returncode == 0
    for command in ["project", "task", "attempt", "evaluate", "recover", "observe"]:
        assert command in help_result.stdout
    for removed in ["design", "run", "verify", "migrate-legacy", "tick", "relay", "activate"]:
        result = subprocess.run([sys.executable, str(KERNEL), removed], text=True, capture_output=True, check=False)
        assert result.returncode != 0


def test_project_init_outside_git_fails_with_actionable_error(tmp_path: Path) -> None:
    result = _run(tmp_path, "project", "init")
    assert result.returncode == 1
    assert "not a git repository" in result.stderr.lower()


def test_cli_begin_and_finish_are_one_ontology_low_friction_path(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _json(_run(repo, "project", "init"))
    contract = {
        "goal": "Complete one routine repair.",
        "rationale": ["Exercise the alpha-optimized path."],
        "constraints": ["Use the declared output."],
        "non_goals": ["Do not require external authority."],
        "acceptance_criteria": ["The executable validator passes."],
        "verification_spec": {"validators": [{"type": "command", "mode": "executable", "severity": "blocking", "command": "true"}], "resource_gates": []},
        "protocol_shape": "single_node",
        "execution_scope": {
            "paths": ["src"],
            "stable_inputs": [{"role": "governing_document", "path": "ARCH.md"}],
            "managed_outputs": [{"role": "implementation", "path": "src/result.txt"}],
            "change_kind": "repair",
            "migration_plan": None,
        },
    }
    contract_path = repo / ".metaloop" / "routine-contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    begun = _json(
        _run(
            repo,
            "task",
            "begin",
            "--title",
            "Routine repair",
            "--contract",
            str(contract_path),
            "--plan",
            "write and verify the output",
        )
    )
    assert begun["recovery"]["status"] == "fresh"
    attempt_id = begun["attempt"]["attempt_id"]
    (repo / "src" / "result.txt").write_text("done\n", encoding="utf-8")

    finished = _json(_run(repo, "attempt", "finish", "--attempt", attempt_id))
    assert finished["task"]["lifecycle_status"] == "completed"
    assert finished["evaluation"]["decision"] == "approved"
    assert finished["pending_authorities"] == []
    assert [item["path"] for item in finished["evidence"]] == ["src/result.txt"]


def test_cli_begin_validation_failure_leaves_no_empty_task(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _json(_run(repo, "project", "init"))
    invalid = {
        "goal": "Reject malformed validator input.",
        "rationale": ["The CLI should fail before creating protocol state."],
        "constraints": [],
        "non_goals": [],
        "acceptance_criteria": ["Malformed manual validators are rejected."],
        "verification_spec": {
            "validators": [{"type": "manual_acceptance", "authority": "reviewer"}],
            "resource_gates": [],
        },
        "protocol_shape": "single_node",
        "execution_scope": {"paths": [], "stable_inputs": [], "managed_outputs": [], "change_kind": "repair", "migration_plan": None},
    }
    contract_path = repo / ".metaloop" / "invalid-contract.json"
    contract_path.write_text(json.dumps(invalid), encoding="utf-8")

    failed = _run(repo, "task", "begin", "--title", "must not remain", "--contract", str(contract_path), "--plan", "reject")
    assert failed.returncode == 1
    assert "manual_acceptance validators require mode=manual" in failed.stderr
    assert _json(_run(repo, "task", "list")) == []


def test_cli_generated_tier_one_contract_avoids_contract_file_ceremony(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _json(_run(repo, "project", "init"))
    begun = _json(
        _run(
            repo,
            "task",
            "begin",
            "--title",
            "Durable routine repair",
            "--plan",
            "write and verify one output",
            "--check",
            "test -f src/result.txt",
            "--allowed-path",
            "src",
            "--managed-output",
            "implementation=src/result.txt",
        )
    )
    assert begun["contract"]["content"]["assurance"]["tier"] == "durable_routine"
    assert begun["contract"]["content"]["goal"] == "Durable routine repair"
    assert "change_kind" not in begun["contract"]["content"]["execution_scope"]
    brief = _json(_run(repo, "observe", "--task", begun["task"]["task_id"], "--format", "brief"))
    assert brief["protocol_activity"]["expected_agent_lifecycle_commands"] == 2
    assert brief["routing_warning"] is None

    (repo / "src" / "result.txt").write_text("done\n", encoding="utf-8")
    (repo / "src" / "implementation.py").write_text("VALUE = 1\n", encoding="utf-8")
    finished = _json(
        _run(
            repo,
            "attempt",
            "finish",
            "--attempt",
            begun["attempt"]["attempt_id"],
            "--external-ref",
            "/runs/routine-42",
            "--external-checkpoint-identity",
            "checkpoint-final",
        )
    )
    assert finished["task"]["lifecycle_status"] == "completed"
    assert finished["evaluation"]["payload"]["validator_results"][0]["passed"] is True
    assert finished["checkpoint"]["payload"]["claimed_paths"] == ["src/implementation.py", "src/result.txt"]
    assert finished["checkpoint"]["payload"]["external_ref"] == {
        "locator": "/runs/routine-42",
        "checkpoint_identity": "checkpoint-final",
    }
    completed_brief = _json(_run(repo, "observe", "--task", begun["task"]["task_id"], "--format", "brief"))
    assert completed_brief["external_ref"] == finished["checkpoint"]["payload"]["external_ref"]
    repeated = _json(_run(repo, "attempt", "finish", "--attempt", begun["attempt"]["attempt_id"]))
    assert repeated["evaluation"]["evaluation_id"] == finished["evaluation"]["evaluation_id"]
    assert repeated["task"]["lifecycle_status"] == "completed"


def test_cli_automatically_adopts_latest_aborted_workspace(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _json(_run(repo, "project", "init"))
    begun = _json(
        _run(
            repo,
            "task",
            "begin",
            "--title",
            "Resume carried work",
            "--plan",
            "first strategy",
            "--check",
            "test -f src/result.txt",
            "--allowed-path",
            "src",
        )
    )
    first = begun["attempt"]
    (repo / "src" / "result.txt").write_text("carried\n", encoding="utf-8")
    _json(_run(repo, "attempt", "abort", "--attempt", first["attempt_id"], "--reason", "change strategy"))

    retry = _json(
        _run(
            repo,
            "attempt",
            "start",
            "--task",
            begun["task"]["task_id"],
            "--expected-version",
            "4",
            "--plan",
            "continue the carried workspace",
        )
    )

    assert retry["carried_forward"]["source_attempt_id"] == first["attempt_id"]
    assert [item["path"] for item in retry["carried_forward"]["paths"]] == ["src/result.txt"]
    finished = _json(_run(repo, "attempt", "finish", "--attempt", retry["attempt_id"]))
    assert finished["task"]["lifecycle_status"] == "completed"


def test_cli_generated_tier_one_rejects_blank_check_without_state(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _json(_run(repo, "project", "init"))

    failed = _run(
        repo,
        "task",
        "begin",
        "--title",
        "Blank check",
        "--plan",
        "must not start",
        "--check",
        "   ",
    )

    assert failed.returncode == 1
    assert "--check must be a non-empty command" in failed.stderr
    assert _json(_run(repo, "task", "list")) == []


def test_cli_high_assurance_review_is_structured_without_host_configuration(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _json(_run(repo, "project", "init"))
    contract = {
        "goal": "Verify one semantic claim.",
        "rationale": ["Exercise fresh-context review."],
        "constraints": ["Do not mutate project files."],
        "non_goals": ["Do not request user authority."],
        "acceptance_criteria": ["Mechanical proof and structured review pass."],
        "verification_spec": {"validators": [{"type": "command", "mode": "executable", "severity": "blocking", "command": "true"}], "resource_gates": []},
        "protocol_shape": "single_node",
        "assurance": {
            "tier": "high_assurance",
            "trigger_ids": ["semantic_change_incomplete_oracle"],
            "rationale": ["Executable checks do not cover the full semantic claim."],
        },
        "execution_scope": {"paths": ["src"], "stable_inputs": [], "managed_outputs": [], "change_kind": "extension", "migration_plan": None},
    }
    contract_path = repo / ".metaloop" / "high-contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    begun = _json(
        _run(
            repo,
            "task",
            "begin",
            "--title",
            "High assurance claim",
            "--contract",
            str(contract_path),
            "--plan",
            "verify and review",
        )
    )
    finished = _json(_run(repo, "attempt", "finish", "--attempt", begun["attempt"]["attempt_id"]))
    verification_id = finished["evaluation"]["evaluation_id"]
    assert finished["pending_authorities"] == ["reviewer"]
    assert finished["task"]["acceptance_head_id"] == verification_id
    assert finished["review_handoff"]["exact_subject"]["evaluation_id"] == verification_id

    missing = _run(
        repo,
        "evaluate",
        "review",
        "--evaluation",
        verification_id,
        "--decision",
        "approved",
        "--reviewer",
        "reviewer",
    )
    assert missing.returncode == 1
    assert "structured report" in missing.stderr

    report = {
        "review_scope": "semantic claim and negative cases",
        "questions_and_findings": [{"question": "Is the claim supported?", "finding": "Yes."}],
        "counterexamples_executed": ["empty input"],
        "blocking_findings": [],
        "nonblocking_risks": [],
        "decision": "approved",
    }
    report_path = repo / ".metaloop" / "review.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    review = _json(
        _run(
            repo,
            "evaluate",
            "review",
            "--evaluation",
            verification_id,
            "--decision",
            "approved",
            "--reviewer",
            "reviewer",
            "--report-file",
            str(report_path),
        )
    )
    assert review["payload"]["review_report"]["exact_evaluation_subject"]["evaluation_id"] == verification_id
    brief = _json(_run(repo, "observe", "--task", begun["task"]["task_id"], "--format", "brief"))
    assert brief["control_status"] == "acceptance_ready"
    assert brief["pending_authorities"] == []
    assert [item["kind"] for item in brief["active_chain"]] == ["verification", "review"]
    assert brief["review_handoff"] is None
    assert brief["recovery_status"] == "fresh"
    assert brief["workspace_alignment"] == "aligned"
    completed = _json(
        _run(
            repo,
            "evaluate",
            "accept",
            "--task",
            begun["task"]["task_id"],
            "--evaluation",
            review["evaluation_id"],
            "--expected-version",
            "7",
        )
    )
    assert completed["lifecycle_status"] == "completed"


def test_cli_context_id_is_optional_annotation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _json(_run(repo, "project", "init"))
    contract = {
        "goal": "Exercise manual context provenance.",
        "rationale": ["Manual labels must not become host attestation."],
        "constraints": ["Do not mutate project files."],
        "non_goals": ["Do not add host authentication to the protocol."],
        "acceptance_criteria": ["A structured Review completes the claim."],
        "verification_spec": {
            "validators": [{"type": "command", "mode": "executable", "command": "true"}],
            "resource_gates": [],
        },
        "protocol_shape": "single_node",
        "assurance": {
            "tier": "high_assurance",
            "trigger_ids": ["fresh_context_required"],
            "rationale": ["The claim requires a decorrelated Review."],
        },
        "execution_scope": {"paths": ["src"], "stable_inputs": [], "managed_outputs": [], "change_kind": "extension", "migration_plan": None},
    }
    contract_path = repo / ".metaloop" / "manual-context-contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    begun = _json(
        _run(
            repo,
            "task",
            "begin",
            "--title",
            "Manual context",
            "--contract",
            str(contract_path),
            "--plan",
            "record provenance",
            "--context-id",
            "manual-worker",
        )
    )
    assert begun["attempt"]["worker_context"] == "manual-worker"
    finished = _json(_run(repo, "attempt", "finish", "--attempt", begun["attempt"]["attempt_id"]))

    report = {
        "review_scope": "manual provenance",
        "questions_and_findings": [],
        "counterexamples_executed": [],
        "blocking_findings": [],
        "nonblocking_risks": [],
        "resolved_trigger_ids": [],
        "decision": "approved",
    }
    report_path = repo / ".metaloop" / "manual-review.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    review = _json(
        _run(
            repo,
            "evaluate",
            "review",
            "--evaluation",
            finished["evaluation"]["evaluation_id"],
            "--decision",
            "approved",
            "--reviewer",
            "reviewer",
            "--context-id",
            "manual-reviewer",
            "--report-file",
            str(report_path),
        )
    )
    assert review["payload"]["context_id"] == "manual-reviewer"
    brief = _json(_run(repo, "observe", "--task", begun["task"]["task_id"], "--format", "brief"))
    assert brief["control_status"] == "acceptance_ready"
    completed = _json(
        _run(
            repo,
            "evaluate",
            "accept",
            "--task",
            begun["task"]["task_id"],
            "--evaluation",
            review["evaluation_id"],
            "--expected-version",
            str(review["task_state_version"]),
        )
    )
    assert completed["lifecycle_status"] == "completed"
