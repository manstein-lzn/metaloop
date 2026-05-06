import sys

from metaloop.codex_adapter import CodexExecOptions, CodexExecResult
from metaloop.user_agent import CodexExecUserAgent, CodexSdkOptions, CodexSdkUserAgent, UserAction, UserAgent


def _status(
    *,
    mission_state: str = "missing",
    run_state: str = "missing",
    verification_status: str | None = None,
    redesign_state: str = "missing",
    capsule_lifecycle: str | None = None,
    next_action: str = "Run `metaloop design`",
) -> dict:
    return {
        "mission": {"state": mission_state},
        "run": {"state": run_state},
        "verification": {"status": verification_status, "reason": ""},
        "redesign": {"state": redesign_state},
        "capsule": {"lifecycle_state": capsule_lifecycle},
        "next_action": next_action,
    }


def test_user_agent_maps_empty_turn_to_design_for_new_workspace() -> None:
    action = UserAgent().propose("", _status())

    assert action.action == UserAction.START_DESIGN
    assert action.command == ["design"]


def test_user_agent_maps_continue_to_run_when_mission_exists() -> None:
    action = UserAgent().propose(
        "继续",
        _status(
            mission_state="ready",
            run_state="missing",
            next_action="Run `metaloop run`",
        ),
    )

    assert action.action == UserAction.RUN_CURRENT_MISSION
    assert action.command == ["run"]


def test_user_agent_does_not_resume_worker_when_redesign_required() -> None:
    action = UserAgent().propose(
        "继续",
        _status(
            mission_state="ready",
            run_state="failed",
            verification_status="failed",
            redesign_state="ready",
            capsule_lifecycle="redesign_required",
            next_action="Review redesign proposal; rerun `metaloop design --resume` or create a revised mission",
        ),
    )

    assert action.action == UserAction.PROPOSE_REVISION
    assert action.command == []
    assert "不能把继续解释为普通 worker rerun" in action.reason


def test_user_agent_collects_feedback_without_contract_mutation() -> None:
    action = UserAgent().propose(
        "结果不满意，验收标准需要改",
        _status(
            mission_state="ready",
            run_state="completed_verified",
            verification_status="completed_verified",
            next_action="Already complete; run `metaloop verify` for details",
        ),
    )

    assert action.action == UserAction.COLLECT_FEEDBACK
    assert action.requires_confirmation is False
    assert "暂不直接修改 locked contract" in action.boundary_note


def test_codex_user_agent_parses_structured_action() -> None:
    class FakeAdapter:
        def __init__(self, _options):
            pass

        def run(self, prompt):
            assert "README" in prompt
            return CodexExecResult(
                final_message=(
                    '{"action":"show_status","reason":"先解释当前项目状态",'
                    '"command":["status"],"requires_confirmation":false,'
                    '"assistant_message":"我会先理解这个现有项目。"}'
                )
            )

    agent = CodexExecUserAgent(CodexExecOptions(), adapter_factory=FakeAdapter)

    action = agent.start(_status())

    assert action.action == UserAction.SHOW_STATUS
    assert action.command == ["status"]
    assert action.assistant_message == "我会先理解这个现有项目。"


def test_codex_user_agent_fails_fast_when_codex_unavailable() -> None:
    class FailingAdapter:
        def __init__(self, _options):
            pass

        def run(self, _prompt):
            return CodexExecResult(returncode=127, stderr="codex binary not found")

    agent = CodexExecUserAgent(CodexExecOptions(), adapter_factory=FailingAdapter)

    try:
        agent.propose("状态", _status())
    except RuntimeError as exc:
        assert "Codex UserAgent unavailable" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_codex_sdk_user_agent_uses_persistent_bridge_thread(tmp_path) -> None:
    bridge = tmp_path / "fake_bridge.py"
    bridge.write_text(
        """
import json
import sys

thread_id = "thread_fake"
turn = 0
for line in sys.stdin:
    request = json.loads(line)
    turn += 1
    action = "show_status" if turn == 1 else "run_current_mission"
    command = ["status"] if turn == 1 else ["run"]
    final = {
        "action": action,
        "reason": f"turn {turn}",
        "command": command,
        "requires_confirmation": False,
        "assistant_message": f"thread={thread_id}; turn={turn}",
    }
    print(json.dumps({
        "id": request["id"],
        "ok": True,
        "threadId": thread_id,
        "finalResponse": json.dumps(final),
    }), flush=True)
""",
        encoding="utf-8",
    )

    agent = CodexSdkUserAgent(
        CodexSdkOptions(
            node_bin=sys.executable,
            bridge_path=str(bridge),
            working_directory=str(tmp_path),
            timeout_seconds=5,
        )
    )
    try:
        first = agent.start(_status())
        second = agent.propose("运行", _status(mission_state="ready", run_state="missing"))
    finally:
        agent.close()

    assert first.action == UserAction.SHOW_STATUS
    assert first.assistant_message == "thread=thread_fake; turn=1"
    assert second.action == UserAction.RUN_CURRENT_MISSION
    assert second.assistant_message == "thread=thread_fake; turn=2"
    assert agent.thread_id == "thread_fake"


def test_codex_sdk_user_agent_persists_and_loads_thread_id(tmp_path) -> None:
    bridge = tmp_path / "fake_bridge.py"
    store = tmp_path / ".metaloop" / "user_agent_thread.json"
    store.parent.mkdir()
    store.write_text(
        '{"schema":"metaloop.user_agent_thread","version":"1.0","thread_id":"thread_existing","backend":"codex_sdk"}',
        encoding="utf-8",
    )
    bridge.write_text(
        """
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    final = {
        "action": "show_status",
        "reason": request.get("threadId", ""),
        "command": ["status"],
        "requires_confirmation": False,
    }
    print(json.dumps({
        "id": request["id"],
        "ok": True,
        "threadId": "thread_updated",
        "finalResponse": json.dumps(final),
    }), flush=True)
""",
        encoding="utf-8",
    )

    agent = CodexSdkUserAgent(
        CodexSdkOptions(
            node_bin=sys.executable,
            bridge_path=str(bridge),
            working_directory=str(tmp_path),
            timeout_seconds=5,
            thread_store_path=str(store),
        )
    )
    try:
        action = agent.start(_status())
    finally:
        agent.close()

    assert action.reason == "thread_existing"
    assert agent.thread_id == "thread_updated"
    assert '"thread_id": "thread_updated"' in store.read_text(encoding="utf-8")


def test_codex_sdk_user_agent_fails_fast_when_bridge_unavailable(tmp_path) -> None:
    bridge = tmp_path / "missing_bridge.mjs"
    agent = CodexSdkUserAgent(
        CodexSdkOptions(
            node_bin=sys.executable,
            bridge_path=str(bridge),
            working_directory=str(tmp_path),
            timeout_seconds=1,
        )
    )

    try:
        agent.start(_status())
    except RuntimeError as exc:
        assert "bridge not found" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
