from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from metaloop.codex_adapter import CodexExecAdapter, CodexExecOptions, map_codex_event_type
from metaloop.policy import PolicyEngine
from metaloop.schemas import Artifact, BudgetUsage, MissionSpec, PlanStep, StepResult, StepStatus, SystemEvent, TaskPlan
from metaloop.tools import ToolRegistry


EventEmitter = Callable[[str, str | None, str | None, dict | None], SystemEvent]


@dataclass(frozen=True)
class WorkerContext:
    run_id: str
    budget_usage: BudgetUsage
    policy_engine: PolicyEngine
    tool_registry: ToolRegistry
    emit_event: EventEmitter
    deadline_seconds: int | None = None


class WorkerBackend(Protocol):
    def run_step(
        self,
        context: WorkerContext,
        mission: MissionSpec,
        plan: TaskPlan,
        step: PlanStep,
        *,
        retry_count: int = 0,
    ) -> StepResult:
        ...


class DummyWorkerBackend:
    """Deterministic worker used for kernel tests and local smoke runs."""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def run_step(
        self,
        context: WorkerContext,
        mission: MissionSpec,
        plan: TaskPlan,
        step: PlanStep,
        *,
        retry_count: int = 0,
    ) -> StepResult:
        intent = mission.intent.lower()
        is_first_step = plan.steps[0].step_id == step.step_id
        should_fail_once = "retry" in intent and retry_count == 0 and is_first_step
        should_fail_always = "fail" in intent
        should_propose = "boundary" in step.title.lower() or any(
            "boundary" in artifact.lower() for artifact in step.expected_artifacts
        )

        if should_fail_always or should_fail_once:
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error_log="dummy worker failure requested by mission intent",
                tokens_used=100,
                tool_calls_used=1,
            )

        if should_propose:
            artifact = context.tool_registry.call(
                mission,
                "artifact.echo",
                {"content": "This mission should be continued as a separate MetaLoop run."},
            )
            artifact.metadata["proposal"] = True
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.SUCCESS,
                artifacts=[artifact],
                tokens_used=80,
                tool_calls_used=1,
            )

        artifact = context.tool_registry.call(
            mission,
            "artifact.echo",
            {"content": f"Dummy artifact for {step.title}"},
        )
        artifact.metadata["step_id"] = step.step_id
        return StepResult(
            step_id=step.step_id,
            status=StepStatus.SUCCESS,
            artifacts=[artifact],
            tokens_used=80,
            tool_calls_used=1,
        )


def text_artifact(content: str, **metadata: object) -> Artifact:
    return Artifact(kind="text", content=content, metadata=metadata)


CODEX_WORKER_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["success", "failed", "blocked_by_policy", "blocked_by_auth"],
        },
        "summary": {"type": "string"},
        "artifacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["file", "json", "text", "command_output", "url"]},
                    "uri": {"type": ["string", "null"]},
                    "content": {"type": ["string", "null"]},
                },
                "required": ["kind", "uri", "content"],
                "additionalProperties": False,
            },
        },
        "error_log": {"type": ["string", "null"]},
    },
    "required": ["status", "summary", "artifacts", "error_log"],
    "additionalProperties": False,
}


class CodexExecWorkerBackend:
    def __init__(self, options: CodexExecOptions | None = None, *, fallback_without_output_schema: bool = True) -> None:
        self.options = options or CodexExecOptions(output_schema=CODEX_WORKER_OUTPUT_SCHEMA)
        if self.options.output_schema is None:
            self.options.output_schema = CODEX_WORKER_OUTPUT_SCHEMA
        self.fallback_without_output_schema = fallback_without_output_schema

    def run_step(
        self,
        context: WorkerContext,
        mission: MissionSpec,
        plan: TaskPlan,
        step: PlanStep,
        *,
        retry_count: int = 0,
    ) -> StepResult:
        prompt = build_codex_worker_prompt(mission, plan, step, retry_count=retry_count)
        result, emitted_live = self._run_codex(prompt, context, step.step_id)
        if self._should_fallback(result):
            context.emit_event(
                "codex_output_schema_fallback",
                "codex",
                step.step_id,
                {"reason": _fallback_reason(result)},
            )
            fallback_options = self.options.model_copy(update={"use_output_schema": False})
            result, emitted_live = self._run_codex(
                prompt + "\n\nOutput only the JSON object. Do not use Markdown.",
                context,
                step.step_id,
                options=fallback_options,
            )

        if not emitted_live:
            for event in result.events:
                context.emit_event(map_codex_event_type(event), "codex", step.step_id, {"raw": event})

        if result.timed_out:
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error_log="worker_error: codex exec timed out",
            )
        if result.returncode == 127:
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error_log=f"worker_error: {result.stderr}",
            )
        if result.returncode != 0:
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error_log="worker_error: " + (result.stderr or f"codex exec exited with code {result.returncode}"),
            )
        if not result.final_message:
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error_log="worker_error: codex exec produced no final agent message",
            )

        try:
            payload = json.loads(result.final_message)
        except json.JSONDecodeError as exc:
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error_log=f"worker_error: codex final message was not JSON: {exc.msg}",
            )

        try:
            artifacts = [Artifact.model_validate(_normalize_artifact(item)) for item in payload.get("artifacts", [])]
        except (TypeError, ValidationError) as exc:
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error_log=f"worker_error: codex artifacts failed schema validation: {exc}",
            )

        usage = result.usage or {}
        return StepResult(
            step_id=step.step_id,
            status=_normalize_step_status(payload.get("status")),
            artifacts=artifacts,
            error_log=_normalize_optional_string(payload.get("error_log")),
            tokens_used=int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0)),
            tool_calls_used=sum(1 for event in result.events if str(map_codex_event_type(event)).endswith("_completed")),
        )

    def _run_codex(
        self,
        prompt: str,
        context: WorkerContext,
        step_id: str,
        *,
        options: CodexExecOptions | None = None,
    ):
        emitted_live = False

        def emit_live(event):
            nonlocal emitted_live
            emitted_live = True
            context.emit_event(map_codex_event_type(event), "codex", step_id, {"raw": event})

        adapter = CodexExecAdapter(options or self.options)
        try:
            result = adapter.run(prompt, on_event=emit_live)
        except TypeError:
            result = adapter.run(prompt)
        return result, emitted_live

    def _should_fallback(self, result) -> bool:
        if not self.fallback_without_output_schema or not self.options.use_output_schema:
            return False
        if result.ok and result.final_message:
            return False
        if result.returncode == 127 or result.timed_out:
            return False
        error_text = (result.stderr or "") + "\n" + _result_error_summary(result)
        return result.returncode != 0 or "用户额度不足" in error_text or "responses" in error_text or "turn.failed" in error_text


def build_codex_worker_prompt(
    mission: MissionSpec,
    plan: TaskPlan,
    step: PlanStep,
    *,
    retry_count: int = 0,
) -> str:
    return "\n\n".join(
        [
            "You are executing one MetaLoop Worker step.",
            "Do not change the mission goals. Work only on the current step.",
            "Codex sandbox permissions are separate from the PlanStep allowed_tools list.",
            "If the sandbox allows reading or writing files, you may use your normal code/file tools inside workspace_root even when PlanStep allowed_tools only names MetaLoop registry tools.",
            "Return only a final response that matches the provided output schema.",
            'If no output schema is enforced, output raw JSON with keys: "status", "summary", "artifacts", "error_log".',
            f"Retry count for this step: {retry_count}",
            "MissionSpec:",
            mission.model_dump_json(indent=2),
            "TaskPlan:",
            plan.model_dump_json(indent=2),
            "Current Step:",
            step.model_dump_json(indent=2),
            "Rules:",
            "- Only work inside workspace_root.",
            "- Prefer minimal, focused changes.",
            "- Mention produced files as artifacts.",
            "- Use blocked_by_auth only when Codex actually needs approval or sandbox permission that is unavailable.",
            "- If blocked by missing context or an impossible requirement, return failed with a concise error_log.",
        ]
    )


def _result_error_summary(result) -> str:
    messages = []
    for event in result.events:
        if isinstance(event, dict):
            if isinstance(event.get("message"), str):
                messages.append(event["message"])
            error = event.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                messages.append(error["message"])
    return "\n".join(messages[-5:])


def _fallback_reason(result, *, max_length: int = 800) -> str:
    parts = []
    summary = _result_error_summary(result)
    if summary:
        parts.append(summary)
    if result.stderr:
        parts.append(_strip_html_noise(result.stderr))
    if result.returncode != 0:
        parts.append(f"codex exec exited with code {result.returncode}")
    reason = "\n".join(part for part in parts if part).strip()
    if not reason:
        reason = "codex output-schema run did not produce a final message"
    if len(reason) > max_length:
        reason = reason[: max_length - 14].rstrip() + "... [truncated]"
    return reason


def _strip_html_noise(text: str) -> str:
    lines = []
    in_html = False
    for line in text.splitlines():
        stripped = line.strip()
        if "<html" in stripped:
            in_html = True
            lines.append(stripped.split("<html", 1)[0].rstrip() + "<html>...[redacted]")
            continue
        if in_html:
            if "</html>" in stripped:
                in_html = False
            continue
        lines.append(line)
    return "\n".join(line for line in lines if line.strip())


def _normalize_artifact(item):
    if not isinstance(item, dict):
        return {"kind": "text", "content": str(item)}
    if "kind" in item:
        return item
    content_parts = []
    for key in ("name", "title", "description", "summary", "content", "uri"):
        if item.get(key):
            content_parts.append(f"{key}: {item[key]}")
    return {
        "kind": "text",
        "content": "\n".join(content_parts) if content_parts else json.dumps(item, ensure_ascii=False),
        "metadata": {"raw": item},
    }


def _normalize_optional_string(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


def _normalize_step_status(value) -> StepStatus:
    status = str(value or "").lower()
    aliases = {
        "ok": StepStatus.SUCCESS,
        "done": StepStatus.SUCCESS,
        "complete": StepStatus.SUCCESS,
        "completed": StepStatus.SUCCESS,
        "success": StepStatus.SUCCESS,
        "failed": StepStatus.FAILED,
        "failure": StepStatus.FAILED,
        "error": StepStatus.FAILED,
        "blocked": StepStatus.FAILED,
        "blocked_by_policy": StepStatus.BLOCKED_BY_POLICY,
        "blocked_by_auth": StepStatus.BLOCKED_BY_AUTH,
    }
    if status not in aliases:
        raise ValueError(f"{value!r} is not a valid StepStatus")
    return aliases[status]
