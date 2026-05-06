from __future__ import annotations

import json
import shutil
import subprocess
import time
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from metaloop.codex_adapter import CodexExecAdapter, CodexExecOptions


class UserAction(StrEnum):
    START_DESIGN = "start_design"
    RESUME_DESIGN = "resume_design"
    RUN_CURRENT_MISSION = "run_current_mission"
    VERIFY_CURRENT_RUN = "verify_current_run"
    SHOW_STATUS = "show_status"
    RESUME_RUN = "resume_run"
    COLLECT_FEEDBACK = "collect_feedback"
    PROPOSE_REVISION = "propose_revision"
    APPLY_REDESIGN = "apply_redesign"
    QUIT = "quit"
    UNKNOWN = "unknown"


class ProposedAction(BaseModel):
    action: UserAction
    reason: str
    command: list[str] = Field(default_factory=list)
    requires_confirmation: bool = True
    boundary_note: str = ""
    user_feedback: str = ""
    assistant_message: str = ""


class CodexSdkOptions(BaseModel):
    node_bin: str = "node"
    bridge_path: str | None = None
    model: str | None = None
    working_directory: str = "."
    timeout_seconds: int = 900
    sandbox_mode: str = "read-only"
    approval_policy: str = "never"
    network_access: bool = False
    skip_git_repo_check: bool = True
    thread_id: str | None = None
    thread_store_path: str | None = None


class UserAgent:
    """Local structured interface agent for the first shell iteration.

    This intentionally does not pretend to be an LLM. It maps common user
    phrases and current .metaloop status into explicit MetaLoop actions.
    """

    def propose(self, user_text: str, status: dict[str, Any]) -> ProposedAction:
        text = user_text.strip()
        normalized = text.casefold()
        if not normalized:
            return self._next_action_from_status(status)
        if normalized in {"q", "quit", "exit", "退出", "关闭"}:
            return ProposedAction(
                action=UserAction.QUIT,
                reason="用户要求退出当前 MetaLoop shell。",
                requires_confirmation=False,
            )
        if self._mentions(normalized, "help", "帮助", "?"):
            return ProposedAction(
                action=UserAction.SHOW_STATUS,
                reason="先展示当前工作区状态和下一步建议。",
                command=["status"],
                requires_confirmation=False,
            )
        if self._mentions(normalized, "status", "where", "state", "状态", "卡在哪", "进度", "看看"):
            return ProposedAction(
                action=UserAction.SHOW_STATUS,
                reason="用户想了解当前结构化状态。",
                command=["status"],
                requires_confirmation=False,
            )
        if self._mentions(normalized, "resume design", "继续设计", "恢复设计"):
            return ProposedAction(
                action=UserAction.RESUME_DESIGN,
                reason="用户明确要求恢复 Co-Design 草稿。",
                command=["design", "--resume"],
            )
        if self._is_feedback(normalized):
            return self._feedback_action(text, status)
        if self._mentions(normalized, "design", "start", "new mission", "开始设计", "设计任务", "新任务"):
            return ProposedAction(
                action=UserAction.START_DESIGN,
                reason="用户要求进入任务设计流程。",
                command=["design"],
            )
        if self._mentions(normalized, "verify", "验收", "验证", "检查结果"):
            return ProposedAction(
                action=UserAction.VERIFY_CURRENT_RUN,
                reason="用户要求用 MetaLoop acceptance checks 验收当前运行。",
                command=["verify"],
            )
        if self._mentions(normalized, "run", "execute", "执行", "开始跑", "运行任务"):
            return ProposedAction(
                action=UserAction.RUN_CURRENT_MISSION,
                reason="用户要求执行当前 MissionSpec。",
                command=["run"],
            )
        if self._mentions(normalized, "resume", "continue", "继续", "恢复"):
            return self._continue_from_status(status)
        return ProposedAction(
            action=UserAction.UNKNOWN,
            reason="暂时无法把这句话可靠映射为结构化 MetaLoop action。",
            requires_confirmation=False,
            boundary_note="可以输入 design、run、verify、status、resume、revise 或 quit。",
        )

    def _next_action_from_status(self, status: dict[str, Any]) -> ProposedAction:
        next_action = str(status.get("next_action") or "")
        if "metaloop design" in next_action:
            return ProposedAction(
                action=UserAction.START_DESIGN,
                reason="当前工作区还没有可运行的 MissionSpec。",
                command=["design"],
            )
        if "metaloop run" in next_action:
            return ProposedAction(
                action=UserAction.RUN_CURRENT_MISSION,
                reason="当前已有 MissionSpec，但还没有结构化 run。",
                command=["run"],
            )
        if "metaloop resume" in next_action:
            return ProposedAction(
                action=UserAction.RESUME_RUN,
                reason="当前 run 需要从结构化状态恢复或重跑。",
                command=["resume"],
            )
        if "redesign" in next_action.casefold():
            return ProposedAction(
                action=UserAction.PROPOSE_REVISION,
                reason="当前 Capsule 已进入 redesign_required，需要用户确认修订方向。",
                boundary_note="第一版 shell 只收集/解释反馈；不会直接改 locked MissionSpec、Capsule 或 GoalContract。",
            )
        return ProposedAction(
            action=UserAction.SHOW_STATUS,
            reason="没有可自动执行的下一步，先展示当前状态。",
            command=["status"],
            requires_confirmation=False,
        )

    def _continue_from_status(self, status: dict[str, Any]) -> ProposedAction:
        if status.get("mission", {}).get("state") == "missing":
            return ProposedAction(
                action=UserAction.START_DESIGN,
                reason="用户要求继续，但当前还没有 MissionSpec，因此下一步是设计任务。",
                command=["design"],
            )
        if status.get("run", {}).get("state") == "missing":
            return ProposedAction(
                action=UserAction.RUN_CURRENT_MISSION,
                reason="用户要求继续，当前已有 MissionSpec 但还没有运行记录。",
                command=["run"],
            )
        if self._needs_redesign(status):
            return ProposedAction(
                action=UserAction.PROPOSE_REVISION,
                reason="当前状态要求 redesign，不能把继续解释为普通 worker rerun。",
                boundary_note="需要进入 revise/redesign 闭环，显式确认 scope、acceptance 或 authority 的变化。",
            )
        verification_status = status.get("verification", {}).get("status")
        if verification_status in {"failed", "blocked"} or status.get("run", {}).get("state") in {"running", "failed", "blocked"}:
            return ProposedAction(
                action=UserAction.RESUME_RUN,
                reason="当前运行未成功闭环，下一步是结构化 resume。",
                command=["resume"],
            )
        return ProposedAction(
            action=UserAction.SHOW_STATUS,
            reason="当前没有需要继续执行的非终态运行。",
            command=["status"],
            requires_confirmation=False,
        )

    def _feedback_action(self, user_text: str, status: dict[str, Any]) -> ProposedAction:
        if self._needs_redesign(status):
            action = UserAction.APPLY_REDESIGN
            reason = "用户反馈与现有 redesign proposal 相关；下一步应进入显式 proposal review/apply 流程。"
        else:
            action = UserAction.COLLECT_FEEDBACK
            reason = "用户表达不满意或要求修改；应收集结构化反馈，而不是让 worker 静默改变 locked contract。"
        return ProposedAction(
            action=action,
            reason=reason,
            requires_confirmation=False,
            boundary_note="Redesign/revision 应生成 revised MissionSpec 或 Capsule revision；第一版 shell 暂不直接修改 locked contract。",
            user_feedback=user_text,
        )

    def _needs_redesign(self, status: dict[str, Any]) -> bool:
        verification_reason = str(status.get("verification", {}).get("reason") or "")
        return (
            status.get("redesign", {}).get("state") == "ready"
            or status.get("capsule", {}).get("lifecycle_state") == "redesign_required"
            or "redesign_required" in verification_reason
        )

    def _is_feedback(self, normalized: str) -> bool:
        return self._mentions(
            normalized,
            "不满意",
            "不对",
            "不行",
            "修改",
            "修订",
            "重设计",
            "redesign",
            "revise",
            "feedback",
            "优化",
        )

    def _mentions(self, text: str, *needles: str) -> bool:
        return any(needle.casefold() in text for needle in needles)


class CodexExecUserAgent:
    """Legacy codex exec-backed user-facing agent.

    Codex may inspect the workspace and talk to the user, but it must return a
    structured ProposedAction. The shell is the only layer that executes
    MetaLoop commands.
    """

    def __init__(
        self,
        options: CodexExecOptions,
        *,
        adapter_factory=CodexExecAdapter,
    ) -> None:
        self.options = options
        self.adapter_factory = adapter_factory

    def start(self, status: dict[str, Any]) -> ProposedAction:
        return self._ask_codex(
            user_text="",
            status=status,
            startup=True,
        )

    def propose(self, user_text: str, status: dict[str, Any]) -> ProposedAction:
        text = user_text.strip()
        if text.casefold() in {"q", "quit", "exit", "退出", "关闭"}:
            return ProposedAction(
                action=UserAction.QUIT,
                reason="用户要求退出当前 MetaLoop shell。",
                requires_confirmation=False,
            )
        return self._ask_codex(user_text=text, status=status, startup=False)

    def _ask_codex(self, *, user_text: str, status: dict[str, Any], startup: bool) -> ProposedAction:
        prompt = _build_codex_user_agent_prompt(user_text=user_text, status=status, startup=startup)
        result = self.adapter_factory(self.options).run(prompt)
        if not result.ok:
            details = result.stderr.strip() or "; ".join(result.parse_errors) or "Codex user agent failed."
            raise RuntimeError(f"Codex UserAgent unavailable: {details}")
        if not result.final_message:
            raise RuntimeError("Codex UserAgent unavailable: no final message.")
        payload = _parse_codex_action_payload(result.final_message)
        try:
            return ProposedAction.model_validate(payload)
        except Exception as exc:
            raise RuntimeError(f"Codex UserAgent returned invalid ProposedAction: {exc}") from exc


class CodexSdkUserAgent:
    """SDK-backed user-facing agent with a persistent Codex thread."""

    def __init__(self, options: CodexSdkOptions) -> None:
        self.options = options
        self.thread_id = options.thread_id or self._load_thread_id()
        self._process: subprocess.Popen[str] | None = None
        self._request_id = 0

    def start(self, status: dict[str, Any]) -> ProposedAction:
        return self._ask_codex(user_text="", status=status, startup=True)

    def propose(self, user_text: str, status: dict[str, Any]) -> ProposedAction:
        text = user_text.strip()
        if text.casefold() in {"q", "quit", "exit", "退出", "关闭"}:
            return ProposedAction(
                action=UserAction.QUIT,
                reason="用户要求退出当前 MetaLoop shell。",
                requires_confirmation=False,
            )
        return self._ask_codex(user_text=text, status=status, startup=False)

    def close(self) -> None:
        if self._process is None:
            return
        process = self._process
        self._process = None
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.terminate()
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
        except OSError:
            pass

    def _ask_codex(self, *, user_text: str, status: dict[str, Any], startup: bool) -> ProposedAction:
        prompt = _build_codex_user_agent_prompt(user_text=user_text, status=status, startup=startup)
        response = self._bridge_request(
            {
                "type": "run",
                "prompt": prompt,
                "outputSchema": ProposedAction.model_json_schema(),
            }
        )
        final_response = str(response.get("finalResponse") or "")
        if not final_response:
            raise RuntimeError("Codex SDK UserAgent unavailable: no final response.")
        self._update_thread_id(str(response.get("threadId") or self.thread_id))
        payload = _parse_codex_action_payload(final_response)
        try:
            return ProposedAction.model_validate(payload)
        except Exception as exc:
            raise RuntimeError(f"Codex SDK UserAgent returned invalid ProposedAction: {exc}") from exc

    def _bridge_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        process = self._ensure_process()
        self._request_id += 1
        request = {
            **payload,
            "id": self._request_id,
            "threadId": self.thread_id or self.options.thread_id,
            "workingDirectory": self.options.working_directory,
            "model": self.options.model,
            "sandboxMode": self.options.sandbox_mode,
            "approvalPolicy": self.options.approval_policy,
            "networkAccess": self.options.network_access,
            "skipGitRepoCheck": self.options.skip_git_repo_check,
        }
        line = json.dumps(request, ensure_ascii=False)
        assert process.stdin is not None
        assert process.stdout is not None
        try:
            process.stdin.write(line + "\n")
            process.stdin.flush()
        except OSError as exc:
            raise RuntimeError(f"Codex SDK bridge write failed: {exc}") from exc
        deadline = time.monotonic() + self.options.timeout_seconds
        while time.monotonic() < deadline:
            response_line = process.stdout.readline()
            if not response_line:
                stderr = self._read_stderr_tail(process)
                raise RuntimeError(f"Codex SDK bridge exited unexpectedly. {stderr}".strip())
            try:
                response = json.loads(response_line)
            except json.JSONDecodeError:
                continue
            if response.get("id") not in {None, self._request_id}:
                continue
            if not response.get("ok"):
                error = response.get("error") or "Codex SDK bridge request failed."
                detail = response.get("detail")
                suffix = f" ({detail})" if detail else ""
                raise RuntimeError(f"Codex SDK UserAgent unavailable: {error}{suffix}")
            return response
        raise RuntimeError("Codex SDK UserAgent unavailable: bridge request timed out.")

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        node_path = shutil.which(self.options.node_bin)
        if node_path is None:
            raise RuntimeError(f"Codex SDK UserAgent unavailable: node binary not found: {self.options.node_bin}")
        bridge_path = Path(self.options.bridge_path) if self.options.bridge_path else Path(__file__).with_name("codex_sdk_bridge.mjs")
        if not bridge_path.exists():
            raise RuntimeError(f"Codex SDK UserAgent unavailable: bridge not found: {bridge_path}")
        self._process = subprocess.Popen(
            [node_path, str(bridge_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.options.working_directory,
            bufsize=1,
        )
        return self._process

    def _load_thread_id(self) -> str:
        if not self.options.thread_store_path:
            return ""
        path = Path(self.options.thread_store_path)
        if not path.exists():
            return ""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        thread_id = payload.get("thread_id")
        return thread_id if isinstance(thread_id, str) else ""

    def _update_thread_id(self, thread_id: str) -> None:
        if not thread_id or thread_id == self.thread_id:
            return
        self.thread_id = thread_id
        if not self.options.thread_store_path:
            return
        path = Path(self.options.thread_store_path)
        payload = {
            "schema": "metaloop.user_agent_thread",
            "version": "1.0",
            "thread_id": self.thread_id,
            "backend": "codex_sdk",
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            return

    def _read_stderr_tail(self, process: subprocess.Popen[str]) -> str:
        if process.stderr is None:
            return ""
        try:
            return process.stderr.read(2000)
        except OSError:
            return ""


def _build_codex_user_agent_prompt(*, user_text: str, status: dict[str, Any], startup: bool) -> str:
    status_json = json.dumps(status, indent=2, ensure_ascii=False)
    action_schema = json.dumps(ProposedAction.model_json_schema(), indent=2, ensure_ascii=False)
    allowed_actions = ", ".join(action.value for action in UserAction)
    mode = "startup" if startup else "user_turn"
    user_text_block = user_text if user_text else "(empty startup turn)"
    return f"""You are MetaLoop's user-facing interface agent.

You are running inside a local project workspace. First understand the current project by inspecting concise local signals as needed: README, manifests, top-level directories, git history, and relevant files. Do not read the whole repository by default.

Your job is to talk to the user and choose one structured MetaLoop action. You do not execute actions yourself. The shell will optionally confirm and then call MetaLoop's built-in commands.

Hard boundaries:
- Do not directly modify locked MissionSpec, MissionCapsule, or GoalContract.
- Do not weaken acceptance criteria or expand authority from an ambiguous user phrase.
- If scope, acceptance, or authority must change, choose collect_feedback, propose_revision, or apply_redesign.
- If the user asks to continue while redesign_required is present, do not choose resume_run.
- Prefer asking/answering conversationally in assistant_message, but always return JSON only.

Allowed actions:
{allowed_actions}

Command mapping:
- start_design -> ["design"]
- resume_design -> ["design", "--resume"]
- run_current_mission -> ["run"]
- verify_current_run -> ["verify"]
- show_status -> ["status"]
- resume_run -> ["resume"]
- collect_feedback/propose_revision/apply_redesign/unknown/quit -> []

Current mode:
{mode}

Current MetaLoop structured status:
```json
{status_json}
```

User text:
```text
{user_text_block}
```

Return a single JSON object matching this schema:
```json
{action_schema}
```
"""


def _parse_codex_action_payload(final_message: str) -> dict[str, Any]:
    text = final_message.strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("Codex UserAgent final message was not JSON.")
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise RuntimeError("Codex UserAgent final JSON was not an object.")
    return payload
