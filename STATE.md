# MetaLoop 当前状态

最后更新：2026-07-12

## 一句话状态

MetaLoop 当前是一套可直接安装的 Codex 轻量开发治理协议：Codex 负责场景智能，Skill
提供深度设计与渐进推进纪律，portable kernel 和 `metaloop_core` 负责锁定状态、证据、
验证、反馈和恢复。

## 当前产品模型

```text
用户目标
  -> $metaloop 引导 Codex 检查项目并形成设计
  -> Mission Capsule + VerificationSpec 锁定当前任务
  -> Codex 完成一个有界、可验证的工作切片
  -> ExecutionReport 记录候选证据
  -> validators / independent reviewer 形成 VerificationResult
  -> complete | continue | repair | redesign | pivot | stop | escalate
```

产品体验围绕四项能力组织：

- **深度设计**：从愿景推导目标模型、缺失维度、风险、关键选择和长期不变量；
- **渐进推进**：以最小端到端切片验证假设，通过模块责任和接口持续扩展；
- **证据验证**：执行前锁定验收，执行后由可追溯证据和独立 authority 决定结果；
- **反馈恢复**：保存观察、诊断、下一计划和上下文 safe point，支持长任务延续。

`Progressive Design` 已进入 Skill 和 Design Autonomy：设计深度与当前实现广度相互独立，
每轮设计讨论应贡献新的推演、风险、选择或更清晰的结构。

## 已交付能力

- 自包含 `skills/metaloop/`，可直接安装到 Codex skills 目录；
- Mission Capsule、ExtensionSpec、VerificationSpec 的锁定、hash 与 revision；
- ExecutionReport、VerificationResult 和独立 ReviewResult；
- executable、manual、advisory、resource 和 forbidden-claim 验证语义；
- Adaptive Goal Loop、ObservationReport、DiagnosisReport 和 typed decisions；
- event log、thread registry 与 context checkpoints；
- engineering governance：governing document、module contracts、allowed paths、
  `repair | extension | redesign` 和 redesign migration plan；
- 可选 routable work units、one-shot tick/relay、只读 observation、显式 control 和
  one-shot activation；
- `metaloop_core` 与 portable skill kernel 的 parity、package 和 import-boundary 测试。

## 实现边界

- Skill 和 references 承载通用思考原则，当前 Codex 将其适配到具体项目；
- 项目文档拥有架构、模块契约、迁移计划和领域认知；
- `metaloop_core` 只拥有确定性的协议状态与验证，不编码场景策略；
- `.metaloop/` 是任务治理事实，不复制项目架构正文；
- `allowed_paths` 当前是锁定的施工范围声明；需要强制隔离时由 hook、sandbox 或
  wrapper 提供；
- observation、control、tick、relay 和 activation 保持显式、one-shot、可审计；
- portable kernel 保持自包含，并通过 parity tests 与 core 对齐。

## 当前验证

仓库的完成检查为：

```bash
python3 tools/check_core_import_boundary.py
.venv/bin/pytest -q
git diff --check
```

2026-07-12 的 Progressive Design 切片通过完整测试、import boundary、安装哈希检查和
本地 `design -> run -> verify` smoke test。

## 当前重点

1. 在真实项目中持续 dogfood Progressive Design，观察设计质量、返工、验证强度和
   长任务恢复效果；
2. 让 README、Skill、STATE、ROADMAP、HANDOFF 和安装入口保持同一产品叙事；
3. 从反复出现的真实失败中选择新的 validator、reference 或外层 enforcement；
4. 评估以模块化 core 为唯一实现来源、确定性生成 self-contained skill runtime 的路径，
   降低双实现长期维护成本；
5. 保持用户入口为一句目标表达，由 Codex 选择最小充分的协议形态。
