from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from metaloop.path_targets import is_valid_path_validation_target
from metaloop.policy import PolicyEngine
from metaloop.schemas import AcceptanceCriteria, MissionSpec


class ValidationResult(BaseModel):
    criteria_id: str
    passed: bool
    message: str = ""
    output: str = ""


class ArtifactValidator:
    def __init__(self, policy_engine: PolicyEngine | None = None) -> None:
        self.policy_engine = policy_engine or PolicyEngine()

    def validate(self, mission: MissionSpec) -> list[ValidationResult]:
        return [self.validate_criterion(mission, criterion) for criterion in mission.acceptance_criteria]

    def validate_criterion(self, mission: MissionSpec, criterion: AcceptanceCriteria) -> ValidationResult:
        if criterion.validation_type in {"manual", "llm_review"}:
            return ValidationResult(criteria_id=criterion.id, passed=True, message="deferred validation")
        if criterion.validation_type == "file_exists":
            return self._validate_file_exists(mission, criterion)
        if criterion.validation_type == "file_contains":
            return self._validate_file_contains(mission, criterion)
        if criterion.validation_type == "command":
            return self._validate_command(mission, criterion)
        if criterion.validation_type == "schema":
            return self._validate_schema(mission, criterion)
        return ValidationResult(criteria_id=criterion.id, passed=False, message="unsupported validation type")

    def _validate_file_exists(self, mission: MissionSpec, criterion: AcceptanceCriteria) -> ValidationResult:
        if not criterion.validation_target:
            return ValidationResult(criteria_id=criterion.id, passed=False, message="file_exists target is required")
        if not is_valid_path_validation_target(criterion.validation_target):
            return ValidationResult(criteria_id=criterion.id, passed=False, message="invalid path validation target")
        decision = self.policy_engine.check_workspace_path(mission, criterion.validation_target)
        if not decision.allowed:
            return ValidationResult(criteria_id=criterion.id, passed=False, message=decision.reason)
        workspace = Path(mission.policy.workspace_root).expanduser().resolve()
        path = Path(criterion.validation_target)
        if not path.is_absolute():
            path = workspace / path
        exists = path.exists()
        return ValidationResult(
            criteria_id=criterion.id,
            passed=exists,
            message="file exists" if exists else f"file does not exist: {path}",
        )

    def _validate_file_contains(self, mission: MissionSpec, criterion: AcceptanceCriteria) -> ValidationResult:
        parsed = _parse_file_contains_target(criterion.validation_target)
        if parsed is None:
            return ValidationResult(
                criteria_id=criterion.id,
                passed=False,
                message="file_contains target must be JSON {\"path\":\"...\",\"contains\":\"...\"} or path::text",
            )
        relative_path, expected_text = parsed
        if not is_valid_path_validation_target(relative_path):
            return ValidationResult(criteria_id=criterion.id, passed=False, message="invalid path validation target")
        decision = self.policy_engine.check_workspace_path(mission, relative_path)
        if not decision.allowed:
            return ValidationResult(criteria_id=criterion.id, passed=False, message=decision.reason)
        workspace = Path(mission.policy.workspace_root).expanduser().resolve()
        path = Path(relative_path)
        if not path.is_absolute():
            path = workspace / path
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ValidationResult(criteria_id=criterion.id, passed=False, message=f"file does not exist: {path}")
        except UnicodeDecodeError as exc:
            return ValidationResult(criteria_id=criterion.id, passed=False, message=f"file is not utf-8 text: {exc}")
        passed = expected_text in content
        return ValidationResult(
            criteria_id=criterion.id,
            passed=passed,
            message="file contains expected text" if passed else f"file does not contain expected text: {path}",
        )

    def _validate_command(self, mission: MissionSpec, criterion: AcceptanceCriteria) -> ValidationResult:
        if not criterion.validation_target:
            return ValidationResult(criteria_id=criterion.id, passed=False, message="command target is required")
        if "validator.command" not in mission.policy.allowed_tools:
            return ValidationResult(
                criteria_id=criterion.id,
                passed=False,
                message="command validator requires explicit allowed_tools entry: validator.command",
            )
        tool_decision = self.policy_engine.check_tool(mission, "validator.command", mission.policy.risk_level)
        if not tool_decision.allowed:
            return ValidationResult(criteria_id=criterion.id, passed=False, message=tool_decision.reason)
        workspace = Path(mission.policy.workspace_root).expanduser().resolve()
        try:
            command = json.loads(criterion.validation_target)
        except json.JSONDecodeError:
            command = shlex.split(criterion.validation_target)
        if isinstance(command, str):
            command = [command]
        if not isinstance(command, list) or not all(isinstance(item, str) and item for item in command):
            return ValidationResult(
                criteria_id=criterion.id,
                passed=False,
                message='command target must be an argv JSON array or shell-like argv string',
            )
        completed = subprocess.run(
            command,
            cwd=workspace,
            text=True,
            capture_output=True,
            timeout=min(120, mission.budget.max_wall_time_seconds),
            check=False,
        )
        output = (completed.stdout + completed.stderr)[-4000:]
        return ValidationResult(
            criteria_id=criterion.id,
            passed=completed.returncode == 0,
            message=f"command exited with {completed.returncode}",
            output=output,
        )

    def _validate_schema(self, mission: MissionSpec, criterion: AcceptanceCriteria) -> ValidationResult:
        if not criterion.validation_target:
            return ValidationResult(criteria_id=criterion.id, passed=False, message="schema target is required")
        if not is_valid_path_validation_target(criterion.validation_target):
            return ValidationResult(criteria_id=criterion.id, passed=False, message="invalid path validation target")
        decision = self.policy_engine.check_workspace_path(mission, criterion.validation_target)
        if not decision.allowed:
            return ValidationResult(criteria_id=criterion.id, passed=False, message=decision.reason)
        workspace = Path(mission.policy.workspace_root).expanduser().resolve()
        path = Path(criterion.validation_target)
        if not path.is_absolute():
            path = workspace / path
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return ValidationResult(criteria_id=criterion.id, passed=False, message=f"invalid json: {exc}")
        return ValidationResult(criteria_id=criterion.id, passed=True, message="json parsed")


def _parse_file_contains_target(target: str | None) -> tuple[str, str] | None:
    if not target:
        return None
    text = target.strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        path = payload.get("path")
        contains = payload.get("contains")
        if isinstance(path, str) and path.strip() and isinstance(contains, str):
            return path.strip(), contains
        return None
    if "::" not in text:
        return None
    path, contains = text.split("::", 1)
    path = path.strip()
    if not path:
        return None
    return path, contains
