# MetaLoop

MetaLoop 是 Codex 的轻量开发治理协议，也是一个 **Skill-only、SQLite-backed 的
durable work protocol**。它帮助 Codex 在具体项目中完成深度设计、渐进推进、证据验证
和反馈恢复，并把长期任务中不能依赖聊天上下文的事实写成可验证状态。

```text
用户愿景与目标
  -> Codex 深度理解项目并形成可检验设计
  -> Progressive Design 选择最小端到端切片
  -> MetaLoop 锁定 Task 合同、执行 Attempt 和证据
  -> Evaluation / Review 决定 complete | repair | redesign | continue
  -> RecoveryView 支持上下文压缩、任务切换和新 session 恢复
```

核心原则是 **Prompt-first / code-backed**，即 **Prompt handles intelligence.
Code handles truth.** Skill 提供思考原则和工作纪律，Codex 负责场景化理解与创造，
项目文档保存架构认知，portable kernel、validators 和 SQLite 保存可锁定、可验证、
可恢复的协议事实。

MetaLoop 不做 agent runtime、scheduler、聊天 transcript 存储、向量 memory、agent pool
或项目管理器。

## 运行前提与依赖

MetaLoop Skill 是 self-contained 的，不需要 `pip install metaloop`，也没有第三方
Python 运行依赖。目标环境只需要：

- 支持 Skill 的 Codex；
- Python `3.12+`，并包含标准库 `sqlite3`；
- 对目标项目中 `.metaloop/` 目录的读写权限。

MetaLoop 本身不依赖 PyYAML、pytest、Node.js、Docker、独立数据库服务、daemon 或
vector database。Git 和网络只在从远端安装或更新 Skill 时需要，日常运行不需要。

ContractRevision 中配置的 validator 可能调用项目自己的命令，例如 `npm test`、
`cargo test` 或特定评测器；这些属于被治理项目的依赖，不是 MetaLoop 的运行依赖。

## 核心体验

### 深度设计

执行前厘清目标、非目标、约束、验收、风险、证据和停止条件。对于架构与长期任务，
Codex 会主动发现遗漏维度、关键选择和长期不变量。

### 渐进推进

完整远期设计与有限当前实现可以同时成立。Progressive Design 选择最小端到端切片验证
当前假设，明确模块责任与接口，并根据验证结果决定继续、修复、重设计或停止。

### 证据验证

新任务使用不可变 ContractRevision 锁定成功标准。执行形成 Attempt 和哈希绑定的
evidence，Evaluation 只接受精确 sealed Attempt；需要人工判断时，Review 也绑定该
Evaluation，而不是笼统批准当前 workspace。

### 反馈恢复

失败或部分进展进入 `Observe -> Evaluate -> Diagnose -> Decide -> Next Plan`。Task、
DecisionEvent、Attempt checkpoint 和 RecoveryView 保存关键认知，使超长任务、任务切换
和新 session 能从明确 safe point 继续。

## 快速使用

将 `skills/metaloop/` 安装到 `${CODEX_HOME:-$HOME/.codex}/skills/metaloop`。完整安装与
smoke test 见 [安装指南](docs/codex_install_metaloop_skill.md)。

然后在任意项目中告诉 Codex：

```text
Use $metaloop. 我想完成 <你的目标>。
```

用户无需学习内部 artifact。Skill 会选择或创建 Task、锁定 ContractRevision、维护一个
可恢复的 open Attempt、记录证据与关键决策，并在上下文压缩后通过 RecoveryView 恢复。

本地试用流程见 [V2 试用指南](docs/metaloop_v2_trial_guide.md)。

## V2 真相模型

```text
Project
  Task
    ContractRevision[]       immutable
    Attempt[]                open -> sealed | aborted
      Action/Evidence[]      append-only
      Evaluation[]           content-bound
    DecisionEvent[]          task/project scoped
    RecoveryView             derived, fresh | stale | incomplete
```

- Task mutation 使用 `expected_state_version` compare-and-swap。
- 一个 Task 最多一个 open Attempt。
- 精确重复 Attempt 默认拒绝，除非记录具体 `retry_reason`。
- Review 绑定一个 Evaluation hash，最终解析到一个 sealed Attempt hash。
- Task 只有一个线性 acceptance chain；全部 blocking authority 通过后才能完成。
- Attempt evidence 在 seal、verify、review 和 accept 前重新校验。
- RecoveryView 绑定 dependency heads，并携带当前 Project/Task decisions 与 acceptance
  chain；delta events 不是长期记忆的替代品。
- 子 Task 只会解除依赖或提供证据，不会自动完成父 Task。

## 设计与工程治理

MetaLoop 通过六个轻量控制点组织工作：

1. `Design Gate`：形成目标、边界、证据和停止条件；
2. `State Checkpoint`：保存重要观察、决策、Attempt checkpoint 和恢复上下文；
3. `Verification Gate`：由锁定验证和精确证据决定完成状态；
4. `Adaptive Loop`：根据失败或部分结果形成下一轮计划；
5. `Control Point`：在 safe point 消费显式控制意图；
6. `Observation Surface`：以只读摘要呈现状态、阻塞和下一步。

对于 architecture、public-contract、migration 或 cross-module 任务，V2
ContractRevision 可以选择性锁定 governance：显式 `change_kind`、不允许漂移的
`stable_inputs`、必须作为 Attempt evidence 交付的 `managed_outputs`、声明性
`allowed_paths`，以及 redesign 必需的 migration plan。治理字段不是第二套状态，也不把
项目架构复制进 MetaLoop core。

## 职责分工

| 层次 | 职责 |
| --- | --- |
| 用户 | 提供愿景、优先级、约束和保留给自己的关键判断。 |
| Codex + Skill | 理解场景、设计、选择协议形态、执行、诊断和推进。 |
| 项目文档 | 保存具体架构、模块契约、迁移计划和领域认知。 |
| `.metaloop/` | 保存锁定任务、执行证据、验证结果、决策和恢复状态。 |
| `metaloop_core` | 处理 refs、hashes、schema、事务、状态一致性和确定性验证。 |
| hooks / sandbox / wrapper | 在需要时提供不可绕过的外层约束。 |

## 存储、兼容与发布

`.metaloop/metaloop.db` 是 v2 canonical operational state。SQLite 负责事务、外键、事件
序列、唯一约束和并发写入；大型 evidence 留在文件系统，数据库保存路径、hash 和来源。

`src/metaloop_core/` 是唯一源实现。`tools/sync_skill_core.py` 将它生成到
`skills/metaloop/lib/metaloop_core/`；portable kernel 只是薄启动器。
`tools/check_skill_core_sync.py` 防止安装包漂移。

旧的 Mission Capsule、ExecutionReport、VerificationResult、context、adaptive 和 routing
文件在 v2 初始化前继续兼容，也可作为 `project migrate-legacy` 的只读输入。一旦 v2
数据库存在，旧写命令 fail closed，避免制造第二份真相。

## 关键命令

```bash
KERNEL=skills/metaloop/scripts/metaloop_kernel.py
python3 "$KERNEL" --workspace . project init
python3 "$KERNEL" --workspace . project status
python3 "$KERNEL" --workspace . task list
python3 "$KERNEL" --workspace . task contract --help
python3 "$KERNEL" --workspace . recover show --task <task_id>
python3 "$KERNEL" --workspace . project integrity
python3 "$KERNEL" --workspace . project export
```

完整 Task/Attempt/Evaluation 命令见试用指南和 `--help`。

## 仓库结构

```text
src/metaloop_core/       canonical protocol implementation
skills/metaloop/         self-contained installed Skill and generated core
tests/                   v1 regression, v2 invariants, parity and portability
tools/                   import-boundary and generated-core checks
docs/                    architecture, governance, operation and trial guidance
```

## 开发验证

```bash
python3 tools/sync_skill_core.py
python3 tools/check_skill_core_sync.py
python3 tools/check_core_import_boundary.py
.venv/bin/pytest -q
git diff --check
```

## 文档导航

- [当前状态](STATE.md)
- [路线图](ROADMAP.md)
- [接手说明](HANDOFF.md)
- [V2 架构评审](docs/metaloop_task_history_architecture_review.md)
- [V2 试用指南](docs/metaloop_v2_trial_guide.md)
- [Design Autonomy 与 Progressive Design](docs/metaloop_design_autonomy.md)
- [Six-Gate Model](docs/metaloop_six_gate_model.md)
- [Prompt-first / code-backed](docs/metaloop_prompt_first_code_backed.md)
- [Engineering Governance](docs/metaloop_engineering_governance_vnext.md)
- [Engineering Governance Module Contract](docs/metaloop_engineering_governance_module_contract.md)
- [Adaptive Goal Loop](docs/metaloop_adaptive_goal_loop.md)
- [Context Checkpoints](docs/metaloop_context_checkpoints.md)
- [Multi-thread Protocol](docs/metaloop_multi_thread_agent_protocol.md)
- [Routable Work Units](docs/metaloop_routable_work_units.md)
- [Observability and Control](docs/metaloop_observability_control.md)
