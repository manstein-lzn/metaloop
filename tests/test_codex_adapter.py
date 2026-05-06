from metaloop.codex_adapter import CodexExecAdapter, CodexExecOptions, map_codex_event_type, parse_codex_jsonl


def test_parse_codex_jsonl_collects_summary_fields() -> None:
    result = parse_codex_jsonl(
        "\n".join(
            [
                '{"type":"thread.started","thread_id":"thread_1"}',
                '{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"{\\"status\\":\\"success\\",\\"summary\\":\\"ok\\",\\"artifacts\\":[]}"}}',
                '{"type":"turn.completed","usage":{"input_tokens":3,"output_tokens":5}}',
            ]
        )
    )

    assert result.thread_id == "thread_1"
    assert result.final_message is not None
    assert result.usage == {"input_tokens": 3, "output_tokens": 5}


def test_parse_codex_jsonl_preserves_bad_and_unknown_lines() -> None:
    result = parse_codex_jsonl('not-json\n["bad"]\n{"type":"new.event","x":1}')

    assert len(result.parse_errors) == 2
    assert result.events[0]["type"] == "codex_parse_error"
    assert result.events[1]["type"] == "codex_unknown_event"
    assert map_codex_event_type(result.events[2]) == "codex_unknown_event"


def test_map_codex_item_events() -> None:
    event = {"type": "item.completed", "item": {"type": "command_execution"}}

    assert map_codex_event_type(event) == "codex_command_completed"


def test_codex_adapter_streams_events(tmp_path) -> None:
    codex_bin = tmp_path / "codex"
    codex_bin.write_text(
        """#!/usr/bin/env python3
import json
import sys
for _ in sys.stdin:
    pass
print(json.dumps({"type":"thread.started","thread_id":"thread_live"}), flush=True)
print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"{\\"status\\":\\"success\\",\\"summary\\":\\"ok\\",\\"artifacts\\":[]}"}}), flush=True)
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":3}}), flush=True)
""",
        encoding="utf-8",
    )
    codex_bin.chmod(0o755)
    streamed = []

    result = CodexExecAdapter(
        CodexExecOptions(codex_bin=str(codex_bin), use_output_schema=False, working_directory=str(tmp_path))
    ).run("hello", on_event=streamed.append)

    assert result.returncode == 0
    assert result.thread_id == "thread_live"
    assert result.usage == {"input_tokens": 2, "output_tokens": 3}
    assert [event["type"] for event in streamed] == ["thread.started", "item.completed", "turn.completed"]
