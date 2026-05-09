from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metaloop_core.ids import utc_now
from metaloop_core.schemas import THREAD_REGISTRY_SCHEMA, THREAD_STATUSES


class ThreadRegistry:
    """Persistent registry for long-lived Codex thread responsibilities."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.path = self.workspace / ".metaloop" / "threads.json"

    def load(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def status(self) -> dict[str, Any]:
        registry = self.load()
        if registry is None:
            return {"state": "missing", "path": str(self.path), "agents": {}}
        return {
            "state": "ready",
            "path": str(self.path),
            "agents": registry.get("agents", {}),
            "count": len(registry.get("agents", {})) if isinstance(registry.get("agents"), dict) else 0,
        }

    def register(
        self,
        *,
        role: str,
        thread_id: str,
        role_type: str = "worker",
        agent_name: str = "",
        responsibilities: list[str] | tuple[str, ...] = (),
        context_policy: str = "persistent_thread_plus_metaloop_artifacts",
        notes: list[str] | tuple[str, ...] = (),
        status: str = "active",
    ) -> dict[str, Any]:
        role = _required_slug(role, "role")
        thread_id = _required_text(thread_id, "thread_id")
        if status not in THREAD_STATUSES:
            raise ValueError(f"unknown thread status: {status}")
        registry = self._ensure_registry()
        agents = registry.setdefault("agents", {})
        previous = agents.get(role) if isinstance(agents, dict) else None
        now = utc_now()
        history = list(previous.get("history", [])) if isinstance(previous, dict) else []
        history.append({"event": "registered" if previous is None else "replaced", "thread_id": thread_id, "status": status, "notes": list(notes), "at": now})
        agents[role] = {
            "role": role,
            "role_type": _required_slug(role_type, "role_type"),
            "thread_id": thread_id,
            "agent_name": agent_name.strip(),
            "responsibilities": list(responsibilities) or [f"Own the {role} MetaLoop responsibility boundary."],
            "context_policy": context_policy.strip() or "persistent_thread_plus_metaloop_artifacts",
            "status": status,
            "current_capsule_id": "",
            "last_handoff_artifact": "",
            "notes": list(notes),
            "created_at": previous.get("created_at", now) if isinstance(previous, dict) else now,
            "updated_at": now,
            "history": history,
        }
        self._write(registry)
        return agents[role]

    def update(
        self,
        *,
        role: str,
        thread_id: str | None = None,
        status: str | None = None,
        notes: list[str] | tuple[str, ...] = (),
    ) -> dict[str, Any]:
        role = _required_slug(role, "role")
        registry = self.load()
        if registry is None or not isinstance(registry.get("agents"), dict) or role not in registry["agents"]:
            raise KeyError(f"thread role not found: {role}")
        agent = registry["agents"][role]
        if thread_id is not None:
            agent["thread_id"] = _required_text(thread_id, "thread_id")
        if status is not None:
            if status not in THREAD_STATUSES:
                raise ValueError(f"unknown thread status: {status}")
            agent["status"] = status
        if notes:
            agent.setdefault("notes", []).extend(notes)
        agent["updated_at"] = utc_now()
        agent.setdefault("history", []).append({"event": "updated", "thread_id": agent.get("thread_id", ""), "status": agent.get("status", ""), "notes": list(notes), "at": agent["updated_at"]})
        self._write(registry)
        return agent

    def _ensure_registry(self) -> dict[str, Any]:
        registry = self.load()
        if registry is not None and isinstance(registry.get("agents"), dict):
            return registry
        now = utc_now()
        return {
            "schema": THREAD_REGISTRY_SCHEMA,
            "version": "1.0",
            "workspace": str(self.workspace),
            "created_at": now,
            "updated_at": now,
            "coordination_rule": "Persistent agent threads may keep their own context; shared operational truth is .metaloop artifacts.",
            "agents": {},
        }

    def _write(self, registry: dict[str, Any]) -> None:
        registry["updated_at"] = utc_now()
        registry.setdefault("schema", THREAD_REGISTRY_SCHEMA)
        registry.setdefault("version", "1.0")
        registry.setdefault("workspace", str(self.workspace))
        registry.setdefault("coordination_rule", "Persistent agent threads may keep their own context; shared operational truth is .metaloop artifacts.")
        registry.setdefault("agents", {})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")


def _required_slug(value: str, name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must be non-empty")
    return stripped


def _required_text(value: str, name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must be non-empty")
    return stripped
