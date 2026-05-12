# MetaLoop Handoff

最后更新：2026-05-12

本文给后续 Codex/session 接手使用。当前项目已经完成一次产品瘦身：MetaLoop 只保留 Codex Skill 和 reusable core，不再维护旧外部交互运行时。

## 快速恢复 Prompt

新 session 可以直接粘贴：

```text
我们继续开发 MetaLoop。仓库在 /home/mansteinl/metaloop。

请先读取：
1. README.md
2. STATE.md
3. ROADMAP.md
4. skills/metaloop/SKILL.md
5. git status / git log --oneline -5

当前产品方向是 Skill-only：用户通过 Codex $metaloop skill 使用 MetaLoop；仓库只保留 skills/metaloop、src/metaloop_core、当前文档和测试。不要恢复旧外部交互运行时。继续遵守 prompt-first / code-backed：prompt 负责智能，代码负责状态、验证、审计和恢复。用户不需要知道 MetaLoop 内部协议；skill 必须主动承担 design、verification、feedback 和必要的 routable handoff。
```

## 当前主路径

```text
Codex conversation
  -> $metaloop skill
  -> bundled kernel locks Mission Capsule + VerificationSpec
  -> Codex executes using project context
  -> ExecutionReport records candidate evidence
  -> locked validators write VerificationResult
  -> repair / redesign / resume / complete
  -> optional tick / outbox / relay for explicit cross-node handoff
```

用户不需要安装一个单独的 MetaLoop 交互工具。`skills/metaloop/scripts/metaloop_kernel.py` 随 skill 部署，目标项目可直接用它写 `.metaloop/` 状态。

## 仓库边界

保留：

- `skills/metaloop/`
- `src/metaloop_core/`
- `tests/test_metaloop_core_*.py`
- `tests/test_skill_package.py`
- `tools/check_core_import_boundary.py`
- 当前 `docs/` 中与 skill-only、extension、multi-thread、adaptive loop、工程控制论、prompt-first 相关的文档

已移除：

- 旧仓库级交互入口和运行时 package。
- Rich / prompt-toolkit UI。
- Node SDK bridge。
- prompt pack runtime。
- 示例 mission 和无关 extension。
- 旧 runtime/backlog 文档与测试。

## 当前核心能力

- Skill package 自包含，可部署到 `${CODEX_HOME:-$HOME/.codex}/skills/metaloop`。
- Kernel 支持 `status`、`design`、`run`、`verify`、`mark`、`threads`、`event`、`adaptive`、`tick`、`relay`。
- `metaloop_core` 提供与 skill kernel 对齐的协议后端。
- Core/skill parity tests 防止 portable kernel 与 core 语义漂移。
- Generic validators 覆盖文件、命令、JSON 指标、字段存在、内容匹配、hash、禁止声明、人工验收和资源门槛。
- Routable work units 支持 `job_envelope.json`、`global_blackboard.json`、`dispatch_map.json`、`.metaloop/outbox/*.json`、`.metaloop/tick_result.json` 和 `.metaloop/relay_result.json`。
- Observability / control / activation 支持只读 summary、显式控制文件和一次性 activation 扫描；它们都不应演变成后台调度器。
- `scripts/metaloop_dashboard.py` 是只读 localhost dashboard；不要给它增加写 control、activate、relay、edit artifact 等 mutation endpoint。
- Context checkpoints 支持 `.metaloop/context/resume_brief.md` 等轻量 Markdown 恢复摘要，解决长期 Codex thread 上下文膨胀后的接手问题。
- `review_required` 不等于用户授权。它应由独立 Codex reviewer 检查证据并通过 `review record` 写 `.metaloop/review_result.json`。`human_acceptance_required` 才是用户专属授权。
- 研究、benchmark、复现、论文结论、promotion 或 leaderboard claim 默认应给最终 claim validation 加 `review_required`，除非用户明确 opt out。

## 运行验证

```bash
python3 tools/check_core_import_boundary.py
.venv/bin/pytest -q
git diff --check
```

如果没有 venv：

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## 后续开发纪律

- 优先改 skill prompt、reference、examples 和 validators，而不是扩展成大框架。
- 只有需要持久化、机器验证、审计、恢复、跨 agent 共享或自动路由的内容才进入 core。
- 领域能力通过 ExtensionSpec / VerificationSpec 生长，不写死到 MetaLoop Core。
- 对开放目标任务，重点是让 design 阶段产生严格 VerificationSpec 和下一轮实验/诊断纪律。
- 不要把失败包装成完成；metric gate 失败就是目标未达成。
- 不要恢复旧交互产品面。Codex 本身就是自然对话层。
- 不要把具体项目、数据集、指标或业务逻辑写进 MetaLoop 仓库。目标项目自己的配置可以包含这些内容，MetaLoop 本体必须保持领域中立。
- 不要把 activation 变成 daemon、watcher 或自动 agent pool；它只能做一次性扫描、显式 worker command 和审计记录。
- 不要把 context checkpoint 变成 transcript、向量库或隐藏 memory；它是人工/agent 可读的恢复摘要。

## 当前风险

- Skill 仍然是软入口，不能单独提供不可绕过的强约束；强约束需要 hooks、sandbox 或 wrapper runtime，但只有真实团队任务证明必要时才添加。
- VerificationSpec 可能被 agent 设计得过宽，锁定前需要 reviewer 或用户检查。
- 不要让 worker thread 自己写 approved review result 来解除自己的 blocker。
- 如果 validator 和被验证工程同仓库，严肃场景应记录 validator 版本/hash，避免 worker 同时改验证规则。
- `tick`、`relay` 和 `activate` 都是显式 one-shot 文件操作，不是全自动后台调度。自动唤醒 agent thread、watcher、daemon 和消息队列仍不属于当前产品面。
- Context checkpoint 质量仍需真实长任务验证：太短会无法恢复，太长会重新造成上下文负担。
