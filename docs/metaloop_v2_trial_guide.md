# MetaLoop V2 Trial Guide

Date: 2026-07-20

## In Codex

正常使用只需说：

```text
Use $metaloop. 我想完成 <目标>。
```

Skill 应自动选择或创建 Task、锁定合同、维护 Attempt 与 RecoveryView。下面的
命令用于调试协议或手工检查，不要求普通用户记忆。

## Initialize

```bash
KERNEL="${CODEX_HOME:-$HOME/.codex}/skills/metaloop/scripts/metaloop_kernel.py"
python3 "$KERNEL" --workspace . project init
python3 "$KERNEL" --workspace . project status
```

旧 workspace 可执行：

```bash
python3 "$KERNEL" --workspace . project migrate-legacy
```

迁移不会删除 v1 文件，但会先验证 Capsule 与 ExecutionReport 内容，并重新运行
锁定 validators；只有 fresh result 仍是 `completed_verified` 且旧 VerificationResult
精确绑定时才授予 authority。其他记录成为 `legacy_unbound`。导入是单事务，失败后
可直接重试。

`.metaloop/metaloop.db` 存在后，v1 的 design/run/verify/review/context/adaptive/
thread-registry/routing 写命令会 fail closed。不要同时维护 root JSON 和 v2 Task；
`event append --task <task_id>` 会自动写入 canonical DecisionEvent。

## Task And Contract

```bash
python3 "$KERNEL" --workspace . task create --title "Implement feature A"
python3 "$KERNEL" --workspace . task list
python3 "$KERNEL" --workspace . task show --task <task_id>
```

Contract JSON 至少包含：

```json
{
  "goal": "Produce the requested outcome.",
  "constraints": [],
  "non_goals": ["Do not weaken verification."],
  "acceptance_criteria": ["Locked validators pass."],
  "verification_spec": {
    "validators": [
      {"type": "command", "mode": "executable", "severity": "blocking", "command": "pytest -q"}
    ],
    "resource_gates": []
  }
}
```

锁定时使用 `task show` 返回的当前 `state_version`：

```bash
python3 "$KERNEL" --workspace . task contract \
  --task <task_id> --expected-version <n> --file contract.json
```

## Attempt

```bash
python3 "$KERNEL" --workspace . attempt start \
  --task <task_id> --expected-version <n> \
  --plan "Implement the smallest verified slice." \
  --input-json '{"git_head":"<revision>"}'

python3 "$KERNEL" --workspace . attempt record \
  --attempt <attempt_id> --type checkpoint \
  --payload-json '{"completed":["schema"],"next":"CLI"}'

python3 "$KERNEL" --workspace . attempt evidence \
  --attempt <attempt_id> --path <artifact>

python3 "$KERNEL" --workspace . attempt seal \
  --attempt <attempt_id> --expected-version <n>
```

完全相同的 contract、plan 和 input snapshot 会触发 duplicate guard。确需重跑时：

```bash
python3 "$KERNEL" --workspace . attempt start ... \
  --retry-reason "The transient dependency failure is resolved."
```

## Evaluation And Acceptance

```bash
python3 "$KERNEL" --workspace . evaluate verify --attempt <attempt_id>
```

如果返回 `review_required`：

```bash
python3 "$KERNEL" --workspace . evaluate review \
  --evaluation <evaluation_id> --decision approved \
  --reviewer <independent_reviewer>
```

使用最终 terminal Evaluation 完成 Task：

```bash
python3 "$KERNEL" --workspace . evaluate accept \
  --task <task_id> --evaluation <terminal_evaluation_id> \
  --expected-version <n>
```

## Recovery And Switching

```bash
python3 "$KERNEL" --workspace . recover show --task <task_id>
python3 "$KERNEL" --workspace . recover write --task <task_id> --from-file resume.md
python3 "$KERNEL" --workspace . task assign --thread <thread_id> --task <task_id>
python3 "$KERNEL" --workspace . task return --thread <thread_id>
python3 "$KERNEL" --workspace . task assignments
python3 "$KERNEL" --workspace . event list --task <task_id> --limit 20
```

开始昂贵工作前，Recovery 状态应为 `fresh`。`stale` 表示 Task head、dependency
head、open Attempt cursor、Evaluation 或 DecisionEvent 在上次 resume projection
后发生了变化。即使 fresh，bundle 仍包含有界 current Project/Task decisions；它们
不会因刷新 watermark 而消失。完整历史使用 `event list/show`，不塞进恢复上下文。

## Branch Repair

```bash
python3 "$KERNEL" --workspace . task create \
  --title "Repair discovered defect" --parent-task <parent_task_id> \
  --spawned-by-event <origin_event_id>

python3 "$KERNEL" --workspace . task depend \
  --task <parent_task_id> --on <repair_task_id> --expected-version <n>
```

Repair Task 完成后只解除 parent dependency。Parent 仍需自己的 Attempt 和
Evaluation 才能完成。

误加 dependency 可在 parent open 且 idle 时移除：

```bash
python3 "$KERNEL" --workspace . task undepend \
  --task <parent_task_id> --on <dependency_task_id> --expected-version <n>
```

## Inspect

```bash
python3 "$KERNEL" --workspace . status --json
python3 "$KERNEL" --workspace . observe --format brief --json
python3 "$KERNEL" --workspace . project integrity
python3 "$KERNEL" --workspace . project export
```

`ready_to_accept` 表示已有当前 Contract/latest Attempt 的有效 terminal Evaluation；
下一步是 `evaluate accept`，不是再启动一个 Attempt。`project integrity` 除 SQLite/
reference chain 外，还会检查 default Task 的当前 workspace evidence 是否仍与记录哈希一致。

重点反馈应记录：恢复缺失、重复工作误判、Task 切换摩擦、Attempt 划分不稳定、
并发冲突和 DecisionEvent 信息密度。
