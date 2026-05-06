from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from metaloop.capsule import AttemptRecord
from metaloop.goal import VerificationResult
from metaloop.schemas import new_id, utc_now


class GitSnapshot(BaseModel):
    commit: str | None = None
    branch: str | None = None
    dirty: bool = False
    changed_files: list[str] = Field(default_factory=list)
    available: bool = False


class AttemptHistoryRecord(BaseModel):
    schema_name: Literal["metaloop.attempt_history_record"] = Field(
        default="metaloop.attempt_history_record",
        alias="schema",
    )
    version: str = "1.0"
    history_id: str = Field(default_factory=lambda: new_id("attempt_history"))
    mission_id: str
    capsule_id: str
    capsule_version: str
    attempt_id: str
    outcome: str
    verification_status: str
    summary: str = ""
    commit_ref: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    validation_result: str = ""
    reviewer_decision: str = ""
    failure_mode: str = ""
    lesson: str = ""
    git: GitSnapshot = Field(default_factory=GitSnapshot)
    created_at: str = Field(default_factory=utc_now)


def build_attempt_history_record(
    *,
    workspace_root: str | Path,
    attempt: AttemptRecord,
    verification: VerificationResult,
) -> AttemptHistoryRecord:
    git = inspect_git_snapshot(workspace_root)
    report = verification.execution_report
    changed_files = filter_attempt_changed_files([*git.changed_files, *attempt.artifacts_produced])
    reviewer_decision = ""
    if verification.soft_review_decision is not None:
        reviewer_decision = verification.soft_review_decision.route.value
    return AttemptHistoryRecord(
        mission_id=verification.mission_id,
        capsule_id=attempt.capsule_id,
        capsule_version=attempt.capsule_version,
        attempt_id=attempt.attempt_id,
        outcome=attempt.outcome.value,
        verification_status=verification.status.value,
        summary=report.summary if report is not None else verification.reason,
        commit_ref=git.commit,
        changed_files=changed_files,
        validation_commands=report.commands_run if report is not None else [],
        validation_result=verification.reason,
        reviewer_decision=reviewer_decision,
        failure_mode=attempt.failure_mode,
        lesson="; ".join(attempt.lessons),
        git=git,
    )


def write_attempt_history_record(
    *,
    workspace_root: str | Path,
    attempt: AttemptRecord,
    verification: VerificationResult,
) -> Path:
    workspace = Path(workspace_root).expanduser().resolve()
    record = build_attempt_history_record(workspace_root=workspace, attempt=attempt, verification=verification)
    attempts_dir = workspace / ".metaloop" / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    path = attempts_dir / f"{attempt.attempt_id}.json"
    path.write_text(record.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
    return path


def inspect_git_snapshot(workspace_root: str | Path) -> GitSnapshot:
    workspace = Path(workspace_root).expanduser().resolve()
    commit = _git(workspace, ["rev-parse", "HEAD"])
    if commit is None:
        return GitSnapshot()
    branch = _git(workspace, ["branch", "--show-current"])
    status = _git(workspace, ["status", "--short"])
    changed_files = _parse_git_status_files(status or "")
    changed_files = filter_attempt_changed_files(changed_files)
    return GitSnapshot(
        commit=commit,
        branch=branch or None,
        dirty=bool(changed_files),
        changed_files=changed_files,
        available=True,
    )


def _git(workspace: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=workspace,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _parse_git_status_files(status: str) -> list[str]:
    files: list[str] = []
    for line in status.splitlines():
        if len(line) < 3:
            continue
        path = line[2:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path:
            files.append(path)
    return list(dict.fromkeys(files))


def filter_attempt_changed_files(paths: list[str] | tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(path for path in paths if path and not is_attempt_changed_file_noise(path)))


def is_attempt_changed_file_noise(path: str) -> bool:
    normalized = path.replace("\\", "/").strip()
    if not normalized:
        return True
    if normalized == ".metaloop" or normalized.startswith(".metaloop/"):
        return True
    if normalized == "metaloop.mission.json":
        return True
    if "/__pycache__/" in f"/{normalized}/":
        return True
    return normalized.endswith((".pyc", ".pyo"))
