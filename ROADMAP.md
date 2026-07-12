# MetaLoop Roadmap

最后更新：2026-07-12

## 方向

MetaLoop 的路线由真实任务证据驱动。Skill 持续提升 Codex 的设计与反馈纪律；代码只
吸收跨场景稳定、反复需要并具有确定性消费者的协议事实。

```text
完整愿景
  -> 最小可验证切片
  -> 真实任务证据
  -> continue | repair | redesign | stop
  -> 下一项必要能力
```

## 已完成的基础

- Skill-first、Prompt-first / code-backed 产品结构；
- Six-Gate Model 与 User Burden Rule；
- Mission Capsule、VerificationSpec、ExecutionReport、VerificationResult 和 ReviewResult；
- Adaptive Goal Loop、event log、thread registry 与 context checkpoints；
- ExtensionSpec 与 generic validators；
- engineering governance、显式 change classification 和文档 hash drift 检查；
- 可选 routable work units、observability、control、dashboard 和 one-shot activation；
- Progressive Design：目标模型、长期不变量、最小纵切、模块责任、有意让步和证据驱动
  的逐步扩展。

## 当前阶段：真实项目验证

目标是证明 MetaLoop 能在保持轻量的同时稳定提升 Codex 工作质量。

重点观察：

- 用户只给目标时，Codex 能否形成足够深入且准确的设计；
- 首个 end-to-end slice 是否足够小，又能验证关键假设；
- 模块责任与接口是否减少跨模块牵连和并行开发阻塞；
- VerificationSpec 是否真正覆盖结论，而不是只验证 artifact 存在；
- repair、redesign 和 stop 决策是否减少重复补丁和无效尝试；
- 新 session 能否基于项目文档和 `.metaloop/` safe point 快速恢复；
- 用户感受到的是更清晰、更可靠的 Codex，而不是额外协议负担。

代表性 dogfood 应覆盖架构设计、功能扩展、缺陷诊断、长期质量改进和跨 session 工作。
这些是验证场景，由当前 Codex 根据项目设计具体过程。

阶段通过条件：

- 多个真实项目能仅通过 `$metaloop` 入口完成设计、执行、验证和反馈闭环；
- Progressive Design 能更早暴露关键风险，并形成可验证的小步交付；
- 失败结果留下可复用的诊断和下一计划；
- 新增协议代码均能追溯到重复出现的实际需求。

## 后续候选

### 公共体验

- 继续压缩 Skill 的机制曝光，让普通语言始终是主要交互面；
- 用少量高质量 references 和 examples 帮助 Codex处理常见证据与设计难题；
- 改善诊断和 observation summary，使用户快速理解当前事实与下一步。

### 证据能力

- 根据真实任务补充高价值 validator examples 和 review checklists；
- 加强 benchmark、质量突破、研究结论和文档交付的证据校准；
- 记录 validator provenance、版本与 hash 的清晰投影。

### 实现一致性

- 评估从 `metaloop_core` 确定性构建 self-contained skill runtime；
- 保持 portable deployment，同时减少 core/kernel 协议逻辑的重复所有权；
- 扩展 parity、package 和 installation smoke evidence。

### 外层约束

- 当真实项目证明声明式约束不足时，再加入 scoped hooks、sandbox 或 wrapper；
- 让外层 enforcement 消费现有 locked contracts，不创建第二套任务事实；
- 保持 control 与 activation 的显式 safe-point 语义。

## 能力进入条件

一项新能力进入 core 前应同时满足：

1. 多个真实任务反复暴露同类失败；
2. 仅靠 Skill、reference 或项目文档无法稳定解决；
3. 存在明确的确定性消费者和独立验证路径；
4. 新能力保持领域中立并复用现有任务事实；
5. 最小纵切能够证明收益高于新增心智与维护成本。
