# MetaLoop Roadmap

最后更新：2026-05-12

MetaLoop 已收敛为 Skill-only 产品。路线图不再围绕自建交互运行时展开，而是围绕 `$metaloop` skill、portable kernel、`metaloop_core`、ExtensionSpec / VerificationSpec 和长任务反馈闭环展开。

## 产品原则

- Codex agent 保持智能：理解项目、提出方案、写代码、跑实验、反思结果。
- MetaLoop 保持纪律：设计先行、合同锁定、证据记录、独立验证、repair/redesign 决策。
- Skill 降低用户心智负担：用户给目标，Codex 主动选择 MetaLoop 协议形态和验证流程。
- Prompt-first / code-backed：能用少量 prompt 稳定驱动智能的地方，不急着写成框架代码；需要真相、状态、验证和审计的地方必须落代码和 artifacts。
- Core 轻量通用，领域能力通过 extension 生长。

## 已完成

- 自包含 Codex Skill：`skills/metaloop/`。
- Portable kernel：`skills/metaloop/scripts/metaloop_kernel.py`。
- Reusable protocol backend：`src/metaloop_core/`。
- Core/skill parity tests。
- Generic extension package。
- Mission Capsule + ExtensionSpec + VerificationSpec locking。
- ExecutionReport / VerificationResult flow。
- Thread registry 和 event log。
- Adaptive Goal Loop 状态和 ObservationReport / DiagnosisReport。
- Routable work units：job envelope、global blackboard、dispatch map、pure router、one-shot tick、one-shot relay。
- Observability / control：read-only node/global summaries，以及 `.metaloop/control/*.json` 显式控制请求。
- Activation：one-shot scanner、`activation_result.json`、lease / idempotency key、dry-run / execute 模式。
- Prompt-first / code-backed 文档和 skill reference。
- 删除旧外部产品面，仓库回到 skill/core/library 结构。

## v0.2 Skill 内测稳定化

目标：让团队在真实项目中可以直接调用 `$metaloop`，并明显感受到 design、verification、feedback 的约束价值。

工作项：

- 改进 `skills/metaloop/SKILL.md` 的开放任务 design 提示，要求 agent 明确目标、非目标、可观测指标、失败诊断路径和下一轮计划。
- 强化 User Burden Rule：agent 不要求用户指定 Mission Capsule、VerificationSpec、Adaptive Loop、blackboard、dispatch map、job envelope、tick 或 relay 等内部机制。
- 增加 2-3 个 domain extension examples：benchmark/metric、文档交付、代码质量门槛。
- 加强 VerificationSpec review checklist，避免宽松指标、subset-only claim、oracle leakage、选择性汇报。
- 增加 skill 安装 smoke test 文档和团队反馈模板。

验收：

- 新用户只看 README 和安装文档就能在 Codex 中使用 `$metaloop`。
- 复杂任务的 `.metaloop/mission_capsule.json` 包含清晰 VerificationSpec，而不是只有文件存在检查。
- 失败任务能产出可复用的 observation/diagnosis/next plan，而不是停在“未完成”。
- 对需要隔离责任的大任务，agent 能主动设计最小 routable work-unit 网络，而不是要求用户手写流程说明。

## v0.3 Extension Protocol 打磨

目标：让不同领域以轻量方式指定自己的验证语言，而不是把规则塞进 core。

工作项：

- 定义 extension authoring guide。
- 为 validators 增加更好的错误信息和 evidence summary。
- 支持 validator version/hash 记录的更清晰展示。
- 为 resource gate、manual acceptance 和 forbidden claim 增加 examples。

验收：

- 新领域可以通过 `extensions/<domain>/profile.json`、examples 和少量 validators 表达完成标准。
- Core 不出现领域专用业务规则。

## v0.4 Long-Task Feedback Discipline

目标：面向开放目标任务，强化“目标逼近”而不是“一次执行”。

工作项：

- 在 skill reference 中加入开放目标任务模板：Goal -> Plan -> Act -> Observe -> Evaluate -> Diagnose -> Decide -> Next Plan。
- 增加失败分类提示：implementation defect、bad hypothesis、insufficient evidence、contract mismatch、resource blocked、target likely infeasible。
- 让 event log 和 adaptive loop 的 recommended usage 更清晰。

验收：

- agent 能在多轮尝试中持续更新 observation、diagnosis 和 next plan。
- 未达到目标时不会把 artifact production 说成成功。

## v0.5 强约束评估

目标：只有在内测证明 skill/kernel 不足时，再决定是否添加 hooks、sandbox 或 wrapper runtime。

候选方向：

- pre-run / post-run hooks。
- validator directory hash pinning。
- resource approval policy。
- 外层 wrapper 统一执行 locked VerificationSpec。

不做：

- 不重建独立聊天界面。
- 不恢复旧外部运行时。
- 不做重型 scheduler 或自动 agent pool，除非真实团队任务反复证明需要。
- 不把具体项目、数据集、指标或业务逻辑写进 MetaLoop 本体。

## v0.6 Activation Layer

目标：在 observe/control 稳定后，用可选 activation wrapper 把“用户手动唤醒下游 node”升级为 one-shot scanner。

已落地：

- `activation_result.json`
- pending envelope scanner
- lease / idempotency key
- pending control check
- explicit worker command plan
- dry-run / once modes

不做：

- 不把 activation 放进 core 智能逻辑。
- 不默认启动 daemon/watch mode。
- 不让 activator 设计任务、修改合同或解释指标。
