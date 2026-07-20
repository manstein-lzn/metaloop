from __future__ import annotations

from pathlib import Path
from typing import Any

from metaloop_core.durable import DurableStore


def safe_point(workspace: str | Path = ".", *, task_id: str | None = None) -> dict[str, Any]:
    """Synchronous optional host hook; it never schedules or mutates work."""

    store = DurableStore(workspace)
    project = store.project()
    selected = task_id or project.get("default_task_id")
    integrity = store.integrity(selected)
    recovery = store.recovery(selected) if selected else None
    allowed = bool(integrity["passed"] and (recovery is None or recovery["workspace_alignment"] == "aligned"))
    return {"allowed": allowed, "project_id": project["project_id"], "task_id": selected, "integrity": integrity, "recovery": recovery}
