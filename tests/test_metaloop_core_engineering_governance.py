from __future__ import annotations

import json

import pytest

from metaloop_core.engineering_governance import build_locked_file, validate_engineering_governance, verify_engineering_governance


def _governance(tmp_path, *, change_type: str = "extension") -> dict:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (tmp_path / "docs" / "module.md").write_text("# Module\n", encoding="utf-8")
    payload = {
        "schema": "metaloop.engineering_governance",
        "version": "1.0",
        "change_type": change_type,
        "governing_document": build_locked_file(tmp_path, "docs/spec.md"),
        "module_contracts": [build_locked_file(tmp_path, "docs/module.md")],
        "allowed_paths": ["src/metaloop_core"],
        "migration_plan": None,
    }
    return payload


def test_governance_locks_workspace_documents_and_detects_drift(tmp_path) -> None:
    payload = _governance(tmp_path)

    assert validate_engineering_governance(payload) == []
    assert verify_engineering_governance(tmp_path, payload) == []

    (tmp_path / "docs" / "module.md").write_text("# Changed\n", encoding="utf-8")
    assert verify_engineering_governance(tmp_path, payload) == ["governance ref hash drifted: docs/module.md"]


def test_redesign_requires_a_locked_migration_plan(tmp_path) -> None:
    payload = _governance(tmp_path, change_type="redesign")

    assert "engineering_governance.migration_plan must be an object" in validate_engineering_governance(payload)

    (tmp_path / "docs" / "migration.md").write_text("# Migration\n", encoding="utf-8")
    payload["migration_plan"] = build_locked_file(tmp_path, "docs/migration.md")
    assert validate_engineering_governance(payload) == []


def test_repair_and_extension_reject_a_migration_plan(tmp_path) -> None:
    payload = _governance(tmp_path)
    payload["migration_plan"] = payload["governing_document"]

    assert "engineering_governance.migration_plan is only valid for redesign" in validate_engineering_governance(payload)


def test_governance_rejects_path_escape(tmp_path) -> None:
    with pytest.raises(ValueError, match="workspace-relative"):
        build_locked_file(tmp_path, "../outside.md")


def test_change_type_is_explicit_not_inferred_from_prose(tmp_path) -> None:
    payload = _governance(tmp_path)
    payload["change_type"] = "please repair the implementation"

    errors = validate_engineering_governance(json.loads(json.dumps(payload)))
    assert any("change_type" in error for error in errors)
