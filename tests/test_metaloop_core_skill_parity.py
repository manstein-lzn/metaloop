from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from metaloop_core import EventLog, ThreadRegistry, WorkspaceState
from metaloop_core.verification import verify_workspace


ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"


def _run(args: list[str], workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(KERNEL), "--workspace", str(workspace), *args], text=True, capture_output=True, check=False)


def test_core_and_skill_kernel_verify_same_success_status(tmp_path) -> None:
    design = _run(
        [
            "design",
            "--intent",
            "Create result.txt",
            "--rationale",
            "File output is enough for parity.",
            "--non-goal",
            "Do not create unrelated files.",
            "--file-exists",
            "result.txt",
        ],
        tmp_path,
    )
    assert design.returncode == 0, design.stderr
    run = _run(["run", "--command", "printf 'done\\n' > result.txt"], tmp_path)
    assert run.returncode == 0, run.stderr

    core_result = verify_workspace(tmp_path, write=False, update_status=False)
    skill = _run(["verify", "--json"], tmp_path)
    assert skill.returncode == 0, skill.stderr
    skill_result = json.loads(skill.stdout)

    assert core_result["status"] == skill_result["status"] == "completed_verified"
    assert core_result["hard_validator_results"][0]["passed"] is True
    assert skill_result["hard_validator_results"][0]["passed"] is True


def test_core_and_skill_kernel_verify_same_manual_status(tmp_path) -> None:
    design = _run(
        [
            "design",
            "--intent",
            "Review result manually",
            "--rationale",
            "The boundary requires human judgment.",
            "--non-goal",
            "Do not pretend manual review is automated.",
            "--acceptance",
            "Human reviewer accepts the boundary.",
            "--allow-manual-only",
        ],
        tmp_path,
    )
    assert design.returncode == 0, design.stderr
    run = _run(["run", "--command", "true"], tmp_path)
    assert run.returncode == 0, run.stderr

    core_result = verify_workspace(tmp_path, write=False, update_status=False)
    skill = _run(["verify", "--json"], tmp_path)
    assert skill.returncode == 1
    skill_result = json.loads(skill.stdout)

    assert core_result["status"] == skill_result["status"] == "human_acceptance_required"
    assert core_result["manual_validator_results"][0]["type"] == "manual_acceptance"
    assert skill_result["manual_validator_results"][0]["type"] == "manual_acceptance"


def test_core_and_skill_kernel_share_thread_registry_semantics(tmp_path) -> None:
    register = _run(
        [
            "threads",
            "register",
            "--role",
            "design",
            "--role-type",
            "design",
            "--thread-id",
            "thread-design-1",
            "--responsibility",
            "Draft Mission Capsule and VerificationSpec.",
        ],
        tmp_path,
    )
    assert register.returncode == 0, register.stderr

    skill_status = _run(["threads", "status", "--json"], tmp_path)
    assert skill_status.returncode == 0, skill_status.stderr
    skill_registry = json.loads(skill_status.stdout)
    core_status = ThreadRegistry(tmp_path).status()
    workspace_status = WorkspaceState(tmp_path).status()

    assert core_status["state"] == "ready"
    assert workspace_status["threads"]["count"] == 1
    assert skill_registry["schema"] == "metaloop.thread_registry"
    assert skill_registry["agents"]["design"]["thread_id"] == core_status["agents"]["design"]["thread_id"] == "thread-design-1"
    assert skill_registry["agents"]["design"]["responsibilities"] == core_status["agents"]["design"]["responsibilities"]


def test_core_and_skill_kernel_share_event_log_semantics(tmp_path) -> None:
    append = _run(
        [
            "event",
            "append",
            "--type",
            "decision",
            "--agent",
            "reviewer",
            "--summary",
            "Keep skill kernel self-contained and verify parity with metaloop_core.",
            "--evidence",
            "tests/test_metaloop_core_skill_parity.py",
            "--next-action",
            "Run parity tests.",
            "--json",
        ],
        tmp_path,
    )
    assert append.returncode == 0, append.stderr
    skill_event = json.loads(append.stdout)

    listed = _run(["event", "list", "--limit", "1", "--json"], tmp_path)
    assert listed.returncode == 0, listed.stderr
    skill_events = json.loads(listed.stdout)["events"]
    core_events = EventLog(tmp_path).list(limit=1)
    workspace_status = WorkspaceState(tmp_path).status()

    assert workspace_status["events"]["count"] == 1
    assert skill_events[0]["schema"] == core_events[0]["schema"] == "metaloop.event"
    assert skill_events[0]["event_id"] == core_events[0]["event_id"] == skill_event["event_id"]
    assert core_events[0]["summary"].startswith("Keep skill kernel self-contained")
