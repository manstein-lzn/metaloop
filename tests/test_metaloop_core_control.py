from __future__ import annotations

import json

import pytest

from metaloop_core.control import control_request_path, load_control_requests, pending_control_requests, write_control_request


def test_write_control_request_creates_explicit_file_and_event(tmp_path) -> None:
    request = write_control_request(
        tmp_path,
        control_type="resource_approval",
        reason="Approve one bounded GPU training attempt.",
        created_by="human",
        payload={"max_hours": 3, "max_parallel_jobs": 1},
    )

    path = control_request_path(tmp_path, "resource_approval")
    payload = json.loads(path.read_text(encoding="utf-8"))
    events = (tmp_path / ".metaloop" / "event_log.jsonl").read_text(encoding="utf-8")

    assert request["schema"] == "metaloop.control_request"
    assert payload["type"] == "resource_approval"
    assert payload["status"] == "pending"
    assert payload["payload"]["max_hours"] == 3
    assert "Control request resource_approval" in events
    assert pending_control_requests(tmp_path)[0]["type"] == "resource_approval"


def test_load_control_requests_ignores_invalid_json_and_rejects_unknown_type(tmp_path) -> None:
    control_dir = tmp_path / ".metaloop" / "control"
    control_dir.mkdir(parents=True)
    (control_dir / "bad.json").write_text("{", encoding="utf-8")

    assert load_control_requests(tmp_path) == []
    with pytest.raises(ValueError):
        write_control_request(tmp_path, control_type="kill_worker", reason="not allowed")
