# MetaLoop 当前状态

最后更新：2026-05-09

## 一句话状态

MetaLoop 已收敛为 **Skill-only / skill-only** 产品：团队通过 Codex `$metaloop` skill 使用它；仓库只保留自包含 skill package、`metaloop_core` 协议库、当前文档和测试。旧的仓库级交互运行时、聊天界面、外部 agent 编排器、Node bridge、prompt pack 和相关测试已经移除。

当前主路径：

```text
Codex agent conversation
  -> $metaloop skill entry
  -> bundled kernel writes .metaloop artifacts
  -> Codex executes with project intelligence
  -> locked validators verify evidence
  -> repair / redesign / resume / complete decision
```

## 核心判断

- MetaLoop 的核心不是自己变成 agent runtime，而是稳定复杂任务的 design、verification、feedback 和 audit。
- Prompt-first / code-backed：prompt 和 skill 负责智能，代码和 `.metaloop/` artifacts 负责真相。
- Design 必须先于执行；Mission Capsule 和 VerificationSpec 是执行合同。
- Agent 可以设计验证方案，但不能在执行后临时改验证来迁就结果。
- Domain extension 提供领域验证语言，MetaLoop Core 不塞满领域规则。
- 多个 Codex thread 可以围绕同一目标协作，但共享真相必须写入 `.metaloop/`，不能只靠聊天记忆。

## 保留的代码面

- `skills/metaloop/`：可一键部署的 Codex Skill，内含 portable kernel、generic extension、参考文档和 metadata。
- `src/metaloop_core/`：可复用协议库，提供 Mission Capsule I/O、ExecutionReport I/O、VerificationSpec 校验、generic validators、`verify_workspace()`、thread registry、event log、adaptive loop、ObservationReport / DiagnosisReport 和 repair/redesign vocabulary。
- `tools/check_core_import_boundary.py`：确保 core 不重新依赖已移除的外部产品面。
- `tests/`：只保留 core、skill package、core/skill parity 和 verification 测试。

## 已移除的产品面

- 仓库级交互命令入口。
- Rich / prompt-toolkit 交互界面。
- 旧 Python/Node 对话桥接实验代码。
- 旧 role pipeline、mission file runtime、storage/runtime/prompt pack 实现。
- 示例 mission、无关 VSCode extension、旧研究/backlog 文档和对应测试。

这次删除是产品决策，不是临时隐藏：用户只需要通过 skill 完成任务，Codex 本身负责自然对话和项目理解。

## 当前能力

- `skills/metaloop/scripts/metaloop_kernel.py` 支持 `status`、`design`、`run`、`verify`、`mark`、`threads`、`event`、`adaptive`。
- Mission Capsule 内锁定 ExtensionSpec 和 VerificationSpec，并记录 hash。
- bundled generic extension 支持 `file_exists`、`command`、`forbidden_path`、`json_metric_gate`、`json_field_exists`、`file_contains`、`artifact_hash`、`forbidden_claim`、`manual_acceptance`、`resource_gate`。
- 验证阶段会检查 capsule/report/spec schema、hash、manual blocker、unsupported blocker 和 hard validator 结果。
- `.metaloop/threads.json` 可记录 persistent Codex thread 的 role、thread_id、职责和 handoff 状态。
- `.metaloop/event_log.jsonl` 可记录长任务观察、决策、阻塞、handoff、验证、repair 和 redesign。
- `.metaloop/adaptive_loop.json` 支持通用目标逼近闭环：Goal -> Plan -> Act -> Observe -> Evaluate -> Diagnose -> Decide -> Next Plan。

## 当前测试目标

```bash
python3 tools/check_core_import_boundary.py
.venv/bin/pytest -q
git diff --check
```

当前成功标准：仓库安装不暴露用户命令入口，测试只覆盖 skill/core 产品面，文档不再引导团队使用旧交互面。

## 下一步

1. 继续打磨 `$metaloop` skill 的 design 指南，让 agent 对开放型任务提出更严格的 VerificationSpec。
2. 增加少量高质量 domain extension examples，但不要把领域规则写死进 core。
3. 加强 adaptive loop 的失败诊断和下一轮计划模板，保持 prompt-first，不急于代码化复杂策略。
4. 建立团队内测反馈机制：记录哪些任务需要更强 hooks、sandbox 或 wrapper runtime，再决定是否新增外层约束。

## 不要做

- 不要重建独立聊天界面。
- 不要恢复旧外部运行时或多 agent 编排器。
- 不要把 Codex 自述完成当作 verified completion。
- 不要把完整聊天史当 operational memory。
- 不要为每个有用推理模式新增 Python 模块。
- 不要在没有真实需求前添加重型 scheduler、agent pool 或领域专用框架。
