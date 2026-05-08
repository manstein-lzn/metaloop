# MetaLoop 轻量协议层重定位

日期：2026-05-08

## 1. 背景

MetaLoop 最初要解决的问题是真实存在的：

1. 很多任务最终效果不好，不是因为执行阶段不努力，而是因为开始阶段没有充分设计，没有深挖需求细节、哲学取舍、边界和验收标准。
2. 仅靠自然语言驱动 Codex agent，长任务中容易出现中途停止、任务漂移、上下文衰减、完成自述和真实完成不一致等问题。
3. 如果任务只存在于聊天文本中，就很难把 agent 智能和代码系统稳定融合，也难以构建更复杂、更可恢复、更可审查的多 agent 系统。

这些需求仍然成立。需要调整的不是 MetaLoop 的核心动机，而是实现边界。

Codexarium 的落地经验提示了一个重要变化：不一定需要用大量框架代码实现所谓强规则约束。更有效的方式可能是提供一个稳定的信息平台、少量硬约束、清晰的对齐规则和可追溯证据，让 Codex agent 在更好的上下文和协议中工作。

因此，MetaLoop 不应继续被理解为一个厚重的“多 agent 操作系统”，而应重新定位为：

```text
Codex 的任务设计与稳定执行协议层
```

## 2. 新定位

MetaLoop 的核心价值不是用代码强行管住 Codex，而是提供一个比自然语言更稳定的任务承载层。

推荐主路径：

```text
深度 Design
  -> 结构化 Mission Capsule
  -> Codex 执行
  -> 独立验证 / 复盘
  -> 必要时 repair / redesign / resume
```

MetaLoop 应该优先成为：

- 任务设计系统
- 任务胶囊协议
- 验收和证据外壳
- Codex 长任务稳定器
- 多 agent 系统的最小结构化底座

而不是优先成为：

- 大型 runtime
- 厚重 shell
- 通用多 agent 编排平台
- 复杂状态机框架
- 试图替代 Codex 智能的控制系统

## 3. 三个不可放弃的核心需求

### 3.1 Design 过程必须存在

Design 不是附加功能，而是 MetaLoop 的产品核心。

很多复杂任务失败的根因是：

- 用户只表达了目标，没有表达边界。
- Agent 直接开始执行，没有追问关键约束。
- 验收标准没有被定义。
- 任务背后的哲学取舍没有被显式化。
- 非目标、禁止路径、风险和失败定义缺失。

因此，MetaLoop 必须保留并强化 Design 阶段。它应该帮助用户和 agent 在动手之前先回答：

- 这个任务真正要解决什么问题？
- 什么结果才算成功？
- 哪些事情明确不做？
- 哪些取舍比局部最优更重要？
- 哪些信息必须作为证据？
- 哪些失败模式必须提前防止？

### 3.2 稳定 Codex 长任务执行

Codex agent 很强，但自然语言驱动存在不稳定性：

- 可能提前停止。
- 可能认为完成但实际未满足验收。
- 可能在长任务中逐渐偏离原目标。
- 可能被局部实现细节带偏。
- 可能在恢复上下文时丢失任务事实。

MetaLoop 不需要接管 Codex 的智能，但需要提供稳定锚点：

- 当前任务事实来自 Mission Capsule，而不是聊天记忆。
- 当前状态来自结构化 artifact，而不是 agent 自述。
- 完成与否由 VerificationResult 和用户验收决定，而不是 `/goal complete`。
- 失败后进入 repair 或 redesign，而不是盲目重跑。

### 3.3 用结构化数据表达任务

自然语言适合探索，结构化数据适合执行、检查和组合。

MetaLoop 应保留 MissionSpec / Mission Capsule / GoalContract 等结构化表达，但需要控制复杂度。结构化任务表达的目的不是制造形式感，而是让系统能够：

- 读取任务边界。
- 检查验收标准。
- 分配给不同 agent。
- 生成验证命令。
- 保存执行证据。
- 支持 resume / repair / redesign。
- 未来扩展到更复杂的多 agent 系统。

## 4. 最小可行协议

MetaLoop 应该先收敛为一个最小但强约束的协议。

### 4.1 Mission Capsule

Mission Capsule 是任务事实的最小稳定单元，至少包含：

```text
intent                  用户真实意图
context                 背景和已有材料
design_rationale        设计阶段形成的关键理解和哲学取舍
constraints             硬约束和软约束
non_goals               明确不做的事情
acceptance_criteria     验收标准
forbidden_paths         禁止路径
evidence_requirements   必须留下的证据
verification_plan       可执行或半可执行验证方式
current_status          当前状态
```

Mission Capsule 不应无限膨胀。它应该是当前任务真相，不是完整聊天记录。

### 4.2 Design Agent

Design Agent 的职责是追问和完善 Mission Capsule，而不是急着执行。

它应该输出：

- 澄清后的目标
- 关键约束
- 非目标
- 验收标准
- 风险点
- 需要用户确认的取舍
- 初版 Mission Capsule

### 4.3 Codex Worker

Codex Worker 负责执行任务。

它应该拿到 Mission Capsule 和当前项目状态，而不是只拿一句自然语言命令。

执行边界：

- 可以探索、写代码、调试、运行测试。
- 必须围绕 Mission Capsule 工作。
- 不能修改 locked 任务边界。
- 发现边界错误时应请求 redesign。

### 4.4 Verifier

Verifier 独立于 Worker。

它负责判断：

- 是否满足 acceptance criteria。
- 是否产生了 required evidence。
- 是否违反 forbidden paths。
- 是否需要 repair。
- 是否需要 redesign。
- 是否需要 human acceptance。

Verifier 不需要一开始就很复杂。第一阶段可以是：

- 命令验证
- 文件验证
- schema 验证
- 测试验证
- 简单 reviewer 判断

### 4.5 Review / Redesign

当执行结果不满足任务时，系统不应该只做重复执行。

应区分：

```text
repair    目标正确，执行有缺陷
redesign  任务定义、边界、验收或方案本身需要改变
resume    任务未完成但方向仍正确
complete  验证通过，等待或完成用户验收
```

## 5. 应保留的 MetaLoop 能力

以下能力是核心，不应删除：

- `design` 阶段。
- MissionSpec / Mission Capsule。
- 验收标准结构化。
- VerificationResult。
- `.metaloop/` 结构化 artifacts。
- resume / repair / redesign。
- 任务状态文档和 handoff。
- Codex SDK UserAgent 作为长期交互入口。
- Codex agent 不直接修改 locked contract 的边界。

这些能力代表 MetaLoop 的真实价值。

## 6. 应压缩或暂缓的复杂度

以下方向容易导致过度设计，应谨慎推进：

- 复杂多层 runtime。
- 太多固定 agent 角色。
- 厚重 shell 体验。
- 过早构建通用多 agent 编排。
- 过早引入完整状态机框架。
- 试图用大量代码模拟 agent 判断。
- 为了强规则而强规则，导致用户需要先理解 MetaLoop 本身。

原则：

```text
只有当真实任务反复暴露同一种不稳定，才把它沉淀成代码机制。
```

## 7. 和 Codexarium 经验的关系

Codexarium 的经验说明：给 Codex agent 一个稳定知识平台和清晰规则，往往比构建厚重控制系统更有效。

这对 MetaLoop 的启发是：

- 不要把所有约束都代码化。
- 优先把任务事实、证据、验收和状态整理好。
- 让 Codex agent 在稳定协议内发挥智能。
- 用少量 verification hooks 防止明显漂移。
- 用结构化 artifact 支持恢复和审查。

MetaLoop 和 Codexarium 不冲突。

更合理的关系是：

```text
Codexarium 维护长期知识和项目记忆。
MetaLoop 维护单个复杂任务的设计、执行和验证协议。
```

## 8. 推荐的新主线

后续开发应按以下顺序收敛：

### Phase 1: 轻量 Mission Capsule

目标：

- 降低 Mission Capsule 概念负担。
- 保留最少字段。
- 让用户和 Codex 都容易读懂。
- 支持从设计对话生成 capsule。

### Phase 2: Design 质量

目标：

- 强化需求挖掘。
- 强化哲学取舍和非目标。
- 强化验收标准。
- 让 design 阶段成为 MetaLoop 最有价值的体验。

### Phase 3: 稳定执行

目标：

- Codex Worker 始终围绕 capsule 执行。
- 执行报告结构化。
- 失败时进入 repair/resume/redesign，而不是自然语言漂移。

### Phase 4: 独立验证

目标：

- 优先做好文件、命令、schema、测试等硬验证。
- 软验证只用于无法代码化的验收。
- VerificationResult 成为完成判断的依据。

### Phase 5: 多 agent 扩展

目标：

- 等单任务协议稳定后，再扩展多 agent。
- 多 agent 应从真实任务需要长出来，而不是预先设计一套完整体系。

## 9. 设计准则

后续开发 MetaLoop 时应遵守：

1. Design 优先于执行。
2. Mission Capsule 是任务真相，不是聊天记录。
3. Codex 负责智能工作，MetaLoop 负责协议、状态和验证。
4. 能用文档和结构化字段解决的，不急着写复杂 runtime。
5. 能用一个 agent 完成的，不急着拆成多个 agent。
6. 验证必须独立于执行自述。
7. 不满意结果要区分 repair 和 redesign。
8. 不为抽象而抽象，只沉淀真实反复出现的问题。

## 10. 作为 Codex Skill 的纪律边界

MetaLoop 可以构建为 Codex Skill，但不能把 Skill 误解成一个天然具备强制执行权的 runtime。

更准确的判断是：

```text
Skill 可以承载系统。
Skill 可以分发协议、脚本、schema、reference 和模板。
Skill 可以显著提高 agent 遵守流程的概率。
但 Skill 本身主要仍是被 agent 调用和遵循的能力包，不是不可绕过的强制执行层。
```

这意味着，MetaLoop 适合采用 skill-first 形态，但不应采用 prompt-only 形态。

推荐分层：

```text
$metaloop skill
  -> 告诉 Codex 何时进入 design、如何生成 capsule、何时调用验证脚本

scripts / schemas / templates
  -> 用确定性代码检查 Mission Capsule、VerificationResult、证据文件和状态流转

MetaLoop CLI / helper
  -> 生成、锁定、验证、恢复、修复、复盘结构化 artifacts

Codex 配置、hooks、sandbox、wrapper runtime
  -> 在需要时提供更强的不可绕过约束
```

因此，Skill 的价值不在于“用 prompt 强行管住 agent”，而在于把 MetaLoop 的使用入口变轻：

- 用户可以通过 `$metaloop` 直接触发设计和整理。
- Codex 可以通过 Skill 快速理解 MetaLoop 的纪律。
- 重资产 reference 可以沉淀设计哲学、任务模板和验收范式。
- 脚本和 schema 可以把关键边界变成可执行检查。
- 真正需要硬约束的地方交给 CLI、hooks、sandbox 或外层 runtime。

这也给 MetaLoop 的工程边界一个清晰结论：

```text
不要把所有纪律都塞进 Skill 的自然语言说明。
也不要因为 Skill 没有强制权，就放弃 Skill。
正确做法是：Skill 负责入口和对齐，代码负责检查和状态，外层机制负责不可绕过约束。
```

从这个角度看，MetaLoop 最合理的产品形态可能是：

```text
轻量 $metaloop skill
  + 最小 MetaLoop CLI/helper
  + Mission Capsule / VerificationResult schema
  + 少量必要 hooks
  + Obsidian/Codexarium 可追溯知识沉淀
```

这条路线符合 Codexarium 的经验：用尽量少的硬规则提供足够稳定的平台，而不是为了“强控制”构建厚重系统。

## 11. 结论

MetaLoop 不应该被废弃，但需要从“强规则多 agent 操作系统”收敛为“Codex 任务设计与稳定执行协议层”。

真正要保留的是：

```text
Design 的深度
任务表达的结构化
执行过程的可恢复
结果判断的独立验证
长期任务的抗漂移能力
```

真正要避免的是：

```text
为了控制而控制
为了多 agent 而多 agent
为了框架完整性而增加用户心智负担
```

MetaLoop 的下一阶段应该是减法：保留最能稳定 Codex 的结构，把其余复杂度推迟到真实任务证明必要之后。
