# MetaLoop v3.2 认知可靠性升级规范

状态：已实施  
日期：2026-07-22

## 1. 核心思想

> MetaLoop 是一个极小、正交、事件触发的外环控制系统。它通过持久目标、当前状态、反馈纠正和按需独立观察，使强大但存在随机性、局部视野与自我误判的 Agent，在不确定环境中持续收敛到用户锁定的目标；用户只负责指挥意图、真实例外和保留的最终决策。

MetaLoop 默认信任 Agent 是合作的。v3.2 防止的是上下文压缩、遗漏、旧状态误用、自我误判和相关性盲点，而不是恶意 Agent。内核约束是外部化记忆和反馈护栏，不是审批系统。

## 2. 升级目标

v3.2 同时修复两种不对称：

- 低风险任务不再因为 MetaLoop 产生额外 ceremony；
- 高风险语义任务不能只凭机械测试或与报告失联的一词 Review 完成。

升级不增加第二套 lifecycle、Task ontology、scheduler、daemon、transcript store 或 vector memory。数据库 `schema_version` 保持 3。

## 3. Assurance 路由

| Tier | 名称 | 行为 |
| --- | --- | --- |
| 0 | `atomic_direct` | 直接使用 Git，零 MetaLoop kernel 调用 |
| 1 | `durable_routine` | 默认 `task begin -> Work -> attempt finish` |
| 2 | `governed` | 增加 stable inputs、强 validators、Evidence 或 conformance view |
| 3 | `high_assurance` | 在机械验证后增加 fresh-context structured Review |

显式 `$metaloop` 调用至少为 Tier 1。Tier 0 不是 MetaLoop Task，不能从 SQLite 统计。

### 3.1 Trigger 分类

无条件 Tier 3：安全或访问控制、隐私、生产影响、不可逆外部副作用，以及正式 evidence、holdout 或 label 泄漏。

条件 Tier 3 同时满足：发生语义变化，且 executable oracle 不能完整判定义务。

跨模块、schema、protocol 或正式 Contract 变化在义务可以完整机械判定时保持 Tier 2。Worker 同时编写实现和测试只是相关性风险信号，不单独触发 Tier 3。无法判断 applicability 时保守提升。

## 4. Contract Assurance

新 Contract 内容版本为 `1.1`，包含规范化 block：

```json
{
  "assurance": {
    "tier": "durable_routine | governed | high_assurance",
    "trigger_ids": [],
    "rationale": [],
    "required_authorities": [],
    "resolved_trigger_ids": [],
    "resolution_evaluation_id": null
  }
}
```

内核规则：

- Tier 3 自动加入 reviewer authority，Contract 输入不能删除它；
- v3 Contract v1.0 继续以 legacy 语义读取，不追溯增加 authority；
- `effective_tier` 由当前声明和未解决 Tier 3 trigger 推导；
- Tier 3 trigger 对当前 acceptance target 保持 sticky；
- 降级必须使用新的 ContractRevision，列出全部 resolved triggers，提供 rationale，并引用旧 Contract 下的 approved active Evaluation；
- 每个 resolved trigger 必须有规范化 proof：passing executable validator 的稳定
  `validator_id` + `resolves_trigger_ids` 映射，或 host-verified structured reviewer
  Evaluation 的 `resolved_trigger_ids`；普通 true、未映射 Evidence、manual validator 和
  unverified Review 均不计入；
- 新 ContractRevision 清除旧 active Evaluation pointer，旧 Attempt/Evaluation 保留为历史但不能再 acceptance。

## 5. Active Evaluation Head

v3.2 复用 `tasks.acceptance_head_id` 作为 Task 当前 Evaluation 指针，不新增表：

```text
sealed Attempt
  -> verification (active head)
    -> Review (new active head)
      -> optional user Review (new active head)
        -> accept(active head)
```

Review 只能追加到当前 active head；stale parent 或 sibling Review 被拒绝；accept 只能接受当前 active head，并且必须绑定当前 ContractRevision 和最新 Attempt。failed verification 或 `needs_changes` 后的新 Attempt 清除旧 pointer，repair 仍在同一 Task 中完成。

统一 control projection 从 active head 确定唯一外环转换：

| 当前投影 | 唯一下一步 |
| --- | --- |
| latest sealed current-Contract Attempt，无 Evaluation | `verify` |
| verification approved，reviewer pending | `review:reviewer` |
| reviewer approved，reserved user pending | `review:user` |
| 所有 authority approved | `accept` |
| verification rejected | `start_repair_attempt` |
| 任意 Review non-approved | `start_repair_attempt` |
| historical authority 顺序、重复、额外或 target 绑定错误 | `start_repair_attempt` |

机械 verification、reviewer、reserved user 的顺序不可交换。terminal Review 后不能再追加，
authority 完成后不能追加 extra Review，verification 只能绑定当前 Contract 的 latest sealed
Attempt。每次 verification/Review head transition 同时以 `state_version + expected head` 做
CAS，并递增 Task `state_version`。

历史错误链只读不改：扫描整条链，任意 non-approved Review 投影为
`review_needs_changes`，其余 malformed chain 投影为 `evaluation_chain_invalid`；新 Attempt
清除 active pointer，但旧 Evaluation content 和 hash 保持原样。

该设计避免恢复上下文后的 Agent 意外引用旧 Evaluation，而不是假设调用者会恶意选链。

## 6. Structured Fresh-Context Review

Tier 3 reviewer 在机械验证后运行，并提交：

```text
review_scope
questions_and_findings
counterexamples_executed
blocking_findings
nonblocking_risks
resolved_trigger_ids
decision
```

内核自动加入 exact parent Evaluation、Contract、Attempt 和 Evidence identities，以及 reviewer context provenance 和 independence projection。规范化报告直接进入 Review Evaluation payload 和 content hash，不允许用 DecisionEvent sidecar 代替。`approved` 报告不能保留 blocking findings。

Context provenance 分三类：host adapter 或 `METALOOP_HOST_CONTEXT_ID` 产生
`host/verified`；显式 CLI `--context-id` 产生 `manual/unverified`；缺失为
`unavailable/unverified`。旧记录没有显式 source/verified 字段时按 unverified 读取。
Tier 3 只有两个不同的 verified host context 才满足 independence。无法确认时允许通过同一
Task 的 repair Attempt 继续开发，但不能完成 Tier 3 acceptance。

## 7. Read-Only Git Observation

Workspace observation 使用：

- repository 外临时 index；
- repository 外临时 object directory；
- 原 object store 作为只读 alternate；
- `GIT_OPTIONAL_LOCKS=0`；
- index 副本计算 index tree，避免更新真实 cache-tree；
- 回归测试比较 observation 前后的真实 index、objects、refs 和 lock files。

因此 stamp、status、Recovery 和 reviewer observation 不会改变被观察的 Git state。

## 8. 状态与 CLI 兼容

`acceptance_status`/Recovery 使用：

```text
working
verification_failed
mechanically_verified_pending_reviewer
review_needs_changes
evaluation_chain_invalid
high_assurance_review_unverified
reviewed_ready_for_user_acceptance
acceptance_ready
accepted
```

现有 `observe --format full|brief` 保留，默认仍为 `full`，不新增平行 `--full`。brief 输出增加 `control_status`、`authority_sequence`、`pending_authorities`、`next_transition`、`next_action`、`blocker`、`resolved_trigger_proofs` 和 `assurance`，原字段保持不变。

Tier 3 Review 使用：

```bash
METALOOP_HOST_CONTEXT_ID=<host_context_id> \
METALOOP_HOST_CONTEXT_PROVIDER=<host_provider> \
python3 "$KERNEL" --workspace . evaluate review \
  --evaluation <active_head_id> \
  --decision approved \
  --reviewer <reviewer> \
  --report-file review.json
```

## 9. 保证边界

内核保证：

```text
No unacknowledged WorkspaceStamp may pass acceptance.
Only the active Evaluation head may pass acceptance.
Declared high assurance cannot silently lose unresolved trigger memory.
Tier 3 acceptance binds a structured fresh-context Review.
Recovery exposes one legal, CAS-protected next transition.
No trigger is resolved without an explicit per-trigger proof mapping.
```

内核不理解任意项目的领域语义。正确识别 trigger 仍由 Skill、host policy 和项目 validator 负责。v3.2 强制执行已声明或已提升的 assurance，不宣称消除所有分类遗漏。

## 10. 校准指标

内部 Tier 1-3 观察用户首先发现的遗漏、Recovery 后的重复工作、routine protocol operation 数、review blocking-finding rate 与 latency、同 Task repair 比例和不必要用户中断。

Tier 0 通过自愿试用日志、Git 抽样或用户研究评估，不能写入 MetaLoop SQLite 后再称为零调用。
