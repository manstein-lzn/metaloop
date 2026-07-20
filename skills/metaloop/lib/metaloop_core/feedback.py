from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from metaloop_core.adaptive_loop import decide_next
from metaloop_core.execution import load_execution_report
from metaloop_core.ids import new_id, utc_now
from metaloop_core.schemas import ADAPTIVE_DECISIONS, DIAGNOSIS_REPORT_SCHEMA, OBSERVATION_REPORT_SCHEMA
from metaloop_core.verification import load_verification_summary


@dataclass(frozen=True)
class ObservationReport:
    """Generic observed feedback from execution and verification artifacts."""

    observation_id: str
    status: str
    summary: str
    evidence: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": OBSERVATION_REPORT_SCHEMA,
            "version": "1.0",
            "observation_id": self.observation_id,
            "created_at": self.created_at,
            "status": self.status,
            "summary": self.summary,
            "evidence": list(self.evidence),
            "signals": dict(self.signals),
        }


@dataclass(frozen=True)
class DiagnosisReport:
    """Generic diagnosis and control decision after observing feedback."""

    diagnosis_id: str
    evaluation_status: str
    diagnosis: str
    decision: str
    next_plan: str
    evidence: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DIAGNOSIS_REPORT_SCHEMA,
            "version": "1.0",
            "diagnosis_id": self.diagnosis_id,
            "created_at": self.created_at,
            "evaluation_status": self.evaluation_status,
            "diagnosis": self.diagnosis,
            "decision": self.decision,
            "next_plan": self.next_plan,
            "evidence": list(self.evidence),
        }


def observation_report_path(workspace: str | Path = ".") -> Path:
    return Path(workspace).expanduser().resolve() / ".metaloop" / "observation_report.json"


def diagnosis_report_path(workspace: str | Path = ".") -> Path:
    return Path(workspace).expanduser().resolve() / ".metaloop" / "diagnosis_report.json"


def observe_workspace(workspace: str | Path = ".", *, write: bool = False) -> dict[str, Any]:
    """Summarize execution and verification artifacts into observable feedback."""

    root = Path(workspace).expanduser().resolve()
    execution = load_execution_report(root)
    verification = load_verification_summary(root)
    evidence: list[str] = []
    signals: dict[str, Any] = {}

    if execution is not None:
        evidence.append(".metaloop/execution_report.json")
        signals["execution_status"] = execution.get("status")
        signals["command_count"] = len(execution.get("commands", [])) if isinstance(execution.get("commands"), list) else 0
        signals["execution_evidence_count"] = len(execution.get("evidence", [])) if isinstance(execution.get("evidence"), list) else 0
    if verification is not None:
        evidence.append(".metaloop/verification_result.json")
        signals["verification_status"] = verification.status
        signals["hard_failures"] = verification.hard_failures
        signals["manual_blockers"] = verification.manual_blockers
        signals["review_blockers"] = verification.review_blockers
        signals["human_authority_blockers"] = verification.human_authority_blockers
        signals["unsupported_blockers"] = verification.unsupported_blockers

    if execution is None and verification is None:
        status = "missing_feedback"
        summary = "No ExecutionReport or VerificationResult is available to observe."
    elif verification is None:
        status = "unverified_execution"
        summary = f"ExecutionReport status is {signals.get('execution_status')}; verification has not run."
    elif verification.completed_verified:
        status = "satisfied"
        summary = "Verification completed successfully."
    else:
        status = "not_satisfied"
        summary = f"Verification status is {verification.status}: {verification.reason}"

    report = ObservationReport(
        observation_id=new_id("observation"),
        status=status,
        summary=summary,
        evidence=evidence,
        signals=signals,
    ).to_dict()
    if write:
        write_observation_report(root, report)
    return report


def diagnose_next(observation: dict[str, Any], *, next_plan: str = "", decision: str = "") -> dict[str, Any]:
    """Create a domain-neutral diagnosis and control decision from observation."""

    status = str(observation.get("status") or "unknown")
    signals = observation.get("signals") if isinstance(observation.get("signals"), dict) else {}
    evidence = observation.get("evidence") if isinstance(observation.get("evidence"), list) else []
    if status == "satisfied":
        evaluation_status = "satisfied"
        diagnosis = "Locked verification gates are satisfied."
        default_next_plan = "Ask for any explicitly required final acceptance or close the loop."
    elif status == "missing_feedback":
        evaluation_status = "unknown"
        diagnosis = "The loop lacks observable feedback; execution and verification must run before reliable control decisions."
        default_next_plan = "Run execution and verification to collect observable feedback."
    elif status == "unverified_execution":
        evaluation_status = "unknown"
        diagnosis = "Execution exists but has not been independently verified."
        default_next_plan = "Run verification before choosing repair, pivot, or redesign."
    elif signals.get("unsupported_blockers", 0) > 0:
        evaluation_status = "blocked"
        diagnosis = "A blocking validator requires unsupported verification capability."
        default_next_plan = "Add extension support or redesign the unsupported verification gate."
        default_decision = "escalate"
    elif signals.get("human_authority_blockers", 0) > 0:
        evaluation_status = "blocked"
        diagnosis = "A blocking validator requires user authority."
        default_next_plan = "Escalate for user authorization or revise acceptance through redesign."
        default_decision = "escalate"
    elif signals.get("review_blockers", 0) > 0 or signals.get("manual_blockers", 0) > 0:
        evaluation_status = "blocked"
        diagnosis = "A blocking validator requires independent reviewer judgment."
        default_next_plan = "Ask a Codex reviewer to inspect the locked evidence and record the review outcome."
        default_decision = "escalate"
    elif signals.get("hard_failures", 0) > 0:
        evaluation_status = "not_satisfied"
        diagnosis = "One or more executable blocking validators failed."
        default_next_plan = "Analyze failed validators, preserve the locked gates, and choose the next high-signal attempt."
        default_decision = "continue"
    else:
        evaluation_status = "unknown"
        diagnosis = "Feedback is present but does not classify cleanly; inspect artifacts before acting."
        default_next_plan = "Inspect ExecutionReport and VerificationResult, then record a more specific diagnosis."
        default_decision = "continue"

    if status in {"satisfied", "missing_feedback", "unverified_execution"}:
        default_decision = decide_next(evaluation_status=evaluation_status, diagnosis=diagnosis, next_plan=default_next_plan)

    plan = next_plan.strip() or default_next_plan
    resolved_decision = decision.strip() or default_decision
    if resolved_decision not in ADAPTIVE_DECISIONS:
        raise ValueError(f"decision must be one of {sorted(ADAPTIVE_DECISIONS)}")
    return DiagnosisReport(
        diagnosis_id=new_id("diagnosis"),
        evaluation_status=evaluation_status,
        diagnosis=diagnosis,
        decision=resolved_decision,
        next_plan=plan,
        evidence=[str(item) for item in evidence if isinstance(item, str)],
    ).to_dict()


def write_observation_report(workspace: str | Path, report: dict[str, Any]) -> Path:
    path = observation_report_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_diagnosis_report(workspace: str | Path, report: dict[str, Any]) -> Path:
    path = diagnosis_report_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
