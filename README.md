# MetaLoop

MetaLoop 是 Codex 的轻量开发治理协议。它帮助 Codex 在具体项目中完成深度设计、
渐进推进、证据验证和反馈恢复，让复杂工作既保留智能弹性，又能稳定地形成项目事实。

```text
用户愿景与目标
  -> Codex 理解项目并形成可检验设计
  -> 选择最小端到端切片并执行
  -> MetaLoop 锁定目标、边界和验证方式
  -> 证据与独立验证决定当前结果
  -> complete | continue | repair | redesign | pivot | stop | escalate
  -> 有效认知沉淀回项目文档和下一轮计划
```

MetaLoop 采用 **Prompt-first / code-backed** 的分工：Skill 提供思考原则和工作纪律，
Codex 负责场景化理解与创造，项目文档保存架构认知，portable kernel、validators 和
`.metaloop/` artifacts 保存可锁定、可验证、可恢复的事实。

## 核心体验

### 深度设计

Codex 在执行前厘清目标、约束、验收、风险和停止条件。对于架构与长期任务，它会把
用户愿景扩展成连贯的目标模型，主动发现遗漏维度、关键选择和长期不变量。

### 渐进推进

完整的远期设计与有限的当前实现可以同时成立。Codex 选择最小端到端切片验证当前
假设，明确模块责任与接口，记录有意让步及其重访证据，再根据验证结果决定下一步。

### 证据验证

Mission Capsule 和 VerificationSpec 在执行前锁定当前任务及其完成标准。执行结果形成
ExecutionReport，确定性 validators 和独立 reviewer 基于证据形成 VerificationResult；
验收强度与结论强度保持一致。

### 反馈恢复

失败或部分进展进入 `Observe -> Evaluate -> Diagnose -> Decide -> Next Plan`。Event log、
adaptive loop 和 context checkpoints 保存关键认知，使长任务和新 session 能从明确的
safe point 继续。

## 快速使用

将 `skills/metaloop/` 安装到 `${CODEX_HOME:-$HOME/.codex}/skills/metaloop`。完整安装与
smoke test 见 [安装指南](docs/codex_install_metaloop_skill.md)。

然后在任意项目中告诉 Codex：

```text
Use $metaloop. 我想完成 <你的目标>。
```

Codex 会检查项目上下文、选择最小充分的治理方式、提出必要问题、锁定验证并推进任务。
用户只需要表达目标、原则、关键约束以及需要保留给自己的决策权限。

## 工作模型

MetaLoop 通过六个轻量控制点组织工作：

1. `Design Gate`：形成目标、边界、证据和停止条件；
2. `State Checkpoint`：保存重要观察、决策和恢复上下文；
3. `Verification Gate`：由锁定验证和证据决定完成状态；
4. `Adaptive Loop`：根据失败或部分结果形成下一轮计划；
5. `Control Point`：在 safe point 消费显式控制意图；
6. `Observation Surface`：以只读摘要呈现状态、阻塞和下一步。

大多数任务只需要一个本地 Mission Capsule。责任隔离、跨 workspace 交接或长期上下文
隔离确有价值时，Codex 可以使用 persistent threads 或 routable work units。所有形态共享
同一套 `.metaloop/` 任务事实和验证边界。

## 职责分工

| 层次 | 职责 |
| --- | --- |
| 用户 | 提供愿景、优先级、约束和关键判断。 |
| Codex + Skill | 理解场景、设计方案、选择工作形态、执行、诊断和推进。 |
| 项目文档 | 保存具体架构、模块契约、迁移计划和领域认知。 |
| `.metaloop/` | 保存锁定任务、执行证据、验证结果、反馈和恢复状态。 |
| `metaloop_core` / portable kernel | 处理 refs、hashes、schema、状态一致性和确定性验证。 |
| ExtensionSpec / VerificationSpec | 为具体场景定义证据语言和验收方式。 |
| hooks / sandbox / wrapper | 在需要时提供不可绕过的外层约束。 |

这一分工让 MetaLoop 保持轻量：场景智能留在 Codex，具体设计留在项目，只有反复需要且
具有确定性消费者的事实才进入协议代码。

## 当前实现

仓库由四个主要部分组成：

```text
skills/metaloop/      可直接部署的自包含 Codex Skill
src/metaloop_core/    可复用的状态、验证和反馈协议库
tests/                skill package、core、parity 与边界测试
docs/                 产品原则、协议和工程治理文档
```

当前已经交付 Mission Capsule、VerificationSpec、ExecutionReport、VerificationResult、
独立 ReviewResult、Adaptive Goal Loop、context checkpoints、thread registry、event log、
工程治理 refs/hashes、可选的 routable handoff、只读观测、显式控制和 one-shot activation。

## 开发验证

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
python3 tools/check_core_import_boundary.py
.venv/bin/pytest -q
git diff --check
```

## 文档导航

从这里开始：

- [当前状态](STATE.md)
- [路线图](ROADMAP.md)
- [接手说明](HANDOFF.md)
- [Design Autonomy 与 Progressive Design](docs/metaloop_design_autonomy.md)
- [Six-Gate Model](docs/metaloop_six_gate_model.md)
- [Prompt-first / code-backed](docs/metaloop_prompt_first_code_backed.md)

按需深入：

- [Lightweight Protocol](docs/metaloop_lightweight_protocol_reframing.md)
- [Adaptive Goal Loop](docs/metaloop_adaptive_goal_loop.md)
- [Context Checkpoints](docs/metaloop_context_checkpoints.md)
- [Multi-thread Protocol](docs/metaloop_multi_thread_agent_protocol.md)
- [Routable Work Units](docs/metaloop_routable_work_units.md)
- [Observability and Control](docs/metaloop_observability_control.md)
- [Dynamic Extension Protocol](docs/metaloop_dynamic_extension_protocol_upgrade.md)
- [Engineering Governance](docs/metaloop_engineering_governance_vnext.md)
- [Engineering Governance Module Contract](docs/metaloop_engineering_governance_module_contract.md)
