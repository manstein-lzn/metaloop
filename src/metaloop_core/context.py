from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from metaloop_core.event_log import EventLog
from metaloop_core.ids import utc_now
from metaloop_core.schemas import CONTEXT_FILE_NAMES, CONTEXT_SUMMARY_SCHEMA


CONTEXT_TEMPLATES: dict[str, str] = {
    "project_brief.md": """# Project Brief

## Goal

-

## Non-Goals

-

## Locked Acceptance

-

## Constraints

-

## Key Paths

-
""",
    "resume_brief.md": """# Resume Brief

## Current Goal

-

## Locked Acceptance

-

## Current Best Result

-

## Latest Diagnosis

-

## Next Plan

-

## Read First

- .metaloop/mission_capsule.json
- .metaloop/verification_result.json
- .metaloop/adaptive_loop.json
""",
    "current_hypothesis.md": """# Current Hypothesis

## Hypothesis

-

## Rationale

-

## Evidence

-

## Next Test

-
""",
    "failed_attempts.md": """# Failed Attempts

## Do Not Repeat

-

## Attempt Notes

-
""",
}

RESUME_READ_ORDER = [
    ".metaloop/context/resume_brief.md",
    ".metaloop/mission_capsule.json",
    ".metaloop/verification_result.json",
    ".metaloop/adaptive_loop.json",
    ".metaloop/context/current_hypothesis.md",
    ".metaloop/context/failed_attempts.md",
    ".metaloop/event_log.jsonl",
]


def context_dir(workspace: str | Path = ".") -> Path:
    return Path(workspace).expanduser().resolve() / ".metaloop" / "context"


def context_file_path(workspace: str | Path, name: str) -> Path:
    return context_dir(workspace) / _context_filename(name)


def ensure_context_files(
    workspace: str | Path,
    *,
    names: list[str] | tuple[str, ...] | None = None,
    created_by: str = "codex",
) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    selected = [_context_filename(name) for name in (names or sorted(CONTEXT_FILE_NAMES))]
    created: list[str] = []
    existing: list[str] = []
    for name in selected:
        path = context_file_path(root, name)
        if path.exists():
            existing.append(str(path))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(CONTEXT_TEMPLATES[name], encoding="utf-8")
        created.append(str(path))
    if created:
        EventLog(root).append(
            event_type="note",
            agent=created_by,
            summary=f"Initialized context checkpoint files: {', '.join(Path(item).name for item in created)}",
            evidence=created,
            next_action="keep_resume_brief_current_during_long_tasks",
        )
    return {"created": created, "existing": existing, "summary": context_summary(root)}


def write_context_file(
    workspace: str | Path,
    *,
    name: str,
    content: str,
    created_by: str = "codex",
    append: bool = False,
) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    filename = _context_filename(name)
    if not content.strip():
        raise ValueError("content must be non-empty")
    path = context_file_path(root, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = content.rstrip() + "\n"
    if append and path.exists():
        previous = path.read_text(encoding="utf-8")
        text = previous.rstrip() + "\n\n" + text
    path.write_text(text, encoding="utf-8")
    EventLog(root).append(
        event_type="note",
        agent=created_by.strip() or "codex",
        summary=f"Updated context checkpoint {filename}.",
        evidence=[str(path)],
        next_action="use_context_checkpoint_before_reading_full_history",
    )
    return {"name": filename, "path": str(path), "size": path.stat().st_size, "updated_at": _mtime(path)}


def read_context_file(workspace: str | Path, name: str) -> str:
    return context_file_path(workspace, name).read_text(encoding="utf-8")


def context_summary(workspace: str | Path = ".") -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    files = []
    for name in sorted(CONTEXT_FILE_NAMES):
        path = context_file_path(root, name)
        files.append(
            {
                "name": name,
                "path": str(path),
                "state": "ready" if path.exists() else "missing",
                "size": path.stat().st_size if path.exists() else 0,
                "updated_at": _mtime(path) if path.exists() else "",
                "required_for_resume": name == "resume_brief.md",
            }
        )
    ready_count = sum(1 for item in files if item["state"] == "ready")
    return {
        "schema": CONTEXT_SUMMARY_SCHEMA,
        "version": "1.0",
        "created_at": utc_now(),
        "workspace": str(root),
        "context_dir": str(context_dir(root)),
        "state": "ready" if ready_count else "missing",
        "ready_count": ready_count,
        "missing": [item["name"] for item in files if item["state"] == "missing"],
        "resume_read_order": RESUME_READ_ORDER,
        "files": files,
    }


def _context_filename(name: str) -> str:
    filename = Path(name).name
    if filename not in CONTEXT_FILE_NAMES:
        raise ValueError(f"unknown context checkpoint file: {name}")
    return filename


def _mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
