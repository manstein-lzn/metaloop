# Codex SDK 能力边界调研

调研日期：2026-05-01

## 1. 核心结论

Codex SDK 不是一个普通的“模型调用 SDK”。它是对本地 Codex Agent 的程序化控制接口。

对 MetaLoop 来说，Codex 最适合承担：

- Worker：执行代码修改、命令运行、文件变更。
- Strategy Reviewer：基于上下文审查变更和提出修复建议。
- Planner / Brainstormer：生成工程计划和方案，但应通过结构化输出约束。

Codex 不适合直接承担：

- MetaLoop Scheduler 的最终路由权。
- MetaLoop Policy Engine 的硬约束判断。
- MetaLoop Checkpoint / Event Log 的事实来源。
- 多 MetaLoop 编排器。

MetaLoop 应该把 Codex 视为“强执行型 Agent 后端”，而不是让 Codex 接管整个 Kernel。

## 2. SDK 形态

### 2.1 TypeScript SDK

官方 Codex SDK 主路径是 TypeScript：

- 包名：`@openai/codex-sdk`
- 运行时要求：Node.js 18+
- 机制：包装 `@openai/codex` CLI，启动本地 `codex` 子进程，通过 stdin/stdout 交换 JSONL 事件。

关键能力：

- `Codex.startThread()`
- `Codex.resumeThread(threadId)`
- `thread.run(prompt)`
- `thread.runStreamed(prompt)`
- structured output via `outputSchema`
- local images as input
- working directory control
- sandbox / approval / network / model / config overrides

这意味着 Python 版 MetaLoop 不能直接 `import Codex` 使用 TypeScript SDK。需要以下二选一：

1. 通过 Python 子进程直接调用 `codex exec --json`。
2. 写一个 Node bridge，用 TypeScript SDK 包一层 RPC/stdio 接口给 Python 调用。

第一阶段建议采用方案 1。

### 2.2 Python SDK

官方文档中存在 Python SDK，但它被标注为 experimental。

它的机制不是包装 `codex exec`，而是控制本地 `codex app-server` JSON-RPC v2。

边界：

- 需要 Python 3.10+
- 需要本地 Codex 开源仓库 checkout
- 包名/路径在仓库 `sdk/python`
- 需要通过 context manager 管理生命周期
- 更适合未来深入集成，不适合作为 MetaLoop 第一阶段依赖

MetaLoop 当前是 Python 项目，但不应该立即绑定 experimental Python SDK。先用 `codex exec --json` 建立稳定适配层更稳；`--output-schema` 可以作为增强能力，但不能作为唯一执行路径。

## 3. CLI / exec 能力

`codex exec` 是非交互自动化入口，适合 CI、脚本和流水线。

关键能力：

- 非交互运行任务。
- stdin 可以作为 prompt 或上下文。
- `--json` 输出 JSONL 事件流。
- `--output-schema` 约束最终响应。当前本机 provider 下该路径会触发 Responses/provider 失败，而普通 `--json` 可用，因此 MetaLoop 必须保留 fallback。
- `-o/--output-last-message` 写出最终消息。
- `resume` 继续已有 session。
- `--cd` 设置 workspace。
- `--sandbox` 控制权限：`read-only` / `workspace-write` / `danger-full-access`。
- `--skip-git-repo-check` 允许非 Git 目录。
- `--image` 输入图片。
- `--model` 指定模型。

`--json` 事件类型包括：

- `thread.started`
- `turn.started`
- `turn.completed`
- `turn.failed`
- `item.started`
- `item.updated`
- `item.completed`
- `error`

item 类型包括：

- `agent_message`
- `reasoning`
- `command_execution`
- `file_change`
- `mcp_tool_call`
- `web_search`
- `todo_list`
- `error`

这些事件非常适合映射到 MetaLoop 的 `SystemEvent`。

### 3.1 `--output-schema` 的定位

`--output-schema` 不是 MetaLoop 必须依赖的高级能力，而是“结构化最终消息”的便利约束。它的价值是减少最终响应解析的不确定性；它的风险是不同 provider / API 路径对结构化输出支持不一致。

当前策略：

- 优先尝试 `codex exec --json --output-schema`。
- 如果 schema 路径失败且 Codex binary 存在、未超时，则自动 fallback 到 `codex exec --json`。
- fallback 模式要求 Codex 输出 raw JSON，MetaLoop 自己负责 parse / normalize / validate。
- CLI 提供 `--no-output-schema`，用于直接绕开 schema 路径。

## 4. 安全与权限边界

Codex 自带 sandbox 和 approval 机制，但 MetaLoop 不能把它当成唯一安全层。

Codex sandbox 模式：

- `read-only`：能读，不能直接编辑或运行未授权命令。
- `workspace-write`：能读文件、在 workspace 内编辑、运行常规本地命令。
- `danger-full-access`：无沙箱限制，只适合外部隔离环境。

推荐 MetaLoop 默认：

```text
sandbox = workspace-write
approval = on-request
```

MetaLoop 自己仍必须保留：

- workspace_root 校验。
- 工具白名单/黑名单。
- 高风险操作拦截。
- 预算约束。
- 事件落库。
- Scheduler 路由权。

Codex 的权限系统是执行层安全边界；MetaLoop Policy Engine 是产品层安全边界。

## 5. 与 MetaLoop 的正确嵌入方式

### 5.1 建议架构

```text
MetaLoop Kernel
  -> CodexAdapter
      -> codex exec --json --output-schema
          -> JSONL events
  -> EventMapper
      -> SystemEvent / Artifact / StepResult
  -> ArtifactValidator
      -> command validators
  -> StrategyReviewer
      -> structured ReviewResult
  -> Scheduler
      -> next_step / retry / replan / fail / complete / propose_next_task
```

CodexAdapter 应是可替换后端，而不是 Kernel 的核心。

### 5.2 角色映射

| MetaLoop 角色 | 是否适合 Codex | 建议方式 |
| --- | --- | --- |
| Interviewer | 适合，但后置 | 用 structured output 生成 MissionSpec 草案 |
| Brainstormer | 适合 | `outputSchema` 约束方案列表 |
| Planner | 适合 | `outputSchema` 约束 TaskPlan |
| Worker | 最适合 | `workspace-write` 下执行真实代码任务 |
| Artifact Validator | 不应主要用 Codex | 优先命令/schema/file 检查 |
| Strategy Reviewer | 适合 | 输出结构化 ReviewResult |
| Scheduler | 不适合 | 必须由 MetaLoop 代码硬路由 |
| Policy Engine | 不适合 | 必须由 MetaLoop 代码硬约束 |

### 5.3 第一阶段接入顺序

1. 实现 `CodexExecAdapter`：Python 调 `codex exec --json`。
2. 把 JSONL events 映射到 MetaLoop `SystemEvent`。
3. 支持 `outputSchema`，让 Codex Worker 返回结构化 `StepResult` 摘要。
4. 支持 workspace/sandbox/model/approval 参数。
5. Worker 先接 Codex，Reviewer 仍用当前 dummy/规则逻辑。
6. 再接 Strategy Reviewer。
7. 最后接 Planner 和 Co-Design。

不要一开始把所有 Agent 都接 Codex，否则无法判断问题来自哪个节点。

## 6. MetaLoop 需要避免的错误假设

1. **不要假设 Codex SDK 是 Python 原生稳定库。**  
   当前稳定主路径是 TS SDK 和 CLI；Python SDK 仍是 experimental。

2. **不要让 Codex 决定 Scheduler 路由。**  
   Codex 可以建议，MetaLoop 必须硬路由。

3. **不要把 Codex session 当作 MetaLoop checkpoint。**  
   Codex session 可以 resume，但 MetaLoop checkpoint 必须自己存。

4. **不要把 Codex JSONL 当作最终状态。**  
   JSONL 是观测输入，必须映射成 MetaLoop 的 `SystemEvent`、`Artifact`、`StepResult`。

5. **不要一开始使用 `danger-full-access`。**  
   默认应使用 `workspace-write`，必要时由 MetaLoop Policy Engine 决定是否允许更高权限。

6. **不要依赖 Codex 自己的上下文来保存任务契约。**  
   `MissionSpec` 必须由 MetaLoop 持有，并在每个 Codex turn 中显式注入必要上下文。

## 7. 对当前 MetaLoop 代码的设计影响

当前 Python Kernel 应新增：

- `src/metaloop/codex_adapter.py`
- `CodexExecOptions`
- `CodexExecResult`
- `CodexEventMapper`
- `CodexWorker`

`Worker` 的接口应从“直接生成 artifact”变成：

```python
class WorkerBackend:
    def run_step(self, mission: MissionSpec, plan: TaskPlan, step: PlanStep) -> StepResult:
        ...
```

然后提供两个实现：

- `DummyWorkerBackend`
- `CodexExecWorkerBackend`

这样 MetaLoop Kernel 不关心底层是 dummy 还是 Codex。

## 8. 参考资料

- OpenAI Codex SDK docs: https://developers.openai.com/codex/sdk
- OpenAI Codex non-interactive mode: https://developers.openai.com/codex/noninteractive
- OpenAI Codex CLI command reference: https://developers.openai.com/codex/cli/reference
- OpenAI Codex sandboxing docs: https://developers.openai.com/codex/concepts/sandboxing
- OpenAI Codex TypeScript SDK repo: https://github.com/openai/codex/tree/main/sdk/typescript
- OpenAI Codex Python SDK repo: https://github.com/openai/codex/tree/main/sdk/python
