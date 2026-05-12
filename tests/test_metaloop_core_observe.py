from __future__ import annotations

import json
from pathlib import Path

from metaloop_core.observe import observe_node, observe_root


def test_observe_node_summarizes_metaloop_artifacts_without_writing(tmp_path) -> None:
    metaloop_dir = tmp_path / ".metaloop"
    metaloop_dir.mkdir()
    (metaloop_dir / "mission_capsule.json").write_text(
        json.dumps({"capsule_id": "capsule-1", "current_status": "executed", "intent": "Train a cost model."}),
        encoding="utf-8",
    )
    (metaloop_dir / "verification_result.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "reason": "MAPE gate failed.",
                "hard_validator_results": [{"severity": "blocking", "passed": False}],
                "manual_validator_results": [],
                "unsupported_validator_results": [],
                "best_metric": {"mape": 0.238, "dataset": "tenset"},
            }
        ),
        encoding="utf-8",
    )
    (metaloop_dir / "adaptive_loop.json").write_text(
        json.dumps(
            {
                "goal": "Push MAPE below 20%.",
                "current_plan": "Try a lower-loss tensor mapping.",
                "iterations": [{"decision": "repair"}],
            }
        ),
        encoding="utf-8",
    )
    (metaloop_dir / "outbox").mkdir()
    (metaloop_dir / "outbox" / "reviewer.json").write_text("{}", encoding="utf-8")
    (metaloop_dir / "event_log.jsonl").write_text(
        json.dumps({"created_at": "2026-05-12T00:00:00Z", "type": "observation", "agent": "worker", "summary": "MAPE improved but missed gate."}) + "\n",
        encoding="utf-8",
    )

    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    summary = observe_node(tmp_path)
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    assert before == after
    assert summary["schema"] == "metaloop.node_summary"
    assert summary["node_id"] == "capsule-1"
    assert summary["status"] == "failed"
    assert summary["goal"] == "Train a cost model."
    assert summary["current_plan"] == "Try a lower-loss tensor mapping."
    assert summary["best_metric"]["mape"] == 0.238
    assert summary["last_event"]["summary"] == "MAPE improved but missed gate."
    assert summary["last_verification"]["hard_failures"] == 1
    assert summary["adaptive_decision"] == "repair"
    assert summary["outbox_count"] == 1
    assert summary["waiting_on"] == ""
    assert summary["updated_at"]


def test_observe_root_summarizes_multiple_nodes(tmp_path) -> None:
    node_a = tmp_path / "architect"
    node_b = tmp_path / "ml_engineer"
    for node, status in [(node_a, "completed_verified"), (node_b, "review_required")]:
        metaloop_dir = node / ".metaloop"
        metaloop_dir.mkdir(parents=True)
        (metaloop_dir / "verification_result.json").write_text(json.dumps({"status": status}), encoding="utf-8")

    summary = observe_root(tmp_path)

    assert summary["schema"] == "metaloop.global_summary"
    assert summary["node_count"] == 2
    assert summary["status_counts"]["completed_verified"] == 1
    assert summary["status_counts"]["review_required"] == 1
    assert len(summary["blocked_nodes"]) == 1
    assert summary["blocked_nodes"][0]["waiting_on"] == "review"
