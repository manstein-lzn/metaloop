# MetaLoop Roadmap

最后更新：2026-07-20

## 方向

MetaLoop 的路线由真实任务证据驱动。Skill 持续提升 Codex 的深度设计、Progressive
Design、验证和恢复纪律；代码只吸收跨场景稳定、反复需要并具有确定性消费者的协议
事实。

```text
完整愿景
  -> 最小可验证切片
  -> 锁定 Task 成功合同
  -> 可恢复 Attempt 与精确 evidence
  -> Evaluation / Review
  -> 真实项目反馈
  -> 仅对重复失败扩展协议
```

## 已完成：Durable Work Graph V2

- SQLite canonical store 和 schema migration 基础。
- Task graph、immutable ContractRevision、recoverable Attempt。
- content-bound Evaluation/Review acceptance chain。
- CAS、dependency DAG、duplicate fingerprint 和 legacy migration。
- bounded freshness-checked RecoveryView。
- canonical core 到 self-contained Skill 的生成发布。
- 完整 v1 regression、v2 invariants、parity 和 installed-path smoke tests。

## 已完成：设计与工程治理切片

- 深度设计和 Progressive Design Rule 进入 Skill 工作纪律。
- repair / extension / redesign 使用显式分类，不从自由文本机械猜测。
- V2 ContractRevision 原生支持 stable inputs、managed outputs、allowed paths 和
  redesign migration plan。
- governance drift 在 start、seal、verify、review、accept 和 selected-task integrity
  前 fail closed。
- 项目架构仍由项目文档拥有，core 只保存引用、hash 和确定性规则。

## 当前阶段：真实项目验证

用真实开发任务收集以下证据：

1. 上下文压缩后的恢复质量和重复工作减少程度；
2. Task / Attempt 边界及任务切换成本；
3. parent、dependency、repair branch 的实际使用方式；
4. fingerprint 的 false positive / false negative；
5. 长历史 integrity 与 RecoveryView 的性能和信息密度；
6. Progressive Design 对返工、设计质量和交付速度的影响；
7. engineering governance 在哪些任务中有价值，哪些任务中过重。

反馈应包含具体任务、失败现象、当时状态、期望行为和可复现路径，而不只是功能愿望。

## 候选后续切片

只有真实反馈支持时才进入实现：

- 更好的 Task/Attempt 创建与切换 ergonomics。
- RecoveryView payload 的自适应阈值与更清晰的 stale 诊断。
- 长历史 integrity 的增量检查或可证明缓存。
- exact fingerprint 之外的 agent-assisted duplicate 提示，不宣称机械语义判重。
- governance scope 的外层 hook/sandbox enforcement，但只有真实越界证据出现后才实现。
- 围绕真实故障新增 validator、reference 或外层 enforcement。

## 能力进入条件

一项新能力进入 core 前应同时满足：

1. 多个真实任务反复暴露同类失败；
2. 仅靠 Skill、reference 或项目文档无法稳定解决；
3. 存在明确的确定性消费者和独立验证路径；
4. 新能力保持领域中立并复用现有任务事实；
5. 最小纵切能够证明收益高于新增心智与维护成本。

## 明确不做

- 后台 scheduler、daemon、watcher 或 agent pool。
- 聊天 transcript 存储、向量 memory 或第二个 agent brain。
- deadline、priority、资源排期、团队看板等项目管理能力。
- 让 root JSON、Markdown 或 dashboard 成为第二份真相。
- 为每个推理模式新增 schema/module。
- 在缺少重复真实失败前扩展抽象层。
