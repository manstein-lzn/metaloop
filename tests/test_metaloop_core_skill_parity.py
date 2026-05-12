from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from metaloop_core import EventLog, ThreadRegistry, WorkspaceState
from metaloop_core.adaptive_loop import load_adaptive_loop, new_adaptive_loop, record_iteration, write_adaptive_loop
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

    assert core_result["status"] == skill_result["status"] == "review_required"
    assert core_result["manual_validator_results"][0]["type"] == "manual_acceptance"
    assert skill_result["manual_validator_results"][0]["type"] == "manual_acceptance"
    assert core_result["manual_validator_results"][0]["reviewer"] == "codex_reviewer"
    assert skill_result["manual_validator_results"][0]["reviewer"] == "codex_reviewer"


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


def test_core_and_skill_kernel_share_adaptive_loop_semantics(tmp_path) -> None:
    init = _run(
        [
            "adaptive",
            "init",
            "--goal",
            "Improve a measurable target without weakening locked acceptance.",
            "--current-plan",
            "Run the first high-signal attempt.",
            "--success-criterion",
            "Locked VerificationSpec passes.",
            "--known-fact",
            "Previous attempts did not satisfy the target.",
            "--json",
        ],
        tmp_path,
    )
    assert init.returncode == 0, init.stderr
    skill_state = json.loads(init.stdout)
    core_state = load_adaptive_loop(tmp_path)

    assert core_state is not None
    assert skill_state["schema"] == core_state["schema"] == "metaloop.adaptive_goal_loop"
    assert skill_state["goal"] == core_state["goal"]
    assert WorkspaceState(tmp_path).status()["adaptive_loop"]["status"] == "active"

    record = _run(
        [
            "adaptive",
            "record",
            "--plan",
            "Run the first high-signal attempt.",
            "--observation",
            "The artifact was produced but the metric gate did not pass.",
            "--evaluation-status",
            "not_satisfied",
            "--diagnosis",
            "The likely issue is an implementation bug in the attempted change.",
            "--next-plan",
            "Repair the implementation bug and rerun the same metric gate.",
            "--evidence",
            ".metaloop/verification_result.json",
            "--json",
        ],
        tmp_path,
    )
    assert record.returncode == 0, record.stderr
    skill_updated = json.loads(record.stdout)
    core_updated = load_adaptive_loop(tmp_path)

    assert core_updated is not None
    assert skill_updated["iterations"][0]["decision"] == core_updated["iterations"][0]["decision"] == "repair"
    assert core_updated["current_plan"].startswith("Repair the implementation bug")


def test_core_written_adaptive_loop_is_readable_by_skill_kernel(tmp_path) -> None:
    state = new_adaptive_loop(goal="Ship a reliable change.", current_plan="Implement and verify the smallest useful slice.")
    write_adaptive_loop(tmp_path, state)
    record_iteration(
        tmp_path,
        plan="Implement and verify the smallest useful slice.",
        observation="Tests passed but the reviewer found the goal was scoped too narrowly.",
        evaluation_status="partial",
        diagnosis="The acceptance criteria miss an important user workflow.",
        next_plan="Redesign acceptance criteria before further implementation.",
    )

    skill_status = _run(["adaptive", "status", "--json"], tmp_path)
    assert skill_status.returncode == 0, skill_status.stderr
    skill_state = json.loads(skill_status.stdout)

    assert skill_state["schema"] == "metaloop.adaptive_goal_loop"
    assert skill_state["iterations"][0]["decision"] == "redesign"
