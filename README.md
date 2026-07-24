# MetaLoop v3.4

MetaLoop v3.4 是 Codex 的极小、正交、事件触发外环控制系统。它把长期
开发中不能依赖聊天上下文的事实写成可验证状态，同时让 Git 负责机械
workspace-change truth。实现阶段优先使用项目自己的开发循环；只有最终高风险主张才
按需增加 fresh-context structured Review：

```text
Codex / Skill -> Frame -> Work -> Reconcile -> Adapt -> Prove
Git worktree  -> repository identity + WorkspaceStamp + changed paths
SQLite        -> Project -> Task -> ContractRevision -> Attempt -> Evidence -> Evaluation
              -> DecisionEvent + RecoveryView
```

核心分工是 **Prompt handles intelligence. Git and code handle mechanical truth. SQLite
handles protocol truth.** MetaLoop 不是项目管理器、agent runtime、scheduler、daemon、
watcher、transcript store、vector memory 或 agent pool。

MetaLoop 默认信任 Agent 是合作的。它处理上下文压缩、遗漏、局部视野、自我误判和
相关性盲点，不构建针对 Agent 的零信任安全边界。仓库级架构宪章见
[AGENTS.md](AGENTS.md)。

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

Skill 会进行有界检查，选择最低充分 assurance，锁定一个 ContractRevision，维护一个
可恢复 Attempt，自动 reconcile 当前 Attempt 的 Git changed paths，并只通过精确 Evaluation chain 接受
完成。用户不需要记住内部 record 名称。

普通局部修改、文档同步、测试修复和可逆小改动默认直接使用 Git + 项目测试，不创建
MetaLoop Task。只有需要跨上下文恢复、任务切换、managed Evidence、正式封存或真实语义
Review 时才启用 MetaLoop。

## 最终模型

```text
Project / Workspace
  Task graph
    ContractRevision[]   immutable
    Attempt[]             one strategy, baseline WorkspaceStamp
      Checkpoint[]        append-only semantic progress + current stamp
      Evidence[]          exact file hashes
    DecisionEvent[]
    Evaluation[]          one active head: verification -> Review overlays
  RecoveryView            live-derived, fresh whenever aligned
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

只有 `aligned` 才能 seal、verify、review 或 accept；active Attempt 的 `ahead` 只能继续工作
或进入 `finish` reconcile。直接
Git commit 若满足父提交、materialized tree、HEAD tree、index 和 clean worktree 的精确
等价证明，视为 content-preserving promotion，保持 aligned；额外内容、reset、amend、
branch switch 或 dirty post-commit 仍然 conflicted。`.git/` 和 `.metaloop/` 排除在
generic scan 外；managed outputs 和 Evidence 始终单独重检。

观察输出将完整性拆成 `valid`、`not_yet_reconciled` 和 `violated`。active Attempt 中正常的
`ahead` 表示尚待 `finish` 收口，不是协议损坏；`conflicted/unknown`、identity/hash、Evidence
或 stable input 漂移才是 violation。兼容字段 `integrity` boolean 继续保留。

WorkspaceStamp 的临时 tree 使用仓库外 index 和 object directory 计算，原 object store
只作为 alternate，并设置 `GIT_OPTIONAL_LOCKS=0`；status/recovery 不会刷新真实 index 或
写入真实 objects。

后续 Tier 0 Git 修改不会让默认 Project status 把历史 completed Task 误报为协议损坏；需要
对旧封存结果与当前文件做精确复核时，显式运行 `project integrity --task <task_id>`。

### Progressive Design 与 Reconcile

架构和长周期任务先建立完整目标模型，分离 durable invariants 与当前 scope，选择最小
端到端 walking skeleton，明确模块 ownership 和接口，记录有意让步，再由证据选择下一
个 slice。一行修复不触发不必要的设计仪式。

正常 `attempt finish` 把 baseline 后的 changed paths 归入当前 Attempt；Agent 只需显式声明
真正的 `defer`、`assign` 或 `conflict`。调用同一 Task 的新 Attempt 是对 carried-forward
workspace 归属的确认，内核保存来源 hashes 和逐路径 provenance。

## Primary Commands

```bash
KERNEL=skills/metaloop/scripts/metaloop_kernel.py
# One-time setup for a repository without a v3 Project.
python3 "$KERNEL" --workspace . project init

# Routine path: two lifecycle writes.
python3 "$KERNEL" --workspace . task begin --title "<task>" --plan "<plan>" --check "<project verifier>"
python3 "$KERNEL" --workspace . attempt finish --attempt <attempt_id>
```

Use `observe --format brief` or `recover show` only when resuming, switching
Tasks, or resolving uncertainty. Use `project integrity` for high-assurance
closure or suspected corruption, not as a routine heartbeat.

Tier 1 的最小 Contract 由 title、plan 和可重复的 `--check` 自动生成；Tier 2/3 才使用
`--contract contract.json` 声明 managed sealing、显式 authority 或更强 policy。
空白 `--check` 会在创建 Task 前失败；完全省略 check 表示只记录 Agent 的 durable
completion，不构成技术验证。生成式 Contract 不猜测 change kind。

`task begin` 在一次事务中组合 create/contract/select/start，输入校验失败不会遗留空 Task。
`attempt finish` 自动 reconcile、绑定 managed Evidence、checkpoint、seal、verify，并只在
没有 pending authority 时 accept；重复执行会从已有 checkpoint、sealed Attempt 或
Evaluation 继续，不制造重复记录。

最新 aborted、rejected 或被 stale workspace supersede 的同 Task Attempt 会自动成为下一
Attempt 的 carried-forward source。Agent 不需要反向还原补丁、逐文件登记 inherited path，
或为了协议重新应用工作。继承集合覆盖 source baseline、最新 checkpoint 和当前 workspace；
任何不符合新 Contract scope 的路径都会在新 Attempt 创建前被拒绝。

Assurance 使用 Tier 0-3：Tier 0 零 kernel 调用，Tier 1 保持两次 Agent-facing lifecycle
command，Tier 2
增加机械可判定的治理证据，Tier 3 对不完整 semantic oracle 增加结构化 Review。
新 Contract v1.1 记录 assurance；旧 v3 Contract v1.0 保持兼容。Tier 3 report、context、
Contract、Attempt、Evidence 和 parent Evaluation 被绑定在同一 Review content hash 中。
Tier 3 trigger 只能由 approved structured reviewer report 的
`resolved_trigger_ids` 逐项解除；普通 validator 只提供机械证据，不自动改变风险记忆。
CLI `--context-id` 只是可选诊断标签，宿主不需要提供身份证明。

当当前转换是 `review:reviewer` 时，`finish` 和 RecoveryView 自动派生最小
`review_handoff`：锁定 claim、trigger、validator 摘要、路径、Evidence、active chain 和空
report template。该 handoff 不持久化、不形成新 authority；reviewer 完成的结构化 Evaluation
仍是唯一 Review 事实。普通恢复默认查看 current `active_chain`，旧分支只在显式诊断时展开。

Assurance 约束最终 completion claim，而不是实现权限。架构、跨模块、schema、测试修复、
文档同步和普通性能工程不会仅因工作类型自动触发 reviewer；安全/隐私/泄漏、不可逆生产
影响、不完整 oracle 下的因果或合同语义，以及正式实验/论文/benchmark 主张才进入 Tier 3。

项目 verifier 和测试负责技术正确性，MetaLoop 只记录完成证明、恢复状态和必要 Review，
不在 SQLite 中复制项目 schema 或领域语义。

Evaluation head 的下一步是 typed `next_transition`：`verify`、`review:reviewer`、
`review:user`、`accept` 或 `start_repair_attempt`。authority 固定为 mechanical
verification -> reviewer -> reserved user；坏链保留为历史并由同一 Task 的新 Attempt
恢复。

测试失败、reviewer 修改、Contract 修订、文档同步和 exact Git commit 本身都不会创建
新 Task。只有独立 ownership、acceptance 或 stopping condition 才需要子 Task。

brief status 和 finish 结果提供派生的 `protocol_activity` 与 `routing_warning`。Tier 1 默认预算
为 `begin + finish` 两个 Agent-facing lifecycle command；不为了测量 MetaLoop 而增加状态写入。

外部长训练或进程可以在 checkpoint/finish 上选择性传入 `--external-ref` 和
`--external-checkpoint-identity`。它们只帮助恢复定位；epoch、liveness、metrics 和 completion
始终由外部系统自己的 manifest/log 负责，MetaLoop 不监控或调度运行。

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

v3 基础架构见 [docs/metaloop_final_architecture_upgrade_spec.md](docs/metaloop_final_architecture_upgrade_spec.md)，
v3.2 可靠性升级见 [docs/metaloop_v3_2_reliability_upgrade_spec.md](docs/metaloop_v3_2_reliability_upgrade_spec.md)，
试用流程见 [docs/metaloop_v3_trial_guide.md](docs/metaloop_v3_trial_guide.md)。
