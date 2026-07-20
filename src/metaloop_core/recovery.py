from __future__ import annotations

from typing import Any


def recovery_view(store: Any, task_id: str) -> dict[str, Any]:
    """Return the derived, workspace-aware recovery projection."""

    return store.recovery(task_id)


def write_recovery(store: Any, task_id: str, markdown: str) -> dict[str, Any]:
    return store.write_recovery(task_id, markdown)
