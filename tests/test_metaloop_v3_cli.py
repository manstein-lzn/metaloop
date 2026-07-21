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


def test_cli_high_assurance_review_is_structured_and_brief_status_is_compatible(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    _json(_run(repo, "project", "init"))
    monkeypatch.setenv("METALOOP_HOST_CONTEXT_ID", "worker-context")
    monkeypatch.setenv("METALOOP_HOST_CONTEXT_PROVIDER", "pytest-host")
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

    monkeypatch.setenv("METALOOP_HOST_CONTEXT_ID", "reviewer-context")
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


def test_cli_context_id_is_manual_and_cannot_satisfy_tier_three(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    _json(_run(repo, "project", "init"))
    monkeypatch.setenv("METALOOP_HOST_CONTEXT_ID", "host-worker")
    monkeypatch.setenv("METALOOP_HOST_CONTEXT_PROVIDER", "pytest-host")
    contract = {
        "goal": "Exercise manual context provenance.",
        "rationale": ["Manual labels must not become host attestation."],
        "constraints": ["Do not mutate project files."],
        "non_goals": ["Do not accept an unverified Tier 3 Review."],
        "acceptance_criteria": ["The kernel blocks unverified independence."],
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
    assert begun["attempt"]["worker_context"]["source"] == "manual"
    assert begun["attempt"]["worker_context"]["verified"] is False
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
    monkeypatch.setenv("METALOOP_HOST_CONTEXT_ID", "host-reviewer")
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
    assert review["payload"]["context"]["source"] == "manual"
    assert review["payload"]["independence"] == "unverified"
    brief = _json(_run(repo, "observe", "--task", begun["task"]["task_id"], "--format", "brief"))
    assert brief["control_status"] == "high_assurance_review_unverified"
    assert brief["next_transition"] == "start_repair_attempt"
    blocked = _run(
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
    assert blocked.returncode == 1
    assert "start_repair_attempt" in blocked.stderr
