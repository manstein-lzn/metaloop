from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metaloop_core.ids import new_id, utc_now
from metaloop_core.schemas import EVENT_SCHEMA, EVENT_TYPES


class EventLog:
    """Append-only JSONL event log for lightweight long-task continuity."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.path = self.workspace / ".metaloop" / "event_log.jsonl"

    def append(
        self,
        *,
        event_type: str,
        summary: str,
        agent: str = "",
        evidence: list[str] | tuple[str, ...] = (),
        decision: str = "",
        next_action: str = "",
        thread_role: str = "",
        thread_id: str = "",
        capsule_id: str = "",
    ) -> dict[str, Any]:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {event_type}")
        summary = summary.strip()
        if not summary:
            raise ValueError("summary must be non-empty")
        event = {
            "schema": EVENT_SCHEMA,
            "version": "1.0",
            "event_id": new_id("event"),
            "created_at": utc_now(),
            "workspace": str(self.workspace),
            "capsule_id": capsule_id,
            "type": event_type,
            "agent": agent.strip(),
            "thread_role": thread_role.strip(),
            "thread_id": thread_id.strip(),
            "summary": summary,
            "evidence": list(evidence),
            "decision": decision.strip(),
            "next_action": next_action.strip(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def list(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
        if limit is not None and limit >= 0:
            return events[-limit:]
        return events
