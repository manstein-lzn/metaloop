from __future__ import annotations

import json
from pathlib import Path

from metaloop_core.execution import build_execution_report, write_execution_report
from metaloop_core.specs import hash_object
from metaloop_core.verification import build_review_result, verify_workspace, write_review_result


def _extension_spec() -> dict:
    spec = {
        "schema": "metaloop.extension_spec",
        "version": "1.0",
        "domain": "generic",
        "purpose": "Generic local task verification.",
        "validator_types": [
            {"type": "file_exists", "mode": "executable", "description": "file exists"},
            {"type": "file_contains", "mode": "executable", "description": "file contains"},
            {"type": "json_metric_gate", "mode": "executable", "description": "metric gate"},
            {"type": "json_field_exists", "mode": "executable", "description": "field exists"},
            {"type": "artifact_hash", "mode": "executable", "description": "artifact hash"},
            {"type": "manual_acceptance", "mode": "manual", "description": "manual"},
            {"type": "resource_gate", "mode": "manual", "description": "resource"},
            {"type": "future_gate", "mode": "unsupported", "description": "future"},
        ],
        "risk_checks": [],
        "review_questions": [],
        "known_gaps": [],
    }
    spec["extension_hash"] = hash_object(spec, "extension_hash")
    return spec


def _verification_spec(extension: dict, validators: list[dict], resource_gates: list[dict] | None = None) -> dict:
    spec = {
        "schema": "metaloop.verification_spec",
        "version": "1.0",
        "domain": "generic",
        "extension": "generic",
        "extension_version": "1.0",
        "extension_hash": extension["extension_hash"],
        "validators": validators,
        "evidence_requirements": [],
        "resource_gates": resource_gates or [],
    }
    spec["spec_hash"] = hash_object(spec, "spec_hash")
    return spec


def _write_capsule(tmp_path: Path, validators: list[dict], resource_gates: list[dict] | None = None) -> dict:
    extension = _extension_spec()
    verification = _verification_spec(extension, validators, resource_gates)
    capsule = {
        "schema": "metaloop.lightweight_capsule",
        "version": "1.0",
        "capsule_id": "capsule_test",
        "revision": 1,
        "previous_capsule_id": None,
        "revision_reason": "",
        "created_at": "2026-05-09T00:00:00Z",
        "updated_at": "2026-05-09T00:00:00Z",
        "locked_at": "2026-05-09T00:00:00Z",
        "workspace": str(tmp_path),
        "locked": True,
        "intent": "Verify core behavior",
        "context": [],
        "design_rationale": ["test"],
        "constraints": [],
        "non_goals": ["none"],
        "acceptance_criteria": [],
        "forbidden_paths": [],
        "evidence_requirements": [],
        "extension_spec": extension,
        "verification_spec": verification,
        "verification_plan": {"hard_validators": []},
        "verification_review": {},
        "current_status": "executed",
        "status_history": [{"status": "designed", "reason": "test", "at": "2026-05-09T00:00:00Z"}],
    }
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir(parents=True)
    (metaloop_dir / "mission_capsule.json").write_text(json.dumps(capsule, indent=2), encoding="utf-8")
    report = build_execution_report(workspace=tmp_path, capsule=capsule, status="completed", commands=[], evidence=[])
    write_execution_report(tmp_path, report)
    return capsule


def test_verify_workspace_completes_executable_validators(tmp_path) -> None:
    (tmp_path / "result.txt").write_text("ok\n", encoding="utf-8")
    (tmp_path / "summary.json").write_text(json.dumps({"held_out": {"score": 0.3}}), encoding="utf-8")
    _write_capsule(
        tmp_path,
        [
            {"type": "file_exists", "mode": "executable", "severity": "blocking", "path": "result.txt"},
            {"type": "file_contains", "mode": "executable", "severity": "blocking", "path": "result.txt", "contains": "ok"},
            {"type": "json_field_exists", "mode": "executable", "severity": "blocking", "path": "summary.json", "field": "held_out.score"},
            {"type": "json_metric_gate", "mode": "executable", "severity": "blocking", "path": "summary.json", "metric": "held_out.score", "operator": ">=", "threshold": 0.2},
        ],
    )

    result = verify_workspace(tmp_path)

    assert result["status"] == "completed_verified"
    assert (tmp_path / ".metaloop" / "verification_result.json").exists()


def test_verify_workspace_fails_blocking_metric(tmp_path) -> None:
    (tmp_path / "summary.json").write_text(json.dumps({"score": 0.1}), encoding="utf-8")
    _write_capsule(
        tmp_path,
        [{"type": "json_metric_gate", "mode": "executable", "severity": "blocking", "path": "summary.json", "metric": "score", "operator": ">=", "threshold": 0.2}],
    )

    result = verify_workspace(tmp_path)

    assert result["status"] == "failed"
    assert result["hard_validator_results"][0]["passed"] is False


def test_verify_workspace_routes_manual_and_unsupported_blockers(tmp_path) -> None:
    _write_capsule(
        tmp_path,
        [{"type": "manual_acceptance", "mode": "manual", "severity": "blocking", "description": "review boundary"}],
    )
    manual = verify_workspace(tmp_path)
    assert manual["status"] == "review_required"
    assert manual["manual_validator_results"][0]["delegable"] is True

    _write_capsule(
        tmp_path / "authority",
        [{"type": "manual_acceptance", "mode": "manual", "severity": "blocking", "description": "user-only boundary", "requires_user_confirmation": True}],
    )
    authority = verify_workspace(tmp_path / "authority")
    assert authority["status"] == "human_acceptance_required"
    assert authority["manual_validator_results"][0]["delegable"] is False

    _write_capsule(
        tmp_path / "other",
        [{"type": "future_gate", "mode": "unsupported", "severity": "blocking", "description": "future validator"}],
    )
    unsupported = verify_workspace(tmp_path / "other")
    assert unsupported["status"] == "unsupported_verification_spec"


def test_verify_workspace_delegates_resource_gates_by_default(tmp_path) -> None:
    _write_capsule(
        tmp_path,
        [{"type": "file_exists", "mode": "executable", "severity": "blocking", "path": "result.txt"}],
        [{"type": "resource_gate", "mode": "manual", "severity": "blocking", "resource": "gpu"}],
    )
    (tmp_path / "result.txt").write_text("ok\n", encoding="utf-8")

    result = verify_workspace(tmp_path)

    assert result["status"] == "review_required"
    assert result["manual_validator_results"][0]["requires_user_confirmation"] is False
    assert result["manual_validator_results"][0]["delegable"] is True


def test_verify_workspace_applies_independent_review_result(tmp_path) -> None:
    capsule = _write_capsule(
        tmp_path,
        [{"type": "manual_acceptance", "mode": "manual", "severity": "blocking", "description": "review boundary"}],
    )
    first = verify_workspace(tmp_path)
    assert first["status"] == "review_required"

    review = build_review_result(
        workspace=tmp_path,
        capsule=capsule,
        decision="approved",
        reviewer="codex-reviewer",
        reviewer_role="reviewer",
        evidence=[".metaloop/execution_report.json", ".metaloop/verification_result.json"],
        notes="Evidence matches the locked review boundary.",
    )
    write_review_result(tmp_path, review)

    second = verify_workspace(tmp_path)
    assert second["status"] == "completed_verified"
    assert second["review_result"]["decision"] == "approved"


def test_verify_workspace_rejects_worker_or_stale_review_result(tmp_path) -> None:
    capsule = _write_capsule(
        tmp_path,
        [{"type": "manual_acceptance", "mode": "manual", "severity": "blocking", "description": "review boundary"}],
    )
    worker_review = build_review_result(
        workspace=tmp_path,
        capsule=capsule,
        decision="approved",
        reviewer="worker",
        reviewer_role="worker",
        evidence=[".metaloop/execution_report.json"],
    )
    write_review_result(tmp_path, worker_review)

    result = verify_workspace(tmp_path)

    assert result["status"] == "review_required"
    assert any("reviewer_role" in item["message"] for item in result["warnings"])


def test_old_review_cannot_approve_a_new_execution_report(tmp_path) -> None:
    capsule = _write_capsule(
        tmp_path,
        [{"type": "manual_acceptance", "mode": "manual", "severity": "blocking", "description": "review boundary"}],
    )
    first_report = json.loads((tmp_path / ".metaloop" / "execution_report.json").read_text(encoding="utf-8"))
    first = verify_workspace(tmp_path)
    assert first["status"] == "review_required"
    review = build_review_result(
        workspace=tmp_path,
        capsule=capsule,
        decision="approved",
        reviewer="codex-reviewer",
        evidence=[".metaloop/execution_report.json"],
    )
    write_review_result(tmp_path, review)
    assert verify_workspace(tmp_path)["status"] == "completed_verified"

    second_report = build_execution_report(workspace=tmp_path, capsule=capsule, status="completed", commands=[], evidence=["new execution"])
    write_execution_report(tmp_path, second_report)
    second = verify_workspace(tmp_path)

    assert first_report["execution_id"] != second_report["execution_id"]
    assert second["status"] == "review_required"
    messages = [item["message"] for item in second["warnings"] if item.get("type") == "review_result_invalid"]
    assert any("execution_id" in item for item in messages)
    assert any("execution_hash" in item for item in messages)


def test_verify_workspace_rejects_tampered_spec_hash(tmp_path) -> None:
    _write_capsule(tmp_path, [{"type": "file_exists", "mode": "executable", "severity": "blocking", "path": "missing.txt"}])
    capsule_path = tmp_path / ".metaloop" / "mission_capsule.json"
    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    capsule["verification_spec"]["validators"][0]["path"] = "other.txt"
    capsule_path.write_text(json.dumps(capsule, indent=2), encoding="utf-8")

    result = verify_workspace(tmp_path)

    assert result["status"] == "invalid_capsule"
    assert any("spec_hash" in error for error in result["errors"])
