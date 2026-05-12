# MetaLoop

MetaLoop 是一个 **Skill-only** 的 Codex 任务治理层。它不再提供仓库级交互命令、聊天界面或外部 agent 编排器；团队使用方式是：在 Codex 里调用 `$metaloop` skill，让 Codex agent 保持智能和上下文，MetaLoop 只负责把目标、边界、验证和反馈写成可审计的 `.metaloop/` 状态。

当前产品形态：

```text
Codex $metaloop skill
  -> skills/metaloop/scripts/metaloop_kernel.py
  -> .metaloop/Mission Capsule + VerificationSpec + ExecutionReport + VerificationResult
  -> optional persistent Codex thread roles recorded in .metaloop/threads.json
  -> adaptive goal loop events and repair/redesign decisions
  -> optional routable work units through job envelopes, tick, outbox, and relay
  -> read-only observability and explicit control files
  -> optional one-shot activation scans for explicit worker commands
```

核心原则：**Prompt-first / code-backed**。Codex agent 和 skill prompt 负责理解、设计、反思和策略；kernel、schemas、validators、`metaloop_core` 和 `.metaloop/` artifacts 负责状态、验证、审计和恢复。

产品收敛原则：**MetaLoop 不做 agent runtime，MetaLoop 做关键控制点。** 当前核心模型是六个 gate：Design Gate、State Checkpoint、Verification Gate、Adaptive Loop、Control Point、Observation Surface。

## 怎么使用

把本仓库的 `skills/metaloop/` 部署到 `${CODEX_HOME:-$HOME/.codex}/skills/metaloop`，然后在目标项目里对 Codex 说：

```text
Use $metaloop. 我想完成 <你的目标>。
```

用户不需要知道 Mission Capsule、VerificationSpec、Adaptive Loop、blackboard、job envelope、tick 或 relay 的细节。Codex 在 `$metaloop` skill 内负责判断任务形态、主动设计协议、提出必要确认、锁定验证方式，再进入执行和反馈闭环。

团队一键安装说明见 [docs/codex_install_metaloop_skill.md](docs/codex_install_metaloop_skill.md)，团队内测边界见 [docs/team_internal_preview_guide.md](docs/team_internal_preview_guide.md)。

## 仓库结构

```text
skills/metaloop/      自包含 Codex Skill，可直接部署到 Codex skills 目录
src/metaloop_core/    可复用协议库：状态、验证、thread registry、event log、反馈闭环
tests/                skill package、core API、core/skill parity 和 verification 测试
tools/                仓库一致性检查
docs/                 当前产品原则和团队使用文档
```

`skills/metaloop/scripts/metaloop_kernel.py` 是 skill 的 portable kernel。目标项目不需要先安装本仓库的 Python package，也不需要额外 Node 依赖。

`src/metaloop_core/` 是给 skill、未来 wrapper 或测试复用的协议后端。它不是用户交互产品，不应该重新长出独立命令界面。

## MetaLoop 管什么

- 深度 design：先把任务目标、上下文、哲学取舍、约束和非目标讲清楚。
- Mission Capsule：把任务合同落到 `.metaloop/mission_capsule.json`。
- VerificationSpec：把“怎么算完成”变成结构化验证规则，而不是事后口头解释。
- ExecutionReport：把执行证据写入 `.metaloop/execution_report.json`。
- VerificationResult：由 locked validators 独立验收，不信 worker 自述。
- Adaptive Goal Loop：当目标未达成时，记录观察、评估、诊断、下一轮计划和 repair/redesign 决策。
- Thread registry：多个 Codex thread 参与时，用 `.metaloop/threads.json` 记录职责和 handoff 边界。
- Event log：用 `.metaloop/event_log.jsonl` 记录长任务中的关键观察、阻塞、决策和验证笔记。
- Context checkpoints：用 `.metaloop/context/*.md` 保存 `resume_brief`、当前假设和失败尝试，避免长期任务因 Codex thread 上下文膨胀而无法接手。
- Routable work units：当一个工作单元不够时，用 `job_envelope.json`、`global_blackboard.json`、`dispatch_map.json`、`tick`、`outbox` 和 `relay` 做显式、可审计的跨节点交接。
- Observability / control：用只读 summary 观察节点和全局状态，用 `.metaloop/control/*.json` 表达 halt、resource approval、inject fact、revise contract 等显式控制意图。
- Dashboard：用 `scripts/metaloop_dashboard.py` 在本地浏览器实时查看只读状态；它不写文件、不路由、不启动 agent。
- Activation：用一次性 scanner 发现 ready node、检查 control/lease，并在调用者显式给出 worker command 时启动 bounded worker；它不是 daemon、agent brain 或隐藏调度器。

## MetaLoop 不管什么

- 不替代 Codex agent 的项目理解、搜索、编码、调试和实验设计能力。
- 不提供独立聊天界面。
- 不维护旧式多 agent 执行流水线。
- 不启动后台 daemon、watcher、自动 agent pool 或隐藏调度器。
- 不把领域规则塞进 core；具体领域通过 ExtensionSpec / VerificationSpec 表达证据类型、指标门槛、风险规则和 validators。
- 不把自然语言的“完成了”当成 verified completion。

## 开发和验证

本仓库现在只需要 Python 测试依赖：

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

关键检查：

```bash
python3 tools/check_core_import_boundary.py
.venv/bin/pytest -q
git diff --check
```

## 重要文档

- [STATE.md](STATE.md)：当前项目状态。
- [HANDOFF.md](HANDOFF.md)：给下一位 Codex/session 的接手说明。
- [ROADMAP.md](ROADMAP.md)：后续路线。
- [docs/metaloop_lightweight_protocol_reframing.md](docs/metaloop_lightweight_protocol_reframing.md)：轻量协议层与 skill 边界。
- [docs/metaloop_six_gate_model.md](docs/metaloop_six_gate_model.md)：MetaLoop 六个关键控制点和 safe-point 纪律。
- [docs/metaloop_dynamic_extension_protocol_upgrade.md](docs/metaloop_dynamic_extension_protocol_upgrade.md)：ExtensionSpec / VerificationSpec 扩展协议。
- [docs/metaloop_multi_thread_agent_protocol.md](docs/metaloop_multi_thread_agent_protocol.md)：多 thread agent 协作协议。
- [docs/metaloop_adaptive_goal_loop.md](docs/metaloop_adaptive_goal_loop.md)：通用目标逼近闭环。
- [docs/metaloop_context_checkpoints.md](docs/metaloop_context_checkpoints.md)：长任务上下文压缩和接手恢复摘要。
- [docs/metaloop_design_autonomy.md](docs/metaloop_design_autonomy.md)：如何让 `$metaloop` 自动完成设计、分类任务形态并降低用户心智负担。
- [docs/metaloop_routable_work_units.md](docs/metaloop_routable_work_units.md)：面向多节点路由的 job envelope / blackboard / router 骨架。
- [docs/metaloop_observability_control.md](docs/metaloop_observability_control.md)：只读可观测和显式控制文件协议。
- [docs/metaloop_engineering_cybernetics_principles.md](docs/metaloop_engineering_cybernetics_principles.md)：工程控制论原则。
- [docs/metaloop_prompt_first_code_backed.md](docs/metaloop_prompt_first_code_backed.md)：Prompt-first / code-backed 产品纪律。
