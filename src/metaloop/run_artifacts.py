from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from metaloop.capsule import AttemptRecord, MissionCapsule
from metaloop.goal import GoalContract, RedesignProposal, VerificationResult
from metaloop.schemas import MissionSpec, utc_now


class StructuredRunManifest(BaseModel):
    schema_name: str = Field(default="metaloop.structured_run", alias="schema")
    version: str = "1.0"
    run_id: str
    mission_id: str
    mode: str
    status: str = "running"
    mission_path: str
    mission_capsule_path: str = ".metaloop/mission_capsule.json"
    goal_contract_path: str
    goal_prompt_path: str
    execution_report_path: str
    verification_result_path: str
    redesign_proposal_path: str = ".metaloop/redesign_proposal.json"
    attempt_record_path: str = ""
    codex_events_path: str
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StructuredRunArtifacts:
    """Small, stable .metaloop filesystem layout for the current run."""

    def __init__(self, workspace_root: str | Path, run_id: str) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.root = self.workspace_root / ".metaloop"
        self.run_id = run_id
        self.run_dir = self.root / "runs" / run_id
        self.mission_path = self.root / "mission.json"
        self.mission_capsule_path = self.root / "mission_capsule.json"
        self.goal_contract_path = self.root / "goal_contract.json"
        self.goal_prompt_path = self.root / "goal_prompt.md"
        self.execution_report_path = self.root / "execution_report.json"
        self.verification_result_path = self.root / "verification_result.json"
        self.redesign_proposal_path = self.root / "redesign_proposal.json"
        self.run_manifest_path = self.root / "run.json"
        self.attempts_dir = self.root / "attempts"
        self.codex_events_path = self.run_dir / "codex_events.jsonl"

    def prepare(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.attempts_dir.mkdir(parents=True, exist_ok=True)

    def write_inputs(
        self,
        mission: MissionSpec,
        contract: GoalContract,
        goal_prompt: str,
        *,
        mode: str,
        capsule: MissionCapsule | None = None,
    ) -> StructuredRunManifest:
        self.prepare()
        self.mission_path.write_text(mission.model_dump_json(indent=2), encoding="utf-8")
        if capsule is not None:
            self.mission_capsule_path.write_text(capsule.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        self.goal_contract_path.write_text(contract.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        self.goal_prompt_path.write_text(goal_prompt, encoding="utf-8")
        manifest = StructuredRunManifest(
            run_id=mission.run_id,
            mission_id=mission.run_id,
            mode=mode,
            mission_path=_relative(self.workspace_root, self.mission_path),
            mission_capsule_path=_relative(self.workspace_root, self.mission_capsule_path),
            goal_contract_path=_relative(self.workspace_root, self.goal_contract_path),
            goal_prompt_path=_relative(self.workspace_root, self.goal_prompt_path),
            execution_report_path=_relative(self.workspace_root, self.execution_report_path),
            verification_result_path=_relative(self.workspace_root, self.verification_result_path),
            redesign_proposal_path=_relative(self.workspace_root, self.redesign_proposal_path),
            codex_events_path=_relative(self.workspace_root, self.codex_events_path),
        )
        self.write_manifest(manifest)
        return manifest

    def append_codex_event(self, event: dict[str, Any]) -> None:
        self.prepare()
        with self.codex_events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def write_verification(self, result: VerificationResult) -> None:
        self.prepare()
        self.verification_result_path.write_text(result.model_dump_json(by_alias=True, indent=2), encoding="utf-8")

    def write_capsule(self, capsule: MissionCapsule) -> None:
        self.prepare()
        self.mission_capsule_path.write_text(capsule.model_dump_json(by_alias=True, indent=2), encoding="utf-8")

    def write_redesign_proposal(self, proposal: RedesignProposal) -> None:
        self.prepare()
        self.redesign_proposal_path.write_text(proposal.model_dump_json(by_alias=True, indent=2), encoding="utf-8")

    def write_attempt(self, attempt: AttemptRecord) -> Path:
        self.prepare()
        path = self.attempts_dir / f"{attempt.attempt_id}.json"
        path.write_text(attempt.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        return path

    def write_manifest(self, manifest: StructuredRunManifest) -> None:
        self.prepare()
        manifest.updated_at = utc_now()
        self.run_manifest_path.write_text(manifest.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        (self.run_dir / "run.json").write_text(manifest.model_dump_json(by_alias=True, indent=2), encoding="utf-8")


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
