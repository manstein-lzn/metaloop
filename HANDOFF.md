# MetaLoop Handoff

最后更新：2026-05-08

本文是给新 Codex/session 的接力文档。目标是让新会话能快速恢复 MetaLoop 项目的当前状态，不从头推演，不丢失架构判断。

## 快速恢复 Prompt

新 session 可以直接粘贴这段：

```text
我们继续开发 MetaLoop。仓库在 /home/mansteinl/metaloop。

请先读取：
1. HANDOFF.md
2. STATE.md
3. ROADMAP.md
4. docs/mission_capsule_constitution.md
5. docs/minimal_v3_codex_goal_architecture.md
6. git status / git log --oneline -5

然后基于当前状态继续，不要从头推演。

当前最高优先级是：
1. RedesignProposal -> Capsule revision / revised MissionSpec 的用户确认闭环。
2. long-running TUI shell v2：把第一版 prompt-loop shell 打磨成更完整的状态流/命令面板。
3. Codex SDK UserAgent v2：打磨 action confirmation UX 和 thread 状态展示。
4. skill-first 重构：让 `$metaloop` skill 成为可一键部署的自包含 Codex Skill；强约束仍落在 bundled kernel/CLI/schema/validator/hook/sandbox/wrapper runtime。
```

## 当前仓库状态

仓库路径：

```bash
/home/mansteinl/metaloop
```

远端：

```bash
origin git@github.com:manstein-lzn/metaloop.git
```

当前分支：

```bash
main
```

本轮开始基线提交：

```bash
4d78660 Add SDK-backed MetaLoop shell agent
```

上一次确认状态：

```bash
git status --short --branch
# ## main...origin/main
```

测试基线：

```bash
.venv/bin/pytest -q
# 233 passed
```

环境注意：

- 当前 checkout 原本没有 `.venv/`；本 session 已用 `python3 -m venv .venv` 创建，并安装 `pytest==8.4.2`、`pydantic>=2.0`、`rich>=13.0`、`pluggy>=1.5,<2`，再执行 `pip install -e . --no-deps`。
- 使用 `.venv/bin/python`，不要假设系统存在 `python`
- package 入口：`metaloop = metaloop.cli:main`
- Python 要求：`>=3.12`

## 项目一句话

MetaLoop 是一个本地优先的任务治理层，用结构化 Co-Design、MissionSpec、MissionCapsule、GoalContract、ExecutionReport、VerificationResult 和 attempt history 来治理 Codex 执行复杂任务。

核心判断：

```text
Codex 是高智能执行器。
MetaLoop 是结构化需求、边界、验收、审计、状态和长期维护层。
```

MetaLoop 不是为了“比 Codex 更会写代码”。它的价值在于：

- 把用户模糊需求压榨成结构化 contract。
- 把一次性 prompt 变成有状态的任务闭环。
- 把 Codex 自述完成替换为 MetaLoop 独立验收。
- 把执行证据、失败、修复、重设计记录为长期可追踪资产。

## 当前主路径

当前极简 v3 主路径：

```text
Co-Design
  -> MissionSpec
  -> MissionCapsule
  -> GoalContract
  -> ordinary Codex exec goal-style runtime
  -> ExecutionReport
  -> VerificationResult
  -> SoftReviewDecision
  -> repair / redesign / complete
```

默认 `metaloop run` 对 mission 文件走 goal-style 单 Codex agent runtime。

旧多 agent pipeline：

```text
brainstormer -> planner -> worker -> reviewer -> scheduler
```

仍存在，但不是默认路径。只作为：

```bash
metaloop run --mode rigorous
```

或显式 worker/诊断路径。

## 已实现能力

### Co-Design

- `metaloop design`
- 默认交互模式使用 Codex co-designer。
- Rich 交互、resume、设计 review 页面。
- 需求发现 -> brainstorm expansion -> human design review -> interactive refinement -> contract lock。
- 用户必须显式 approve / lock / 完成 / 确认，交互模式才锁定。
- 非交互/JSON 模式只有在 reviewer 通过且无任务特定 unresolved decisions 时才自动锁定。
- Codex co-designer / brainstormer / answerer 不可用时 fail-fast，不静默回落 rule backend。

### Mission / Capsule / Goal

- `MissionSpec`
- `MissionCapsule`
- `GoalContract`
- `ExecutionReport`
- `VerificationResult`
- `SoftReviewDecision`
- `RedesignProposal`
- `AttemptRecord`
- `.metaloop/` 结构化 artifacts。

### Run / Verify / Resume / Status

- `metaloop` / `metaloop shell`
- `metaloop run`
- `metaloop verify`
- `metaloop status`
- `metaloop resume`
- `metaloop compile`
- `metaloop list`
- `metaloop show`

goal mode 行为：

- MissionSpec 文件中的 `run_id` 被保留为稳定 contract/capsule id。
- `.metaloop/run.json` 指向最新 runtime mission。
- `metaloop verify` 如果发现 `.metaloop/run.json`，会优先验证最新 runtime mission，避免原始 mission id 和 ExecutionReport id mismatch。

### Long-Running Shell / UserAgent v1

- 默认空命令 `metaloop` 现在进入 `metaloop shell`，不再等价于 `metaloop run`。
- `src/metaloop/tui_shell.py` 提供第一版 Rich prompt-loop shell：启动时读取 `.metaloop/` 状态，展示 workspace overview，循环接收自然语言或显式 action。
- `src/metaloop/user_agent.py` 提供 Codex SDK-backed UserAgent v1：默认 shell 启动时通过 Node bridge 调用 `@openai/codex-sdk`，创建/保留 Codex thread，让 Codex 理解现存项目并输出 `ProposedAction`。
- SDK thread id 持久化到 `.metaloop/user_agent_thread.json`；重启 `metaloop` 后会读取该文件并通过 `resumeThread(threadId)` 继续同一个 Codex agent 历史。
- `metaloop shell --reset-user-agent-thread` 只删除 `.metaloop/user_agent_thread.json` 并退出；不会删除 MissionSpec、Capsule、run、verification 或 attempt history。
- `src/metaloop/codex_sdk_bridge.mjs` 是 Python -> TypeScript SDK stdio bridge；根目录 `package.json` 声明 `@openai/codex-sdk`，已执行 `npm install` 生成 `package-lock.json`。
- `CodexExecUserAgent` 保留为 `metaloop shell --user-agent exec` 兼容路径；`UserAgent` 本地规则映射仍保留，但只作为 `metaloop shell --user-agent local` 调试路径；默认路径不静默回落到规则假智能。
- CodexSdkUserAgent 输出 action：`start_design`、`resume_design`、`run_current_mission`、`verify_current_run`、`show_status`、`resume_run`、`collect_feedback`、`propose_revision`、`apply_redesign`、`quit`。
- Shell 执行动作时仍调用现有 `main(["design" / "run" / "verify" / "status" / "resume", "--workspace", ...])`，不创建平行状态系统。
- 用户说“不满意/修改/重设计”等反馈时，第一版 shell 只收集和解释边界；不会直接修改 locked MissionSpec、MissionCapsule 或 GoalContract。
- 当状态是 `redesign_required` 时，UserAgent 不会把“继续”映射成普通 worker rerun，而是提出 revision/redesign action。

### Skill-First Protocol Layer

- `docs/metaloop_lightweight_protocol_reframing.md` 是新的轻量协议层方向文档。
- `skills/metaloop/SKILL.md` 是 repo 内 `$metaloop` skill 入口。
- `skills/metaloop/agents/openai.yaml` 是 skill UI metadata。
- `skills/metaloop/references/lightweight_protocol.md` 沉淀轻量协议和 skill 边界。
- `skills/metaloop/scripts/metaloop_kernel.py` 是 skill 内置 lightweight kernel，避免目标环境必须先安装完整 MetaLoop package；当前支持 status/design/run/verify/mark，写入 capsule/execution_report/verification_result，并做最小 schema 校验、design gate、locked VerificationSpec、generic validators 和 extension hash 审计。
- 核心原则：MetaLoop 可以 skill-first，但不能 prompt-only。Skill 负责入口和对齐；bundled kernel/代码负责检查和状态；hooks/sandbox/wrapper runtime 负责更强约束。

### Runtime Review / Repair / Redesign

- hard validators authoritative。
- `ask_worker_to_fix` 只允许 implementation repair。
- repair 不允许改 locked MissionSpec / MissionCapsule / GoalContract。
- repeated repair 会升级到 redesign gate。
- `ask_architect_to_rethink` / `ask_planner_to_replan` / `ask_brainstormer_for_options` 会生成 `.metaloop/redesign_proposal.json`。
- Capsule 可进入 `redesign_required`。
- status/resume 不会把 `redesign_required` 当普通 worker rerun。

### Attempt History

- `.metaloop/attempts/<attempt_id>.json`
- 记录 git commit ref、changed files、validation、reviewer decision、failure/lesson。
- 过滤 `.metaloop/`、`metaloop.mission.json`、`__pycache__/`、`.pyc/.pyo` 噪声。
- 当前不会自动 commit。

### Prompt Pack / Prompt Compiler

已迁移到 prompt pack 的 runtime prompt：

- `prompts/co_design/brainstorm.md`
- `prompts/co_design/discovery.md`
- `prompts/run/redesign.md`
- `prompts/run/soft_reviewer.md`

未迁移：

- 主 goal prompt
- repair prompt

原则：

- prompt pack 渲染失败必须 fail-fast。
- 不允许静默回退到另一套 hardcoded prompt。
- 不要贸然把 runtime 全量切到 prompt md。

## 当前最高优先级

### 1. Redesign / Revision 闭环

当前已有 shell/UserAgent v1 会识别反馈和 redesign_required，但还不会真正 apply proposal。

下一步应实现：

- structured user feedback schema。
- `metaloop revise` / `metaloop redesign` 或 shell 内等价 action。
- 用户确认 RedesignProposal。
- 生成 revised MissionSpec。
- 生成 Capsule revision id/version。
- 新 run 绑定 revised contract。

### 2. Long-Running TUI Shell v2

目标：

```bash
metaloop
```

启动后进入持续 TUI 会话，而不是一个命令跑完就退出。

v1 已实现 prompt-loop 最小闭环；v2 继续补齐更完整的状态流、命令面板、历史 attempts 视图和 revision flow。

应提供：

- 当前 workspace 总览。
- mission/capsule/run/verification/redesign/attempt history 状态。
- 用户自然语言输入区。
- 状态流：Codex、reviewer、verification、repair/redesign route 当前动作。
- 命令面板：design、run、verify、status、resume、revise、quit。
- 中断恢复：重启后从 `.metaloop/` 恢复。

验收：

- 新 repo 中运行 `metaloop`，无需记忆命令即可完成 design -> run -> verify。
- 中途退出后重新运行 `metaloop`，能看到当前状态并继续。
- 用户说“不满意”时能进入 feedback/revise/redesign，而不是只显示 completed。

### 3. Codex SDK UserAgent v2

目标：新增一个专门面向用户的 agent。

职责：

- 读取 `.metaloop/` 结构化状态。
- 解释当前状态。
- 理解用户自然语言。
- 建议下一步。
- 把用户意图映射为结构化 MetaLoop action。

建议 action：

```text
start_design
resume_design
run_current_mission
verify_current_run
show_status
resume_run
collect_feedback
propose_revision
apply_redesign
quit
```

v1 已默认接入 Codex SDK agent，并持久化 SDK thread id 支持跨 shell resume，也提供 reset/forget thread 命令。v2 应打磨 action confirmation UX 和 thread 状态展示，并继续遵守 fail-fast；Codex SDK 不可用时直接报错，不允许静默回落为看似智能的规则答复。规则映射只作为显式 local/basic mode。

数据流建议：

```text
UserTurn
  -> UserIntent
  -> ProposedAction
  -> TUI Confirmation
  -> MetaLoop Command/Runtime Call
```

硬边界：

- UserAgent 不能直接修改 locked MissionSpec。
- UserAgent 不能直接修改 MissionCapsule / GoalContract。
- 用户一句“继续”不能自动扩大权限或弱化验收。
- 涉及 scope、acceptance、authority 变化必须进入 revise/redesign。
- Codex 不可用时直接报错，不允许假智能规则兜底。

### 3. Redesign / Revision 闭环

当前已有：

- `.metaloop/redesign_proposal.json`
- Capsule `redesign_required`
- status/resume 会阻止 blind rerun

缺失：

- `metaloop revise` / `metaloop redesign` / TUI feedback flow。
- 用户确认 RedesignProposal。
- 生成 revised MissionSpec。
- 生成 Capsule revision。
- 新 run 绑定 revised contract。

建议实现顺序：

1. 先定义 structured user feedback schema。
2. 再定义 revised MissionSpec 生成路径。
3. 再定义 Capsule revision id/version 规则。
4. 最后接入 TUI/UserAgent。

## 关键不变量

这些不能破坏：

- Codex 自述完成不等于 MetaLoop verified completion。
- hard validator 失败不能进入 `completed_verified`。
- `manual` 是最终 human acceptance，不是内部 agent route。
- `llm_review` 是 soft acceptance，不能伪装成 hard verified。
- repair 不能改变 locked contract。
- redesign 必须显式记录，不允许 worker 静默改 scope/acceptance/authority。
- MetaLoop 不内建递归，不自动 spawn 子 MetaLoop。
- 不默认启用旧多 agent pipeline。
- 不默认塞完整聊天史、完整仓库、完整日志给 LLM。
- `.metaloop/` structured artifacts 是 operational memory。
- Git history / attempt history 是历史学习来源。

## 不要做

- 不要从头重写架构。
- 不要重新争论是否需要递归 MetaLoop；当前结论是不内建递归。
- 不要把 TUI 做成平行状态系统。
- 不要让 UserAgent 绕过 MissionCapsule。
- 不要把规则 fallback 伪装成 Codex agent。
- 不要默认 `danger-full-access`。
- 不要把 node_modules、VSIX、traced `.pt`、`.venv`、`.metaloop` 提交进 Git。
- 不要把主 goal prompt 贸然迁移到 prompt pack。

## 重要文件

必读：

- `HANDOFF.md`
- `STATE.md`
- `ROADMAP.md`
- `README.md`
- `docs/mission_capsule_constitution.md`
- `docs/minimal_v3_codex_goal_architecture.md`

核心代码：

- `src/metaloop/cli.py`
- `src/metaloop/ui.py`
- `src/metaloop/co_design.py`
- `src/metaloop/goal.py`
- `src/metaloop/goal_runtime.py`
- `src/metaloop/capsule.py`
- `src/metaloop/run_artifacts.py`
- `src/metaloop/attempt_history.py`
- `src/metaloop/soft_review.py`
- `src/metaloop/prompt_pack.py`

测试：

- `tests/test_cli.py`
- `tests/test_co_design.py`
- `tests/test_goal.py`
- `tests/test_goal_runtime.py`
- `tests/test_capsule.py`
- `tests/test_prompt_semantics.py`

## 常用命令

测试：

```bash
cd /home/mansteinl/metaloop
.venv/bin/pytest -q
```

运行：

```bash
metaloop design
metaloop run
metaloop status
metaloop verify
metaloop resume
```

调试：

```bash
metaloop compile --json
metaloop verify --json
metaloop run --json
metaloop show <run_id> --events
```

Git：

```bash
git status --short --branch
git log --oneline --decorate -5
git push
```

## 新 Session 推荐工作方式

1. 先读 `HANDOFF.md`。
2. 再读 `STATE.md` 和 `ROADMAP.md`。
3. 用 `git status --short --branch` 确认是否干净。
4. 如果要开发，优先实现 TUI shell / UserAgent 的最小闭环。
5. 每次修改后跑相关测试，关键路径跑 `.venv/bin/pytest -q`。
6. 更新 `STATE.md` / `ROADMAP.md` / `HANDOFF.md`。
7. commit。

## 推荐下一步开发切片

第一阶段最小产品闭环已完成：

```text
metaloop
  -> 读取 workspace status
  -> 显示当前状态
  -> 提供自然语言输入
  -> UserAgent 输出 ProposedAction
  -> 用户确认
  -> 调用现有 design/run/status/verify/resume 函数
  -> 回到 shell
```

已新增模块：

```text
src/metaloop/user_agent.py
src/metaloop/tui_shell.py
src/metaloop/codex_sdk_bridge.mjs
tests/test_user_agent.py
tests/test_tui_shell.py
```

接下来建议在此基础上实现 RedesignProposal apply/revision，而不是继续扩 shell 外观。

第一版 TUI 是 Rich prompt loop，未引入 Textual。目标是产品控制流成立，而不是先做复杂 UI 框架。
