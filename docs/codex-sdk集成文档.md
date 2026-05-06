# Codex SDK 集成文档

本文是 MetaLoop 接入 Codex 的工程手册。`docs/codex-sdk能力边界.md` 记录调研结论，本文面向实现。

## 1. 集成目标

MetaLoop 要把 Codex 嵌入为执行 runtime，而不是让 Codex 接管 MissionSpec 和最终验收。

2026-05-02 更新：Codex CLI 0.128.0 引入 `/goal` feature 后，默认集成方向应从“每个 PlanStep 调 `codex exec`”调整为“MissionSpec 编译到 Codex goal runtime，MetaLoop 再验收”。

实现约束：当前本机 `codex --help` / `codex exec --help` 没有暴露独立非交互式 `goal` 子命令，`/goal` 仍表现为交互式 TUI 功能。因此 MetaLoop 先实现稳定的 `GoalContract` / `ExecutionReport` / `VerificationResult` 边界；真正的 `GoalRuntimeAdapter` 在 Codex 暴露稳定 API/CLI 后替换传输层。

宪法层文档：`docs/mission_capsule_constitution.md`。

当前权威 MVP 实现文档：`docs/minimal_v3_codex_goal_architecture.md`。

正确边界：

```text
MetaLoop Kernel
  owns: MissionSpec / Policy / Budget / Event Log / Checkpoint / Scheduler

Codex Backend
  owns: code understanding / file edits / command execution / patch generation / local engineering work
```

Codex 可以建议 `retry`、`replan`、`complete`，但最终路由必须由 MetaLoop Scheduler 决定。

Codex `/goal complete` 只能表示 Codex 认为目标完成，不能直接等同于 MetaLoop Mission 完成。

## 2. 可用入口

### 2.1 v3 推荐入口：Codex `/goal`

默认长任务执行应优先使用 Codex `/goal` 或 app-server goal API。

原因：

- `/goal` 是 Codex runtime 的一级目标状态。
- 支持持久化目标、continuation、pause/resume、budget 状态。
- 避免 MetaLoop 每个小步骤重新启动 Codex worker/reviewer 导致上下文和 token 爆炸。
- 更符合 Codex 的强项：单 agent 针对一个明确目标持续完成工程任务。

MetaLoop 对接方式：

```text
MissionSpec
  -> MissionCompiler
  -> goal_objective
  -> Codex /goal runtime
  -> MetaLoop verification_plan
  -> final acceptance classification
```

### 2.2 兼容入口：`codex exec`

`codex exec` 保留为 fallback 和 rigorous/multi-agent 模式的执行入口。

```bash
codex exec --json --output-schema schema.json --cd <workspace> --sandbox workspace-write <prompt>
```

原因：

- 不需要引入 Node bridge。
- 能直接消费 JSONL 事件。
- 能通过 `--output-schema` 约束最终响应。
- 能控制 workspace、sandbox、approval、model。
- 与当前 SQLite Event Store 容易对接。
- 适合短任务、单步修复、reviewer、fallback。

不再建议把普通工程任务默认拆成多个 `codex exec` worker step。

### 2.3 TypeScript SDK

官方 TypeScript SDK 包名：

```bash
@openai/codex-sdk
```

它包装 `@openai/codex` CLI，通过 stdin/stdout 交换 JSONL 事件。当前 human-facing shell UserAgent 已使用 Node bridge 接入 TypeScript SDK：

```text
src/metaloop/codex_sdk_bridge.mjs
  -> @openai/codex-sdk
  -> Codex.startThread() / thread.run()
```

同一 `metaloop` shell 会话内复用 Codex thread，因此用户可以持续和同一个 Codex agent 对话。Python Kernel 不直接 import TS SDK；它通过 JSONL stdio 请求 bridge，并要求 Codex 返回 `ProposedAction` JSON。真正执行 action 的仍是 MetaLoop shell。

### 2.4 Python SDK

官方 Python SDK 目前是 experimental，控制本地 `codex app-server` JSON-RPC v2。它适合未来深度集成，不作为当前 MVP 依赖。

## 3. Adapter 设计

### 3.1 新增模块

```text
src/metaloop/codex_adapter.py
src/metaloop/workers.py
tests/test_codex_adapter.py
tests/test_workers.py
```

### 3.2 WorkerBackend 接口

```python
from typing import Protocol

from metaloop.schemas import MissionSpec, PlanStep, StepResult, TaskPlan


class WorkerBackend(Protocol):
    def run_step(self, mission: MissionSpec, plan: TaskPlan, step: PlanStep) -> StepResult:
        ...
```

实现：

- `DummyWorkerBackend`：当前确定性实现，用于测试。
- `CodexExecWorkerBackend`：调用 `codex exec`，用于真实工程任务。

Kernel 只依赖 `WorkerBackend`，不直接知道 Codex。

v3 后应新增：

```text
src/metaloop/mission_compiler.py
src/metaloop/goal_runtime.py
src/metaloop/verification.py
```

其中：

- `MissionCompiler` 生成 `goal_objective` 和 `verification_plan`。
- `GoalRuntimeAdapter` 负责启动、观察、恢复 Codex goal。
- `VerificationRunner` 负责 hard validators / soft review / evidence checks。

## 4. CodexExecOptions

建议定义：

```python
class CodexExecOptions(BaseModel):
    codex_bin: str = "codex"
    model: str | None = None
    sandbox: Literal["read-only", "workspace-write", "danger-full-access"] = "workspace-write"
    approval_policy: Literal["never", "on-request", "on-failure", "untrusted"] = "on-request"
    network_access: bool = False
    skip_git_repo_check: bool = False
    timeout_seconds: int = 900
    output_schema: dict[str, Any] | None = None
```

默认不要使用 `danger-full-access`。

## 5. Prompt 组装

每次 Codex Worker 调用必须显式注入 MetaLoop 契约，不依赖 Codex session 自己记住上下文。

最小 prompt 结构：

```text
You are executing one MetaLoop Worker step.

MissionSpec:
<mission json>

TaskPlan:
<plan json>

Current Step:
<step json>

Rules:
- Only work inside workspace_root.
- Do not change mission goals.
- Prefer minimal, focused changes.
- Return final response matching the output schema.
```

## 6. 输出 Schema

Codex 最终响应应被约束为一个 Worker 摘要，而不是直接作为 MetaLoop 真相。

建议第一版 schema：

```json
{
  "type": "object",
  "properties": {
    "status": {
      "type": "string",
      "enum": ["success", "failed", "blocked_by_policy", "blocked_by_auth"]
    },
    "summary": { "type": "string" },
    "artifacts": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "kind": { "type": "string" },
          "uri": { "type": "string" },
          "content": { "type": "string" }
        },
        "required": ["kind"]
      }
    },
    "error_log": { "type": "string" }
  },
  "required": ["status", "summary", "artifacts"],
  "additionalProperties": false
}
```

MetaLoop 再把该 JSON 映射成 `StepResult`。

## 6.5 MissionSpec 与 Goal 的边界

`goal_objective` 是自然语言，不是硬 schema。它应该包含：

- 任务目标。
- 交付物。
- 实现约束。
- 范围边界。
- Definition of Done。
- 执行前/完成前应运行的验证。
- 无法验证时需要记录的证据和限制。

`verification_plan` 是 MetaLoop 的结构化验收，不交给 Codex 自己裁决。

验收方式分层：

- hard validation：命令、文件、schema、测试。
- soft review：架构、可用性、文档、安全边界。
- evidence：截图、日志、manual steps、known limitations。
- final human acceptance：只能由用户在所有内部工作完成后判断的产品方向或体验。

最终状态必须由 MetaLoop 分类：

```text
completed_verified
completed_with_soft_acceptance
completed_with_limitations
completed_pending_human_acceptance
blocked
failed
```

## 7. JSONL 事件映射

Codex `--json` 事件应映射为 MetaLoop `SystemEvent`。

| Codex event/item | MetaLoop event |
| --- | --- |
| `thread.started` | `codex_thread_started` |
| `turn.started` | `codex_turn_started` |
| `item.started command_execution` | `codex_command_started` |
| `item.completed command_execution` | `codex_command_completed` |
| `item.completed file_change` | `codex_file_changed` |
| `item.completed mcp_tool_call` | `codex_mcp_tool_completed` |
| `item.completed agent_message` | `codex_agent_message` |
| `turn.completed` | `codex_turn_completed` |
| `turn.failed` | `codex_turn_failed` |
| `error` | `codex_error` |

这些事件进入 Event Store，但 Scheduler 不直接根据原始 Codex 事件路由。路由基于 `StepResult` 和 `ReviewResult`。

## 8. 安全策略

默认参数：

```text
sandbox = workspace-write
approval_policy = on-request
network_access = false
```

MetaLoop 仍必须执行：

- `PolicyEngine.check_workspace_path`
- budget 检查
- tool scope 检查
- run event/checkpoint 落库
- Scheduler 路由裁决

Codex sandbox 是执行层护栏，MetaLoop Policy Engine 是产品层护栏。

## 9. MVP 接入步骤

### Step 1：抽象 WorkerBackend

- 移出 Kernel 内部 dummy worker 逻辑。
- 新增 `DummyWorkerBackend`。
- 确保现有 14 个测试不变。

### Step 2：实现 CodexExecAdapter

- 生成临时 output schema 文件。
- 调用 `codex exec --json`。
- 逐行解析 JSONL。
- 支持 timeout。
- 收集 usage、thread id、items。

### Step 3：事件映射

- 将 Codex JSONL 映射到 `SystemEvent`。
- 所有事件写入 SQLite。
- 不因未知事件崩溃，未知事件保留原始 payload。

### Step 4：CodexExecWorkerBackend

- 组装 prompt。
- 调用 adapter。
- 解析 final agent message。
- 映射成 `StepResult`。
- 对解析失败生成 failed `StepResult`。

### Step 5：CLI 开关

```bash
metaloop run "Fix failing tests" --worker codex
metaloop run "Fix failing tests" --worker codex --sandbox workspace-write
metaloop run "Summarize repo" --worker codex --sandbox read-only
metaloop run "Summarize repo" --worker codex --sandbox read-only --no-output-schema
```

Codex backend 下 runtime roles 已拆分为独立 Codex 调用：brainstormer、planner、worker、strategy_reviewer。RuleBased backend 仅用于测试和离线 smoke。

`--no-output-schema` 用于 provider 不支持或不稳定支持 structured output 的情况。此时 Codex 仍以 `--json` 输出事件流，最终 agent message 必须是 JSON；MetaLoop 会执行解析、宽松规范化和 validator 检查。

## 10. 非目标

当前不做：

- Codex Python experimental SDK。
- Node bridge。
- Codex app-server。
- 多 MetaLoop Orchestrator。
- 让 Codex 控制 Scheduler。
- 将 Codex session 当作 MetaLoop checkpoint。

## 11. 验收标准

Codex 集成第一阶段完成的标准：

- `metaloop run ... --worker dummy` 仍全绿。
- `metaloop run ... --worker codex --sandbox read-only` 能完成只读任务。
- `metaloop run ... --worker codex --sandbox workspace-write` 能在 workspace 内写文件。
- Codex JSONL 事件进入 SQLite。
- Codex 最终响应可通过 output schema 或 fallback JSON 解析成 `StepResult`。
- 失败时生成 `FailureReport` 或 failed `StepResult`，不能吞错。
