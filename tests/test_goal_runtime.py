from pathlib import Path
import json
import shutil
import subprocess

import pytest

from metaloop.codex_adapter import CodexExecOptions
from metaloop.goal import RedesignProposal, ReviewRoute, SoftReviewDecision, VerificationResult, VerificationStatus
from metaloop.goal_runtime import CodexExecGoalRuntimeAdapter, build_repair_prompt
from metaloop.schemas import AcceptanceCriteria, MissionSpec, PolicyScope


def test_codex_exec_goal_runtime_writes_structured_artifacts(tmp_path) -> None:
    codex_bin = tmp_path / "codex"
    codex_bin.write_text(
        """#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
prompt = sys.stdin.read()
mission_id = re.search(r'"mission_id": "([^"]+)"', prompt).group(1)
Path("hello.txt").write_text("hello from goal runtime\\n", encoding="utf-8")
Path(".metaloop").mkdir(exist_ok=True)
Path(".metaloop/execution_report.json").write_text(json.dumps({
    "schema": "metaloop.execution_report",
    "version": "1.0",
    "mission_id": mission_id,
    "status": "completed",
    "summary": "created hello.txt",
    "changed_files": ["hello.txt", ".metaloop/run.json", "pkg/__pycache__/x.pyc", "metaloop.mission.json"],
    "commands_run": [],
    "validation_results": [],
    "evidence": ["hello.txt"],
    "known_limitations": []
}), encoding="utf-8")
print(json.dumps({"type":"thread.started","thread_id":"thread_goal"}), flush=True)
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":3}}), flush=True)
""",
        encoding="utf-8",
    )
    codex_bin.chmod(0o755)
    mission = MissionSpec(
        intent="Create hello.txt",
        deliverables=["hello.txt"],
        acceptance_criteria=[
            AcceptanceCriteria(
                description="hello.txt exists",
                validation_type="file_exists",
                validation_target="hello.txt",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    statuses: list[str] = []
    result = CodexExecGoalRuntimeAdapter(
        CodexExecOptions(codex_bin=str(codex_bin), working_directory=str(tmp_path), use_output_schema=False)
    ).run(mission, on_status=statuses.append)

    assert result.verification.status == VerificationStatus.COMPLETED_VERIFIED
    assert any("Structured artifacts prepared" in item for item in statuses)
    assert any("mission_capsule.json" in item for item in statuses)
    assert any("Initial verification: status=completed_verified" in item for item in statuses)
    assert any("Reviewer route: complete" in item for item in statuses)
    assert any("Final verification: status=completed_verified" in item for item in statuses)
    assert (tmp_path / ".metaloop" / "mission.json").exists()
    assert (tmp_path / ".metaloop" / "mission_capsule.json").exists()
    assert (tmp_path / ".metaloop" / "goal_contract.json").exists()
    assert (tmp_path / ".metaloop" / "goal_prompt.md").exists()
    assert (tmp_path / ".metaloop" / "execution_report.json").exists()
    assert (tmp_path / ".metaloop" / "verification_result.json").exists()
    assert (tmp_path / ".metaloop" / "run.json").exists()
    assert (tmp_path / ".metaloop" / "runs" / mission.run_id / "codex_events.jsonl").exists()
    attempt_files = list((tmp_path / ".metaloop" / "attempts").glob("*.json"))
    assert len(attempt_files) == 1
    attempt_history = json.loads(attempt_files[0].read_text(encoding="utf-8"))
    assert attempt_history["schema"] == "metaloop.attempt_history_record"
    assert attempt_history["mission_id"] == mission.run_id
    assert attempt_history["verification_status"] == "completed_verified"
    capsule = json.loads((tmp_path / ".metaloop" / "mission_capsule.json").read_text(encoding="utf-8"))
    assert capsule["lifecycle_state"] == "closed"
    assert capsule["closure_outcome"] == "accepted"
    assert len(capsule["evidence_ledger"]) >= 3
    assert capsule["attempt_history"][0]["outcome"] == "completed"
    assert (tmp_path / ".metaloop" / "attempts" / f"{capsule['attempt_history'][0]['attempt_id']}.json").exists()


def test_goal_runtime_attempt_history_records_git_snapshot(tmp_path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "metaloop@example.test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "MetaLoop Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=tmp_path, check=True, capture_output=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    codex_bin = tmp_path / "codex"
    codex_bin.write_text(
        """#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
prompt = sys.stdin.read()
mission_id = re.search(r'"mission_id": "([^"]+)"', prompt).group(1)
Path("hello.txt").write_text("hello from git backed attempt\\n", encoding="utf-8")
Path(".metaloop").mkdir(exist_ok=True)
Path(".metaloop/execution_report.json").write_text(json.dumps({
    "schema": "metaloop.execution_report",
    "version": "1.0",
    "mission_id": mission_id,
    "status": "completed",
    "summary": "created hello.txt",
    "changed_files": ["hello.txt"],
    "commands_run": [],
    "validation_results": [],
    "evidence": ["hello.txt"],
    "known_limitations": []
}), encoding="utf-8")
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":3}}), flush=True)
""",
        encoding="utf-8",
    )
    codex_bin.chmod(0o755)
    mission = MissionSpec(
        intent="Create hello.txt",
        deliverables=["hello.txt"],
        acceptance_criteria=[
            AcceptanceCriteria(
                description="hello.txt exists",
                validation_type="file_exists",
                validation_target="hello.txt",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = CodexExecGoalRuntimeAdapter(
        CodexExecOptions(codex_bin=str(codex_bin), working_directory=str(tmp_path), use_output_schema=False)
    ).run(mission)

    attempt_path = tmp_path / result.manifest.attempt_record_path
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    capsule = json.loads((tmp_path / ".metaloop" / "mission_capsule.json").read_text(encoding="utf-8"))
    assert attempt["commit_ref"] == head
    assert "hello.txt" in attempt["changed_files"]
    assert ".metaloop/run.json" not in attempt["changed_files"]
    assert "pkg/__pycache__/x.pyc" not in attempt["changed_files"]
    assert "metaloop.mission.json" not in attempt["changed_files"]
    assert "hello.txt" in capsule["attempt_history"][0]["changed_files"]
    assert not any("contains" in item or "defines" in item for item in capsule["attempt_history"][0]["changed_files"])
    assert not any(item.startswith(".metaloop/") or "__pycache__" in item or item.endswith(".pyc") for item in capsule["attempt_history"][0]["changed_files"])
    assert capsule["attempt_history"][0]["git_commit_ref"] == head


def test_codex_exec_goal_runtime_failed_codex_fails_verification(tmp_path) -> None:
    codex_bin = tmp_path / "codex"
    codex_bin.write_text(
        """#!/usr/bin/env python3
import sys
sys.stdin.read()
sys.exit(2)
""",
        encoding="utf-8",
    )
    codex_bin.chmod(0o755)
    mission = MissionSpec(
        intent="Do work",
        acceptance_criteria=[AcceptanceCriteria(description="manual check")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = CodexExecGoalRuntimeAdapter(
        CodexExecOptions(codex_bin=str(codex_bin), working_directory=str(tmp_path), use_output_schema=False)
    ).run(mission)

    assert result.verification.status == VerificationStatus.FAILED
    assert any(item.name == "codex_runtime" for item in result.verification.evidence_results)


def test_codex_exec_goal_runtime_repairs_worker_when_review_requests_fix(tmp_path) -> None:
    codex_bin = tmp_path / "codex"
    codex_bin.write_text(
        """#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
prompt = sys.stdin.read()
mission_id = re.search(r'"mission_id": "([^"]+)"', prompt).group(1)
if "repairing a MetaLoop mission" in prompt:
    Path("hello.txt").write_text("hello after repair\\n", encoding="utf-8")
Path(".metaloop").mkdir(exist_ok=True)
Path(".metaloop/execution_report.json").write_text(json.dumps({
    "schema": "metaloop.execution_report",
    "version": "1.0",
    "mission_id": mission_id,
    "status": "completed",
    "summary": "updated report",
    "changed_files": ["hello.txt"] if Path("hello.txt").exists() else [],
    "commands_run": [],
    "validation_results": [],
    "evidence": [],
    "known_limitations": []
}), encoding="utf-8")
print(json.dumps({"type":"thread.started","thread_id":"thread_goal"}), flush=True)
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":3}}), flush=True)
""",
        encoding="utf-8",
    )
    codex_bin.chmod(0o755)
    mission = MissionSpec(
        intent="Create hello.txt",
        deliverables=["hello.txt"],
        acceptance_criteria=[
            AcceptanceCriteria(
                description="hello.txt exists",
                validation_type="file_exists",
                validation_target="hello.txt",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    statuses: list[str] = []
    result = CodexExecGoalRuntimeAdapter(
        CodexExecOptions(codex_bin=str(codex_bin), working_directory=str(tmp_path), use_output_schema=False)
    ).run(mission, on_status=statuses.append)

    assert result.verification.status == VerificationStatus.COMPLETED_VERIFIED
    assert (tmp_path / "hello.txt").exists()
    assert any("Repair attempt 1/1" in item for item in statuses)
    assert result.verification.repair_attempts[0].repair_attempt_index == 1
    assert any("update ExecutionReport" in item for item in result.verification.repair_attempts[0].prompt_requirements)
    assert any("Post-repair verification: status=completed_verified" in item for item in statuses)
    capsule = json.loads((tmp_path / ".metaloop" / "mission_capsule.json").read_text(encoding="utf-8"))
    assert capsule["lifecycle_state"] == "closed"
    assert capsule["closure_outcome"] == "accepted"
    assert not (tmp_path / ".metaloop" / "redesign_proposal.json").exists()


def test_codex_exec_goal_runtime_architect_route_generates_redesign_proposal(tmp_path) -> None:
    codex_bin = tmp_path / "codex"
    codex_bin.write_text(
        """#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
prompt = sys.stdin.read()
mission_id = re.search(r'"mission_id": "([^"]+)"', prompt).group(1)
Path(".metaloop").mkdir(exist_ok=True)
if "focused architect agent" in prompt:
    print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"Diagnosis: acceptance needs redesign. Why worker repair is insufficient: the requested artifact is underspecified. Proposed acceptance change: specify exact file contents. Proposed scope change: clarify whether tests are required."}}), flush=True)
    print(json.dumps({"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":3}}), flush=True)
    sys.exit(0)
if "repairing a MetaLoop mission" in prompt:
    Path("hello.txt").write_text("hello after architect guidance\\n", encoding="utf-8")
Path(".metaloop/execution_report.json").write_text(json.dumps({
    "schema": "metaloop.execution_report",
    "version": "1.0",
    "mission_id": mission_id,
    "status": "completed",
    "summary": "updated report",
    "changed_files": ["hello.txt"] if Path("hello.txt").exists() else [],
    "commands_run": [],
    "validation_results": [],
    "evidence": [],
    "known_limitations": []
}), encoding="utf-8")
print(json.dumps({"type":"thread.started","thread_id":"thread_goal"}), flush=True)
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":3}}), flush=True)
""",
        encoding="utf-8",
    )
    codex_bin.chmod(0o755)

    class ArchitectReviewer:
        def review(self, mission, verification):
            if any(not item.passed for item in verification.hard_validator_results):
                return SoftReviewDecision(
                    mission_id=mission.run_id,
                    passed=False,
                    route=ReviewRoute.ASK_ARCHITECT_TO_RETHINK,
                    repair_instructions="Apply the architect guidance and satisfy hard validators.",
                )
            return SoftReviewDecision(mission_id=mission.run_id, passed=True, route=ReviewRoute.COMPLETE)

    mission = MissionSpec(
        intent="Create hello.txt",
        deliverables=["hello.txt"],
        acceptance_criteria=[
            AcceptanceCriteria(
                description="hello.txt exists",
                validation_type="file_exists",
                validation_target="hello.txt",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = CodexExecGoalRuntimeAdapter(
        CodexExecOptions(codex_bin=str(codex_bin), working_directory=str(tmp_path), use_output_schema=False),
        soft_reviewer=ArchitectReviewer(),
    ).run(mission)

    assert result.verification.status == VerificationStatus.FAILED
    assert "redesign_required" in result.verification.reason
    assert not (tmp_path / "hello.txt").exists()
    proposal_path = tmp_path / ".metaloop" / "redesign_proposal.json"
    assert proposal_path.exists()
    proposal = RedesignProposal.model_validate(json.loads(proposal_path.read_text(encoding="utf-8")))
    assert proposal.reviewer_route == ReviewRoute.ASK_ARCHITECT_TO_RETHINK
    assert proposal.reason
    assert proposal.why_worker_repair_is_insufficient
    assert proposal.contract_delta.evidence_delta
    assert "contract_delta" in json.loads(proposal.model_dump_json(by_alias=True))
    capsule = json.loads((tmp_path / ".metaloop" / "mission_capsule.json").read_text(encoding="utf-8"))
    assert capsule["lifecycle_state"] == "redesign_required"
    assert capsule["closure_outcome"] is None
    assert any("redesign_required" in decision["summary"] for decision in capsule["decision_ledger"])


def test_repeated_repair_prompt_requires_root_cause_and_hypothesis(tmp_path) -> None:
    mission = MissionSpec(
        intent="Create hello.txt",
        deliverables=["hello.txt"],
        acceptance_criteria=[
            AcceptanceCriteria(
                description="hello.txt exists",
                validation_type="file_exists",
                validation_target="hello.txt",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )
    verification = VerificationResult(
        mission_id=mission.run_id,
        status=VerificationStatus.FAILED,
        reason="Required hard validators failed.",
        soft_review_decision=SoftReviewDecision(
            mission_id=mission.run_id,
            passed=False,
            route=ReviewRoute.ASK_WORKER_TO_FIX,
            repair_instructions="Create the missing file.",
        ),
    )

    prompt = build_repair_prompt(
        mission,
        verification,
        repair_attempt_index=2,
        failed_fix_summary="first repair did not create hello.txt",
    )

    assert "root_cause" in prompt
    assert "hypothesis" in prompt
    assert "previous fix failed" in prompt
    assert "redesign_required" in prompt


def test_codex_exec_goal_runtime_fail_route_closes_failed(tmp_path) -> None:
    codex_bin = tmp_path / "codex"
    codex_bin.write_text(
        """#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
prompt = sys.stdin.read()
mission_id = re.search(r'"mission_id": "([^"]+)"', prompt).group(1)
Path(".metaloop").mkdir(exist_ok=True)
Path(".metaloop/execution_report.json").write_text(json.dumps({
    "schema": "metaloop.execution_report",
    "version": "1.0",
    "mission_id": mission_id,
    "status": "completed",
    "summary": "done",
    "changed_files": [],
    "commands_run": [],
    "validation_results": [],
    "evidence": [],
    "known_limitations": []
}), encoding="utf-8")
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":3}}), flush=True)
""",
        encoding="utf-8",
    )
    codex_bin.chmod(0o755)

    class FailReviewer:
        def review(self, mission, verification):
            return SoftReviewDecision(mission_id=mission.run_id, passed=False, route=ReviewRoute.FAIL)

    mission = MissionSpec(
        intent="Do work",
        acceptance_criteria=[AcceptanceCriteria(description="manual check")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = CodexExecGoalRuntimeAdapter(
        CodexExecOptions(codex_bin=str(codex_bin), working_directory=str(tmp_path), use_output_schema=False),
        soft_reviewer=FailReviewer(),
    ).run(mission)

    assert result.verification.status == VerificationStatus.FAILED
    capsule = json.loads((tmp_path / ".metaloop" / "mission_capsule.json").read_text(encoding="utf-8"))
    assert capsule["lifecycle_state"] == "closed"
    assert capsule["closure_outcome"] == "failed"
