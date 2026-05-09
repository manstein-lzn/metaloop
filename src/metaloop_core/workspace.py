from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from metaloop_core.event_log import EventLog
from metaloop_core.thread_registry import ThreadRegistry


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path

    @property
    def metaloop_dir(self) -> Path:
        return self.root / ".metaloop"

    @property
    def mission_capsule(self) -> Path:
        return self.metaloop_dir / "mission_capsule.json"

    @property
    def execution_report(self) -> Path:
        return self.metaloop_dir / "execution_report.json"

    @property
    def verification_result(self) -> Path:
        return self.metaloop_dir / "verification_result.json"

    @property
    def thread_registry(self) -> Path:
        return self.metaloop_dir / "threads.json"

    @property
    def event_log(self) -> Path:
        return self.metaloop_dir / "event_log.jsonl"

    @property
    def adaptive_loop(self) -> Path:
        return self.metaloop_dir / "adaptive_loop.json"


class WorkspaceState:
    """Read-only view over the portable ``.metaloop`` workspace state."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self.paths = WorkspacePaths(Path(workspace).expanduser().resolve())

    @property
    def root(self) -> Path:
        return self.paths.root

    def read_json(self, path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def mission_capsule(self) -> dict[str, Any] | None:
        return self.read_json(self.paths.mission_capsule)

    def execution_report(self) -> dict[str, Any] | None:
        return self.read_json(self.paths.execution_report)

    def verification_result(self) -> dict[str, Any] | None:
        return self.read_json(self.paths.verification_result)

    def adaptive_loop(self) -> dict[str, Any] | None:
        return self.read_json(self.paths.adaptive_loop)

    def status(self) -> dict[str, Any]:
        capsule = self.mission_capsule()
        execution = self.execution_report()
        verification = self.verification_result()
        adaptive_loop = self.adaptive_loop()
        thread_registry = ThreadRegistry(self.root).load()
        events = EventLog(self.root).list()
        return {
            "workspace": str(self.root),
            "capsule": _artifact_state(capsule, self.paths.mission_capsule, status_key="current_status"),
            "execution": _artifact_state(execution, self.paths.execution_report, status_key="status"),
            "verification": _artifact_state(verification, self.paths.verification_result, status_key="status"),
            "adaptive_loop": _artifact_state(adaptive_loop, self.paths.adaptive_loop, status_key="status"),
            "threads": {
                "state": "ready" if thread_registry else "missing",
                "path": str(self.paths.thread_registry),
                "count": len(thread_registry.get("agents", {})) if thread_registry else 0,
            },
            "events": {
                "state": "ready" if self.paths.event_log.exists() else "missing",
                "path": str(self.paths.event_log),
                "count": len(events),
                "latest": events[-1] if events else None,
            },
        }


def _artifact_state(payload: dict[str, Any] | None, path: Path, *, status_key: str) -> dict[str, Any]:
    if payload is None:
        return {"state": "missing", "path": str(path), "status": None}
    return {
        "state": "ready",
        "path": str(path),
        "status": payload.get(status_key),
        "schema": payload.get("schema"),
    }
