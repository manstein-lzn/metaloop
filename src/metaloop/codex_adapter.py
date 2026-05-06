from __future__ import annotations

import json
from queue import Empty, Queue
import shutil
import subprocess
import tempfile
from threading import Thread
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


SandboxMode = Literal["read-only", "workspace-write", "danger-full-access"]
ApprovalPolicy = Literal["never", "on-request", "on-failure", "untrusted"]


class CodexExecOptions(BaseModel):
    codex_bin: str = "codex"
    model: str | None = None
    sandbox: SandboxMode = "workspace-write"
    approval_policy: ApprovalPolicy = "on-request"
    network_access: bool = False
    skip_git_repo_check: bool = False
    timeout_seconds: int = 900
    output_schema: dict[str, Any] | None = None
    use_output_schema: bool = True
    working_directory: str = "."


@dataclass
class CodexExecResult:
    events: list[dict[str, Any]] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    final_message: str | None = None
    usage: dict[str, Any] | None = None
    thread_id: str | None = None
    returncode: int = 0
    stderr: str = ""
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class CodexExecAdapter:
    def __init__(self, options: CodexExecOptions | None = None) -> None:
        self.options = options or CodexExecOptions()

    def run(self, prompt: str, on_event: Callable[[dict[str, Any]], None] | None = None) -> CodexExecResult:
        codex_path = shutil.which(self.options.codex_bin)
        if codex_path is None:
            return CodexExecResult(returncode=127, stderr=f"codex binary not found: {self.options.codex_bin}")

        with self._schema_file() as schema_file:
            command = self._build_command(codex_path, schema_file)
            try:
                result = self._run_streaming(command, prompt, on_event=on_event)
            except subprocess.TimeoutExpired as exc:
                return CodexExecResult(
                    returncode=-1,
                    stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
                    timed_out=True,
                    parse_errors=["codex exec timed out"],
                )
        return result

    def _run_streaming(
        self,
        command: list[str],
        prompt: str,
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> CodexExecResult:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.options.working_directory,
            bufsize=1,
        )
        stdout_queue: Queue[str | None] = Queue()
        stderr_parts: list[str] = []
        write_errors: list[str] = []

        def write_prompt() -> None:
            try:
                assert process.stdin is not None
                process.stdin.write(prompt)
                process.stdin.close()
            except Exception as exc:  # pragma: no cover - defensive thread guard
                write_errors.append(str(exc))

        def read_stdout() -> None:
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    stdout_queue.put(line)
            finally:
                stdout_queue.put(None)

        def read_stderr() -> None:
            assert process.stderr is not None
            for line in process.stderr:
                stderr_parts.append(line)

        writer = Thread(target=write_prompt, daemon=True)
        stdout_reader = Thread(target=read_stdout, daemon=True)
        stderr_reader = Thread(target=read_stderr, daemon=True)
        writer.start()
        stdout_reader.start()
        stderr_reader.start()

        result = CodexExecResult()
        deadline = time.monotonic() + self.options.timeout_seconds
        line_number = 0
        stdout_done = False

        while not stdout_done or process.poll() is None:
            if time.monotonic() > deadline:
                process.kill()
                result.timed_out = True
                result.returncode = -1
                result.parse_errors.append("codex exec timed out")
                break
            try:
                line = stdout_queue.get(timeout=0.1)
            except Empty:
                continue
            if line is None:
                stdout_done = True
                continue
            line_number += 1
            event = _parse_codex_jsonl_line(result, line, line_number)
            if event is not None and on_event is not None:
                on_event(event)

        while not stdout_queue.empty():
            line = stdout_queue.get_nowait()
            if line is None:
                continue
            line_number += 1
            event = _parse_codex_jsonl_line(result, line, line_number)
            if event is not None and on_event is not None:
                on_event(event)

        try:
            result.returncode = process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            result.returncode = -1
            result.timed_out = True
            result.parse_errors.append("codex exec timed out")
        writer.join(timeout=1)
        stdout_reader.join(timeout=1)
        stderr_reader.join(timeout=1)
        result.stderr = "".join(stderr_parts)
        if write_errors:
            result.parse_errors.extend(f"stdin write failed: {item}" for item in write_errors)
        return result

    def _build_command(self, codex_path: str, schema_file: str | None) -> list[str]:
        command = [
            codex_path,
            "exec",
            "--json",
            "--sandbox",
            self.options.sandbox,
            "--config",
            f'approval_policy="{self.options.approval_policy}"',
            "--config",
            f"sandbox_workspace_write.network_access={str(self.options.network_access).lower()}",
            "--cd",
            self.options.working_directory,
        ]
        if self.options.model:
            command.extend(["--model", self.options.model])
        if self.options.skip_git_repo_check:
            command.append("--skip-git-repo-check")
        if schema_file is not None:
            command.extend(["--output-schema", schema_file])
        command.append("-")
        return command

    def _schema_file(self):
        if self.options.output_schema is None or not self.options.use_output_schema:
            return _NullContext()
        return _SchemaFileContext(self.options.output_schema)


def parse_codex_jsonl(stdout: str) -> CodexExecResult:
    result = CodexExecResult()
    for line_number, line in enumerate(stdout.splitlines(), start=1):
        _parse_codex_jsonl_line(result, line, line_number)
    return result


def _parse_codex_jsonl_line(result: CodexExecResult, line: str, line_number: int) -> dict[str, Any] | None:
    if not line.strip():
        return None
    try:
        event = json.loads(line)
    except json.JSONDecodeError as exc:
        result.parse_errors.append(f"line {line_number}: {exc.msg}")
        event = {"type": "codex_parse_error", "raw": line, "line_number": line_number}
        result.events.append(event)
        return event
    if not isinstance(event, dict):
        result.parse_errors.append(f"line {line_number}: event is not an object")
        event = {"type": "codex_unknown_event", "raw": event, "line_number": line_number}
        result.events.append(event)
        return event
    result.events.append(event)
    _update_result_summary(result, event)
    return event


def map_codex_event_type(event: dict[str, Any]) -> str:
    event_type = event.get("type")
    if event_type == "thread.started":
        return "codex_thread_started"
    if event_type == "turn.started":
        return "codex_turn_started"
    if event_type == "turn.completed":
        return "codex_turn_completed"
    if event_type == "turn.failed":
        return "codex_turn_failed"
    if event_type == "error":
        return "codex_error"
    if event_type in {"item.started", "item.updated", "item.completed"}:
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        item_type = item.get("type")
        suffix = event_type.split(".")[1]
        if item_type == "command_execution":
            return f"codex_command_{suffix}"
        if item_type == "file_change":
            return f"codex_file_change_{suffix}"
        if item_type == "mcp_tool_call":
            return f"codex_mcp_tool_{suffix}"
        if item_type == "agent_message":
            return f"codex_agent_message_{suffix}"
        if item_type == "todo_list":
            return f"codex_todo_list_{suffix}"
        if item_type == "reasoning":
            return f"codex_reasoning_{suffix}"
        if item_type == "error":
            return f"codex_item_error_{suffix}"
        return f"codex_unknown_item_{suffix}"
    if event_type == "codex_parse_error":
        return "codex_parse_error"
    return "codex_unknown_event"


def _update_result_summary(result: CodexExecResult, event: dict[str, Any]) -> None:
    event_type = event.get("type")
    if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
        result.thread_id = event["thread_id"]
    elif event_type == "turn.completed" and isinstance(event.get("usage"), dict):
        result.usage = event["usage"]
    elif event_type == "item.completed":
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            result.final_message = item["text"]


class _NullContext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> None:
        return None


class _SchemaFileContext:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema
        self.path: Path | None = None
        self.directory: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> str:
        self.directory = tempfile.TemporaryDirectory(prefix="metaloop-codex-schema-")
        self.path = Path(self.directory.name) / "schema.json"
        self.path.write_text(json.dumps(self.schema), encoding="utf-8")
        return str(self.path)

    def __exit__(self, *_args: object) -> None:
        if self.directory is not None:
            self.directory.cleanup()
