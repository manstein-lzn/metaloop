from __future__ import annotations

import pytest

from metaloop_core.context import context_file_path, context_summary, ensure_context_files, read_context_file, write_context_file
from metaloop_core.observe import observe_node
from metaloop_core.workspace import WorkspaceState


def test_ensure_context_files_creates_resume_checkpoint_templates(tmp_path) -> None:
    result = ensure_context_files(tmp_path)
    summary = context_summary(tmp_path)

    assert len(result["created"]) == 4
    assert summary["schema"] == "metaloop.context_summary"
    assert summary["state"] == "ready"
    assert summary["ready_count"] == 4
    assert summary["missing"] == []
    assert context_file_path(tmp_path, "resume_brief.md").exists()
    assert "Current Goal" in read_context_file(tmp_path, "resume_brief.md")
    assert "Initialized context checkpoint files" in (tmp_path / ".metaloop" / "event_log.jsonl").read_text(encoding="utf-8")


def test_write_context_file_updates_one_checkpoint_and_observe_summary(tmp_path) -> None:
    write_context_file(
        tmp_path,
        name="resume_brief.md",
        content="# Resume Brief\n\n## Current Goal\n\n- Reach the locked metric gate.",
        created_by="worker",
    )

    text = read_context_file(tmp_path, "resume_brief.md")
    node = observe_node(tmp_path)
    workspace = WorkspaceState(tmp_path).status()

    assert "Reach the locked metric gate" in text
    assert node["context"]["state"] == "ready"
    assert node["context"]["resume_brief"]["state"] == "ready"
    assert workspace["context"]["ready_count"] == 1
    assert "Updated context checkpoint resume_brief.md" in (tmp_path / ".metaloop" / "event_log.jsonl").read_text(encoding="utf-8")


def test_context_checkpoint_rejects_unknown_file_and_empty_content(tmp_path) -> None:
    with pytest.raises(ValueError):
        context_file_path(tmp_path, "../memory.md")
    with pytest.raises(ValueError):
        write_context_file(tmp_path, name="resume_brief.md", content="")
