# MetaLoop v3

MetaLoop v3 是 Codex 的轻量 Git-backed durable work protocol。它把长期开发中不能依赖
聊天上下文的事实写成可验证状态，同时让 Git 负责机械 workspace-change truth：

```text
Codex / Skill -> Frame -> Work -> Reconcile -> Adapt -> Prove
Git worktree  -> repository identity + WorkspaceStamp + changed paths
SQLite        -> Project -> Task -> ContractRevision -> Attempt -> Evidence -> Evaluation
              -> DecisionEvent + RecoveryView
```

核心分工是 **Prompt handles intelligence. Git and code handle mechanical truth. SQLite
handles protocol truth.** MetaLoop 不是项目管理器、agent runtime、scheduler、daemon、
watcher、transcript store、vector memory 或 agent pool。

## 运行前提

- 支持 Skill 的 Codex；
- Python `3.12+` 标准库与 `sqlite3`；
- 目标项目必须位于本地 Git repository/worktree；
- 不需要 GitHub、SSH、remote repository 或 clean worktree。

MetaLoop 本身无第三方 Python runtime 依赖。Contract validator 可以调用项目自己的
测试或评测命令，那些依赖属于被治理项目。

## 使用

```text
Use $metaloop. 我想完成 <你的目标>。
```

Skill 会进行有界检查，形成比例合适的 Progressive Design，锁定一个 ContractRevision，
维护一个可恢复 Attempt，显式 reconcile Git changed paths，并只通过精确 Evaluation chain
接受完成。用户不需要记住内部 record 名称。

## 最终模型

```text
Project / Workspace
  Task graph
    ContractRevision[]   immutable
    Attempt[]             one strategy, baseline WorkspaceStamp
      Checkpoint[]        append-only semantic progress + current stamp
      Evidence[]          exact file hashes
    DecisionEvent[]
    Evaluation[]          verification -> linear Review overlays
  RecoveryView            derived, fresh only when aligned
```

SQLite 是唯一 mutable protocol-state authority；Git 是 workspace-change authority；项目
文档是 architecture-content authority。没有一层可以代替另一层的判断。

### WorkspaceStamp

每个 Project 绑定 repository root、worktree path 和 adapter version。每个 Attempt 绑定
baseline stamp；每个 checkpoint 记录 code-computed current stamp。对比状态严格为：

- `aligned`：当前 Git state 等于最新 checkpoint；
- `ahead`：项目在 checkpoint 后发生变化；
- `conflicted`：worktree identity、HEAD、merge state 或 attribution 不安全；
- `unknown`：Git 或有界扫描失败。

只有 `aligned` 才能 seal、verify、review、accept 或通过 selected Task integrity。`.git/`
和 `.metaloop/` 排除在 generic scan 外；managed outputs 和 Evidence 始终单独重检。

### Progressive Design 与 Reconcile

架构和长周期任务先建立完整目标模型，分离 durable invariants 与当前 scope，选择最小
端到端 walking skeleton，明确模块 ownership 和接口，记录有意让步，再由证据选择下一
个 slice。一行修复不触发不必要的设计仪式。

当 Recovery 显示 `ahead`，Agent 必须把每个 changed path 明确标成 `claim`、`defer`、
`assign` 或 `conflict`。MetaLoop 不从文件名、路径或自然语言猜 Task ownership。

## Canonical Commands

```bash
KERNEL=skills/metaloop/scripts/metaloop_kernel.py
python3 "$KERNEL" --workspace . project init
python3 "$KERNEL" --workspace . project status
python3 "$KERNEL" --workspace . task create --title "<task>"
python3 "$KERNEL" --workspace . task contract --task <task_id> --expected-version <n> --file contract.json
python3 "$KERNEL" --workspace . recover show --task <task_id>
python3 "$KERNEL" --workspace . recover write --task <task_id> --from-file resume.md
python3 "$KERNEL" --workspace . attempt start --task <task_id> --expected-version <n> --plan "<plan>"
python3 "$KERNEL" --workspace . attempt record-checkpoint --attempt <attempt_id> --expected-version <n> --claimed-path src/feature.py
python3 "$KERNEL" --workspace . attempt evidence --attempt <attempt_id> --path src/feature.py
python3 "$KERNEL" --workspace . attempt seal --attempt <attempt_id> --expected-version <n>
python3 "$KERNEL" --workspace . evaluate verify --attempt <attempt_id>
python3 "$KERNEL" --workspace . evaluate accept --task <task_id> --evaluation <evaluation_id> --expected-version <n>
python3 "$KERNEL" --workspace . project integrity
```

完整参数见 kernel `--help`。`task assign/return` 只维护线程导航，不调度 Agent。

## Guarantee Boundary

Optional host hooks may call `metaloop_core.host.safe_point` synchronously at turn boundaries,
before compaction, handoff, seal, verify, and accept. It never starts workers or runs a daemon.

```text
No unacknowledged WorkspaceStamp may pass acceptance.
```

Skill 无法控制绕过所有 protocol entry 的 Agent；这种 divergence 会在下一次 explicit command
或 safe point 被发现并 fail closed。

## Repository Layout

```text
src/metaloop_core/       canonical v3 implementation
skills/metaloop/         self-contained Skill and generated core
tests/                   workspace, lifecycle, CLI, distribution and surface tests
tools/                   source/vendor and v3 surface checks
docs/                    final architecture and trial guidance
```

## Verification

```bash
python3 tools/sync_skill_core.py
python3 tools/check_skill_core_sync.py
python3 tools/check_core_import_boundary.py
python3 tools/check_v3_surface.py
pytest -q
git diff --check
```

架构实现规范见 [docs/metaloop_final_architecture_upgrade_spec.md](docs/metaloop_final_architecture_upgrade_spec.md)，
试用流程见 [docs/metaloop_v3_trial_guide.md](docs/metaloop_v3_trial_guide.md)。
