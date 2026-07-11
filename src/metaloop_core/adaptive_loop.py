from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from metaloop_core.ids import new_id, utc_now
from metaloop_core.schemas import (
    ADAPTIVE_DECISIONS,
    ADAPTIVE_ITERATION_SCHEMA,
    ADAPTIVE_LOOP_SCHEMA,
    ADAPTIVE_LOOP_STATUSES,
    EVALUATION_STATUSES,
)


@dataclass(frozen=True)
class AdaptiveIteration:
    """One generic goal-seeking loop iteration."""

    iteration_id: str
    goal: str
    plan: str
    observation: str
    evaluation_status: str
    diagnosis: str
    decision: str
    next_plan: str
    rationale: str = ""
    evidence: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ADAPTIVE_ITERATION_SCHEMA,
            "version": "1.0",
            "iteration_id": self.iteration_id,
            "created_at": self.created_at,
            "goal": self.goal,
            "plan": self.plan,
            "rationale": self.rationale,
            "observation": self.observation,
            "evaluation_status": self.evaluation_status,
            "diagnosis": self.diagnosis,
            "decision": self.decision,
            "next_plan": self.next_plan,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class AdaptiveLoopState:
    """Durable state for a generic adaptive goal loop."""

    loop_id: str
    goal: str
    status: str
    current_plan: str
    created_at: str
    updated_at: str
    constraints: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    known_facts: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    iterations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ADAPTIVE_LOOP_SCHEMA,
            "version": "1.0",
            "loop_id": self.loop_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "goal": self.goal,
            "status": self.status,
            "current_plan": self.current_plan,
            "constraints": list(self.constraints),
            "success_criteria": list(self.success_criteria),
            "known_facts": list(self.known_facts),
            "open_questions": list(self.open_questions),
            "iterations": list(self.iterations),
        }


def adaptive_loop_path(workspace: str | Path = ".") -> Path:
    return Path(workspace).expanduser().resolve() / ".metaloop" / "adaptive_loop.json"


def new_adaptive_loop(
    *,
    goal: str,
    current_plan: str,
    constraints: list[str] | tuple[str, ...] = (),
    success_criteria: list[str] | tuple[str, ...] = (),
    known_facts: list[str] | tuple[str, ...] = (),
    open_questions: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    now = utc_now()
    state = AdaptiveLoopState(
        loop_id=new_id("loop"),
        goal=_required_text(goal, "goal"),
        status="active",
        current_plan=_required_text(current_plan, "current_plan"),
        created_at=now,
        updated_at=now,
        constraints=_clean_list(constraints),
        success_criteria=_clean_list(success_criteria),
        known_facts=_clean_list(known_facts),
        open_questions=_clean_list(open_questions),
        iterations=[],
    )
    return state.to_dict()


def load_adaptive_loop(workspace: str | Path = ".") -> dict[str, Any] | None:
    path = adaptive_loop_path(workspace)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_adaptive_loop(workspace: str | Path, state: dict[str, Any]) -> Path:
    path = adaptive_loop_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def validate_adaptive_loop(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["adaptive_loop.json is missing or is not a JSON object"]
    errors: list[str] = []
    if payload.get("schema") != ADAPTIVE_LOOP_SCHEMA:
        errors.append(f"schema must be {ADAPTIVE_LOOP_SCHEMA}")
    for key in ["version", "loop_id", "created_at", "updated_at", "goal", "status", "current_plan"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    if payload.get("status") not in ADAPTIVE_LOOP_STATUSES:
        errors.append(f"status must be one of {sorted(ADAPTIVE_LOOP_STATUSES)}")
    for key in ["constraints", "success_criteria", "known_facts", "open_questions", "iterations"]:
        if not isinstance(payload.get(key), list):
            errors.append(f"{key} must be a list")
    for index, iteration in enumerate(payload.get("iterations", [])):
        errors.extend(f"iterations[{index}].{error}" for error in validate_iteration(iteration))
    return errors


def validate_iteration(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["iteration must be a JSON object"]
    errors: list[str] = []
    if payload.get("schema") != ADAPTIVE_ITERATION_SCHEMA:
        errors.append(f"schema must be {ADAPTIVE_ITERATION_SCHEMA}")
    for key in ["version", "iteration_id", "created_at", "goal", "plan", "observation", "evaluation_status", "diagnosis", "decision", "next_plan"]:
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"{key} must be a non-empty string")
    if payload.get("evaluation_status") not in EVALUATION_STATUSES:
        errors.append(f"evaluation_status must be one of {sorted(EVALUATION_STATUSES)}")
    if payload.get("decision") not in ADAPTIVE_DECISIONS:
        errors.append(f"decision must be one of {sorted(ADAPTIVE_DECISIONS)}")
    if not isinstance(payload.get("evidence"), list):
        errors.append("evidence must be a list")
    elif not all(isinstance(item, str) for item in payload["evidence"]):
        errors.append("evidence items must be strings")
    return errors


def append_iteration(
    state: dict[str, Any],
    *,
    plan: str,
    observation: str,
    evaluation_status: str,
    diagnosis: str,
    next_plan: str,
    decision: str | None = None,
    rationale: str = "",
    evidence: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    errors = validate_adaptive_loop(state)
    if errors:
        raise ValueError("invalid adaptive loop state: " + "; ".join(errors))
    status = _required_text(evaluation_status, "evaluation_status")
    resolved_decision = decision or decide_next(evaluation_status=status, diagnosis=diagnosis, next_plan=next_plan)
    iteration = AdaptiveIteration(
        iteration_id=new_id("iteration"),
        goal=str(state["goal"]),
        plan=_required_text(plan, "plan"),
        rationale=rationale.strip(),
        observation=_required_text(observation, "observation"),
        evaluation_status=status,
        diagnosis=_required_text(diagnosis, "diagnosis"),
        decision=resolved_decision,
        next_plan=_required_text(next_plan, "next_plan"),
        evidence=_clean_list(evidence),
    ).to_dict()
    iteration_errors = validate_iteration(iteration)
    if iteration_errors:
        raise ValueError("invalid adaptive loop iteration: " + "; ".join(iteration_errors))

    updated = dict(state)
    updated["iterations"] = [*state.get("iterations", []), iteration]
    updated["updated_at"] = utc_now()
    updated["current_plan"] = iteration["next_plan"]
    updated["status"] = _status_after_decision(resolved_decision)
    return updated


def record_iteration(workspace: str | Path, **kwargs: Any) -> dict[str, Any]:
    state = load_adaptive_loop(workspace)
    if state is None:
        raise FileNotFoundError("No adaptive_loop.json found; create a loop before recording iterations")
    updated = append_iteration(state, **kwargs)
    write_adaptive_loop(workspace, updated)
    return updated


def decide_next(*, evaluation_status: str, diagnosis: str = "", next_plan: str = "") -> str:
    """Map mechanical status only; semantic next actions must be explicit."""

    status = evaluation_status.strip()
    if status == "satisfied":
        return "complete"
    if status == "invalid_goal":
        return "redesign"
    if status == "blocked":
        return "escalate"
    return "continue"


def _status_after_decision(decision: str) -> str:
    if decision == "complete":
        return "completed"
    if decision == "stop":
        return "stopped"
    if decision == "escalate":
        return "blocked"
    return "active"


def _required_text(value: str, name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must be non-empty")
    return stripped


def _clean_list(values: list[str] | tuple[str, ...]) -> list[str]:
    return [item.strip() for item in values if isinstance(item, str) and item.strip()]
