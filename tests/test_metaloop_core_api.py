from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from metaloop_core import EventLog, ThreadRegistry, WorkspaceState, classify_dissatisfaction, load_verification_summary, observe_node, write_control_request
from metaloop_core.ids import new_id, utc_now


ROOT = Path(__file__).resolve().parents[1]


def test_metaloop_core_public_api_is_importable() -> None:
    assert new_id("core").startswith("core_")
    assert "T" in utc_now()
    assert WorkspaceState(".").root.is_absolute()
    assert classify_dissatisfaction("目标不对，需要重设计") == "redesign"
    assert observe_node(".")["schema"] == "metaloop.node_summary"
    assert callable(write_control_request)


def test_metaloop_core_does_not_import_legacy_runtime_modules() -> None:
    completed = subprocess.run(
        [sys.executable, "tools/check_core_import_boundary.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "core import boundary ok" in completed.stdout


def test_workspace_state_reads_metaloop_artifacts(tmp_path) -> None:
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    (metaloop_dir / "mission_capsule.json").write_text(
        json.dumps({"schema": "metaloop.lightweight_mission_capsule", "current_status": "designed"}),
        encoding="utf-8",
    )
    (metaloop_dir / "verification_result.json").write_text(
        json.dumps({"schema": "metaloop.lightweight_verification_result", "status": "failed", "reason": "gate failed"}),
        encoding="utf-8",
    )
    (metaloop_dir / "relay_result.json").write_text(
        json.dumps({"schema": "metaloop.relay_result", "status": "completed"}),
        encoding="utf-8",
    )

    status = WorkspaceState(tmp_path).status()

    assert status["capsule"]["state"] == "ready"
    assert status["capsule"]["status"] == "designed"
    assert status["verification"]["status"] == "failed"
    assert status["relay"]["status"] == "completed"
    assert status["threads"]["state"] == "missing"


def test_thread_registry_records_persistent_agent_boundaries(tmp_path) -> None:
    registry = ThreadRegistry(tmp_path)

    agent = registry.register(
        role="design",
        role_type="design",
        thread_id="thread-design-1",
        responsibilities=["Draft Mission Capsule and VerificationSpec."],
        notes=["initial registration"],
    )
    updated = registry.update(role="design", status="handoff_required", notes=["handoff to reviewer"])

    assert agent["thread_id"] == "thread-design-1"
    assert updated["status"] == "handoff_required"
    assert registry.status()["count"] == 1
    payload = json.loads((tmp_path / ".metaloop" / "threads.json").read_text(encoding="utf-8"))
    assert payload["schema"] == "metaloop.thread_registry"
    assert payload["agents"]["design"]["history"][-1]["event"] == "updated"


def test_event_log_appends_long_task_events(tmp_path) -> None:
    log = EventLog(tmp_path)

    event = log.append(
        event_type="decision",
        agent="interface",
        summary="Keep the product skill-only and use metaloop_core for protocol truth.",
        evidence=["docs/metaloop_prompt_first_code_backed.md"],
        next_action="Verify skill/core parity.",
    )

    assert event["schema"] == "metaloop.event"
    assert event["type"] == "decision"
    assert log.list()[0]["summary"].startswith("Keep the product skill-only")


def test_verification_summary_counts_blockers(tmp_path) -> None:
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    (metaloop_dir / "verification_result.json").write_text(
        json.dumps(
            {
                "status": "human_acceptance_required",
                "reason": "manual review remains",
                "hard_validator_results": [{"severity": "blocking", "passed": True}],
                "forbidden_path_results": [],
                "manual_validator_results": [{"severity": "blocking", "passed": False}],
                "unsupported_validator_results": [],
            }
        ),
        encoding="utf-8",
    )

    summary = load_verification_summary(tmp_path)

    assert summary is not None
    assert summary.status == "human_acceptance_required"
    assert summary.hard_failures == 0
    assert summary.manual_blockers == 1
    assert not summary.completed_verified
