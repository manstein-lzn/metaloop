from __future__ import annotations

import json

import pytest

from metaloop_core.cli import main as cli_main
from metaloop_core.durable import DurableStore, InvalidTransitionError
from metaloop_core.engineering_governance import (
    build_v2_governance,
    validate_v2_governance,
)


def _verification_spec() -> dict:
    return {
        "validators": [
            {
                "type": "command",
                "mode": "executable",
                "severity": "blocking",
                "command": "true",
            }
        ],
        "resource_gates": [],
    }


def _governed_contract(tmp_path, *, change_kind: str = "repair") -> dict:
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (docs / "module.md").write_text("# Module\n", encoding="utf-8")
    if change_kind == "redesign":
        (docs / "migration.md").write_text("# Migration\n", encoding="utf-8")
    governance = build_v2_governance(
        tmp_path,
        change_kind=change_kind,
        stable_inputs=[
            ("governing_document", "docs/architecture.md"),
            ("module_contract", "docs/module.md"),
        ],
        managed_outputs=[("implementation", "src/result.txt")],
        allowed_paths=["src"],
        migration_plan="docs/migration.md" if change_kind == "redesign" else None,
    )
    return {
        "goal": "Deliver one governed V2 change.",
        "constraints": ["Keep stable governance inputs unchanged."],
        "non_goals": ["Do not infer semantic decisions."],
        "acceptance_criteria": ["The managed output is evidence-bound."],
        "verification_spec": _verification_spec(),
        "governance": governance,
    }


def _task_with_governance(tmp_path, *, change_kind: str = "repair") -> tuple[DurableStore, dict]:
    store = DurableStore(tmp_path)
    task = store.create_task(title="Governed V2 task")
    store.lock_contract(
        task["task_id"],
        _governed_contract(tmp_path, change_kind=change_kind),
        expected_version=task["state_version"],
    )
    return store, store.get_task(task["task_id"])


def test_v2_governance_builder_and_schema_are_explicit(tmp_path) -> None:
    contract = _governed_contract(tmp_path, change_kind="redesign")
    governance = contract["governance"]

    assert governance["schema"] == "metaloop.v2.engineering_governance"
    assert governance["change_kind"] == "redesign"
    assert governance["migration_plan"]["path"] == "docs/migration.md"
    assert validate_v2_governance(governance) == []

    governance["change_kind"] = "please repair this implementation"
    assert any("change_kind" in error for error in validate_v2_governance(governance))


def test_v2_governance_rejects_managed_output_outside_allowed_paths(tmp_path) -> None:
    contract = _governed_contract(tmp_path)
    contract["governance"]["allowed_paths"] = ["lib"]

    task = DurableStore(tmp_path).create_task(title="Invalid governed scope")
    with pytest.raises(ValueError, match="managed_outputs.*allowed_paths"):
        DurableStore(tmp_path).lock_contract(
            task["task_id"],
            contract,
            expected_version=task["state_version"],
        )


def test_stable_input_drift_blocks_attempt_start(tmp_path) -> None:
    store, task = _task_with_governance(tmp_path)
    (tmp_path / "docs" / "module.md").write_text("# Drifted\n", encoding="utf-8")

    with pytest.raises(InvalidTransitionError, match="governance stable input drifted before attempt start"):
        store.start_attempt(
            task["task_id"],
            plan="Implement the governed output.",
            input_snapshot={},
            expected_version=task["state_version"],
        )


def test_managed_output_requires_exact_attempt_evidence(tmp_path) -> None:
    store, task = _task_with_governance(tmp_path)
    attempt = store.start_attempt(
        task["task_id"],
        plan="Implement the governed output.",
        input_snapshot={},
        expected_version=task["state_version"],
    )
    output = tmp_path / "src" / "result.txt"
    output.parent.mkdir()
    output.write_text("done\n", encoding="utf-8")

    with pytest.raises(InvalidTransitionError, match="managed output is not Attempt evidence"):
        store.seal_attempt(
            attempt["attempt_id"],
            expected_task_version=store.get_task(task["task_id"])["state_version"],
        )

    store.add_evidence(attempt["attempt_id"], path="src/result.txt")
    sealed = store.seal_attempt(
        attempt["attempt_id"],
        expected_task_version=store.get_task(task["task_id"])["state_version"],
    )
    evaluation = store.verify_attempt(sealed["attempt_id"])
    completed = store.accept_task(
        task["task_id"],
        terminal_evaluation_id=evaluation["evaluation_id"],
        expected_version=store.get_task(task["task_id"])["state_version"],
    )

    assert completed["lifecycle_status"] == "completed"


def test_stable_input_is_rechecked_at_seal_verify_accept_and_integrity(tmp_path) -> None:
    store, task = _task_with_governance(tmp_path)
    attempt = store.start_attempt(
        task["task_id"],
        plan="Implement and verify the governed output.",
        input_snapshot={},
        expected_version=task["state_version"],
    )
    output = tmp_path / "src" / "result.txt"
    output.parent.mkdir()
    output.write_text("done\n", encoding="utf-8")
    store.add_evidence(attempt["attempt_id"], path="src/result.txt")
    stable = tmp_path / "docs" / "architecture.md"

    stable.write_text("# Drift before seal\n", encoding="utf-8")
    with pytest.raises(InvalidTransitionError, match="before seal"):
        store.seal_attempt(
            attempt["attempt_id"],
            expected_task_version=store.get_task(task["task_id"])["state_version"],
        )

    stable.write_text("# Architecture\n", encoding="utf-8")
    sealed = store.seal_attempt(
        attempt["attempt_id"],
        expected_task_version=store.get_task(task["task_id"])["state_version"],
    )

    stable.write_text("# Drift before verify\n", encoding="utf-8")
    with pytest.raises(InvalidTransitionError, match="before verification"):
        store.verify_attempt(sealed["attempt_id"])

    stable.write_text("# Architecture\n", encoding="utf-8")
    evaluation = store.verify_attempt(sealed["attempt_id"])
    stable.write_text("# Drift before accept\n", encoding="utf-8")
    with pytest.raises(InvalidTransitionError, match="before review"):
        store.review_evaluation(
            evaluation["evaluation_id"],
            decision="approved",
            reviewer="independent-reviewer",
        )
    with pytest.raises(InvalidTransitionError, match="before acceptance"):
        store.accept_task(
            task["task_id"],
            terminal_evaluation_id=evaluation["evaluation_id"],
            expected_version=store.get_task(task["task_id"])["state_version"],
        )

    stable.write_text("# Architecture\n", encoding="utf-8")
    store.accept_task(
        task["task_id"],
        terminal_evaluation_id=evaluation["evaluation_id"],
        expected_version=store.get_task(task["task_id"])["state_version"],
    )
    store.set_default_task(task["task_id"])
    stable.write_text("# Drift after accept\n", encoding="utf-8")
    integrity = store.integrity_check()

    assert integrity["passed"] is False
    assert any("governance stable input drifted" in error for error in integrity["workspace_evidence"]["errors"])


def test_recovery_contains_compact_governance_summary(tmp_path) -> None:
    store, task = _task_with_governance(tmp_path)

    recovery = store.recovery(task["task_id"])
    governance = recovery["current_source"]["governance"]

    assert governance["change_kind"] == "repair"
    assert governance["stable_input_paths"] == ["docs/architecture.md", "docs/module.md"]
    assert governance["managed_output_paths"] == ["src/result.txt"]
    assert governance["stable_inputs_fresh"] is True


def test_governed_v1_migration_preserves_v2_governance(tmp_path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (docs / "module.md").write_text("# Module\n", encoding="utf-8")
    assert cli_main(
        [
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Migrate governed legacy work.",
            "--rationale",
            "Preserve governance across the cutover.",
            "--non-goal",
            "Do not create a second truth.",
            "--command",
            "true",
            "--change-type",
            "repair",
            "--governing-document",
            "docs/architecture.md",
            "--module-contract",
            "docs/module.md",
            "--allowed-path",
            "src",
        ]
    ) == 0

    store = DurableStore(tmp_path)
    migrated = store.migrate_legacy()
    governance = store.get_task(migrated["task_id"])["contract"]["content"]["governance"]

    assert governance["schema"] == "metaloop.v2.engineering_governance"
    assert governance["change_kind"] == "repair"
    assert [item["path"] for item in governance["stable_inputs"]] == [
        "docs/architecture.md",
        "docs/module.md",
    ]


def test_v1_cli_does_not_infer_semantic_decision_from_keywords(tmp_path) -> None:
    assert cli_main(
        [
            "--workspace",
            str(tmp_path),
            "adaptive",
            "init",
            "--goal",
            "Improve a measurable target.",
            "--current-plan",
            "Run one attempt.",
        ]
    ) == 0
    assert cli_main(
        [
            "--workspace",
            str(tmp_path),
            "adaptive",
            "record",
            "--plan",
            "Run one attempt.",
            "--observation",
            "The output missed the target.",
            "--evaluation-status",
            "partial",
            "--diagnosis",
            "The implementation bug suggests repair.",
            "--next-plan",
            "Repair the implementation and rerun.",
        ]
    ) == 0

    state = json.loads((tmp_path / ".metaloop" / "adaptive_loop.json").read_text(encoding="utf-8"))
    assert state["iterations"][0]["decision"] == "continue"
