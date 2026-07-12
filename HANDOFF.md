# MetaLoop Handoff

最后更新：2026-07-12

## 快速恢复

新 session 可以从以下上下文开始：

```text
我们继续开发 MetaLoop。仓库在 /home/mansteinl/metaloop。

请先读取 README.md、STATE.md、ROADMAP.md、skills/metaloop/SKILL.md，
然后检查 git status 和最近提交。

MetaLoop 是 Codex 的轻量开发治理协议。当前方向是：深度设计、Progressive Design、
证据验证和反馈恢复。Skill 提供通用思考纪律，Codex 负责具体项目的设计与执行，
项目文档保存架构认知，kernel/core 保存锁定状态和验证事实。优先用真实任务证据推进，
只把具有确定性消费者的跨场景事实加入代码。
```

## 当前主路径

```text
用户愿景
  -> $metaloop + Codex 项目理解
  -> 项目设计文档 + Mission Capsule + VerificationSpec
  -> 最小端到端切片
  -> ExecutionReport + VerificationResult + optional ReviewResult
  -> complete | continue | repair | redesign | pivot | stop | escalate
  -> 更新项目文档、反馈状态和下一计划
```

Progressive Design 已加入 Skill：Codex 应形成连贯目标模型，区分长期不变量与当前实现，
选择最小可验证切片，明确模块责任，记录有意让步及其重访证据，并让每轮设计讨论产生
新的推演价值。

## Authority 与实现分工

- 用户提供愿景、优先级、约束和关键判断；
- Codex 负责理解、设计、执行、诊断和策略；
- `skills/metaloop/` 提供入口、原则、references 和 self-contained kernel；
- 项目 `docs/` 保存具体架构、模块契约、迁移计划和领域事实；
- `.metaloop/` 保存锁定任务、证据、验证、反馈和恢复状态；
- `src/metaloop_core/` 保存可复用的确定性协议实现；
- hooks、sandbox 和 wrapper 在需要时实现不可绕过的外层约束。

## 已交付能力

- Mission Capsule、ExtensionSpec、VerificationSpec 与 revision；
- ExecutionReport、VerificationResult、independent ReviewResult；
- Adaptive Goal Loop、ObservationReport、DiagnosisReport；
- thread registry、event log 和 context checkpoints；
- engineering governance refs/hashes 与显式 `repair | extension | redesign`；
- optional routable work units、tick/relay、observation/control/dashboard 和 one-shot activation；
- core/portable-kernel parity、package、import-boundary 和 smoke tests。

## 开发纪律

- 从 governing document 开始，以更新后的 governing document 结束；
- 用 Skill/reference 表达智能工作原则，用代码处理状态、hash、验证和审计；
- 让当前 Codex 根据项目选择模块、阶段、证据和协作方式；
- 每个切片形成可独立观察和证伪的端到端结果；
- 验证失败先记录 observation 和 diagnosis，再选择下一步；
- 架构、authority、状态模型或公共契约变化使用 redesign 和 migration plan；
- independent reviewer 基于锁定证据处理 `review_required`；
- domain-specific 任务、数据和指标留在目标项目及其 verification extension 中。

## 当前边界与关注点

- `allowed_paths` 是锁定声明；强制路径隔离由外层 enforcement 提供；
- Skill kernel 与 `metaloop_core` 通过 parity tests 对齐，后续可评估确定性构建路径；
- context checkpoints 是紧凑恢复摘要，其质量继续通过真实长任务校准；
- routable handoff、control 和 activation 保持显式、one-shot 和可审计；
- 新协议能力需要重复的真实失败、确定性消费者和最小纵切证据。

## 验证

```bash
python3 tools/check_core_import_boundary.py
.venv/bin/pytest -q
git diff --check
```
