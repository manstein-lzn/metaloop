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
    completed = _json(_run(repo, "evaluate", "accept", "--task", task_id, "--evaluation", evaluation["evaluation_id"], "--expected-version", "5"))
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
