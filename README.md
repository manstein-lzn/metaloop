# MetaLoop

MetaLoop 是一个 **Skill-only、SQLite-backed 的 Codex durable work protocol**。
它不替代 Codex 的理解、编码、实验和诊断能力，而是把长期任务中不能依赖聊天
上下文的事实写成可验证状态：Task、锁定合同、执行 Attempt、Evaluation、关键
DecisionEvent 和 freshness-checked RecoveryView。

```text
Codex $metaloop skill
  -> thin scripts/metaloop_kernel.py
  -> vendored metaloop_core
  -> .metaloop/metaloop.db
  -> Project / Task / ContractRevision / Attempt / Evaluation / DecisionEvent
  -> rebuildable JSON/Markdown projections under .metaloop/v2/
```

核心原则：**Prompt-first / code-backed**，即 **Prompt handles intelligence.
Code handles truth.** MetaLoop 不做 agent runtime、scheduler、聊天记忆、
向量库或项目管理器。

## 使用

将 `skills/metaloop/` 安装到 `${CODEX_HOME:-$HOME/.codex}/skills/metaloop`，
然后在 Codex 中说：

```text
Use $metaloop. 我想完成 <目标>。
```

用户不需要理解内部协议。Skill 会选择或创建 Task、锁定 ContractRevision、
启动和 checkpoint Attempt、验证精确 evidence chain，并在上下文压缩或任务切换
后通过 RecoveryView 恢复。

本地试用流程见 [docs/metaloop_v2_trial_guide.md](docs/metaloop_v2_trial_guide.md)。

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
- 精确重复 Attempt 默认拒绝，除非记录 `retry_reason`。
- Review 绑定一个 Evaluation hash，最终解析到一个 sealed Attempt hash。
- Task 只有一个 `acceptance_head_ref`；完整链通过后才能完成。
- Attempt evidence 在 seal、verify 和 accept 前都会重新哈希；默认 Task 的
  workspace evidence 漂移也会让 `project integrity` 失败。
- RecoveryView 绑定 dependency heads，并始终携带有界的当前 Project/Task
  decisions 与已接受的 Evaluation chain。
- `default_task_id` 和 thread assignment 只用于导航，不是隐式写作用域。
- 子 Task 只会解除依赖或提供证据，不会自动完成父 Task。

## 存储与发布

`.metaloop/metaloop.db` 是 canonical operational state。SQLite 来自 Python
标准库，负责事务、外键、事件序列、唯一约束和并发写入。大型 evidence 保留在
文件系统，数据库保存路径、hash 和来源。

`src/metaloop_core/` 是唯一源实现。`tools/sync_skill_core.py` 将它生成到
`skills/metaloop/lib/metaloop_core/`；portable kernel 只是薄启动器。CI/本地检查
使用 `tools/check_skill_core_sync.py` 防止安装包漂移。

旧的 root-level Mission Capsule、ExecutionReport、VerificationResult、context、
adaptive 和 routing 文件只在 v2 初始化前作为 v1 状态使用，或作为
`project migrate-legacy` 的只读输入。一旦 `.metaloop/metaloop.db` 存在，旧写命令
会 fail closed，避免制造第二份真相。迁移只有在 v1 ExecutionReport 内容哈希有效、
VerificationResult 精确绑定且锁定 validators 重新执行仍通过时才授予 bound authority；
其余记录保持 `legacy_unbound`。显式 control intent 文件仍是外部控制输入，不是 Task 真相。

## 关键命令

```bash
KERNEL=skills/metaloop/scripts/metaloop_kernel.py
python3 "$KERNEL" --workspace . project init
python3 "$KERNEL" --workspace . project status
python3 "$KERNEL" --workspace . task list
python3 "$KERNEL" --workspace . recover show --task <task_id>
python3 "$KERNEL" --workspace . project integrity
python3 "$KERNEL" --workspace . project export
```

完整 Task/Attempt/Evaluation 命令见试用指南和 `--help`。

## 仓库结构

```text
src/metaloop_core/       canonical protocol implementation
skills/metaloop/         self-contained installed Skill and generated core
tests/                   v1 regression, v2 invariants, Skill portability
tools/                   import-boundary and generated-core checks
docs/                    architecture, operation, and trial guidance
```

## 验证

```bash
python3 tools/sync_skill_core.py
python3 tools/check_skill_core_sync.py
python3 tools/check_core_import_boundary.py
.venv/bin/pytest -q
git diff --check
```

架构依据见
[docs/metaloop_task_history_architecture_review.md](docs/metaloop_task_history_architecture_review.md)，
当前状态见 [STATE.md](STATE.md)，接手说明见 [HANDOFF.md](HANDOFF.md)。

其他协议边界：

- [docs/metaloop_six_gate_model.md](docs/metaloop_six_gate_model.md)
- [docs/metaloop_design_autonomy.md](docs/metaloop_design_autonomy.md)
- [docs/metaloop_multi_thread_agent_protocol.md](docs/metaloop_multi_thread_agent_protocol.md)
- [docs/metaloop_context_checkpoints.md](docs/metaloop_context_checkpoints.md)
- [docs/metaloop_observability_control.md](docs/metaloop_observability_control.md)
- [docs/metaloop_prompt_first_code_backed.md](docs/metaloop_prompt_first_code_backed.md)
- [docs/metaloop_routable_work_units.md](docs/metaloop_routable_work_units.md)
