from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"


def _run(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(KERNEL), "--workspace", str(workspace), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_vendored_skill_runs_v2_project_task_and_recovery_flow(tmp_path) -> None:
    initialized = _run(tmp_path, "project", "init", "--project-id", "project_cli")
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    created = _run(tmp_path, "task", "create", "--title", "CLI task")
    assert created.returncode == 0, created.stdout + created.stderr
    task = json.loads(created.stdout)
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(
        json.dumps(
            {
                "goal": "Exercise the self-contained Skill.",
                "constraints": [],
                "non_goals": ["No hidden runtime."],
                "acceptance_criteria": ["result.txt exists"],
                "verification_spec": {
                    "validators": [{"type": "file_exists", "mode": "executable", "severity": "blocking", "path": "result.txt"}]
                },
            }
        ),
        encoding="utf-8",
    )
    locked = _run(
        tmp_path,
        "task",
        "contract",
        "--task",
        task["task_id"],
        "--expected-version",
        str(task["state_version"]),
        "--file",
        str(contract_path),
    )
    assert locked.returncode == 0, locked.stdout + locked.stderr
    shown = json.loads(_run(tmp_path, "task", "show", "--task", task["task_id"]).stdout)
    recovery = _run(tmp_path, "recover", "write", "--task", task["task_id"])
    assert recovery.returncode == 0, recovery.stdout + recovery.stderr
    bundle = json.loads(recovery.stdout)

    assert shown["readiness"] == "ready"
    assert bundle["status"] == "fresh"
    assert (tmp_path / ".metaloop" / "metaloop.db").exists()


def test_vendored_skill_reports_v2_duplicate_attempt_as_failure(tmp_path) -> None:
    _run(tmp_path, "project", "init")
    task = json.loads(_run(tmp_path, "task", "create", "--title", "Duplicate guard").stdout)
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "goal": "Guard exact replay.",
                "constraints": [],
                "non_goals": [],
                "acceptance_criteria": [],
                "verification_spec": {"validators": [{"type": "file_exists", "path": "result.txt"}]},
            }
        ),
        encoding="utf-8",
    )
    _run(tmp_path, "task", "contract", "--task", task["task_id"], "--expected-version", "1", "--file", str(contract))
    current = json.loads(_run(tmp_path, "task", "show", "--task", task["task_id"]).stdout)
    first = json.loads(
        _run(
            tmp_path,
            "attempt",
            "start",
            "--task",
            task["task_id"],
            "--expected-version",
            str(current["state_version"]),
            "--plan",
            "Run the plan.",
        ).stdout
    )
    current = json.loads(_run(tmp_path, "task", "show", "--task", task["task_id"]).stdout)
    _run(tmp_path, "attempt", "seal", "--attempt", first["attempt_id"], "--expected-version", str(current["state_version"]))
    current = json.loads(_run(tmp_path, "task", "show", "--task", task["task_id"]).stdout)
    duplicate = _run(
        tmp_path,
        "attempt",
        "start",
        "--task",
        task["task_id"],
        "--expected-version",
        str(current["state_version"]),
        "--plan",
        "Run the plan.",
    )

    assert duplicate.returncode == 1
    assert json.loads(duplicate.stdout)["error"] == "DuplicateAttemptError"


def test_vendored_v1_review_is_invalidated_by_a_second_run(tmp_path) -> None:
    designed = _run(
        tmp_path,
        "design",
        "--intent",
        "Review one exact execution",
        "--rationale",
        "Review identity must bind execution content.",
        "--non-goal",
        "Do not reuse an old review.",
        "--acceptance",
        "Independent reviewer accepts the exact execution.",
        "--allow-manual-only",
    )
    assert designed.returncode == 0, designed.stdout + designed.stderr
    assert _run(tmp_path, "run", "--command", "true").returncode == 0
    assert _run(tmp_path, "verify", "--json").returncode == 1
    reviewed = _run(
        tmp_path,
        "review",
        "record",
        "--decision",
        "approved",
        "--reviewer",
        "independent-reviewer",
        "--evidence",
        ".metaloop/execution_report.json",
    )
    assert reviewed.returncode == 0, reviewed.stdout + reviewed.stderr
    assert json.loads(_run(tmp_path, "verify", "--json").stdout)["status"] == "completed_verified"

    assert _run(tmp_path, "run", "--command", "true", "--evidence", "second execution").returncode == 0
    second = _run(tmp_path, "verify", "--json")
    assert second.returncode == 1
    payload = json.loads(second.stdout)
    assert payload["status"] == "review_required"
    assert any(item.get("type") == "review_result_invalid" for item in payload["warnings"])


def test_v2_status_observe_and_dashboard_import_use_vendored_core(tmp_path) -> None:
    _run(tmp_path, "project", "init")
    task = json.loads(_run(tmp_path, "task", "create", "--title", "Observed task").stdout)
    _run(tmp_path, "recover", "write", "--task", task["task_id"])

    status = json.loads(_run(tmp_path, "status", "--json").stdout)
    observed = json.loads(_run(tmp_path, "observe", "--format", "brief", "--json").stdout)
    dashboard = subprocess.run(
        [sys.executable, str(ROOT / "skills" / "metaloop" / "scripts" / "metaloop_dashboard.py"), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert status["v2"]["state"] == "ready"
    assert status["v2"]["task_count"] == 1
    assert observed["task_count"] == 1
    assert observed["recovery_status"] == "fresh"
    assert dashboard.returncode == 0, dashboard.stdout + dashboard.stderr


def test_v2_routes_event_append_into_canonical_task_history(tmp_path) -> None:
    assert _run(tmp_path, "project", "init").returncode == 0
    task = json.loads(_run(tmp_path, "task", "create", "--title", "Durable decisions").stdout)
    appended = _run(
        tmp_path,
        "event",
        "append",
        "--task",
        task["task_id"],
        "--type",
        "decision",
        "--summary",
        "Never repeat the discarded implementation.",
        "--decision",
        "use replacement design",
    )
    assert appended.returncode == 0, appended.stdout + appended.stderr
    event = json.loads(appended.stdout)

    listed = _run(tmp_path, "event", "list", "--task", task["task_id"], "--limit", "10")
    shown = _run(tmp_path, "event", "show", "--event", event["event_id"])
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert shown.returncode == 0, shown.stdout + shown.stderr
    assert any(item["event_id"] == event["event_id"] for item in json.loads(listed.stdout))
    assert json.loads(shown.stdout)["summary"] == "Never repeat the discarded implementation."
    assert not (tmp_path / ".metaloop" / "event_log.jsonl").exists()


def test_v1_mutable_surfaces_fail_closed_after_v2_initialization(tmp_path) -> None:
    assert _run(tmp_path, "project", "init").returncode == 0
    task = json.loads(_run(tmp_path, "task", "create", "--title", "Canonical v2").stdout)

    design = _run(
        tmp_path,
        "design",
        "--intent",
        "Competing truth",
        "--rationale",
        "This must be rejected.",
        "--non-goal",
        "No dual state.",
        "--acceptance",
        "Rejected.",
        "--command",
        "true",
    )
    context = _run(
        tmp_path,
        "context",
        "write",
        "--file",
        "resume_brief.md",
        "--content",
        "stale v1 truth",
    )
    threads = _run(
        tmp_path,
        "threads",
        "register",
        "--role",
        "worker",
        "--thread-id",
        "thread-legacy",
    )

    assert design.returncode == context.returncode == threads.returncode == 1
    assert json.loads(design.stdout)["error"] == "LegacyWriteDisabled"
    assert json.loads(context.stdout)["error"] == "LegacyWriteDisabled"
    assert "disabled" in json.loads(threads.stdout)["message"]
    assert not (tmp_path / ".metaloop" / "mission_capsule.json").exists()
    assert not (tmp_path / ".metaloop" / "context" / "resume_brief.md").exists()
    assert not (tmp_path / ".metaloop" / "threads.json").exists()

    assigned = _run(tmp_path, "task", "assign", "--thread", "thread-v2", "--task", task["task_id"])
    assignments = _run(tmp_path, "task", "assignments", "--thread", "thread-v2")
    legacy_status = _run(tmp_path, "threads", "status", "--json")
    assert assigned.returncode == assignments.returncode == legacy_status.returncode == 0
    assert json.loads(assignments.stdout)["task_id"] == task["task_id"]
    assert json.loads(legacy_status.stdout)[0]["thread_id"] == "thread-v2"
